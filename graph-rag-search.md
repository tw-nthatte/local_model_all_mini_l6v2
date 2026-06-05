# TKG — Hybrid Search, Insert Document & Document Quality Guide

---

## 1. Why pure vector search isn't enough for your use case

Your incident descriptions contain two kinds of signals:

| Signal type | Example | Best matched by |
|---|---|---|
| **Semantic / conceptual** | "service is slow" → latency tool | Vector search |
| **Exact operational terms** | "OOMKilled", "connection pool exhausted", "HTTP 503" | Full-text keyword search |

Pure vector search misses exact error strings because they get diluted in the embedding
space. A query for "OOMKilled" semantically clusters near "memory" and "crash", which
is fine, but it may rank a generic "get memory metrics" tool above a specific
"investigate_oom_events" tool that has "OOMKilled" verbatim in its document.

The fix is **hybrid search = vector search + full-text search, fused with RRF**,
the same strategy you already use in your incident store.

---

## 2. Schema addition (one-time migration)

Add a weighted `tsvector` generated column to the existing `tools` table.
This is the full-text search target. Weights give match priority:
`A` (tool_name) > `B` (description + use cases) > `C` (output).

```sql
-- Add generated tsvector column (PostgreSQL 12+)
-- GENERATED ALWAYS AS means it updates automatically on every INSERT/UPDATE
ALTER TABLE tools ADD COLUMN IF NOT EXISTS search_text tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(tool_name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
        setweight(to_tsvector('english',
            coalesce(array_to_string(example_use_cases, ' '), '')), 'B') ||
        setweight(to_tsvector('english',
            coalesce(output_description, '')), 'C')
    ) STORED;

-- GIN index on the tsvector for fast keyword lookup
CREATE INDEX IF NOT EXISTS tools_search_text_gin_idx
    ON tools USING gin(search_text);
```

After running this, existing rows will auto-populate `search_text`.
Every future INSERT/UPDATE auto-maintains it — no code change needed.

---

## 3. Updated `tkg/discovery_service.py` — full file

