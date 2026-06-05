import json
import sys
from pathlib import Path

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from docling_core.types.doc import DocItemLabel, DoclingDocument


def page_of_item(item) -> int:
    """
    Gets the 1-based page number for a Docling item, or 0 if unknown.
    Docling items have a .prov (provenance) list that may include page info.

    :return: The 1-based page number for an item, or 0 if unknown.
    """
    if item.prov:
        return item.prov[0].page_no
    return 0


def current_parent_id(section_stack: list[tuple[int, int | float]]) -> int | None:
    """
    Helper to get the current parent section ID from the section stack.

    :param section_stack: A stack of (section_id, section_level) tuples representing the current section hierarchy.

    :return: The current parent section ID, or None if there is no parent.
    """
    return section_stack[-1][0] if section_stack else None


def add_page(pages: dict[int, list[dict]], page_no: int, item_dict: dict) -> dict[int, list[dict]]:
    """
    Helper to add an item dict to the appropriate page in the pages dict.

    :param pages: The dictionary of pages to modify.
    :param page_no: The 1-based page number for the item.
    :param item_dict: A dict representing the content item (e.g. type, label, content).

    :return: A new dictionary with the item added to the appropriate page.
    """
    pages.setdefault(page_no, []).append(item_dict)
    return pages


def extract_pdf(pdf_path: str, output_path: str | None = None) -> dict:
    """
    Convert a PDF with Docling and export all parsed content to a dict,
    grouped by page number. Tables are exported as Markdown strings.

    :param pdf_path: Path to the source PDF.
    :param output_path: Optional path to write the JSON output file.

    :return: A dict of: {
        "metadata": document level metadata (e.g. source file, total pages),
        "pages": list of page dicts, each with a list of content items (text, tables, etc.),
        "full_markdown": the entire document exported as a single Markdown string (useful for RAG chunking)
    }
    """
    # Configure a PDF conversion pipeline with Docling's options
    pipeline_options = PdfPipelineOptions(
        do_ocr=False,            # set True for scanned / image-only PDFs
        do_table_structure=True, # detect and reconstruct tables
        generate_page_images=False,  # ignore images
        generate_picture_images=False,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    # Convert the PDF to a DoclingDocument
    print(f"Converting: {pdf_path}")
    result = converter.convert(pdf_path)
    doc: DoclingDocument = result.document

    # Pages will be a dictionary of {page_no: [item_dict, ...]}
    pages: dict[int, list[dict]] = {}

    # Iterate over the items in the document. 
    # Each item has a label (e.g. title, section_header, text, footnote, table, picture, etc.)
    item_id = 0
    current_section_id = None
    section_stack: list[tuple[int, int | float]] = []  # stack of (section_id, section_level) for nested sections
    for item, _ in doc.iterate_items():
        label: DocItemLabel = item.label
        # print(f"Processing item with label: {label} on page {page_of_item(item)}")

        # Skip pictures/images
        if label == DocItemLabel.PICTURE:
            continue

        item_id += 1

        # If the item is a table, try to export it as Markdown. If that fails, fall back to raw text.
        if label == DocItemLabel.TABLE:
            try:
                md_table = item.export_to_markdown(doc=doc)
            except Exception:
                md_table = item.text if hasattr(item, "text") else ""
            # Add the table as a content item on the appropriate page
            pages = add_page(
                pages=pages, 
                page_no=page_of_item(item),
                item_dict={
                    "id": item_id,
                    "parent_section_id": current_section_id,
                    "label": label.value,
                    "type": "table",
                    "content": md_table,
                    "header_level": None,
                }
            )
            continue

        # For all other labels...
        text_content = ""
        # Try to get the text content
        if hasattr(item, "text") and item.text:
            text_content = item.text
        # If there is no direct .text, but the item supports export_to_markdown, try that as a fallback
        elif hasattr(item, "export_to_markdown"):
            try:
                text_content = item.export_to_markdown(doc=doc)
            # If export fails, skip the item
            except Exception:
                print(f"Warning: Failed to interpret item {label} on page {page_of_item(item)}. Skipping.")
                pass

        # Skip items with no text content
        if not text_content:
            item_id -= 1  # revert the item_id increment if skipping the item
            continue

        # Build a dict for this content item
        item_dict = {
            "id": item_id,
            "parent_section_id": current_parent_id(section_stack),
            "label": label.value,
            "type": "text",
            "content": text_content,
            "header_level": None,
        }

        # If the item has a .level attribute (e.g. for section headers), include that in the item dict
        # Also fix the parent_section_id for the section headers, based on the level
        # NOTE: Level is inferred by Docling based on font size, etc., but is not guaranteed to be present or accurate.
        # Update this after building the item dict, so the section header's parent is the previous section.
        if label == DocItemLabel.SECTION_HEADER:
            # Get the level if it exists, otherwise None
            level = getattr(item, "level", None)
            item_dict["header_level"] = level

            if level is not None:
                # Pop all sections at the same or deeper level off the stack, since they are siblings or children
                while section_stack and section_stack[-1][1] >= level:
                    section_stack.pop()
                # Parent is now whatever is on top of the stack
                item_dict["parent_section_id"] = current_parent_id(section_stack)
                # Push this header onto the stack
                section_stack.append((item_id, level))
            else:
                # When there is no level info, treat as child of current top of stack
                # Also set the section level to inf so it does not pop any future headers off the stack until we hit another header with a level
                item_dict["parent_section_id"] = current_parent_id(section_stack)
                section_stack.append((item_id, float("inf")))

            # Update the current_section_id to this new section header's ID
            current_section_id = item_id

        # Add the text item to the appropriate page
        pages = add_page(
            pages=pages,
            page_no=page_of_item(item),
            item_dict=item_dict
        )

    # Sort the pages by page number and convert to a list of dicts
    sorted_pages = [
        {
            "page": page_no,
            "items": items,
        }
        for page_no, items in sorted(pages.items())
    ]

    # Prepare a full text string for the entire document by exporting to Markdown
    full_text = doc.export_to_markdown(strict_text=False)

    # Compile the final output dict
    output = {
        "metadata": {
            "source_file": str(Path(pdf_path).resolve()),
            "total_pages": len(sorted_pages),
        },
        "pages": sorted_pages,
        "full_markdown": full_text,
    }

    # Write the output to a JSON file if a path is provided, otherwise just return the dict
    if output_path is None:
        output_path = str(Path(pdf_path).with_suffix(".json"))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved output to file: {output_path}")
    print(f"Pages processed: {len(sorted_pages)}")

    return output


def get_section_from_json(json_data: dict, section_id: int) -> list[dict] | None:
    """
    Helper function to retrieve a section item from the JSON output by its ID.

    :param json_data: The JSON data dict containing the pages and items.
    :param section_id: The ID of the section to retrieve.

    :return: A list of section item dicts if found, otherwise None.
    """
    pages = json_data.get("pages", [])
    results = [
        item for page in pages for item in page.get("items", []) 
        if item.get("id") == section_id or item.get("parent_section_id") == section_id
    ]
    results = sorted(results, key=lambda x: x.get("id", 0))
    return results if results else None


def export_md(extracted_data: dict, output_path: str | None = None) -> str:
    """
    Helper function to export the full Markdown text from the extracted data dict.

    :param extracted_data: The dict containing the extracted data, including the "full_markdown" key.
    :param output_path: Optional path to write the Markdown output file.

    :return: The full Markdown string extracted from the document.
    """
    full_markdown = extracted_data.get("full_markdown", "")
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_markdown)
        print(f"Saved full Markdown to file: {output_path}")
    return full_markdown


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_extract.py <input.pdf> [output.json]")
        sys.exit(1)

    pdf_in  = sys.argv[1]
    json_out = sys.argv[2] if len(sys.argv) > 2 else None
    md_out = sys.argv[2].replace(".json", ".md") if len(sys.argv) > 2 else None
    output = extract_pdf(pdf_in, json_out)
    _ = export_md(output, md_out)
