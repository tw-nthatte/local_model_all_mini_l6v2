# TKG — pgvector Implementation
## Replaces the Qdrant-specific modules from the main plan

Everything in the original plan stays the same **except** the four modules below:
`db.py`, `indexer.py`, `dependency_graph.py`, `discovery_service.py`.
`schema.py` and `embedder.py` are **unchanged**.

---

## Stack change summary

| Component | Original plan | This plan |
|-----------|---------------|-----------|
| Vector store | Qdrant (separate service) | pgvector table inside your existing PostgreSQL |
| Payload filtering | Qdrant filter API | SQL `WHERE app_tags && $1::text[]` |
| ANN index | Qdrant HNSW (internal) | `CREATE INDEX USING hnsw` |
| Dependency persistence | NetworkX → JSON file | NetworkX loaded from the `tools.depends_on` column |
| New infrastructure needed | Qdrant Docker/K8s | Nothing — just `CREATE EXTENSION vector` on your existing DB |

### On your question: separate DB or same DB as incident store?

Same PostgreSQL instance, **different table**. Your incident store stays completely
untouched — its schema, search logic (keyword + semantic + RRF), and purge
strategy are irrelevant to the tools table. You get operational simplicity (one
DB to manage) with clean isolation (different schema, different indexes, different
query path).

```
Your PostgreSQL instance
├── table: incidents        ← existing, 3-year data, unchanged
└── table: tools            ← new, TKG, separate schema and indexes
```

---

## Required packages

```
# requirements additions (remove qdrant-client)
pgvector>=0.2.5
psycopg2-binary>=2.9.9     # or psycopg[binary]>=3.1 for async
sentence-transformers>=2.7  # unchanged
networkx>=3.3               # unchanged
```

---

## SQL setup (run once — or in a migration)

```sql
-- Enable the extension (requires superuser on first run)
CREATE EXTENSION IF NOT EXISTS vector;

-- Main tools table
CREATE TABLE IF NOT EXISTS tools (
    tool_id          UUID         PRIMARY KEY,
    tool_name        VARCHAR(255) NOT NULL,
    description      TEXT         NOT NULL,
    app_tags         TEXT[]       NOT NULL DEFAULT '{}',
    tool_type        VARCHAR(50)  NOT NULL,
    depends_on       TEXT[]       NOT NULL DEFAULT '{}',  -- stores tool_id strings
    parameters       JSONB        NOT NULL DEFAULT '[]',
    output_description  TEXT,
    example_use_cases   TEXT[]    NOT NULL DEFAULT '{}',
    credential_ref   VARCHAR(255),
    base_url         TEXT,
    endpoint         TEXT,
    query_template   TEXT,
    version          VARCHAR(20)  DEFAULT '1.0',
    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
    embedding        vector(384)  NOT NULL               -- 384 for MiniLM; 1536 for OpenAI
);

-- HNSW index: better recall than IVFFlat, no nlist to tune, ideal for <1M vectors
-- m=16 and ef_construction=64 are good defaults; raise ef_construction to 128 for
-- higher recall at cost of slower index build time
CREATE INDEX IF NOT EXISTS tools_embedding_hnsw_idx
    ON tools USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index on app_tags array — makes the && overlap filter fast
CREATE INDEX IF NOT EXISTS tools_app_tags_gin_idx
    ON tools USING gin (app_tags);

-- Optional: index on tool_type if you ever filter by it
CREATE INDEX IF NOT EXISTS tools_tool_type_idx
    ON tools (tool_type);
```

**Why HNSW over IVFFlat:**
IVFFlat needs a pre-specified `nlist` (number of clusters) tuned to dataset size, and
requires running `ANALYZE` after bulk inserts before recall is reliable. HNSW builds
incrementally, needs no tuning parameter, and gives better recall at query time. At
15k vectors the build time difference is irrelevant (seconds either way).

---

## tkg/db.py