```python
import json
from dataclasses import dataclass
from typing import List, Optional, Set
from .db import get_conn, release_conn
from .embedder import embed_one
from .dependency_graph import ToolDependencyGraph

RRF_K = 60          # standard RRF constant; higher = smoother rank fusion
CANDIDATE_POOL = 60  # retrieve this many candidates before RRF re-ranking
MIN_SCORE = 0.0     # RRF scores aren't bounded 0-1; keep at 0 to not filter


@dataclass
class DiscoveredTool:
    tool_id: str
    tool_name: str
    description: str
    tool_type: str
    parameters: list
    output_description: str
    credential_ref: str
    app_tags: list
    base_url: Optional[str]
    endpoint: Optional[str]
    query_template: Optional[str]
    score: float
    is_dependency: bool


class ToolDiscoveryService:

    def __init__(self, dep_graph: ToolDependencyGraph):
        self.dep_graph = dep_graph

    # ------------------------------------------------------------------
    # Main entrypoint
    # ------------------------------------------------------------------

    def discover(
        self,
        incident_description: str,
        app_tags: List[str],
        top_k: int = 20,
        include_infra_tags: Optional[List[str]] = None,
    ) -> List[DiscoveredTool]:
        search_tags = app_tags + (include_infra_tags or [])
        query_vector = embed_one(incident_description)

        # Hybrid search (vector + FTS + RRF) — preferred
        candidate_rows = self._hybrid_search(
            query_vector, incident_description, search_tags, top_k
        )

        # If FTS produced zero hits the hybrid still works (falls back to
        # vector-only via the FULL OUTER JOIN), but if the entire result is
        # empty (no tools tagged for this app at all) surface a clear error.
        if not candidate_rows:
            raise ValueError(
                f"No tools found for app_tags={search_tags}. "
                "Ensure tools are indexed with the correct app_tags."
            )

        candidate_map = {row["tool_id"]: row for row in candidate_rows}
        candidate_ids = list(candidate_map.keys())

        # Dependency resolution
        full_id_set: Set[str] = self.dep_graph.resolve_with_dependencies(candidate_ids)
        dependency_only_ids = full_id_set - set(candidate_ids)

        if dependency_only_ids:
            for row in self._fetch_by_ids(list(dependency_only_ids)):
                row["score"] = 0.0
                candidate_map[row["tool_id"]] = row

        ordered_ids = self.dep_graph.topological_order(full_id_set)

        return [
            DiscoveredTool(
                tool_id=tid,
                tool_name=(row := candidate_map[tid])["tool_name"],
                description=row["description"],
                tool_type=row["tool_type"],
                parameters=(
                    row["parameters"] if isinstance(row["parameters"], list)
                    else json.loads(row["parameters"])
                ),
                output_description=row.get("output_description", ""),
                credential_ref=row.get("credential_ref", ""),
                app_tags=row.get("app_tags", []),
                base_url=row.get("base_url"),
                endpoint=row.get("endpoint"),
                query_template=row.get("query_template"),
                score=row["score"],
                is_dependency=tid in dependency_only_ids,
            )
            for tid in ordered_ids
            if tid in candidate_map
        ]

    # ------------------------------------------------------------------
    # Hybrid search: vector + full-text + RRF
    # ------------------------------------------------------------------

    def _hybrid_search(
        self,
        query_vector: List[float],
        query_text: str,
        app_tags: List[str],
        top_k: int,
    ) -> List[dict]:
        """
        Retrieval Rank Fusion over two sources:
          - vector_search : cosine ANN on embeddings  (semantic match)
          - text_search   : weighted tsvector FTS      (exact term match)

        RRF score = 1/(RRF_K + vec_rank) + 1/(RRF_K + text_rank)

        If text_search finds nothing (no FTS hits), the FULL OUTER JOIN
        means vector_search results survive with their rrf contribution
        alone — it degrades gracefully to pure vector search.

        websearch_to_tsquery is used instead of plainto_tsquery because
        incident descriptions sometimes contain quoted strings and OR logic
        (e.g. "OOMKilled OR CrashLoopBackOff").
        """
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH
                    -- ── Vector search candidate pool ─────────────────────────────
                    vector_search AS (
                        SELECT
                            tool_id::text,
                            ROW_NUMBER() OVER (
                                ORDER BY embedding <=> %s::vector
                            ) AS vec_rank
                        FROM tools
                        WHERE app_tags && %s::text[]
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    ),

                    -- ── Full-text search candidate pool ───────────────────────────
                    -- websearch_to_tsquery handles natural query strings safely;
                    -- returns NULL (not an error) when query has no valid FTS tokens
                    text_search AS (
                        SELECT
                            tool_id::text,
                            ROW_NUMBER() OVER (
                                ORDER BY ts_rank_cd(search_text, query) DESC
                            ) AS text_rank
                        FROM
                            tools,
                            websearch_to_tsquery('english', %s) AS query
                        WHERE
                            app_tags && %s::text[]
                            AND search_text @@ query
                        LIMIT %s
                    ),

                    -- ── RRF score fusion ──────────────────────────────────────────
                    rrf AS (
                        SELECT
                            COALESCE(v.tool_id, t.tool_id)            AS tool_id,
                            COALESCE(1.0 / (%s + v.vec_rank),  0.0)   AS vec_rrf,
                            COALESCE(1.0 / (%s + t.text_rank), 0.0)   AS text_rrf,
                            COALESCE(1.0 / (%s + v.vec_rank),  0.0) +
                            COALESCE(1.0 / (%s + t.text_rank), 0.0)   AS total_rrf
                        FROM vector_search  v
                        FULL OUTER JOIN text_search t ON v.tool_id = t.tool_id
                    )

                    -- ── Final join and return ─────────────────────────────────────
                    SELECT
                        r.tool_id,
                        t.tool_name,
                        t.description,
                        t.tool_type,
                        t.parameters,
                        t.output_description,
                        t.credential_ref,
                        t.app_tags,
                        t.base_url,
                        t.endpoint,
                        t.query_template,
                        t.depends_on,
                        r.total_rrf           AS score,
                        r.vec_rrf,
                        r.text_rrf
                    FROM rrf r
                    JOIN tools t ON t.tool_id::text = r.tool_id
                    ORDER BY r.total_rrf DESC
                    LIMIT %s;
                    """,
                    (
                        query_vector,           # %s  vec search embedding
                        app_tags,               # %s  vec WHERE app_tags &&
                        query_vector,           # %s  vec ORDER BY
                        CANDIDATE_POOL,         # %s  vec LIMIT
                        query_text,             # %s  FTS query string
                        app_tags,               # %s  FTS WHERE app_tags &&
                        CANDIDATE_POOL,         # %s  FTS LIMIT
                        float(RRF_K),           # %s  vec rrf denominator
                        float(RRF_K),           # %s  vec rrf denominator (score col)
                        float(RRF_K),           # %s  text rrf denominator
                        float(RRF_K),           # %s  text rrf denominator (score col)
                        top_k,                  # %s  final LIMIT
                    ),
                )
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            release_conn(conn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_by_ids(self, tool_ids: List[str]) -> List[dict]:
        if not tool_ids:
            return []
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        tool_id::text, tool_name, description, tool_type,
                        parameters, output_description, credential_ref,
                        app_tags, base_url, endpoint, query_template
                    FROM tools
                    WHERE tool_id = ANY(%s::uuid[]);
                    """,
                    (tool_ids,),
                )
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            release_conn(conn)
```

