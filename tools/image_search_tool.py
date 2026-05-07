#!/usr/bin/env python3
"""
Image Search Tool Module — find royalty-free images for documents and slides.

Supports three providers (whichever API keys are configured):
  - Pexels     (PEXELS_API_KEY)
  - Unsplash   (UNSPLASH_ACCESS_KEY)
  - Pixabay    (PIXABAY_API_KEY)

Returns structured results: URL, thumbnail URL, width, height, license, attribution.

Also provides ensure_raster_image: converts SVG → PNG via cairosvg so that
images can be safely embedded in PPTX/DOCX (which require raster formats).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _search_pexels(query: str, per_page: int, orientation: str) -> list[dict]:
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return []
    params = {"query": query, "per_page": per_page}
    if orientation in ("landscape", "portrait", "square"):
        params["orientation"] = orientation
    try:
        resp = httpx.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params=params, timeout=15,
        )
        resp.raise_for_status()
        return [
            {
                "url": p["src"]["large"],
                "thumbnail": p["src"]["small"],
                "width": p["width"], "height": p["height"],
                "license": "Pexels License (free commercial use)",
                "attribution": f"Photo by {p['photographer']} on Pexels",
                "provider": "pexels",
                "id": str(p["id"]),
            }
            for p in resp.json().get("photos", [])
        ]
    except Exception as exc:
        logger.warning("Pexels search failed: %s", exc)
        return []


def _search_unsplash(query: str, per_page: int, orientation: str) -> list[dict]:
    api_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if not api_key:
        return []
    params = {"query": query, "per_page": per_page, "client_id": api_key}
    if orientation in ("landscape", "portrait", "squarish"):
        params["orientation"] = "squarish" if orientation == "square" else orientation
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params=params, timeout=15,
        )
        resp.raise_for_status()
        return [
            {
                "url": p["urls"]["regular"],
                "thumbnail": p["urls"]["thumb"],
                "width": p["width"], "height": p["height"],
                "license": "Unsplash License (free commercial use)",
                "attribution": f"Photo by {p['user']['name']} on Unsplash",
                "provider": "unsplash",
                "id": p["id"],
            }
            for p in resp.json().get("results", [])
        ]
    except Exception as exc:
        logger.warning("Unsplash search failed: %s", exc)
        return []


def _search_pixabay(query: str, per_page: int, orientation: str) -> list[dict]:
    api_key = os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        return []
    params = {
        "key": api_key, "q": query, "per_page": min(per_page, 200),
        "image_type": "photo", "safesearch": "true",
    }
    if orientation == "landscape":
        params["orientation"] = "horizontal"
    elif orientation == "portrait":
        params["orientation"] = "vertical"
    try:
        resp = httpx.get("https://pixabay.com/api/", params=params, timeout=15)
        resp.raise_for_status()
        return [
            {
                "url": p["largeImageURL"],
                "thumbnail": p["previewURL"],
                "width": p["imageWidth"], "height": p["imageHeight"],
                "license": "Pixabay License (free commercial use)",
                "attribution": f"Image by {p['user']} from Pixabay",
                "provider": "pixabay",
                "id": str(p["id"]),
            }
            for p in resp.json().get("hits", [])
        ]
    except Exception as exc:
        logger.warning("Pixabay search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Ensure raster helper
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    return re.sub(r"[/\\]", "_", name.strip())


def _ensure_raster(input_path: str, output_path: Optional[str]) -> str:
    """Convert SVG → PNG via cairosvg. Non-SVG files are passed through unchanged."""
    p = Path(input_path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {input_path}"})
    if p.suffix.lower() != ".svg":
        return json.dumps({"ok": True, "path": input_path, "converted": False})
    try:
        import cairosvg
        out = Path(output_path) if output_path else p.with_suffix(".png")
        cairosvg.svg2png(url=str(p), write_to=str(out))
        return json.dumps({"ok": True, "path": str(out), "converted": True})
    except ImportError:
        return json.dumps({"error": "cairosvg not installed. Run: pip install 'hermes-agent[deliverables]'"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _download_image(url: str, dest_path: str) -> str:
    """Download a remote image to dest_path. Returns JSON ok/error."""
    from agent.file_safety import is_write_denied
    dest = Path(dest_path)
    if is_write_denied(str(dest)):
        return json.dumps({"error": f"Write denied by security policy: {dest}"})
    # Basic SSRF protection: block private/loopback ranges
    import ipaddress
    import urllib.parse
    try:
        host = urllib.parse.urlparse(url).hostname or ""
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return json.dumps({"error": "SSRF: download from private/loopback addresses is not allowed."})
        except ValueError:
            pass  # hostname, not IP — allow
    except Exception:
        pass
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, follow_redirects=True, timeout=30) as r:
            r.raise_for_status()
            dest.write_bytes(r.read())
        return json.dumps({"ok": True, "path": str(dest), "size_bytes": dest.stat().st_size})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def image_search_tool(action: str, **kwargs) -> str:
    if action == "search":
        query = kwargs.get("query", "").strip()
        if not query:
            return json.dumps({"error": "query is required."})
        per_page = min(int(kwargs.get("per_page", 5)), 20)
        orientation = kwargs.get("orientation", "landscape")
        provider = kwargs.get("provider", "auto")

        results: list[dict] = []
        if provider in ("pexels", "auto"):
            results.extend(_search_pexels(query, per_page, orientation))
        if not results and provider in ("unsplash", "auto"):
            results.extend(_search_unsplash(query, per_page, orientation))
        if not results and provider in ("pixabay", "auto"):
            results.extend(_search_pixabay(query, per_page, orientation))

        if not results:
            configured = []
            if os.environ.get("PEXELS_API_KEY"): configured.append("pexels")
            if os.environ.get("UNSPLASH_ACCESS_KEY"): configured.append("unsplash")
            if os.environ.get("PIXABAY_API_KEY"): configured.append("pixabay")
            if not configured:
                return json.dumps({"error": "No image search API keys configured. Set PEXELS_API_KEY, UNSPLASH_ACCESS_KEY, or PIXABAY_API_KEY."})
            return json.dumps({"results": [], "message": f"No results for '{query}'."})

        return json.dumps({"results": results[:per_page]})

    elif action == "download":
        return _download_image(kwargs.get("url", ""), kwargs.get("dest_path", ""))

    elif action == "ensure_raster":
        return _ensure_raster(kwargs.get("input_path", ""), kwargs.get("output_path"))

    else:
        return json.dumps({"error": f"Unknown action '{action}'. Use: search, download, ensure_raster"})


def check_image_search_requirements() -> bool:
    return bool(
        os.environ.get("PEXELS_API_KEY") or
        os.environ.get("UNSPLASH_ACCESS_KEY") or
        os.environ.get("PIXABAY_API_KEY")
    )


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

IMAGE_SEARCH_SCHEMA = {
    "name": "image_search",
    "description": (
        "Search for royalty-free images (Pexels, Unsplash, Pixabay) and download them for "
        "use in slides and documents. Also converts SVG → PNG for PPTX/DOCX embedding.\n\n"
        "Actions:\n"
        "- **search**: Find images by keyword. Returns URL, thumbnail, license, attribution.\n"
        "- **download**: Download a remote image URL to a local path.\n"
        "- **ensure_raster**: Convert SVG to PNG via cairosvg (required before PPTX embedding).\n\n"
        "Requires: PEXELS_API_KEY, UNSPLASH_ACCESS_KEY, or PIXABAY_API_KEY env var."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "download", "ensure_raster"],
                "description": "Operation to perform.",
            },
            "query": {"type": "string", "description": "Search keywords (for 'search' action)."},
            "per_page": {"type": "integer", "default": 5, "description": "Number of results (max 20)."},
            "orientation": {
                "type": "string", "enum": ["landscape", "portrait", "square"],
                "default": "landscape",
                "description": "Image orientation filter.",
            },
            "provider": {
                "type": "string", "enum": ["auto", "pexels", "unsplash", "pixabay"],
                "default": "auto",
                "description": "Which provider to use. 'auto' tries all configured providers.",
            },
            "url": {"type": "string", "description": "Image URL to download (for 'download' action)."},
            "dest_path": {"type": "string", "description": "Local file path for downloaded image."},
            "input_path": {"type": "string", "description": "Local SVG path to convert (for 'ensure_raster')."},
            "output_path": {"type": "string", "description": "Optional PNG output path for 'ensure_raster'."},
        },
        "required": ["action"],
    },
}


# --- Registry ---
from tools.registry import registry  # noqa: E402

registry.register(
    name="image_search",
    toolset="image_search",
    schema=IMAGE_SEARCH_SCHEMA,
    handler=lambda args, **kw: image_search_tool(
        action=args.get("action", ""),
        query=args.get("query", ""),
        per_page=args.get("per_page", 5),
        orientation=args.get("orientation", "landscape"),
        provider=args.get("provider", "auto"),
        url=args.get("url", ""),
        dest_path=args.get("dest_path", ""),
        input_path=args.get("input_path", ""),
        output_path=args.get("output_path"),
    ),
    check_fn=check_image_search_requirements,
    emoji="🖼️",
)
