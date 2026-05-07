#!/usr/bin/env python3
"""
Deck Tool Module — HTML → PPTX slide deck production.

Provides actions for the full slide creation pipeline:
  deck_create        — Initialise a new presentation project
  deck_insert_slides — Generate blank HTML slide stubs (content added via deck_modify_slide)
  deck_modify_slide  — Write or overwrite a single slide's HTML
  deck_read_slide    — Read a slide's HTML content
  deck_delete_slide  — Remove a slide and re-index remaining slides
  deck_list_slides   — List all slides in a project
  deck_build_pptx    — Convert HTML slides → editable PPTX via dom-to-pptx (Node/Playwright)
  deck_screenshot    — Render a slide to a JPEG via headless Chromium
  deck_check         — QA: detect overflow and basic accessibility issues on a slide
  deck_manage_theme  — Write / update shared CSS theme file for a project

Project layout (under HERMES_DELIVERABLES_DIR, default ./mnt):
  mnt/<project>/presentations/
    slide_01_title.html
    slide_02_overview.html
    _theme.css
    assets/
    snapshots/
    <output>.pptx

All file writes are security-checked via agent.file_safety.is_write_denied().
The html2pptx pipeline requires Node.js + dom-to-pptx (npm install in hermes-agent/).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory helpers (mirrors document_tool pattern)
# ---------------------------------------------------------------------------

_SLIDE_LAYOUTS = {
    "LAYOUT_16x9_1280": {"width": 13.333, "height": 7.5,   "vw": 1280, "vh": 720},
    "LAYOUT_16x9_1920": {"width": 20.0,   "height": 11.25, "vw": 1920, "vh": 1080},
    "LAYOUT_16x9":      {"width": 10.0,   "height": 5.625, "vw": 960,  "vh": 540},
    "LAYOUT_4x3":       {"width": 10.0,   "height": 7.5,   "vw": 960,  "vh": 720},
    "LAYOUT_16x10":     {"width": 10.0,   "height": 6.25,  "vw": 960,  "vh": 625},
}


def _get_deliverables_dir() -> Path:
    raw = os.environ.get("HERMES_DELIVERABLES_DIR", "")
    if raw:
        return Path(raw).expanduser().resolve()
    if Path("/.dockerenv").is_file():
        return Path("/app/mnt")
    return Path.cwd() / "mnt"


def _get_project_dir(project_name: str) -> Path:
    return _get_deliverables_dir() / _safe_name(project_name) / "presentations"


def _safe_name(name: str) -> str:
    return re.sub(r"[/\\]", "_", name.strip())


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _check_write(path: Path) -> Optional[str]:
    from agent.file_safety import is_write_denied
    if is_write_denied(str(path)):
        return f"Write denied by security policy: {path}"
    root = _get_deliverables_dir().resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return f"Path escapes deliverables sandbox: {path}"
    return None


# ---------------------------------------------------------------------------
# Slide file helpers
# ---------------------------------------------------------------------------

def _list_slides(project_dir: Path) -> list[tuple[int, str, Path]]:
    """Return sorted list of (index, suffix, path) for all slide HTML files."""
    pattern = re.compile(r"^slide_(\d+)(.*?)\.html$", re.IGNORECASE)
    slides = []
    for path in project_dir.glob("slide_*.html"):
        m = pattern.match(path.name)
        if m:
            slides.append((int(m.group(1)), m.group(2), path))
    return sorted(slides, key=lambda t: t[0])


def _pad_width(slides: list[tuple], extra: int = 0) -> int:
    max_idx = max((s[0] for s in slides), default=0) + extra
    return max(2, len(str(max_idx or 1)))


def _slide_name(index: int, suffix: str, pad: int) -> str:
    return f"slide_{index:0{pad}d}{suffix}.html"


def _snapshot_slide(slide_path: Path) -> None:
    try:
        snap_dir = slide_path.parent / "snapshots"
        snap_dir.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(slide_path, snap_dir / f"{slide_path.stem}.{ts}.html")
    except Exception:
        pass


def _next_pptx_version(desired: Path) -> Path:
    if not desired.exists():
        return desired
    base = re.sub(r"_v\d+$", "", desired.stem)
    n = 2
    while True:
        candidate = desired.parent / f"{base}_v{n}{desired.suffix}"
        if not candidate.exists():
            return candidate
        n += 1


# ---------------------------------------------------------------------------
# Base HTML template for new slides
# ---------------------------------------------------------------------------

_BASE_SLIDE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1280, height=720" />
  <title>{title}</title>
  <link rel="stylesheet" href="./_theme.css" />
  <style>
    html, body {{
      margin: 0; padding: 0;
      width: 1280px; height: 720px;
      overflow: hidden;
      font-family: var(--font-body, 'Inter', 'Helvetica Neue', sans-serif);
      background: var(--color-bg, #ffffff);
      color: var(--color-text, #1a1a1a);
    }}
    .slide {{
      width: 1280px; height: 720px;
      position: relative;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      padding: 60px;
      box-sizing: border-box;
    }}
  </style>
</head>
<body>
  <div class="slide">
    <h1>{title}</h1>
    <p>{content}</p>
  </div>
</body>
</html>
"""