---

## 4. Insert document

```python
# tkg/insert.py
import json
from datetime import datetime, timezone
from uuid import uuid4
from .schema import ToolDefinition, ToolParameter
from .embedder import embed_one
from .db import get_conn, release_conn


def insert_tool(definition: ToolDefinition) -> str:
    """
    Validates, embeds, and inserts a single tool definition.
    Returns the tool_id.
    Uses ON CONFLICT DO UPDATE so it is safe to re-run on updates.
    """
    _validate(definition)

    embedding = embed_one(definition.get_embedding_text())

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tools (
                    tool_id, tool_name, description, app_tags, tool_type,
                    depends_on, parameters, output_description,
                    example_use_cases, credential_ref,
                    base_url, endpoint, query_template,
                    version, updated_at, embedding
                )
                VALUES (
                    %s::uuid, %s, %s, %s, %s,
                    %s, %s::jsonb, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (tool_id) DO UPDATE SET
                    tool_name         = EXCLUDED.tool_name,
                    description       = EXCLUDED.description,
                    app_tags          = EXCLUDED.app_tags,
                    tool_type         = EXCLUDED.tool_type,
                    depends_on        = EXCLUDED.depends_on,
                    parameters        = EXCLUDED.parameters,
                    output_description = EXCLUDED.output_description,
                    example_use_cases = EXCLUDED.example_use_cases,
                    credential_ref    = EXCLUDED.credential_ref,
                    base_url          = EXCLUDED.base_url,
                    endpoint          = EXCLUDED.endpoint,
                    query_template    = EXCLUDED.query_template,
                    version           = EXCLUDED.version,
                    embedding         = EXCLUDED.embedding,
                    updated_at        = EXCLUDED.updated_at;
                """,
                (
                    definition.tool_id,
                    definition.tool_name,
                    definition.description,
                    definition.app_tags,
                    definition.tool_type,
                    definition.depends_on,
                    json.dumps([p.dict() for p in definition.parameters]),
                    definition.output_description,
                    definition.example_use_cases,
                    definition.credential_ref,
                    definition.base_url,
                    definition.endpoint,
                    definition.query_template,
                    definition.version,
                    datetime.now(timezone.utc),
                    embedding,
                ),
            )
        conn.commit()
    finally:
        release_conn(conn)

    return definition.tool_id


def _validate(d: ToolDefinition):
    errors = []

    if not d.tool_name or not d.tool_name.strip():
        errors.append("tool_name is required")

    if not d.description or len(d.description.strip()) < 40:
        errors.append(
            f"description is too short ({len(d.description.strip())} chars). "
            "Minimum 40 chars — short descriptions produce poor embeddings."
        )

    if not d.app_tags:
        errors.append("app_tags must contain at least one application name")

    if not d.example_use_cases or len(d.example_use_cases) < 2:
        errors.append(
            "example_use_cases must contain at least 2 entries. "
            "These are the primary FTS keyword source."
        )

    if d.tool_type == "api" and not d.base_url:
        errors.append("base_url is required for tool_type='api'")

    if d.tool_type == "sql" and not d.query_template:
        errors.append("query_template is required for tool_type='sql'")

    for dep_id in d.depends_on:
        try:
            from uuid import UUID
            UUID(dep_id)
        except ValueError:
            errors.append(
                f"depends_on contains '{dep_id}' which is not a valid UUID. "
                "Use tool_id values, not tool_name strings."
            )

    if errors:
        raise ValueError(
            f"Tool definition '{d.tool_name}' has {len(errors)} validation error(s):\n"
            + "\n".join(f"  • {e}" for e in errors)
        )
```