```python
import os
import json
import psycopg2
from psycopg2 import pool
from pgvector.psycopg2 import register_vector

DATABASE_URL = os.environ["TKG_DATABASE_URL"]
# e.g. "postgresql://user:password@localhost:5432/incident_bot"
# Same connection string as your incident store — just a different table

VECTOR_DIM = 384  # match your embedding model:
                  # 384  → sentence-transformers/all-MiniLM-L6-v2
                  # 1536 → text-embedding-3-small (OpenAI)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


def get_conn():
    """
    Borrow a connection from the pool and register the vector type adapter.
    Always pair with release_conn() in a finally block.
    """
    conn = _get_pool().getconn()
    register_vector(conn)
    return conn


def release_conn(conn):
    _get_pool().putconn(conn)


def init_schema():
    """
    Idempotent schema bootstrap — safe to run on every startup.
    Requires the SQL from the migration section above to have been applied,
    OR run it here programmatically.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS tools (
                    tool_id          UUID         PRIMARY KEY,
                    tool_name        VARCHAR(255) NOT NULL,
                    description      TEXT         NOT NULL,
                    app_tags         TEXT[]       NOT NULL DEFAULT '{{}}',
                    tool_type        VARCHAR(50)  NOT NULL,
                    depends_on       TEXT[]       NOT NULL DEFAULT '{{}}',
                    parameters       JSONB        NOT NULL DEFAULT '[]',
                    output_description  TEXT,
                    example_use_cases   TEXT[]    NOT NULL DEFAULT '{{}}',
                    credential_ref   VARCHAR(255),
                    base_url         TEXT,
                    endpoint         TEXT,
                    query_template   TEXT,
                    version          VARCHAR(20)  DEFAULT '1.0',
                    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
                    embedding        vector({VECTOR_DIM}) NOT NULL
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS tools_embedding_hnsw_idx
                ON tools USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS tools_app_tags_gin_idx
                ON tools USING gin (app_tags);
            """)
        conn.commit()
    finally:
        release_conn(conn)
```

---

## tkg/indexer.py

```python
import json
from pathlib import Path
from typing import List
from .schema import ToolDefinition
from .embedder import embed
from .db import get_conn, release_conn

TOOLS_DIR = Path("tools")


def load_all_definitions() -> List[ToolDefinition]:
    definitions = []
    for json_file in TOOLS_DIR.rglob("*.json"):
        with open(json_file) as f:
            data = json.load(f)
        definitions.append(ToolDefinition(**data))
    return definitions


def build_and_index():
    """
    Full re-index: embeds all tool definitions and upserts into PostgreSQL.
    ON CONFLICT DO UPDATE makes this idempotent — safe to re-run.
    """
    definitions = load_all_definitions()
    print(f"Loaded {len(definitions)} tool definitions.")

    # Batch embed — sentence-transformers handles batching internally
    texts = [d.get_embedding_text() for d in definitions]
    vectors = embed(texts)  # returns List[List[float]]
    print(f"Embeddings generated ({len(vectors[0])}-dim).")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for d, vec in zip(definitions, vectors):
                cur.execute(
                    """
                    INSERT INTO tools (
                        tool_id, tool_name, description, app_tags, tool_type,
                        depends_on, parameters, output_description,
                        example_use_cases, credential_ref, base_url,
                        endpoint, query_template, version, embedding
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s,
                        %s, %s::jsonb, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s
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
                        updated_at        = NOW();
                    """,
                    (
                        d.tool_id,
                        d.tool_name,
                        d.description,
                        d.app_tags,                                  # TEXT[]
                        d.tool_type,
                        d.depends_on,                                # TEXT[]
                        json.dumps([p.dict() for p in d.parameters]),
                        d.output_description,
                        d.example_use_cases,                         # TEXT[]
                        d.credential_ref,
                        d.base_url,
                        d.endpoint,
                        d.query_template,
                        d.version,
                        vec,                  # pgvector adapter converts list → vector
                    ),
                )
        conn.commit()
        print(f"Upserted {len(definitions)} tools into PostgreSQL.")
    finally:
        release_conn(conn)


def index_single(definition: ToolDefinition):
    """
    Re-index one tool after its JSON file changes.
    Called from CI/CD on changed files.
    """
    vec = embed([definition.get_embedding_text()])[0]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tools (
                    tool_id, tool_name, description, app_tags, tool_type,
                    depends_on, parameters, output_description,
                    example_use_cases, credential_ref, base_url,
                    endpoint, query_template, version, embedding
                )
                VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tool_id) DO UPDATE SET
                    tool_name = EXCLUDED.tool_name,
                    description = EXCLUDED.description,
                    app_tags = EXCLUDED.app_tags,
                    depends_on = EXCLUDED.depends_on,
                    parameters = EXCLUDED.parameters,
                    output_description = EXCLUDED.output_description,
                    example_use_cases = EXCLUDED.example_use_cases,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW();
                """,
                (
                    definition.tool_id, definition.tool_name, definition.description,
                    definition.app_tags, definition.tool_type, definition.depends_on,
                    json.dumps([p.dict() for p in definition.parameters]),
                    definition.output_description, definition.example_use_cases,
                    definition.credential_ref, definition.base_url,
                    definition.endpoint, definition.query_template, definition.version, vec,
                ),
            )
        conn.commit()
    finally:
        release_conn(conn)


if __name__ == "__main__":
    build_and_index()
```

