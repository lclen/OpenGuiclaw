"""
Property-based tests for core/bootstrap.py packaging fixes.

Tests cover:
- _parse_pkg_name: scoped and plain npm package name parsing
- _is_npm_pkg_installed: directory-based npm package detection
- ensure_data_dirs: idempotent data directory creation
- ensure_config: config.json auto-copy from example
- get_app_base_dir: correct base directory resolution
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers to import bootstrap functions without triggering side effects
# ---------------------------------------------------------------------------

def _import_bootstrap():
    """Import bootstrap module with a fresh _already_run state."""
    import importlib
    import core.bootstrap as bs
    bs._already_run = False  # reset guard so tests are independent
    return bs


# ---------------------------------------------------------------------------
# _parse_pkg_name
# ---------------------------------------------------------------------------

class TestParsePkgName:
    def test_scoped_with_version(self):
        from core.bootstrap import _parse_pkg_name
        assert _parse_pkg_name("@pixiv/three-vrm@2.1.0") == "@pixiv/three-vrm"

    def test_scoped_no_version(self):
        from core.bootstrap import _parse_pkg_name
        assert _parse_pkg_name("@scope/pkg") == "@scope/pkg"

    def test_plain_with_version(self):
        from core.bootstrap import _parse_pkg_name
        assert _parse_pkg_name("agent-browser@0.16.3") == "agent-browser"

    def test_plain_no_version(self):
        from core.bootstrap import _parse_pkg_name
        assert _parse_pkg_name("agent-browser") == "agent-browser"

    @given(
        name=st.from_regex(r"[a-z][a-z0-9\-]{1,20}", fullmatch=True),
        version=st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_plain_pbt_no_at_no_version(self, name, version):
        """For any plain package name, result must not contain '@' and must equal the name part."""
        from core.bootstrap import _parse_pkg_name
        result = _parse_pkg_name(f"{name}@{version}")
        assert "@" not in result
        assert result == name

    @given(
        name=st.from_regex(r"[a-z][a-z0-9\-]{1,20}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_plain_pbt_no_version_unchanged(self, name):
        """Plain package name without version should be returned unchanged."""
        from core.bootstrap import _parse_pkg_name
        assert _parse_pkg_name(name) == name


# ---------------------------------------------------------------------------
# _is_npm_pkg_installed
# ---------------------------------------------------------------------------

class TestIsNpmPkgInstalled:
    def test_plain_installed(self, tmp_path):
        from core.bootstrap import _is_npm_pkg_installed
        (tmp_path / "node_modules" / "agent-browser").mkdir(parents=True)
        assert _is_npm_pkg_installed("agent-browser", str(tmp_path)) is True

    def test_plain_missing(self, tmp_path):
        from core.bootstrap import _is_npm_pkg_installed
        (tmp_path / "node_modules").mkdir()
        assert _is_npm_pkg_installed("agent-browser", str(tmp_path)) is False

    def test_scoped_installed(self, tmp_path):
        from core.bootstrap import _is_npm_pkg_installed
        (tmp_path / "node_modules" / "@pixiv" / "three-vrm").mkdir(parents=True)
        assert _is_npm_pkg_installed("@pixiv/three-vrm", str(tmp_path)) is True

    def test_scoped_missing(self, tmp_path):
        from core.bootstrap import _is_npm_pkg_installed
        (tmp_path / "node_modules" / "@pixiv").mkdir(parents=True)
        assert _is_npm_pkg_installed("@pixiv/three-vrm", str(tmp_path)) is False

    def test_no_node_modules(self, tmp_path):
        from core.bootstrap import _is_npm_pkg_installed
        assert _is_npm_pkg_installed("any-pkg", str(tmp_path)) is False


# ---------------------------------------------------------------------------
# ensure_data_dirs
# ---------------------------------------------------------------------------

REQUIRED_SUBDIRS = [
    "data",
    "data/sessions",
    "data/memory",
    "data/diary",
    "data/journals",
    "data/identities",
    "data/identity",
    "data/plans",
    "data/scheduler",
    "data/screenshots",
    "data/consolidation",
]


class TestEnsureDataDirs:
    def test_creates_all_dirs(self, tmp_path):
        from core.bootstrap import ensure_data_dirs
        with patch("core.bootstrap.get_app_base_dir", return_value=tmp_path):
            ensure_data_dirs()
        for rel in REQUIRED_SUBDIRS:
            target = tmp_path / rel
            assert target.is_dir(), f"Missing: {rel}"
            assert os.access(target, os.W_OK), f"Not writable: {rel}"

    def test_idempotent(self, tmp_path):
        from core.bootstrap import ensure_data_dirs
        with patch("core.bootstrap.get_app_base_dir", return_value=tmp_path):
            ensure_data_dirs()
            ensure_data_dirs()  # second call must not raise
        for rel in REQUIRED_SUBDIRS:
            assert (tmp_path / rel).is_dir()

    @given(st.integers(min_value=2, max_value=5))
    @settings(max_examples=10)
    def test_idempotent_pbt(self, n):
        """Calling ensure_data_dirs n times must always leave all dirs present."""
        from core.bootstrap import ensure_data_dirs
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch("core.bootstrap.get_app_base_dir", return_value=base):
                for _ in range(n):
                    ensure_data_dirs()
            for rel in REQUIRED_SUBDIRS:
                assert (base / rel).is_dir()


# ---------------------------------------------------------------------------
# ensure_config
# ---------------------------------------------------------------------------

class TestEnsureConfig:
    def test_copies_example_when_missing(self, tmp_path):
        from core.bootstrap import ensure_config
        example = tmp_path / "config.json.example"
        example.write_text('{"api_key": ""}', encoding="utf-8")
        with patch("core.bootstrap.get_app_base_dir", return_value=tmp_path):
            ensure_config()
        config = tmp_path / "config.json"
        assert config.exists()
        assert config.read_text(encoding="utf-8") == '{"api_key": ""}'

    def test_no_overwrite_existing(self, tmp_path):
        from core.bootstrap import ensure_config
        example = tmp_path / "config.json.example"
        example.write_text('{"api_key": "example"}', encoding="utf-8")
        config = tmp_path / "config.json"
        config.write_text('{"api_key": "my-real-key"}', encoding="utf-8")
        with patch("core.bootstrap.get_app_base_dir", return_value=tmp_path):
            ensure_config()
        assert config.read_text(encoding="utf-8") == '{"api_key": "my-real-key"}'

    def test_warn_when_both_missing(self, tmp_path, capsys):
        from core.bootstrap import ensure_config
        with patch("core.bootstrap.get_app_base_dir", return_value=tmp_path):
            ensure_config()
        captured = capsys.readouterr()
        assert "WARN" in captured.out


# ---------------------------------------------------------------------------
# get_app_base_dir
# ---------------------------------------------------------------------------

class TestGetAppBaseDir:
    def test_dev_mode_returns_project_root(self):
        from core.bootstrap import get_app_base_dir
        # In dev mode (not frozen), should return the directory containing core/
        base = get_app_base_dir()
        assert (base / "core").is_dir(), f"Expected project root, got: {base}"

    def test_frozen_returns_exe_parent(self, tmp_path):
        from core.bootstrap import get_app_base_dir
        fake_exe = tmp_path / "openGuiclaw.exe"
        fake_exe.touch()
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", str(fake_exe)):
                base = get_app_base_dir()
        assert base == tmp_path