### Calling insert_tool — examples

```python
from tkg.schema import ToolDefinition, ToolParameter
from tkg.insert import insert_tool

# Construct and insert one tool
tool = ToolDefinition(
    tool_id="a3f8c2d1-4b5e-4c6f-8d9e-1a2b3c4d5e6f",   # generate once, keep stable
    tool_name="get_pod_status",
    description=(
        "Retrieves the current lifecycle phase, container restart count, "
        "last exit code, and 20 most recent events for a Kubernetes pod. "
        "Use this when an incident involves a service becoming unhealthy, "
        "pods crashing repeatedly, CrashLoopBackOff, OOMKilled, or a "
        "deployment rollout that is not completing."
    ),
    app_tags=["app_payments", "infra-k8s"],
    tool_type="api",
    base_url="https://k8s-api.internal",
    endpoint="/api/v1/namespaces/{namespace}/pods/{pod_name}/status",
    parameters=[
        ToolParameter(name="namespace",  type="string", required=True,
                      description="Kubernetes namespace of the pod"),
        ToolParameter(name="pod_name",   type="string", required=True,
                      description="Exact name of the pod to inspect"),
    ],
    output_description=(
        "Returns pod phase (Running/Pending/Failed/Succeeded/Unknown), "
        "per-container restart count, last termination exit code and reason, "
        "and the 20 most recent pod events (e.g. OOMKilled, BackOff, Pulled)."
    ),
    example_use_cases=[
        "pod keeps restarting after deployment",
        "CrashLoopBackOff alert on payments service",
        "OOMKilled — container ran out of memory",
        "deployment rollout not completing, pods stuck in Pending",
        "service is responding with 503, check if pods are alive",
        "container exit code 137 — likely OOM or SIGKILL",
    ],
    depends_on=["c1d2e3f4-..."],   # tool_id of get_namespace_list, if required
    credential_ref="secret://k8s-api/token",
    version="1.0",
)

tool_id = insert_tool(tool)
print(f"Inserted: {tool_id}")
```

---

## 5. Sample discovery queries (showing accuracy difference)

```python
from tkg.discovery_service import ToolDiscoveryService
from bootstrap import get_dep_graph

svc = ToolDiscoveryService(dep_graph=get_dep_graph())


# ── Query A: raw incident text (baseline) ────────────────────────────────────
# Works for semantic matches but misses exact error terms
tools = svc.discover(
    incident_description="payments service is returning 503 errors",
    app_tags=["app_payments"],
    top_k=20,
)


# ── Query B: exact error code in description ──────────────────────────────────
# FTS arm fires on "CrashLoopBackOff" and "OOMKilled" — lifts the right tools
tools = svc.discover(
    incident_description=(
        "payments service pods are in CrashLoopBackOff. "
        "kubectl describe shows OOMKilled as the last exit reason."
    ),
    app_tags=["app_payments"],
    include_infra_tags=["infra-k8s"],   # add shared-infra tools to scope
    top_k=20,
)


# ── Query C: RAG-enriched description (best accuracy) ────────────────────────
# Pass the combined output of context_builder, not just the raw incident.
# The RAG step already surfaced that previous similar incidents used
# get_pod_status + get_db_connection_pool + restart_deployment.
# Including that vocabulary in the query boosts recall significantly.
rag_context = """
Incident: payments-api pod error rate 45%, p99 latency 12,000ms.
Historical pattern from similar incidents:
  - Root cause was usually DB connection pool exhaustion combined with OOMKilled pods.
  - Resolution involved checking pod status (CrashLoopBackOff), querying connection
    pool metrics, and restarting pods after increasing memory limits.
Key alerts firing: KubePodCrashLooping, HighDBConnectionCount, HighErrorRate503.
"""
tools = svc.discover(
    incident_description=rag_context,
    app_tags=["app_payments"],
    include_infra_tags=["infra-k8s", "infra-postgres"],
    top_k=20,
)


# ── Query D: multi-app scope ───────────────────────────────────────────────────
# When context_builder suspects cross-app issue, broaden app_tags.
# Tool discovery still returns tools in topo-sorted dependency order.
tools = svc.discover(
    incident_description=(
        "order placement failing — orders service times out calling "
        "payments service. Suspect payments DB or payments pods degraded."
    ),
    app_tags=["app_orders", "app_payments"],
    include_infra_tags=["infra-k8s", "infra-postgres"],
    top_k=25,   # increase top_k when scope is wider
)


# ── Inspect scores to validate retrieval quality ─────────────────────────────
for t in tools:
    print(
        f"[{'DEP' if t.is_dependency else 'HIT'}] "
        f"{t.score:.4f}  {t.tool_name:<40} {t.tool_type}"
    )
```

