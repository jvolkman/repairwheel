"""Tests for Linux-specific repair logic."""

import sys
from pathlib import Path

import pytest

from repairwheel._vendor.auditwheel.libc import Libc
from repairwheel.linux import monkeypatch
from repairwheel.linux.repair import _detect_libc_and_musl_policy, _parse_platform_for_libc

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


class TestParsePlatformForLibc:
    """Unit tests for _parse_platform_for_libc."""

    def test_musllinux_1_1(self):
        result = _parse_platform_for_libc("musllinux_1_1_x86_64")
        assert result == (Libc.MUSL, "musllinux_1_1")

    def test_musllinux_1_2(self):
        result = _parse_platform_for_libc("musllinux_1_2_aarch64")
        assert result == (Libc.MUSL, "musllinux_1_2")

    def test_manylinux_2_17(self):
        result = _parse_platform_for_libc("manylinux_2_17_x86_64")
        assert result == (Libc.GLIBC, None)

    def test_manylinux2014(self):
        result = _parse_platform_for_libc("manylinux2014_x86_64")
        assert result == (Libc.GLIBC, None)

    def test_linux_plain(self):
        result = _parse_platform_for_libc("linux_x86_64")
        assert result is None

    def test_empty_string(self):
        result = _parse_platform_for_libc("")
        assert result is None


class TestDetectLibcAndMuslPolicy:
    """Unit tests for _detect_libc_and_musl_policy."""

    def test_auditwheel_plat_musllinux(self, monkeypatch):
        """AUDITWHEEL_PLAT=musllinux_1_2_x86_64 should detect MUSL."""
        monkeypatch.setenv("AUDITWHEEL_PLAT", "musllinux_1_2_x86_64")
        wheel = Path("pkg-1.0-cp38-cp38-linux_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.MUSL
        assert musl_policy == "musllinux_1_2"

    def test_auditwheel_plat_manylinux(self, monkeypatch):
        """AUDITWHEEL_PLAT=manylinux_2_17_x86_64 should detect GLIBC."""
        monkeypatch.setenv("AUDITWHEEL_PLAT", "manylinux_2_17_x86_64")
        wheel = Path("pkg-1.0-cp38-cp38-linux_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.GLIBC
        assert musl_policy is None

    def test_wheel_filename_musllinux(self, monkeypatch):
        """Wheel filename with musllinux tag should detect MUSL."""
        monkeypatch.delenv("AUDITWHEEL_PLAT", raising=False)
        wheel = Path("pkg-1.0-cp38-cp38-musllinux_1_1_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.MUSL
        assert musl_policy == "musllinux_1_1"

    def test_wheel_filename_manylinux(self, monkeypatch):
        """Wheel filename with manylinux tag should detect GLIBC."""
        monkeypatch.delenv("AUDITWHEEL_PLAT", raising=False)
        wheel = Path("pkg-1.0-cp38-cp38-manylinux_2_17_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.GLIBC
        assert musl_policy is None

    def test_plain_linux_returns_none(self, monkeypatch):
        """Plain linux_x86_64 wheel with no env var → None (ELF detection)."""
        monkeypatch.delenv("AUDITWHEEL_PLAT", raising=False)
        wheel = Path("pkg-1.0-cp38-cp38-linux_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc is None
        assert musl_policy is None

    def test_auditwheel_plat_takes_priority(self, monkeypatch):
        """AUDITWHEEL_PLAT should override the wheel filename."""
        monkeypatch.setenv("AUDITWHEEL_PLAT", "musllinux_1_2_x86_64")
        wheel = Path("pkg-1.0-cp38-cp38-manylinux_2_17_x86_64.whl")
        libc, musl_policy = _detect_libc_and_musl_policy(wheel)
        assert libc == Libc.MUSL
        assert musl_policy == "musllinux_1_2"


class TestPatchLibcDetection:
    """Verify the libc detection monkeypatch works correctly."""

    def setup_method(self):
        from repairwheel._vendor.auditwheel.policy import WheelPolicies

        self._orig_detect = Libc.detect
        self._orig_wp_init = WheelPolicies.__init__

    def teardown_method(self):
        from repairwheel._vendor.auditwheel.policy import WheelPolicies

        Libc.detect = self._orig_detect
        WheelPolicies.__init__ = self._orig_wp_init

    def test_detect_returns_musl_after_patch(self):
        """After patching, Libc.detect() must return MUSL."""
        monkeypatch.patch_libc_detection(libc=Libc.MUSL, musl_policy=None)
        assert Libc.detect() == Libc.MUSL

    def test_detect_returns_glibc_after_patch(self):
        """After patching with GLIBC, Libc.detect() must return GLIBC."""
        monkeypatch.patch_libc_detection(libc=Libc.GLIBC, musl_policy=None)
        assert Libc.detect() == Libc.GLIBC

    def test_none_defaults_to_musl(self):
        """Patching with libc=None must default detect() to MUSL."""
        monkeypatch.patch_libc_detection(libc=None, musl_policy=None)
        assert Libc.detect() == Libc.MUSL

    def test_wheel_policies_gets_musl_policy(self):
        """After patching with a musl_policy, WheelPolicies should use it."""
        from repairwheel._vendor.auditwheel.architecture import Architecture
        from repairwheel._vendor.auditwheel.policy import WheelPolicies

        monkeypatch.patch_libc_detection(libc=Libc.MUSL, musl_policy="musllinux_1_2")
        policies = WheelPolicies(libc=Libc.MUSL, arch=Architecture("x86_64"))
        # The policy should be musllinux_1_2, not whatever the host has
        assert policies._musl_policy == "musllinux_1_2"


class TestGetWheelPlatforms:
    """Verify get_wheel_platforms recognizes musllinux tags."""

    def test_musllinux_wheel(self, tmp_path):
        """A wheel with a musllinux tag should be recognized as linux."""
        from repairwheel.repair import get_wheel_platforms

        # Create a minimal wheel file with a musllinux tag
        import hashlib
        import zipfile
        from base64 import urlsafe_b64encode

        tag = "cp38-cp38-musllinux_1_2_x86_64"
        dist_info = "pkg-1.0.dist-info"
        metadata = "Metadata-Version: 2.1\nName: pkg\nVersion: 1.0\n"
        wheel_info = f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {tag}\n"

        files = {
            f"{dist_info}/METADATA": metadata.encode(),
            f"{dist_info}/WHEEL": wheel_info.encode(),
        }
        record_path = f"{dist_info}/RECORD"
        records = []
        for fname, data in sorted(files.items()):
            digest = urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            records.append(f"{fname},sha256={digest},{len(data)}")
        records.append(f"{record_path},,")
        files[record_path] = "\n".join(records).encode()

        wheel_path = tmp_path / f"pkg-1.0-{tag}.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            for fname, data in files.items():
                zf.writestr(fname, data)

        platforms = get_wheel_platforms(wheel_path)
        assert "linux" in platforms