---

## tkg/dependency_graph.py

```python
import networkx as nx
from typing import List, Set
from .db import get_conn, release_conn


class ToolDependencyGraph:

    def __init__(self):
        self.graph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_from_db(self):
        """
        Reads tool_id + depends_on from PostgreSQL and builds the NetworkX graph.
        Call this once at startup, or after a re-index.

        The `depends_on` column is TEXT[] — each element is a tool_id string.
        Edges go:  tool_id  →  dependency_id
        (meaning: to run tool_id, you must first run dependency_id)
        """
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tool_id::text, tool_name, depends_on FROM tools;"
                )
                rows = cur.fetchall()
        finally:
            release_conn(conn)

        # Add all nodes first so dependency references don't silently vanish
        for tool_id, tool_name, _ in rows:
            self.graph.add_node(tool_id, name=tool_name)

        # Add dependency edges
        missing_deps: List[str] = []
        for tool_id, tool_name, depends_on in rows:
            for dep_id in (depends_on or []):
                if self.graph.has_node(dep_id):
                    self.graph.add_edge(tool_id, dep_id)
                else:
                    missing_deps.append(
                        f"{tool_name} ({tool_id}) → missing dep {dep_id}"
                    )

        if missing_deps:
            print(
                f"WARNING: {len(missing_deps)} unresolved dependency references:\n"
                + "\n".join(missing_deps[:10])
                + ("\n  ... (truncated)" if len(missing_deps) > 10 else "")
            )

        print(
            f"Dependency graph loaded: "
            f"{self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges."
        )

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def resolve_with_dependencies(self, tool_ids: List[str]) -> Set[str]:
        """
        BFS from each seed tool_id, collecting all transitive dependencies.
        Returns the full set including the seeds themselves.
        """
        visited: Set[str] = set()
        queue = list(tool_ids)
        while queue:
            tid = queue.pop()
            if tid in visited:
                continue
            visited.add(tid)
            # graph.successors(tid) returns the tools that tid depends ON
            for dep in self.graph.successors(tid):
                if dep not in visited:
                    queue.append(dep)
        return visited

    def topological_order(self, tool_ids: Set[str]) -> List[str]:
        """
        Returns tool_ids in execution order — dependencies come first.
        Uses NetworkX's topological sort on the subgraph, then reverses
        because our edges run tool→dependency (we want dependency first).
        """
        subgraph = self.graph.subgraph(tool_ids)
        try:
            order = list(nx.topological_sort(subgraph))
            order.reverse()   # dependency-first order
            return order
        except nx.NetworkXUnfeasible:
            # Cycle in the tool dependency graph — should never happen
            # if your tool definitions are correct; log and degrade gracefully
            print("ERROR: Cycle detected in tool dependency graph. "
                  "Returning unordered set.")
            return list(tool_ids)
```

---

## tkg/discovery_service.py

