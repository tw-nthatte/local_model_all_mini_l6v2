import pandas as pd
from docling.document_converter import DocumentConverter
from docling.formats.pdf import PdfPipelineOptions, PdfFormatOption
from docling.formats.pdf.pipelines.table_structure import TableFormerMode
from docling_core.types.doc.page import TextCellUnit

# --- Configuration ---
PDF_FILE_PATH = "./your_document.pdf"  # Replace with the path to your PDF file

# --- 1. Docling Parsing with Table Extraction Enabled ---
def parse_pdf_with_tables(pdf_path: str):
    """
    Parses a PDF document using Docling, enabling table structure analysis.
    Returns the DoclingDocument object.
    """
    pipeline_options = PdfPipelineOptions(do_table_structure=True)
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE # Use a more accurate table detection model
    
    doc_converter = DocumentConverter(
        format_options={
            "pdf": PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = doc_converter.convert(pdf_path)
    return result.document

# --- 2. Separate Text and Tables ---
def separate_text_and_tables(docling_document):
    """
    Separates the text content and extracted tables from a DoclingDocument.
    Returns a list of extracted tables (as DataFrames) and a list of text blocks.
    """
    extracted_tables = []
    text_content_blocks = []

    # Get the bounding boxes of all detected tables
    table_bounding_boxes_per_page = {}
    for page_ix, page in enumerate(docling_document.pages):
        table_bounding_boxes_per_page[page_ix] = []
        for table in page.tables:
            # Export table to DataFrame and store
            table_df: pd.DataFrame = table.export_to_dataframe()
            extracted_tables.append(table_df)
            
            # Store table bounding box (normalized coordinates)
            table_bounding_boxes_per_page[page_ix].append(table.rect)

    # Iterate through pages and extract text, excluding regions within tables
    for page_ix, page in enumerate(docling_document.pages):
        current_page_text = []
        for word in page.iterate_cells(unit_type=TextCellUnit.WORD):
            is_in_table = False
            for table_rect in table_bounding_boxes_per_page[page_ix]:
                # Check if the word's bounding box overlaps with the table's bounding box
                if word.rect.x0 >= table_rect.x0 and word.rect.x1 <= table_rect.x1 and \
                   word.rect.y0 >= table_rect.y0 and word.rect.y1 <= table_rect.y1:
                    is_in_table = True
                    break
            if not is_in_table:
                current_page_text.append(word.text)
        if current_page_text:
            text_content_blocks.append(" ".join(current_page_text))
            
    return extracted_tables, text_content_blocks

# --- 3. Custom Chunking Logic ---

def custom_text_chunking(text_blocks: list[str], max_chars_per_chunk: int = 500):
    """
    Example custom chunking logic for text content.
    This simple example splits text into chunks of a maximum character size.
    You would replace this with your semantic or hierarchical chunking logic.
    """
    chunks = []
    for block in text_blocks:
        current_chunk = []
        current_length = 0
        words = block.split() # Simple word split
        for word in words:
            if current_length + len(word) + 1 > max_chars_per_chunk and current_length > 0:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(word)
            current_length += len(word) + 1
        if current_chunk:
            chunks.append(" ".join(current_chunk))
    return chunks

def custom_table_chunking(tables: list[pd.DataFrame], max_rows_per_chunk: int = 10):
    """
    Example custom chunking logic for tables.
    This example splits tables into smaller tables (chunks) based on a maximum number of rows.
    You could also convert tables to text/markdown/HTML and then apply text chunking.
    """
    table_chunks = []
    for table_df in tables:
        if table_df.empty:
            continue
        
        # Split table into chunks of max_rows_per_chunk
        for i in range(0, len(table_df), max_rows_per_chunk):
            chunk_df = table_df.iloc[i : i + max_rows_per_chunk]
            table_chunks.append(chunk_df)
    return table_chunks


# --- End-to-End Execution ---
if __name__ == "__main__":
    print(f"Parsing PDF: {PDF_FILE_PATH}")
    docling_document = parse_pdf_with_tables(PDF_FILE_PATH)

    extracted_tables, text_blocks = separate_text_and_tables(docling_document)

    print(f"\nExtracted {len(extracted_tables)} tables.")
    if extracted_tables:
        print("First extracted table (as DataFrame):")
        print(extracted_tables[0].head())
        # Apply custom table chunking
        chunked_tables = custom_table_chunking(extracted_tables)
        print(f"Chunked into {len(chunked_tables)} table chunks.")
        if chunked_tables:
            print("First table chunk:")
            print(chunked_tables[0])

    print(f"\nExtracted {len(text_blocks)} text blocks outside of tables.")
    if text_blocks:
        print("First text block:")
        print(text_blocks[0][:500]) # Print first 500 characters
        # Apply custom text chunking
        chunked_texts = custom_text_chunking(text_blocks)
        print(f"Chunked into {len(chunked_texts)} text chunks.")
        if chunked_texts:
            print("First text chunk:")
            print(chunked_texts[0][:500])

