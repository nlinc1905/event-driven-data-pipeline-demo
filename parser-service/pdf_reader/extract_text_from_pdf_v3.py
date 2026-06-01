from pathlib import Path
from typing import Any, List

from docling.document_converter import DocumentConverter


def group_sections_by_page(doc: "DoclingDocument") -> dict[int, list[Any]]:
    """
    Group the parsed Docling nodes by page number, resulting in a mapping of 
    page number to a list of sections and content found on each page.

    :param doc: DoclingDocument instance

    :return: A dictionary mapping page numbers to lists of document sections.
    """
    page_map: dict[int, list[Any]] = {}

    for item, _ in doc.iterate_items():
        # Get the provenance information to determine the page number
        prov = getattr(item, "prov", None)
        if prov and len(prov) > 0:
            # Page numbers are in the first indexed item in the provenance information
            page_number = prov[0].page_no
        else:
            print("Warning: No provenance information found for an item. Defaulting to page 1.")
            # Default to page 1 if no provenance information is available
            page_number = 1

        # Append the item to the corresponding page in the page map
        page_map.setdefault(page_number, []).append(item)

    return page_map


def print_section_tree(
    items: list[dict[str, Any]],
    level: int = 0,
) -> None:
    """
    Recursively print extracted hierarchy.
    """
    indent = "  " * level

    for item in items:
        title = item.get("title", "Untitled")
        text = item.get("text", "").strip()

        print(f"{indent}SECTION: {title}")

        if text:
            preview = text[:300].replace("\n", " ")
            print(f"{indent}TEXT: {preview}")

        tables = item.get("tables", [])
        for idx, table in enumerate(tables):
            print(f"{indent}TABLE {idx + 1}:")
            for row in table:
                print(f"{indent}  {row}")

        children = item.get("children", [])
        if children:
            print_section_tree(children, level + 1)


def extract_page_content(
    doc: "DoclingDocument",
    page_map: dict[int, list[Any]],
    source_pdf_name: str,
) -> list[dict[str, Any]]:
    """
    Convert Docling document into a simple hierarchical structure by extracting page content.

    :param doc: DoclingDocument instance
    :param page_map: Dictionary mapping page numbers to lists of document sections
    :param source_pdf_name: Name of the source PDF file

    :return: A list of sections with nested subsections, text, and tables.
    """
    # Hierarchy to store the structured representation of the document
    hierarchy = []

    # Current stack to manage nested sections
    current_stack: List[dict] = []

    # Iterate over the document items and build the hierarchy based on the page map
    # for page_number, items in page_map.items():
    #     breakpoint()


    elements = []
    for item, _ in doc.iterate_items():
        element = {}

        # Get the provenance information to determine the page number
        prov = getattr(item, "prov", None)
        if prov and len(prov) > 0:
            page_number = prov[0].page_no
        else:
            print("Warning: No provenance information found for an item. Defaulting to page 1.")
            page_number = 1
        element["page_number"] = page_number

        # Get the label to determine the type of content (e.g., section header, paragraph, table)
        label = getattr(item, "label", None)
        element["label"] = label if label else ""

        # Get the text content if available
        text = getattr(item, "text", None)
        element["text"] = text if text else ""

        # Get the level for section headers to determine hierarchy
        level = getattr(item, "level", None)
        element["level"] = level if level is not None else 0

        # Get tables if available
        tables = getattr(item, "tables", None)
        element["tables"] = tables if tables else []

        # Append the element to the list of elements
        elements.append(element)

    breakpoint()
    return elements


def main() -> None:

    # Check for the PDF path
    pdf_path = Path("sample.pdf")
    if not pdf_path.exists():
        raise FileNotFoundError(
            "Place a PDF named 'sample.pdf' next to this script."
        )
    source_pdf_name = pdf_path.name

    # Initialize a CPU version of the converter (no GPU dependencies)
    converter = DocumentConverter()

    # Convert the PDF to a DoclingDocument
    result = converter.convert(str(pdf_path))
    doc = result.document

    # Export the Docling doc to a dictionary format
    exported = doc.export_to_dict()

    # Group sections by page
    page_map = group_sections_by_page(doc)
    print(f"{source_pdf_name} has {len(page_map)} pages")
    # page_info = '\n'.join([f'Page {page}: {len(items)} sections' for page, items in page_map.items()])
    # print(f"Page breakdown:\n{page_info}")

    # Iterate through the pages in the page map and process their section content
    for page_number, items in page_map.items():
        print(f"Processing page {page_number} with {len(items)} sections...")
        # Extract content structure from the Docling document
        hierarchy = extract_page_content(
            doc=doc,
            page_map=page_map,
            source_pdf_name=source_pdf_name,
        )
        breakpoint()

    print("\n========== DOCUMENT STRUCTURE ==========\n")
    print_section_tree(hierarchy)

    # ---------------------------------------------
    # Save markdown output too
    # ---------------------------------------------
    markdown_output = doc.export_to_markdown()

    output_path = Path("output.md")
    output_path.write_text(markdown_output, encoding="utf-8")

    print(f"\nSaved markdown output to: {output_path}")


if __name__ == "__main__":
    main()
