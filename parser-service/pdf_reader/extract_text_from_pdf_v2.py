# file: extract_pdf_hierarchy.py

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List

from docling.document_converter import DocumentConverter


OUTPUT_DIR = Path("output")
TABLE_DIR = OUTPUT_DIR / "tables"

OUTPUT_DIR.mkdir(exist_ok=True)
TABLE_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------
def build_section_metadata(
    title: str,
    heading_level: int,
    page_number: int | None,
    table_ids: list[str],
    source_pdf: str,
) -> dict[str, Any]:
    return {
        "section_title": title,
        "heading_level": heading_level,
        "page_number": page_number,
        "table_ids": table_ids,
        "source_pdf": source_pdf,
    }

# =========================================================
# HTML Table Export
# =========================================================
def table_to_html(table_node, table_id: str) -> str:
    """
    Convert native Docling table node into HTML.
    """

    rows = []

    # -----------------------------------------------------
    # Docling table structure varies by version
    # so stay defensive here.
    # -----------------------------------------------------
    data = getattr(table_node, "data", None)

    if data and hasattr(data, "grid"):

        for row in data.grid:

            row_cells = []

            for cell in row:
                text = getattr(cell, "text", "")
                row_cells.append(text)

            rows.append(row_cells)

    html = ["<table border='1'>"]

    for row in rows:
        html.append("<tr>")

        for cell in row:
            html.append(f"<td>{cell}</td>")

        html.append("</tr>")

    html.append("</table>")

    html_text = "\n".join(html)

    output_path = TABLE_DIR / f"{table_id}.html"

    output_path.write_text(
        html_text,
        encoding="utf-8",
    )

    return html_text


# =========================================================
# Page grouping
# =========================================================
def group_items_by_page(doc) -> dict[int, list[Any]]:
    """
    Group native Docling nodes by page number.
    """

    page_map: dict[int, list[Any]] = {}

    # -----------------------------------------------------
    # Iterate native Docling document nodes
    # -----------------------------------------------------
    for item, _level in doc.iterate_items():

        prov = getattr(item, "prov", None)

        if prov and len(prov) > 0:
            page_number = prov[0].page_no
        else:
            page_number = 1

        page_map.setdefault(page_number, []).append(item)

    return page_map


# =========================================================
# Page processing
# =========================================================
def process_page_items(
    items: list[Any],
    source_pdf: str,
    page_number: int,
) -> list[dict[str, Any]]:

    sections = []
    current_stack: List[dict] = []

    table_counter = 0

    for item in items:

        label = getattr(item, "label", None)

        # -------------------------------------------------
        # Section headings
        # -------------------------------------------------
        if str(label).lower() in [
            "section_header",
            "heading",
            "title",
        ]:

            heading_level = getattr(
                item,
                "level",
                1,
            )

            title = getattr(
                item,
                "text",
                "Untitled",
            )

            node = {
                "metadata": build_section_metadata(
                    title=title,
                    heading_level=heading_level,
                    page_number=page_number,
                    table_ids=[],
                    source_pdf=source_pdf,
                ),
                "text": "",
                "tables": [],
                "children": [],
            }

            while len(current_stack) >= heading_level:
                current_stack.pop()

            if current_stack:
                current_stack[-1]["children"].append(node)
            else:
                sections.append(node)

            current_stack.append(node)

        # -------------------------------------------------
        # Paragraph text
        # -------------------------------------------------
        elif str(label).lower() in [
            "text",
            "paragraph",
            "list_item",
        ]:

            text = getattr(item, "text", "")

            if current_stack:
                current_stack[-1]["text"] += (
                    "\n" + text
                )

        # -------------------------------------------------
        # Tables
        # -------------------------------------------------
        elif str(label).lower() == "table":

            table_counter += 1

            table_id = (
                f"page_{page_number}"
                f"_table_{table_counter}"
            )

            html_table = table_to_html(
                item,
                table_id,
            )

            if current_stack:

                current_stack[-1]["tables"].append(
                    {
                        "table_id": table_id,
                        "html": html_table,
                    }
                )

                current_stack[-1]["metadata"][
                    "table_ids"
                ].append(table_id)

    return sections


# =========================================================
# Markdown rendering
# =========================================================
def render_markdown(
    sections: list[dict[str, Any]],
) -> str:

    markdown = []

    for section in sections:

        metadata = section["metadata"]

        heading = "#" * max(
            1,
            metadata["heading_level"],
        )

        markdown.append(
            f"{heading} "
            f"{metadata['section_title']}"
        )

        markdown.append("")

        markdown.append("```json")

        markdown.append(
            json.dumps(
                metadata,
                indent=2,
            )
        )

        markdown.append("```")

        markdown.append("")

        markdown.append(
            section["text"].strip()
        )

        markdown.append("")

        for table in section["tables"]:

            markdown.append(
                f"<!-- TABLE: "
                f"{table['table_id']} -->"
            )

            markdown.append(
                table["html"]
            )

            markdown.append("")

        if section["children"]:

            markdown.append(
                render_markdown(
                    section["children"]
                )
            )

    return "\n".join(markdown)


# =========================================================
# Main
# =========================================================
def main() -> None:

    pdf_path = Path("sample.pdf")

    if not pdf_path.exists():
        raise FileNotFoundError(
            "Place sample.pdf next to this script."
        )

    # -----------------------------------------------------
    # Native Docling conversion
    # -----------------------------------------------------
    converter = DocumentConverter()

    result = converter.convert(
        str(pdf_path)
    )

    doc = result.document

    # -----------------------------------------------------
    # Native tree traversal
    # -----------------------------------------------------
    page_map = group_items_by_page(doc)

    # -----------------------------------------------------
    # Parallel page processing
    # -----------------------------------------------------
    all_sections = []

    with ThreadPoolExecutor() as executor:

        futures = []

        for (
            page_number,
            items,
        ) in page_map.items():

            futures.append(
                executor.submit(
                    process_page_items,
                    items,
                    pdf_path.name,
                    page_number,
                )
            )

        for future in futures:
            all_sections.extend(
                future.result()
            )

    # -----------------------------------------------------
    # Save structured JSON
    # -----------------------------------------------------
    json_path = (
        OUTPUT_DIR
        / "document_structure.json"
    )

    json_path.write_text(
        json.dumps(
            all_sections,
            indent=2,
        ),
        encoding="utf-8",
    )

    # -----------------------------------------------------
    # Save markdown
    # -----------------------------------------------------
    markdown = render_markdown(
        all_sections
    )

    markdown_path = (
        OUTPUT_DIR
        / "document.md"
    )

    markdown_path.write_text(
        markdown,
        encoding="utf-8",
    )

    print(
        f"Saved markdown: "
        f"{markdown_path}"
    )

    print(
        f"Saved JSON: "
        f"{json_path}"
    )

    print(
        f"Saved tables: "
        f"{TABLE_DIR}"
    )


if __name__ == "__main__":
    main()