_BASE_THEME_CSS = """\
/* Hermes Deck Studio — shared theme
   Override these variables per-project to maintain brand consistency. */
:root {
  --color-bg:       #ffffff;
  --color-surface:  #f4f6fb;
  --color-primary:  #2563eb;
  --color-accent:   #f59e0b;
  --color-text:     #1a1a1a;
  --color-muted:    #6b7280;
  --font-heading:   'Inter', 'Helvetica Neue', sans-serif;
  --font-body:      'Inter', 'Helvetica Neue', sans-serif;
  --font-mono:      'JetBrains Mono', 'Fira Code', monospace;
  --radius:         12px;
  --slide-w:        1280px;
  --slide-h:        720px;
}
"""


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------

def _create(project: str) -> str:
    project_dir = _get_project_dir(project)
    err = _check_write(project_dir / ".check")
    if err:
        return json.dumps({"error": err})
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "assets").mkdir(exist_ok=True)
    (project_dir / "snapshots").mkdir(exist_ok=True)
    theme = project_dir / "_theme.css"
    if not theme.exists():
        theme.write_text(_BASE_THEME_CSS, encoding="utf-8")
    return json.dumps({
        "ok": True,
        "project_dir": str(project_dir),
        "hint": "Use deck_insert_slides to add slides, then deck_modify_slide to add content.",
    })


def _insert_slides(project: str, titles: list[str], position: Optional[int]) -> str:
    project_dir = _get_project_dir(project)
    if not project_dir.exists():
        _create(project)

    existing = _list_slides(project_dir)
    insert_at = len(existing) + 1 if position is None else max(1, position)
    pad = _pad_width(existing, extra=len(titles))

    # Re-index slides that come after insertion point
    if existing and insert_at <= len(existing):
        for idx, suffix, path in reversed(existing):
            if idx >= insert_at:
                new_name = _slide_name(idx + len(titles), suffix, pad)
                new_path = project_dir / new_name
                err = _check_write(new_path)
                if err:
                    return json.dumps({"error": err})
                path.rename(new_path)

    created = []
    for i, title in enumerate(titles):
        new_idx = insert_at + i
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:30]
        suffix = f"_{slug}" if slug else ""
        name = _slide_name(new_idx, suffix, pad)
        slide_path = project_dir / name
        err = _check_write(slide_path)
        if err:
            return json.dumps({"error": err})
        slide_path.write_text(
            _BASE_SLIDE_HTML.format(title=title, content="[Add content here]"),
            encoding="utf-8",
        )
        created.append({"index": new_idx, "file": name})

    return json.dumps({"ok": True, "created": created})


def _modify_slide(project: str, slide_name: str, html_content: str) -> str:
    slide_name = slide_name if slide_name.endswith(".html") else f"{slide_name}.html"
    project_dir = _get_project_dir(project)
    slide_path = project_dir / slide_name
    err = _check_write(slide_path)
    if err:
        return json.dumps({"error": err})
    if slide_path.exists():
        _snapshot_slide(slide_path)
    project_dir.mkdir(parents=True, exist_ok=True)
    slide_path.write_text(html_content, encoding="utf-8")
    return json.dumps({"ok": True, "file": slide_name, "size_bytes": slide_path.stat().st_size})


def _read_slide(project: str, slide_name: str) -> str:
    slide_name = slide_name if slide_name.endswith(".html") else f"{slide_name}.html"
    slide_path = _get_project_dir(project) / slide_name
    if not slide_path.exists():
        return json.dumps({"error": f"Slide '{slide_name}' not found in project '{project}'."})
    content = slide_path.read_text(encoding="utf-8")
    return json.dumps({
        "file": slide_name, "size_bytes": slide_path.stat().st_size,
        "content": content[:10000] + ("... [truncated]" if len(content) > 10000 else ""),
    })