Expected output shape (Query C):
```
[HIT] 0.0312  get_pod_status                           api
[HIT] 0.0287  get_db_connection_pool_metrics           sql
[DEP] 0.0000  get_namespace_list                       api     ← resolved as dep of get_pod_status
[HIT] 0.0241  restart_deployment                       api
[HIT] 0.0198  get_pod_logs_last_crash                  api
[HIT] 0.0176  get_memory_limits_config                 api
```

Higher RRF score = ranked first by more sources. `DEP` tools always have score 0.0
because they weren't found by search — they were pulled in by dependency resolution.

---

## 6. Document quality — what separates good from bad retrieval

The embedding and the tsvector are both derived from the same fields.
Every accuracy problem traces back to one of these fields being weak.

### 6.1 The fields that drive retrieval (in order of impact)

| Field | Impact | Common mistake |
|-------|--------|----------------|
| `example_use_cases` | **Highest** — primary FTS source | Too short, too generic |
| `description` | **High** — primary semantic source | Describes implementation, not symptoms |
| `output_description` | **Medium** — FTS weight C | Omitted entirely |
| `tool_name` | **Medium** — FTS weight A | Abbreviations no one would search |
| `parameters[].description` | **Low** — in embedding text | Often left empty |

### 6.2 Bad vs good: API tool

```json
// ❌  BAD — describes implementation, no symptom vocabulary
{
  "tool_name": "k8s_pod_api",
  "description": "Calls the Kubernetes API to get pod object.",
  "example_use_cases": ["check pod", "get pod info"],
  "output_description": "Pod JSON object"
}

// ✅  GOOD — describes symptoms, uses exact error strings operators search for
{
  "tool_name": "get_pod_status",
  "description": "Retrieves the lifecycle phase, container restart count, exit code, and recent events for a Kubernetes pod. Use this at the start of any investigation involving a pod that is crashing, unresponsive, or stuck in a bad state. Critical first step before attempting a restart.",
  "example_use_cases": [
    "CrashLoopBackOff — pod keeps restarting",
    "OOMKilled — container killed due to memory limit",
    "pod stuck in Pending state, not scheduled",
    "deployment rollout not completing, new pods not coming up",
    "service returning 503, check if backend pods are alive",
    "ImagePullBackOff — container image cannot be pulled",
    "exit code 137 — container killed by signal"
  ],
  "output_description": "Pod phase (Running/Failed/Pending), per-container restart count, last exit code and reason (OOMKilled/Error/Completed), and 20 most recent events"
}
```

### 6.3 Bad vs good: SQL tool

