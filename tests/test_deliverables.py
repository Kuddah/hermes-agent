#!/usr/bin/env python3
"""Unit tests for deliverables tools: document_tool, deck_tool, html_validation, image_search_tool.

Covers:
  - Path sandbox containment (no .. traversal)
  - Unicode normalization for PDF safety
  - Slide naming and index compaction
  - HTML validation (CSS feature detection for DOCX compatibility)
  - Snapshot/restore cycle
  - Extension allowlist enforcement
  - Image search dispatcher routing
  - Toolset registration
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helper: mock agent.file_safety so the tools don't fail on import
# ---------------------------------------------------------------------------

def _mock_file_safety():
    """Return a mock for agent.file_safety that allows all writes."""
    mod = mock.MagicMock()
    mod.is_write_denied = mock.MagicMock(return_value=False)
    return mod


@pytest.fixture(autouse=True)
def _patch_file_safety():
    """Automatically mock agent.file_safety for all tests."""
    import sys
    fake = _mock_file_safety()
    with mock.patch.dict(sys.modules, {"agent": mock.MagicMock(), "agent.file_safety": fake}):
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def deliverables_tmp(tmp_path):
    """Set HERMES_DELIVERABLES_DIR to a temporary directory for test isolation."""
    with mock.patch.dict(os.environ, {"HERMES_DELIVERABLES_DIR": str(tmp_path)}):
        yield tmp_path


# ---------------------------------------------------------------------------
# document_tool tests
# ---------------------------------------------------------------------------

class TestDocumentToolSafeName:
    def test_strips_slashes(self):
        from tools.document_tool import _safe_name
        assert _safe_name("foo/bar\\baz") == "foo_bar_baz"

    def test_strips_leading_trailing_whitespace(self):
        from tools.document_tool import _safe_name
        assert _safe_name("  hello  ") == "hello"


class TestDocumentToolUnicode:
    def test_smart_quotes_normalized(self):
        from tools.document_tool import _normalize_unicode
        text = "\u201cHello\u201d \u2018world\u2019"
        result = _normalize_unicode(text)
        assert "\u201c" not in result
        assert "\u201d" not in result
        assert '"Hello"' in result
        assert "'world'" in result

    def test_em_dash_normalized(self):
        from tools.document_tool import _normalize_unicode
        assert "--" in _normalize_unicode("something\u2014else")

    def test_en_dash_normalized(self):
        from tools.document_tool import _normalize_unicode
        assert "-" in _normalize_unicode("2020\u20132025")

    def test_ellipsis_normalized(self):
        from tools.document_tool import _normalize_unicode
        assert "..." in _normalize_unicode("wait\u2026")


class TestDocumentToolExtensionValidation:
    def test_allowed_extensions_pass(self):
        from tools.document_tool import _validate_extension
        for ext in [".html", ".docx", ".pdf", ".md", ".txt", ".png", ".jpg"]:
            assert _validate_extension(Path(f"test{ext}")) is None

    def test_disallowed_extensions_fail(self):
        from tools.document_tool import _validate_extension
        for ext in [".exe", ".sh", ".py", ".bat", ".js", ".pptx"]:
            result = _validate_extension(Path(f"test{ext}"))
            assert result is not None
            assert "not allowed" in result


class TestDocumentToolSandbox:
    def test_path_traversal_blocked(self, deliverables_tmp):
        from tools.document_tool import _check_write
        evil_path = deliverables_tmp / ".." / ".." / "etc" / "passwd.html"
        result = _check_write(evil_path)
        assert result is not None
        assert "escapes" in result.lower() or "denied" in result.lower()

    def test_valid_path_allowed(self, deliverables_tmp):
        from tools.document_tool import _check_write
        good_path = deliverables_tmp / "myproject" / "documents" / "report.html"
        result = _check_write(good_path)
        # Should pass — path is inside deliverables dir with valid extension
        assert result is None


class TestDocumentToolCreateAndView:
    def test_create_html_document(self, deliverables_tmp):
        from tools.document_tool import document_tool
        result = json.loads(document_tool(
            action="create",
            project="test_project",
            name="my_doc",
            content="<h1>Hello</h1><p>World</p>",
            content_type="html",
        ))
        assert result.get("ok") is True
        assert "source.html" in result.get("path", "")
        p = Path(result["path"])
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "<h1>Hello</h1><p>World</p>"

    def test_view_returns_content(self, deliverables_tmp):
        from tools.document_tool import document_tool
        document_tool(action="create", project="viewtest", name="doc1",
                     content="<h1>Test</h1>", content_type="html")
        result = json.loads(document_tool(action="view", project="viewtest", name="doc1"))
        assert result.get("format") == "html"
        assert "<h1>Test</h1>" in result.get("content", "")

    def test_list_documents(self, deliverables_tmp):
        from tools.document_tool import document_tool
        document_tool(action="create", project="listtest", name="a",
                     content="<p>A</p>", content_type="html")
        document_tool(action="create", project="listtest", name="b",
                     content="<p>B</p>", content_type="html")
        result = json.loads(document_tool(action="list", project="listtest"))
        names = [d["name"] for d in result["documents"]]
        assert "a" in names
        assert "b" in names

    def test_overwrite_creates_snapshot(self, deliverables_tmp):
        from tools.document_tool import document_tool
        document_tool(action="create", project="snaptest", name="doc",
                     content="<p>v1</p>", content_type="html")
        document_tool(action="create", project="snaptest", name="doc",
                     content="<p>v2</p>", content_type="html", overwrite=True)
        # Check snapshot exists
        from tools.document_tool import _get_project_dir
        proj_dir = _get_project_dir("snaptest")
        snapshots = list(proj_dir.glob(".doc.bak.*"))
        assert len(snapshots) >= 1

    def test_html_validation_warnings_on_create(self, deliverables_tmp):
        from tools.document_tool import document_tool
        result = json.loads(document_tool(
            action="create",
            project="flextest",
            name="flex_doc",
            content="<div style='display:flex'><p>Content</p></div>",
            content_type="html",
        ))
        assert result.get("ok") is True
        # Should have DOCX warnings about flex layout
        if "docx_warnings" in result:
            assert "flex" in result["docx_warnings"].lower()


class TestDocumentToolRestore:
    def test_restore_from_snapshot(self, deliverables_tmp):
        from tools.document_tool import document_tool
        document_tool(action="create", project="restore_test", name="doc",
                     content="<p>original</p>", content_type="html")
        document_tool(action="create", project="restore_test", name="doc",
                     content="<p>updated</p>", content_type="html", overwrite=True)
        result = json.loads(document_tool(
            action="restore", project="restore_test", name="doc", snapshot_index=1
        ))
        assert result.get("ok") is True
        view = json.loads(document_tool(action="view", project="restore_test", name="doc"))
        assert "<p>original</p>" in view.get("content", "")


# ---------------------------------------------------------------------------
# deck_tool tests
# ---------------------------------------------------------------------------

class TestDeckToolSlideName:
    def test_slide_name_padding(self):
        from tools.deck_tool import _slide_name
        assert _slide_name(1, "_title", 2) == "slide_01_title.html"
        assert _slide_name(10, "_end", 2) == "slide_10_end.html"
        assert _slide_name(1, "", 3) == "slide_001.html"


class TestDeckToolCreate:
    def test_create_project(self, deliverables_tmp):
        from tools.deck_tool import _create, _get_project_dir
        result = json.loads(_create("test_deck"))
        assert result.get("ok") is True
        proj_dir = _get_project_dir("test_deck")
        assert proj_dir.exists()
        assert (proj_dir / "_theme.css").exists()
        assert (proj_dir / "assets").is_dir()
        assert (proj_dir / "snapshots").is_dir()


class TestDeckToolInsertAndDelete:
    def test_insert_slides(self, deliverables_tmp):
        from tools.deck_tool import _create, _insert_slides, _list
        _create("insert_test")
        result = json.loads(_insert_slides("insert_test", ["Title", "Problem", "Solution"], None))
        assert result.get("ok") is True
        assert len(result["created"]) == 3

        listing = json.loads(_list("insert_test"))
        assert len(listing["slides"]) == 3

    def test_delete_slide_reindexes(self, deliverables_tmp):
        from tools.deck_tool import _create, _insert_slides, _delete_slide, _list
        _create("del_test")
        _insert_slides("del_test", ["A", "B", "C"], None)

        result = json.loads(_delete_slide("del_test", "slide_02_b"))
        assert result.get("ok") is True
        assert result["remaining_slides"] == 2

        listing = json.loads(_list("del_test"))
        indices = [s["index"] for s in listing["slides"]]
        assert indices == [1, 2]  # Should be compacted


class TestDeckToolModifyAndRead:
    def test_modify_and_read_slide(self, deliverables_tmp):
        from tools.deck_tool import _create, _insert_slides, _modify_slide, _read_slide
        _create("rw_test")
        _insert_slides("rw_test", ["Test Slide"], None)

        custom_html = "<!DOCTYPE html><html><body><h1>Custom</h1></body></html>"
        mod = json.loads(_modify_slide("rw_test", "slide_01_test_slide", custom_html))
        assert mod.get("ok") is True

        read = json.loads(_read_slide("rw_test", "slide_01_test_slide"))
        assert "Custom" in read.get("content", "")


# ---------------------------------------------------------------------------
# html_validation tests
# ---------------------------------------------------------------------------

class TestHtmlValidation:
    def test_clean_html_passes(self):
        from tools.html_validation import find_unsupported_html
        issues = find_unsupported_html("<h1>Hello</h1><p>World</p>")
        assert issues == []

    def test_flex_detected(self):
        from tools.html_validation import find_unsupported_html
        issues = find_unsupported_html("<style>.box { display: flex; }</style>")
        assert any("flex" in i for i in issues)

    def test_position_absolute_detected(self):
        from tools.html_validation import find_unsupported_html
        issues = find_unsupported_html("<div style='position: absolute'></div>")
        assert any("positioning" in i.lower() for i in issues)

    def test_pseudo_elements_detected(self):
        from tools.html_validation import find_unsupported_html
        issues = find_unsupported_html("<style>.x::before { content: ''; }</style>")
        assert any("pseudo" in i.lower() for i in issues)

    def test_build_error_message(self):
        from tools.html_validation import build_unsupported_error
        msg = build_unsupported_error(["issue A", "issue B"])
        assert "issue A" in msg
        assert "issue B" in msg
        assert "Warning" in msg


# ---------------------------------------------------------------------------
# image_search_tool tests
# ---------------------------------------------------------------------------

class TestImageSearchToolDispatcher:
    def test_unknown_action_returns_error(self):
        from tools.image_search_tool import image_search_tool
        result = json.loads(image_search_tool(action="unknown"))
        assert "error" in result

    def test_search_without_query_returns_error(self):
        from tools.image_search_tool import image_search_tool
        result = json.loads(image_search_tool(action="search", query=""))
        assert "error" in result

    def test_ensure_raster_non_svg_passthrough(self, tmp_path):
        from tools.image_search_tool import _ensure_raster
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n")
        result = json.loads(_ensure_raster(str(png_file), None))
        assert result.get("ok") is True
        assert result.get("converted") is False

    def test_ensure_raster_missing_file(self):
        from tools.image_search_tool import _ensure_raster
        result = json.loads(_ensure_raster("/nonexistent/file.svg", None))
        assert "error" in result


# ---------------------------------------------------------------------------
# toolsets integration test
# ---------------------------------------------------------------------------

class TestToolsetsDeliverables:
    def test_image_search_toolset_exists(self):
        from toolsets import TOOLSETS
        assert "image_search" in TOOLSETS
        assert "image_search" in TOOLSETS["image_search"]["tools"]

    def test_deliverables_includes_image_search(self):
        from toolsets import TOOLSETS
        assert "image_search" in TOOLSETS["deliverables"]["includes"]

    def test_document_toolset_exists(self):
        from toolsets import TOOLSETS
        assert "document" in TOOLSETS
        assert "document_tool" in TOOLSETS["document"]["tools"]

    def test_deck_toolset_exists(self):
        from toolsets import TOOLSETS
        assert "deck" in TOOLSETS
        assert "deck_create" in TOOLSETS["deck"]["tools"]
        assert "deck_build_pptx" in TOOLSETS["deck"]["tools"]

    def test_core_tools_include_deliverables(self):
        from toolsets import _HERMES_CORE_TOOLS
        assert "document_tool" in _HERMES_CORE_TOOLS
        assert "deck_create" in _HERMES_CORE_TOOLS
        assert "image_search" in _HERMES_CORE_TOOLS
