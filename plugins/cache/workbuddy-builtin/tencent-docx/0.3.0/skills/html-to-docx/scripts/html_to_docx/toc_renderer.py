"""toc_renderer.py — Render <nav class="doc-toc"> into a DOCX document.

Hierarchy:
  <ol>/<li>/<a>  → paragraphs with increasing left indent per nesting level
  <a>            → plain text (href stripped)
  data-page      → appended as " ... N"

Indent map: level 1 → 0, level 2 → Cm(0.5), level 3 → Cm(1.0)
"""
from __future__ import annotations

from docx.shared import Cm
from docx import Document


def render_toc(soup_nav, document: Document) -> None:
    """Render TOC nav element into *document* paragraphs."""
    if soup_nav is None:
        return
    # Find the top-level <ol> or <ul>
    root_list = soup_nav.find(["ol", "ul"])
    if root_list is None:
        return
    _render_list(root_list, document, level=1)


def _render_list(list_el, document: Document, level: int) -> None:
    indent_map = {1: None, 2: Cm(0.5), 3: Cm(1.0)}
    indent = indent_map.get(level, Cm(1.0))

    for li in list_el.find_all("li", recursive=False):
        # Extract link text
        a_tag = li.find("a")
        if a_tag:
            text = a_tag.get_text(strip=True)
        else:
            # Take direct text, exclude nested list text
            text_parts = []
            for child in li.children:
                if child.name in ("ol", "ul"):
                    break
                if hasattr(child, "get_text"):
                    text_parts.append(child.get_text(strip=True))
                elif isinstance(child, str):
                    text_parts.append(child.strip())
            text = " ".join(p for p in text_parts if p)

        # Append page number if present
        page = li.get("data-page", "")
        if page:
            text = f"{text} ... {page}"

        para = document.add_paragraph(text)
        if indent is not None:
            para.paragraph_format.left_indent = indent

        # Recurse into nested list
        nested = li.find(["ol", "ul"])
        if nested and level < 3:
            _render_list(nested, document, level + 1)
