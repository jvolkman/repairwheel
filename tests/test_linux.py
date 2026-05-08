"""Tests for Linux-specific repair logic."""

import sys
from pathlib import Path

import pytest

from repairwheel._vendor.auditwheel.libc import Libc
from repairwheel.linux import monkeypatch

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only tests")


class TestPatchLoadLdPaths:
    """Verify the load_ld_paths monkeypatch matches auditwheel's expected signature."""

    def _get_patched_fn(self, lib_paths, use_sys_paths):
        monkeypatch.patch_load_ld_paths(lib_paths, use_sys_paths)
        import repairwheel._vendor.auditwheel.lddtree

        return repairwheel._vendor.auditwheel.lddtree.load_ld_paths

    def test_use_sys_paths_accepts_libc_arg(self):
        """With use_sys_paths=True, load_ld_paths(Libc.GLIBC) must work."""
        load_ld_paths = self._get_patched_fn([], use_sys_paths=True)
        result = load_ld_paths(Libc.GLIBC)
        assert isinstance(result, dict)
        assert "env" in result
        assert "conf" in result
        assert "interp" in result

    def test_no_sys_paths_accepts_libc_arg(self):
        """With use_sys_paths=False, load_ld_paths(Libc.GLIBC) must work."""
        load_ld_paths = self._get_patched_fn([], use_sys_paths=False)
        result = load_ld_paths(Libc.GLIBC)
        assert result == {"env": [], "conf": [], "interp": []}

    def test_no_sys_paths_includes_lib_paths(self):
        """User-provided lib paths appear in the env key."""
        lib_paths = [Path("/fake/lib1"), Path("/fake/lib2")]
        load_ld_paths = self._get_patched_fn(lib_paths, use_sys_paths=False)
        result = load_ld_paths(Libc.GLIBC)
        assert result["env"] == ["/fake/lib1", "/fake/lib2"]
        assert result["conf"] == []
        assert result["interp"] == []

    def test_use_sys_paths_prepends_lib_paths(self):
        """User-provided lib paths are prepended to the env list."""
        lib_paths = [Path("/fake/lib1")]
        load_ld_paths = self._get_patched_fn(lib_paths, use_sys_paths=True)
        result = load_ld_paths(Libc.GLIBC)
        assert result["env"][0] == "/fake/lib1"

    def test_accepts_none_libc(self):
        """load_ld_paths(None) must also work (libc is Optional)."""
        load_ld_paths = self._get_patched_fn([], use_sys_paths=True)
        result = load_ld_paths(None)
        assert isinstance(result, dict)
        assert "env" in result