def _delete_slide(project: str, slide_name: str) -> str:
    slide_name = slide_name if slide_name.endswith(".html") else f"{slide_name}.html"
    project_dir = _get_project_dir(project)
    slide_path = project_dir / slide_name
    if not slide_path.exists():
        return json.dumps({"error": f"Slide '{slide_name}' not found."})
    _snapshot_slide(slide_path)
    slide_path.unlink()
    # Compact numbering
    remaining = _list_slides(project_dir)
    pad = _pad_width(remaining)
    for new_idx, (_, suffix, path) in enumerate(remaining, start=1):
        new_name = _slide_name(new_idx, suffix, pad)
        if path.name != new_name:
            path.rename(project_dir / new_name)
    return json.dumps({"ok": True, "deleted": slide_name, "remaining_slides": len(remaining)})


def _list(project: str) -> str:
    project_dir = _get_project_dir(project)
    if not project_dir.exists():
        return json.dumps({"project": project, "slides": []})
    slides = _list_slides(project_dir)
    pptx_files = [p.name for p in project_dir.glob("*.pptx")]
    return json.dumps({
        "project": project,
        "slides": [{"index": idx, "file": path.name} for idx, _, path in slides],
        "pptx_exports": pptx_files,
        "theme": "_theme.css",
    })


