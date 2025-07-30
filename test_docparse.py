from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfFormatOption, WordFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.pipeline.simple_pipeline import SimplePipeline

from docling_core.types.doc import (
    TextItem,
    SectionHeaderItem,
    TableItem,
    PictureItem,
    ListItem,
    FormItem
)


def extract_structured_chunks(input_paths):
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=StandardPdfPipeline,
                backend=PyPdfiumDocumentBackend
            ),
            InputFormat.DOCX: WordFormatOption(
                pipeline_cls=SimplePipeline
            )
        }
    )

    results = converter.convert_all([Path(p) for p in input_paths])

    all_chunks = []
    for res in results:
        doc = res.document
        seq = 0

        # Combine all elements from the document
        all_items = doc.texts + doc.tables + doc.pictures

        for item in all_items:
            meta = {
                "source_file": doc.origin.filename,
                "sequence_index": seq,
                "page_number": item.prov[0].page_no if item.prov else None,
                "type": item.__class__.__name__
            }

            if isinstance(item, (TextItem, SectionHeaderItem, ListItem, FormItem)):
                text = item.text
            elif isinstance(item, TableItem):
                text = item.table.to_markdown()
            elif isinstance(item, PictureItem):
                text = "[IMAGE]"
            else:
                continue

            chunk = {
                "chunk_id": f"{doc.origin.filename}__{seq}",
                "chunk_text": text,
                "metadata": meta
            }

            all_chunks.append(chunk)
            seq += 1

    return all_chunks


# Example usage
if __name__ == "__main__":
    paths = ["example_data/sop1.pdf", "example_data/sop2.docx"]
    chunks = extract_structured_chunks(paths)

    for chunk in chunks:
        print("\n--- Chunk ID:", chunk["chunk_id"])
        print("Type:", chunk["metadata"]["type"])
        print("Page:", chunk["metadata"].get("page_number"))
        print("Content:\n", chunk["chunk_text"][:500], "...")

