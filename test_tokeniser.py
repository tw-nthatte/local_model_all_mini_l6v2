import re
import tiktoken
from typing import List, Dict

# 1. Load your text‑based PDF output into one big string
with open("sop_full_text.txt", "r", encoding="utf-8") as f:
    full_text = f.read()

# 2. (Optional) Split off table blocks so we treat each table as an atomic chunk
#    Assume tables are delimited by <<TABLE_START>> ... <<TABLE_END>>
table_pattern = re.compile(r"<<TABLE_START>>(.*?)<<TABLE_END>>", re.DOTALL)
tables = table_pattern.findall(full_text)

# Remove tables from the main text, so we don't re‑split them
text_wo_tables = table_pattern.sub("", full_text)

# 3. Tokenizer setup (choose the encoding your LLM uses)
encoding = tiktoken.get_encoding("cl100k_base")  # adjust to your model

def count_tokens(text: str) -> int:
    return len(encoding.encode(text))

# 4. Chunking function with overlap
def chunk_text(
    text: str,
    max_tokens: int = 500,
    overlap_tokens: int = 100,
    metadata: Dict = None
) -> List[Dict]:
    """
    Splits `text` into chunks of up to max_tokens, 
    with `overlap_tokens` overlap between chunks.
    Returns list of dicts: {"chunk_text": ..., "meta": {…}}.
    """
    if metadata is None:
        metadata = {}
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    chunk_id = 0

    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)

        # Attach metadata, including sequence and page info if you have it
        chunks.append({
            "chunk_id": f"{metadata.get('source_file','unknown')}__{chunk_id}",
            "chunk_text": chunk_text,
            "meta": {
                **metadata,
                "sequence_index": chunk_id,
                "token_start": start,
                "token_end": end,
                "token_count": len(chunk_tokens)
            }
        })
        chunk_id += 1
        # slide window back by overlap_tokens
        start = end - overlap_tokens

    return chunks

# 5. Build chunks from paragraphs + tables
all_chunks = []

# First handle non‑table text, e.g. split by headings or just feed to our sliding window
# If you have logical boundaries (headers/subheaders), you could split first by those
# For simplicity—we chunk the whole text_wo_tables:
all_chunks += chunk_text(
    text_wo_tables,
    max_tokens=400,
    overlap_tokens=80,
    metadata={"source_file": "sop_full.txt", "type": "body"}
)

# Then attach each table as one chunk (no further splitting)
for idx, tbl in enumerate(tables):
    tok_count = count_tokens(tbl)
    all_chunks.append({
        "chunk_id": f"sop_full__table_{idx}",
        "chunk_text": tbl,
        "meta": {
            "source_file": "sop_full.txt",
            "type": "table",
            "sequence_index": len(all_chunks),
            "token_count": tok_count
        }
    })

# 6. Example: print out the first few chunks
for c in all_chunks[:5]:
    print(f"ID: {c['chunk_id']}")
    print(f"Tokens: {c['meta']['token_count']}")
    print(f"Excerpt: {c['chunk_text'][:100]!r}")
    print("───")

# 7. These chunks are now ready:
#    - You can loop: embed = embedder.encode(c["chunk_text"])
#    - faiss_index.add(embed)
#    - store c["chunk_id"] → c["meta"] + c["chunk_text"] in your metadata DB