def _build_pptx(project: str, slide_names: list[str], output_filename: str,
                layout: str) -> str:
    if layout not in _SLIDE_LAYOUTS:
        return json.dumps({"error": f"Invalid layout '{layout}'. Choose from: {', '.join(_SLIDE_LAYOUTS)}."})

    project_dir = _get_project_dir(project)
    if not project_dir.exists():
        return json.dumps({"error": f"Project '{project}' not found. Run deck_create first."})

    # Resolve slide paths
    html_paths = []
    for name in slide_names:
        p = project_dir / (name if name.endswith(".html") else f"{name}.html")
        if not p.exists():
            return json.dumps({"error": f"Slide not found: {name}"})
        html_paths.append(str(p))

    if not html_paths:
        return json.dumps({"error": "No slides specified."})

    out_stem = output_filename.replace(".pptx", "")
    output_path = _next_pptx_version(project_dir / f"{out_stem}.pptx")
    err = _check_write(output_path)
    if err:
        return json.dumps({"error": err})

    # Locate html2pptx_runner.js
    runner_js = Path(__file__).parent / "html2pptx_runner.js"
    if not runner_js.exists():
        return json.dumps({"error": f"html2pptx_runner.js not found at {runner_js}. Run Phase 3 setup."})

    node_modules = runner_js.parent.parent / "node_modules"
    if not node_modules.exists():
        return json.dumps({"error": "node_modules not found. Run 'npm install' in hermes-agent/."})

    try:
        # Set isolated Playwright browsers path to avoid conflicts with Python Playwright
        playwright_path = str(runner_js.parent.parent / ".playwright-browsers")
        env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": playwright_path}

        tmp_dir = tempfile.mkdtemp(prefix="hermes_deck_")
        cmd = [
            "node", str(runner_js),
            "--output", str(output_path),
            "--layout", layout,
            "--tmp-dir", tmp_dir,
            "--",
        ] + html_paths

        # Security: run the command through the same approval gate used by
        # terminal_tool.  This ensures blocklisted patterns are caught and
        # the user is prompted in gateway mode before a subprocess executes.
        cmd_str = " ".join(cmd)
        try:
            from tools.approval import check_all_command_guards
            approval = check_all_command_guards(cmd_str, "local")
            if not approval.get("approved", True):
                msg = approval.get("message", "Subprocess blocked by security policy.")
                return json.dumps({"error": msg, "status": "blocked"})
        except ImportError:
            logger.debug("tools.approval unavailable; skipping command guard check")

        kwargs: dict = {
            "capture_output": True, "text": True,
            "timeout": 300, "cwd": str(runner_js.parent.parent), "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        result = subprocess.run(cmd, **kwargs)
        shutil.rmtree(tmp_dir, ignore_errors=True)

        if result.returncode != 0:
            err_msg = result.stderr.strip() or result.stdout.strip()
            return json.dumps({"error": f"html2pptx failed:\n{err_msg}"})

        return json.dumps({
            "ok": True,
            "pptx": str(output_path),
            "size_bytes": output_path.stat().st_size,
            "slides": len(html_paths),
        })
    except Exception as exc:
        logger.error("deck_build_pptx failed: %s", exc, exc_info=True)
        return json.dumps({"error": str(exc)})


def _screenshot(project: str, slide_name: str, output_image: Optional[str],
                layout: str) -> str:
    slide_name = slide_name if slide_name.endswith(".html") else f"{slide_name}.html"
    project_dir = _get_project_dir(project)
    slide_path = project_dir / slide_name
    if not slide_path.exists():
        return json.dumps({"error": f"Slide '{slide_name}' not found."})

    dims = _SLIDE_LAYOUTS.get(layout, _SLIDE_LAYOUTS["LAYOUT_16x9_1280"])
    vw, vh = dims["vw"], dims["vh"]

    if output_image:
        img_path = Path(output_image)
    else:
        img_path = project_dir / f"{slide_path.stem}.jpg"

    err = _check_write(img_path)
    if err:
        return json.dumps({"error": err})

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": vw, "height": vh})
            page.goto(slide_path.resolve().as_uri(), wait_until="networkidle", timeout=20_000)
            page.wait_for_timeout(1000)
            page.screenshot(path=str(img_path), type="jpeg", quality=90, full_page=False)
            browser.close()
        return json.dumps({"ok": True, "screenshot": str(img_path), "size_bytes": img_path.stat().st_size})
    except ImportError:
        return json.dumps({"error": "playwright not available. Run: pip install playwright && playwright install chromium"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _check(project: str, slide_name: str) -> str:
    """QA check: detect text/element overflow and basic issues."""
    slide_name = slide_name if slide_name.endswith(".html") else f"{slide_name}.html"
    project_dir = _get_project_dir(project)
    slide_path = project_dir / slide_name
    if not slide_path.exists():
        return json.dumps({"error": f"Slide '{slide_name}' not found."})

    try:
        from playwright.sync_api import sync_playwright
        overflow_js = """
        () => {
            const issues = [];
            document.querySelectorAll('*').forEach(el => {
                const s = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    if (el.scrollWidth > el.clientWidth + 2)
                        issues.push({type:'overflow-x', el: el.tagName + (el.className ? '.'+el.className.split(' ')[0] : ''), scrollW: el.scrollWidth, clientW: el.clientWidth});
                    if (el.scrollHeight > el.clientHeight + 2)
                        issues.push({type:'overflow-y', el: el.tagName + (el.className ? '.'+el.className.split(' ')[0] : ''), scrollH: el.scrollHeight, clientH: el.clientHeight});
                }
                // Check if element extends past slide bounds
                if (r.right > 1284 || r.bottom > 724)
                    issues.push({type:'out-of-bounds', el: el.tagName, right: Math.round(r.right), bottom: Math.round(r.bottom)});
            });
            return issues.slice(0, 20);
        }
        """
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(slide_path.resolve().as_uri(), wait_until="networkidle", timeout=20_000)
            issues = page.evaluate(overflow_js)
            browser.close()
        status = "pass" if not issues else "fail"
        return json.dumps({"slide": slide_name, "status": status, "issues": issues})
    except ImportError:
        return json.dumps({"error": "playwright not available for slide check."})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _manage_theme(project: str, css_content: str) -> str:
    project_dir = _get_project_dir(project)
    theme_path = project_dir / "_theme.css"
    err = _check_write(theme_path)
    if err:
        return json.dumps({"error": err})
    project_dir.mkdir(parents=True, exist_ok=True)
    if theme_path.exists():
        _snapshot_slide(theme_path)
    theme_path.write_text(css_content, encoding="utf-8")
    return json.dumps({"ok": True, "theme": str(theme_path)})


# ---------------------------------------------------------------------------
# Unified dispatchers
# ---------------------------------------------------------------------------

def _dispatch_create(args: dict) -> str:
    return _create(project=args.get("project", ""))


def _dispatch_insert(args: dict) -> str:
    return _insert_slides(
        project=args.get("project", ""),
        titles=args.get("titles", []),
        position=args.get("position"),
    )


def _dispatch_modify(args: dict) -> str:
    return _modify_slide(args.get("project", ""), args.get("slide_name", ""), args.get("html_content", ""))


def _dispatch_read(args: dict) -> str:
    return _read_slide(args.get("project", ""), args.get("slide_name", ""))


def _dispatch_delete(args: dict) -> str:
    return _delete_slide(args.get("project", ""), args.get("slide_name", ""))


def _dispatch_list(args: dict) -> str:
    return _list(args.get("project", ""))


def _dispatch_build(args: dict) -> str:
    return _build_pptx(
        project=args.get("project", ""),
        slide_names=args.get("slide_names", []),
        output_filename=args.get("output_filename", "presentation"),
        layout=args.get("layout", "LAYOUT_16x9_1280"),
    )


def _dispatch_screenshot(args: dict) -> str:
    return _screenshot(
        project=args.get("project", ""),
        slide_name=args.get("slide_name", ""),
        output_image=args.get("output_image"),
        layout=args.get("layout", "LAYOUT_16x9_1280"),
    )


def _dispatch_check(args: dict) -> str:
    return _check(args.get("project", ""), args.get("slide_name", ""))


def _dispatch_theme(args: dict) -> str:
    return _manage_theme(args.get("project", ""), args.get("css_content", ""))


# =============================================================================
# OpenAI Function-Calling Schemas (one per tool for clarity)
# =============================================================================

_COMMON_PROJECT = {
    "project": {
        "type": "string",
        "description": "Presentation project folder (e.g. 'product_pitch'). Use lowercase_underscores.",
    }
}

DECK_CREATE_SCHEMA = {
    "name": "deck_create",
    "description": "Initialise a new slide deck project. Creates mnt/<project>/presentations/ with a starter _theme.css.",
    "parameters": {"type": "object", "properties": _COMMON_PROJECT, "required": ["project"]},
}

DECK_INSERT_SLIDES_SCHEMA = {
    "name": "deck_insert_slides",
    "description": (
        "Add blank HTML slide stubs to a project. Each title becomes a slide file. "
        "Optionally insert at a specific position (re-indexes existing slides). "
        "Fill content with deck_modify_slide."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "titles": {
                "type": "array", "items": {"type": "string"},
                "description": "Slide titles in order (e.g. ['Title Slide', 'Problem', 'Solution']).",
            },
            "position": {
                "type": "integer",
                "description": "Insert before this 1-based slide index. Omit to append at end.",
            },
        },
        "required": ["project", "titles"],
    },
}

DECK_MODIFY_SLIDE_SCHEMA = {
    "name": "deck_modify_slide",
    "description": (
        "Write full HTML content to a slide. Always use the 1280×720 viewport. "
        "Link <link rel=\"stylesheet\" href=\"./_theme.css\"> for theme variables. "
        "After writing, run deck_check to verify no overflow."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "slide_name": {"type": "string", "description": "Slide filename (e.g. 'slide_01_title')."},
            "html_content": {"type": "string", "description": "Full HTML for the slide (<!DOCTYPE html>…</html>)."},
        },
        "required": ["project", "slide_name", "html_content"],
    },
}

DECK_READ_SLIDE_SCHEMA = {
    "name": "deck_read_slide",
    "description": "Read the HTML content of a single slide.",
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "slide_name": {"type": "string", "description": "Slide filename or stem (e.g. 'slide_01_title')."},
        },
        "required": ["project", "slide_name"],
    },
}