```python
import json
from dataclasses import dataclass
from typing import List, Optional, Set
from .db import get_conn, release_conn
from .embedder import embed_one
from .dependency_graph import ToolDependencyGraph


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
    score: float        # cosine similarity; 0.0 for dependency-only tools
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
        """
        1. Embed the incident description
        2. Semantic search in PostgreSQL filtered by app_tags
        3. Resolve transitive dependencies via the dep graph
        4. Fetch any dependency-only tools from DB
        5. Return topologically sorted list (execute dependencies first)
        """
        search_tags = app_tags + (include_infra_tags or [])
        query_vector = embed_one(incident_description)

        # --- Step 1: semantic search with app_tag filter ---
        candidate_rows = self._vector_search(query_vector, search_tags, top_k)
        # candidate_rows: list of dicts keyed by column name, with 'score'

        candidate_map = {row["tool_id"]: row for row in candidate_rows}
        candidate_ids = list(candidate_map.keys())

        # --- Step 2: resolve dependencies ---
        full_id_set: Set[str] = self.dep_graph.resolve_with_dependencies(candidate_ids)
        dependency_only_ids = full_id_set - set(candidate_ids)

        # --- Step 3: fetch dependency-only tools from DB ---
        if dependency_only_ids:
            dep_rows = self._fetch_by_ids(list(dependency_only_ids))
            for row in dep_rows:
                row["score"] = 0.0
                candidate_map[row["tool_id"]] = row

        # --- Step 4: topological sort ---
        ordered_ids = self.dep_graph.topological_order(full_id_set)

        # --- Step 5: assemble result ---
        result = []
        for tid in ordered_ids:
            row = candidate_map.get(tid)
            if row is None:
                continue  # dep not in DB (schema inconsistency — already warned at load time)
            result.append(
                DiscoveredTool(
                    tool_id=tid,
                    tool_name=row["tool_name"],
                    description=row["description"],
                    tool_type=row["tool_type"],
                    parameters=row["parameters"] if isinstance(row["parameters"], list)
                               else json.loads(row["parameters"]),
                    output_description=row.get("output_description", ""),
                    credential_ref=row.get("credential_ref", ""),
                    app_tags=row.get("app_tags", []),
                    base_url=row.get("base_url"),
                    endpoint=row.get("endpoint"),
                    query_template=row.get("query_template"),
                    score=row["score"],
                    is_dependency=tid in dependency_only_ids,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _vector_search(
        self,
        query_vector: List[float],
        app_tags: List[str],
        top_k: int,
    ) -> List[dict]:
        """
        Cosine similarity search with app_tag pre-filter.

        The  &&  operator = "array overlap" — returns rows where app_tags
        contains ANY element of the query array. This is what allows a tool
        tagged ["app_payments", "infra-k8s"] to be found when searching
        for either app_payments OR infra-k8s.

        The HNSW index is used for the ORDER BY / LIMIT, and the GIN index
        is used for the WHERE clause — PostgreSQL will use both automatically.
        """
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        tool_id::text,
                        tool_name,
                        description,
                        tool_type,
                        parameters,
                        output_description,
                        credential_ref,
                        app_tags,
                        base_url,
                        endpoint,
                        query_template,
                        depends_on,
                        1 - (embedding <=> %s::vector) AS score
                    FROM tools
                    WHERE app_tags && %s::text[]
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (query_vector, app_tags, query_vector, top_k),
                )
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            release_conn(conn)
        return rows

    def _fetch_by_ids(self, tool_ids: List[str]) -> List[dict]:
        """Fetch full tool records by tool_id list (no vector needed)."""
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
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            release_conn(conn)
        return rows
```

---

## Startup wiring (app entrypoint / crew bootstrap)

```python
# bootstrap.py  — called once when your service starts
from tkg.db import init_schema
from tkg.dependency_graph import ToolDependencyGraph

_dep_graph: ToolDependencyGraph | None = None

def get_dep_graph() -> ToolDependencyGraph:
    """Singleton — load graph once, reuse across all requests."""
    global _dep_graph
    if _dep_graph is None:
        _dep_graph = ToolDependencyGraph()
        _dep_graph.load_from_db()
    return _dep_graph

def startup():
    init_schema()           # CREATE TABLE IF NOT EXISTS — safe to call every time
    get_dep_graph()         # warm the NetworkX graph into memory
    print("TKG ready.")
```

```python
# In your CrewAI flow / main entrypoint:
from bootstrap import startup, get_dep_graph
from tkg.discovery_service import ToolDiscoveryService

startup()

discovery_service = ToolDiscoveryService(dep_graph=get_dep_graph())
# pass this singleton into your SearchToolsTool and context_builder task
```

---

## One important pgvector behaviour to know

When you use `WHERE app_tags && $1::text[]` combined with `ORDER BY embedding <=> $2::vector LIMIT n`,
PostgreSQL has to decide whether to use the GIN index (for the filter) or the HNSW index (for
the sort) first. With large tables and selective filters, the planner usually makes the right
call — but you can verify with `EXPLAIN ANALYZE`:

```sql
EXPLAIN ANALYZE
SELECT tool_id, tool_name, 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) AS score
FROM tools
WHERE app_tags && ARRAY['app_payments']::text[]
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 20;
```

If the planner is doing a sequential scan on a large table, force the HNSW index path by
setting `SET enable_seqscan = off;` in your session, then re-running EXPLAIN to see if it
improves. At 15k rows this is unlikely to matter at all, but worth knowing as tool count
grows into hundreds of thousands.

---

## What stays unchanged from the main plan

- `tkg/schema.py` — ToolDefinition, ToolParameter, get_embedding_text() — no change
- `tkg/embedder.py` — embed(), embed_one() — no change
- `tkg/search_tool.py` — SearchToolsTool wrapping discovery_service.discover() — no change
- `tool_factory.py` — accepts DiscoveredTool list, fetches credentials — no change
- `flow.py` integration — no change
- All stories and effort estimates — no change
- Epic 1 (tool metadata enrichment) — no change; this is still the critical path
