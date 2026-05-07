"""
HTML validation helpers for document and slide creation.

Adapted from OpenSwarm's docs_agent/tools/utils/html_validation.py.
Used by document_tool.py to catch unsupported HTML/CSS features before
attempting PDF/DOCX export with WeasyPrint (which has a limited CSS subset).

For slides (HTML→PPTX pipeline), these checks are NOT applied because
dom-to-pptx uses the full browser rendering engine and supports all CSS.
"""

from __future__ import annotations

import re
from typing import Iterable, List

try:
    from bs4 import BeautifulSoup as _BS
    _BS_AVAILABLE = True
except ImportError:
    _BS_AVAILABLE = False


# CSS features unsupported by WeasyPrint's DOCX export path
UNSUPPORTED_ISSUES_ORDER = [
    "flex or grid layout (display: flex/grid)",
    "positioning or floats (position/float)",
    "pseudo-elements (::before/::after)",
    "advanced selectors (#id, attribute selectors, sibling combinators, pseudo-classes)",
    "unsupported visual effects (background-image, gradients, box-shadow, border-radius, transform)",
    "unsupported units (em, rem, %, vh, vw)",
]

_ISSUE_TO_PATTERNS = {
    "flex or grid layout (display: flex/grid)": [
        re.compile(r"display\s*:\s*(flex|grid)\b", re.IGNORECASE),
    ],
    "positioning or floats (position/float)": [
        re.compile(r"\bposition\s*:\s*(absolute|relative|fixed|sticky)\b", re.IGNORECASE),
        re.compile(r"\bfloat\s*:\s*(left|right|inline-start|inline-end)\b", re.IGNORECASE),
    ],
    "pseudo-elements (::before/::after)": [
        re.compile(r"::before\b", re.IGNORECASE),
        re.compile(r"::after\b", re.IGNORECASE),
    ],
    "unsupported visual effects (background-image, gradients, box-shadow, border-radius, transform)": [
        re.compile(r"\bbackground-image\s*:", re.IGNORECASE),
        re.compile(r"\bbox-shadow\s*:", re.IGNORECASE),
        re.compile(r"\bborder-radius\s*:", re.IGNORECASE),
        re.compile(r"\btransform\s*:", re.IGNORECASE),
        re.compile(r"gradient\s*\(", re.IGNORECASE),
    ],
    "unsupported units (em, rem, %, vh, vw)": [
        re.compile(r"(-?\d*\.?\d+)\s*(em|rem|%|vh|vw)\b", re.IGNORECASE),
    ],
}


def find_unsupported_html(html_content: str) -> List[str]:
    """Scan HTML for CSS features unsupported by WeasyPrint's DOCX export.

    Returns a list of issue descriptions (empty list = clean).
    Only used for the DOCX export path; PDF via WeasyPrint handles most CSS.
    Silently skips parsing if beautifulsoup4 is not installed.
    """
    if not _BS_AVAILABLE:
        return []

    issues: set[str] = set()
    soup = _BS(html_content, "html.parser")

    for style_tag in soup.find_all("style"):
        css_text = style_tag.get_text() or ""
        _scan_css_text(css_text, issues)
        _scan_css_selectors(css_text, issues)

    for tag in soup.find_all(True):
        inline_style = tag.get("style", "")
        if inline_style:
            _scan_css_text(inline_style, issues)

    return [issue for issue in UNSUPPORTED_ISSUES_ORDER if issue in issues]


def build_unsupported_error(issues: Iterable[str]) -> str:
    details = "\n".join(f"  - {issue}" for issue in issues)
    return (
        "Warning: The HTML contains features that may not render correctly in DOCX export:\n"
        f"{details}\n\n"
        "Consider using the 'pdf' format instead (full CSS support via WeasyPrint), "
        "or simplify the HTML to avoid the listed features."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_css_text(css_text: str, issues: set) -> None:
    for issue, patterns in _ISSUE_TO_PATTERNS.items():
        if issue in issues:
            continue
        if any(pattern.search(css_text) for pattern in patterns):
            issues.add(issue)


def _scan_css_selectors(css_text: str, issues: set) -> None:
    if "advanced selectors (#id, attribute selectors, sibling combinators, pseudo-classes)" in issues:
        return
    for selectors in _iter_selectors(css_text):
        for selector in selectors:
            if _selector_has_unsupported(selector):
                issues.add("advanced selectors (#id, attribute selectors, sibling combinators, pseudo-classes)")
                return


def _iter_selectors(css_text: str) -> Iterable[List[str]]:
    for match in re.finditer(r"([^{]+)\{[^}]*\}", css_text, re.DOTALL):
        selector_text = match.group(1)
        selectors = [s.strip() for s in selector_text.split(",") if s.strip()]
        if selectors:
            yield selectors


def _selector_has_unsupported(selector: str) -> bool:
    if any(token in selector for token in ["#", "[", "]", "+", "~"]):
        return True
    if ":" in selector:
        return True
    return False