DECK_DELETE_SLIDE_SCHEMA = {
    "name": "deck_delete_slide",
    "description": "Delete a slide and re-index remaining slides.",
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "slide_name": {"type": "string", "description": "Slide filename or stem to delete."},
        },
        "required": ["project", "slide_name"],
    },
}

DECK_LIST_SCHEMA = {
    "name": "deck_list_slides",
    "description": "List all slides and PPTX exports in a project.",
    "parameters": {"type": "object", "properties": _COMMON_PROJECT, "required": ["project"]},
}

DECK_BUILD_PPTX_SCHEMA = {
    "name": "deck_build_pptx",
    "description": (
        "Convert HTML slides to a fully editable PowerPoint file via dom-to-pptx. "
        "Requires Node.js + npm install in hermes-agent/. Output is auto-versioned (my_deck_v2.pptx …)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "slide_names": {
                "type": "array", "items": {"type": "string"},
                "description": "Ordered list of slide names to include (e.g. ['slide_01_title', 'slide_02_problem']).",
            },
            "output_filename": {"type": "string", "description": "Output stem (e.g. 'product_pitch'). Extension added automatically."},
            "layout": {
                "type": "string",
                "enum": ["LAYOUT_16x9_1280", "LAYOUT_16x9_1920", "LAYOUT_16x9", "LAYOUT_4x3", "LAYOUT_16x10"],
                "default": "LAYOUT_16x9_1280",
            },
        },
        "required": ["project", "slide_names", "output_filename"],
    },
}

