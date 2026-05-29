# file: extract_pdf_hierarchy.py

from pathlib import Path
from typing import Any, List

from docling.document_converter import DocumentConverter


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


def extract_hierarchy(doc) -> list[dict[str, Any]]:
    """
    Convert Docling document into a simple hierarchical structure.

    NOTE:
    This is intentionally lightweight and defensive because
    Docling internals may evolve across versions.
    """

    hierarchy = []

    current_stack: List[dict] = []

    # Export to DocTags / structured representation
    exported = doc.export_to_dict()

    body = exported.get("body", [])

    for item in body:
        if not isinstance(item, dict):
            continue
        label = item.get("label")

        # ---------------------------------------------
        # Headings
        # ---------------------------------------------
        if label in ["section_header", "title", "heading"]:
            level = item.get("level", 1)

            node = {
                "title": item.get("text", "Untitled"),
                "text": "",
                "tables": [],
                "children": [],
            }

            while len(current_stack) >= level:
                current_stack.pop()

            if current_stack:
                current_stack[-1]["children"].append(node)
            else:
                hierarchy.append(node)

            current_stack.append(node)

        # ---------------------------------------------
        # Regular text
        # ---------------------------------------------
        elif label in ["text", "paragraph", "list_item"]:
            text = item.get("text", "")

            if current_stack:
                current_stack[-1]["text"] += "\n" + text

        # ---------------------------------------------
        # Tables
        # ---------------------------------------------
        elif label == "table":
            table_rows = []

            data = item.get("data", {})
            grid = data.get("grid", [])

            for row in grid:
                table_rows.append(
                    [cell.get("text", "") for cell in row]
                )

            if current_stack:
                current_stack[-1]["tables"].append(table_rows)

    return hierarchy


def main() -> None:
    pdf_path = Path("sample.pdf")

    if not pdf_path.exists():
        raise FileNotFoundError(
            "Place a PDF named 'sample.pdf' next to this script."
        )

    # ---------------------------------------------
    # Basic CPU-friendly converter
    # ---------------------------------------------
    converter = DocumentConverter()

    result = converter.convert(str(pdf_path))

    # DoclingDocument
    doc = result.document

    # ---------------------------------------------
    # Extract hierarchy
    # ---------------------------------------------
    hierarchy = extract_hierarchy(doc)

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
