import json
from pathlib import Path

from docling.datamodel.base_models import InputFormat                  # supported formats
from docling.document_converter import DocumentConverter               # core converter
from docling.datamodel.format_options import PdfFormatOption, WordFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend  # fast PDF backend
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.pipeline.simple_pipeline import SimplePipeline

from docling.datamodel.elements import (
    TableItem,
    PictureItem,
    ParagraphItem,
    HeadingItem,
    ListItem,
    FormItem,
)

# ─── CONFIG ────────────────────────────────────────────────────────────────
INPUT_FILES = [
    Path("input/sop1.pdf"),
    Path("input/sop2.docx"),
]

# Only parse PDF + DOCX
converter = DocumentConverter(
    allowed_formats=[InputFormat.PDF, InputFormat.DOCX],               # :contentReference[oaicite:0]{index=0}
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_cls=StandardPdfPipeline,
            backend=PyPdfiumDocumentBackend
        ),
        InputFormat.DOCX: WordFormatOption(
            pipeline_cls=SimplePipeline
        ),
    },
)

# ─── PARSE & CHUNK ─────────────────────────────────────────────────────────
all_chunks = []

for path in INPUT_FILES:
    print(f"→ Converting {path.name} …")
    conv_results = converter.convert_all([path])                      # :contentReference[oaicite:1]{index=1}

    # conv_results is a list; for each file we get one result
    for res in conv_results:
        doc = res.document                                           # DoclingDocument

        seq_idx = 0
        # iterate_items yields (element, hierarchical_level)
        for element, _ in doc.iterate_items():
            meta = {
                "source_file": path.name,
                "sequence_index": seq_idx,
                "page_number": getattr(element, "page", {}).get("page_no", None),
                "type": element.__class__.__name__,
            }

            if isinstance(element, ParagraphItem) or isinstance(element, HeadingItem) \
               or isinstance(element, ListItem) or isinstance(element, FormItem):
                text = element.text  # easy: raw text
                chunk = {
                    "chunk_id": f"{path.stem}__{seq_idx}",
                    "chunk_text": text,
                    "meta": meta
                }

            elif isinstance(element, TableItem):
                # turn table into Markdown (preserves rows/cols)
                md = element.to_markdown()  
                chunk = {
                    "chunk_id": f"{path.stem}__table__{seq_idx}",
                    "chunk_text": md,
                    "meta": meta
                }

            elif isinstance(element, PictureItem):
                # save image bytes to a file if you want
                img_path = Path("output") / f"{path.stem}__img__{seq_idx}.png"
                img_path.parent.mkdir(exist_ok=True, parents=True)
                element.get_image(doc).save(img_path, format="PNG")

                chunk = {
                    "chunk_id": f"{path.stem}__img__{seq_idx}",
                    "chunk_text": "[IMAGE]",                     # placeholder for embedding
                    "meta": {**meta, "image_path": str(img_path)},
                }

            else:
                # skip any unsupported element types
                seq_idx += 1
                continue

            all_chunks.append(chunk)
            seq_idx += 1

# ─── DUMP AS JSONL ──────────────────────────────────────────────────────────
with open("output/chunks.jsonl", "w", encoding="utf-8") as out:
    for c in all_chunks:
        out.write(json.dumps(c, ensure_ascii=False) + "\n")

print(f"✅ Generated {len(all_chunks)} chunks.")