DECK_SCREENSHOT_SCHEMA = {
    "name": "deck_screenshot",
    "description": "Render a slide to a JPEG image via headless Chromium for visual review.",
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "slide_name": {"type": "string", "description": "Slide filename or stem."},
            "output_image": {"type": "string", "description": "Optional JPEG output path."},
            "layout": {"type": "string", "enum": list(_SLIDE_LAYOUTS), "default": "LAYOUT_16x9_1280"},
        },
        "required": ["project", "slide_name"],
    },
}

DECK_CHECK_SCHEMA = {
    "name": "deck_check",
    "description": (
        "QA check a slide: detect text/element overflow, out-of-bounds elements. "
        "Run after every deck_modify_slide call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "slide_name": {"type": "string", "description": "Slide filename or stem to check."},
        },
        "required": ["project", "slide_name"],
    },
}

DECK_MANAGE_THEME_SCHEMA = {
    "name": "deck_manage_theme",
    "description": (
        "Write or update the shared _theme.css for a project. "
        "All slides link to this file for consistent brand colours and fonts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            **_COMMON_PROJECT,
            "css_content": {"type": "string", "description": "Full CSS content for _theme.css (use CSS variables under :root {})."},
        },
        "required": ["project", "css_content"],
    },
}


def check_deck_requirements() -> bool:
    return True


# =============================================================================
# Registry
# =============================================================================

from tools.registry import registry  # noqa: E402

registry.register(name="deck_create", toolset="deck", schema=DECK_CREATE_SCHEMA,
                  handler=lambda args, **kw: _dispatch_create(args),
                  check_fn=check_deck_requirements, emoji="🗂️")

registry.register(name="deck_insert_slides", toolset="deck", schema=DECK_INSERT_SLIDES_SCHEMA,
                  handler=lambda args, **kw: _dispatch_insert(args),
                  check_fn=check_deck_requirements, emoji="➕")

registry.register(name="deck_modify_slide", toolset="deck", schema=DECK_MODIFY_SLIDE_SCHEMA,
                  handler=lambda args, **kw: _dispatch_modify(args),
                  check_fn=check_deck_requirements, emoji="✏️")

registry.register(name="deck_read_slide", toolset="deck", schema=DECK_READ_SLIDE_SCHEMA,
                  handler=lambda args, **kw: _dispatch_read(args),
                  check_fn=check_deck_requirements, emoji="📖")

registry.register(name="deck_delete_slide", toolset="deck", schema=DECK_DELETE_SLIDE_SCHEMA,
                  handler=lambda args, **kw: _dispatch_delete(args),
                  check_fn=check_deck_requirements, emoji="🗑️")

registry.register(name="deck_list_slides", toolset="deck", schema=DECK_LIST_SCHEMA,
                  handler=lambda args, **kw: _dispatch_list(args),
                  check_fn=check_deck_requirements, emoji="📋")

registry.register(name="deck_build_pptx", toolset="deck", schema=DECK_BUILD_PPTX_SCHEMA,
                  handler=lambda args, **kw: _dispatch_build(args),
                  check_fn=check_deck_requirements, emoji="📊")

registry.register(name="deck_screenshot", toolset="deck", schema=DECK_SCREENSHOT_SCHEMA,
                  handler=lambda args, **kw: _dispatch_screenshot(args),
                  check_fn=check_deck_requirements, emoji="📸")

registry.register(name="deck_check", toolset="deck", schema=DECK_CHECK_SCHEMA,
                  handler=lambda args, **kw: _dispatch_check(args),
                  check_fn=check_deck_requirements, emoji="🔍")

registry.register(name="deck_manage_theme", toolset="deck", schema=DECK_MANAGE_THEME_SCHEMA,
                  handler=lambda args, **kw: _dispatch_theme(args),
                  check_fn=check_deck_requirements, emoji="🎨")