```json
// ❌  BAD
{
  "tool_name": "slow_query_check",
  "description": "Runs a query to find slow DB queries.",
  "example_use_cases": ["check slow queries"],
  "query_template": "SELECT * FROM pg_stat_activity WHERE state = 'active'",
  "output_description": "Query results"
}

// ✅  GOOD
{
  "tool_name": "get_slow_queries",
  "description": "Fetches currently running queries exceeding a duration threshold, including their wait type and whether they are blocking other queries. Use when an incident shows high database latency, connection pool exhaustion, or application endpoints timing out on DB-backed operations.",
  "example_use_cases": [
    "high database response time, p99 latency spiking",
    "connection pool exhausted — too many connections open",
    "order service timing out on insert queries",
    "DB CPU at 100%, suspect expensive query",
    "transactions piling up, blocking lock detected",
    "application returns 504 on any DB write operation"
  ],
  "query_template": "SELECT pid, now() - query_start AS duration, wait_event_type, wait_event, state, left(query, 200) AS query_preview, blocking_pids FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '{threshold_seconds} seconds' ORDER BY duration DESC LIMIT 20",
  "parameters": [
    {"name": "threshold_seconds", "type": "integer", "default": "5",
     "description": "Return queries running longer than this many seconds"}
  ],
  "output_description": "Running queries: duration, wait type (Lock/IO/Client), whether blocking other sessions, first 200 chars of query text, PIDs of blocking sessions"
}
```

### 6.4 Bad vs good: CLI / script tool

```json
// ❌  BAD
{
  "tool_name": "log_grep",
  "description": "Greps application logs.",
  "example_use_cases": ["search logs"],
  "output_description": "Matching log lines"
}

// ✅  GOOD
{
  "tool_name": "grep_app_logs_for_errors",
  "description": "Searches the last N minutes of application logs for error patterns, exceptions, and stack traces. Use early in any incident to find the first occurrence of an error and the stack trace associated with it. Significantly faster than opening the logging dashboard for targeted searches.",
  "example_use_cases": [
    "find first occurrence of NullPointerException in payments logs",
    "check if 'connection refused' appears in last 30 minutes of logs",
    "find stack trace for 500 errors on /api/checkout",
    "search for timeout errors in order-processing worker",
    "locate the exact time an error first appeared before the alert fired",
    "find repeated 'WARN' or 'ERROR' lines spiking in the last 5 minutes"
  ],
  "output_description": "Matching log lines with timestamp, log level, and surrounding 2 lines of context. Returns up to 100 matches, newest first.",
  "parameters": [
    {"name": "app_name",    "type": "string",  "required": true,  "description": "Application name as it appears in the log path"},
    {"name": "pattern",     "type": "string",  "required": true,  "description": "Grep-compatible regex pattern to search for"},
    {"name": "minutes_back","type": "integer", "required": false,  "default": "30", "description": "How many minutes of logs to search"}
  ]
}
```

### 6.5 Rule of thumb for writing example_use_cases

Write them the way an on-call engineer would describe the symptom to a colleague,
not the way a developer would describe the tool's function:

```
❌  "retrieve kubernetes pod information"     ← developer framing of the tool
✅  "pod keeps restarting and I don't know why" ← engineer framing of the symptom

❌  "query pg_stat_activity table"
✅  "database is slow and I need to find what query is causing it"

❌  "execute grep on log files"
✅  "I need to find where in the logs the 503 errors started"
```

Write at least 5 use cases per tool, ideally 6–8.
Use exact error codes and metric names when they exist (`OOMKilled`, `SIGKILL`,
`connection pool exhausted`, `HTTP 503`, `exit code 137`).
These exact strings are what FTS matches against incident descriptions that
contain copy-pasted alert text.

### 6.6 What the embedding text looks like after assembly

`get_embedding_text()` from `schema.py` concatenates all fields.
This is what gets fed to the sentence transformer:

```
get_pod_status. Retrieves the lifecycle phase, container restart count, exit code,
and recent events for a Kubernetes pod. Use this at the start of any investigation
involving a pod that is crashing, unresponsive, or stuck in a bad state. Critical
first step before attempting a restart. Use cases: CrashLoopBackOff — pod keeps
restarting. OOMKilled — container killed due to memory limit. pod stuck in Pending
state, not scheduled. deployment rollout not completing, new pods not coming up.
service returning 503, check if backend pods are alive. ImagePullBackOff — container
image cannot be pulled. exit code 137 — container killed by signal. Inputs: namespace
(Kubernetes namespace of the pod), pod_name (Exact name of the pod to inspect).
Output: Pod phase (Running/Failed/Pending), per-container restart count, last exit
code and reason (OOMKilled/Error/Completed), and 20 most recent events.
```

This gives the embedding model rich, varied vocabulary that covers both the technical
action (what the tool does) and the operational symptoms (why you would reach for it).
