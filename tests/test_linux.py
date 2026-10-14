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


class TestLinuxRepairSignature:
    def test_repair_accepts_no_exclude(self, monkeypatch, tmp_path):
        import repairwheel._vendor.auditwheel.wheel_abi
        from repairwheel._vendor.auditwheel.error import NonPlatformWheelError
        from repairwheel.linux import repair as linux_repair

        monkeypatch.setattr(linux_repair, "get_machine_from_wheel", lambda w: "x86_64")
        monkeypatch.setattr(linux_repair.monkeypatch, "patch_load_ld_paths", lambda p, s: None)
        monkeypatch.setattr(linux_repair, "_detect_libc_and_musl_policy", lambda w: (None, None))
        monkeypatch.setattr(linux_repair.monkeypatch, "patch_libc_detection", lambda libc, musl: None)

        recorded = {}

        def fake_analyze(libc, arch, wheel_file, exclude, **kwargs):
            recorded["exclude"] = exclude
            raise NonPlatformWheelError("x86_64", [])

        monkeypatch.setattr(repairwheel._vendor.auditwheel.wheel_abi, "analyze_wheel_abi", fake_analyze)

        fake_wheel = tmp_path / "pkg-1.0-cp38-cp38-linux_x86_64.whl"
        # Calling without exclude
        linux_repair.repair(fake_wheel, tmp_path / "out", [], True)
        assert recorded["exclude"] == frozenset()

        # Calling with exclude=None
        linux_repair.repair(fake_wheel, tmp_path / "out", [], True, exclude=None)
        assert recorded["exclude"] == frozenset()

        # Calling with exclude list
        linux_repair.repair(fake_wheel, tmp_path / "out", [], True, exclude=["foo.so"])
        assert recorded["exclude"] == frozenset(["foo.so"])


class TestElfFileAndPatcher:
    """Unit tests for ElfFile, RepairWheelElfPatcher, and fileutil helpers."""

    def test_fileutil_fmove_and_fzero_edge_cases(self, tmp_path: Path):
        from repairwheel.fileutil import fmove, fzero

        path = tmp_path / "data.bin"
        path.write_bytes(b"0123456789abcdef")

        with open(path, "r+b") as fh:
            # No-op cases
            fzero(fh, 4, 0)
            fzero(fh, 4, -5)
            fmove(fh, 2, 2, 8)
            fmove(fh, 0, 4, 0)
            fh.seek(0)
            assert fh.read() == b"0123456789abcdef"

            # Moving past EOF raises EOFError
            with pytest.raises(EOFError):
                fmove(fh, 0, 10, 10)
            with pytest.raises(EOFError):
                fmove(fh, 12, 10, 10)

    def test_patcher_handles_readonly_binary(self, orig_linux_x86_64_wheel, tmp_path: Path):
        import shutil
        import stat
        from repairwheel.linux.patcher import RepairWheelElfPatcher

        so_src = orig_linux_x86_64_wheel.lib_dir / "libtestdep.so"
        so_copy = tmp_path / "libtestdep.so"
        shutil.copyfile(so_src, so_copy)
        so_copy.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        patcher = RepairWheelElfPatcher()
        assert patcher.get_rpath(so_copy) == ""
        patcher.set_soname(so_copy, "libtestdep-patched.so")
        patcher.set_rpath(so_copy, "$ORIGIN/.libs")
        assert patcher.get_rpath(so_copy) == "$ORIGIN/.libs"
        # Permission bits should be restored after patching
        assert (so_copy.stat().st_mode & 0o777) == 0o444

    def test_elffile_remove_versioned_needed(self, orig_linux_x86_64_wheel, tmp_path: Path):
        from repairwheel.linux.elffile import (
            DT_NEEDED,
            DT_VERNEED,
            DT_VERNEEDNUM,
            ElfFile,
            VerneedEntry,
            get_strtab_entry,
            sizeof,
        )

        so_src = orig_linux_x86_64_wheel.lib_dir / "libtestdep.so"
        so_copy = tmp_path / "libtestdep_verneed.so"
        # Repurpose the 14-byte '.debug_aranges' section name in .shstrtab as '.gnu.version_r'
        so_bytes = so_src.read_bytes().replace(b".debug_aranges", b".gnu.version_r", 1)
        so_copy.write_bytes(so_bytes)

        # Populate the .gnu.version_r section and two versioned DT_NEEDED dependencies
        # into ElfFile to exercise partial and complete removal of versioned dependencies.
        with open(so_copy, "r+b") as fh:
            ef = ElfFile(fh)
            verneed_shdr = ef.get_shdr(b".gnu.version_r")
            verneed_shdr.sh_type = 0x6FFFFFFE  # SHT_GNU_verneed
            verneed_shdr.sh_link = ef.shdr_names.index(b".dynstr")
            verneed_shdr.sh_addralign = ef._class.alignment
            ef.dyn.insert(0, ef._class.Dyn(d_tag=DT_NEEDED, d_ptr_or_val=0))
            ef.verneed_entries = [
                VerneedEntry(
                    verneed=ef._class.Verneed(
                        vn_version=1,
                        vn_cnt=1,
                        vn_file=0,
                        vn_aux=sizeof(ef._class.Verneed),
                        vn_next=0,
                    ),
                    vernaux=[
                        ef._class.Vernaux(
                            vna_hash=0x1234,
                            vna_flags=0,
                            vna_other=2,
                            vna_name=0,
                            vna_next=0,
                        )
                    ],
                    verneed_name=b"libfoo.so.1",
                    vernaux_names=[b"FOO_1.0"],
                ),
                VerneedEntry(
                    verneed=ef._class.Verneed(
                        vn_version=1,
                        vn_cnt=1,
                        vn_file=0,
                        vn_aux=sizeof(ef._class.Verneed),
                        vn_next=0,
                    ),
                    vernaux=[
                        ef._class.Vernaux(
                            vna_hash=0x5678,
                            vna_flags=0,
                            vna_other=3,
                            vna_name=0,
                            vna_next=0,
                        )
                    ],
                    verneed_name=b"libbar.so.1",
                    vernaux_names=[b"BAR_1.0"],
                ),
            ]
            ef.rewrite(needed_replacements={b"": b"libfoo.so.1"})

        with open(so_copy, "r+b") as fh:
            ef = ElfFile(fh)
            assert [ve.verneed_name for ve in ef.verneed_entries] == [b"libfoo.so.1", b"libbar.so.1"]

            # Partial removal: remove libfoo.so.1, keeping libbar.so.1
            ef.rewrite(needed_removals={b"libfoo.so.1"})
            assert [ve.verneed_name for ve in ef.verneed_entries] == [b"libbar.so.1"]
            needed = [get_strtab_entry(ef.dynstr, d.d_ptr_or_val) for d in ef.dyn if d.d_tag == DT_NEEDED]
            assert b"libfoo.so.1" not in needed

            # Complete removal of remaining versioned dependency: remove libbar.so.1
            ef.rewrite(needed_removals={b"libbar.so.1"})
            assert ef.verneed_entries == []
            dyn_tags = {d.d_tag for d in ef.dyn}
            assert DT_VERNEED not in dyn_tags
            assert DT_VERNEEDNUM not in dyn_tags

            # Subsequent rewrite should still succeed cleanly and overwrite last PT_LOAD
            ef.rewrite(new_rpath=b"$ORIGIN")
            assert ef.rpath == b"$ORIGIN"

    def test_elffile_remove_versioned_needed_end_to_end(self, tmp_path: Path):
        import shutil
        import subprocess
        from repairwheel.linux.elffile import DT_NEEDED, DT_VERNEED, DT_VERNEEDNUM, DT_VERSYM, ElfFile, get_strtab_entry

        cc = shutil.which("cc") or shutil.which("gcc")
        if not cc:
            pytest.skip("C compiler required for end-to-end versioned DT_NEEDED test")

        # Build libfoo.so.1 with versioned symbol foo@@FOO_1.0
        (tmp_path / "foo.c").write_text("int foo(void) { return 1; }\n")
        (tmp_path / "foo.map").write_text("FOO_1.0 { global: foo; local: *; };\n")
        libfoo = tmp_path / "libfoo.so.1"
        subprocess.check_call(
            [
                cc,
                "-shared",
                "-fPIC",
                "-Wl,-soname,libfoo.so.1",
                f"-Wl,--version-script,{tmp_path / 'foo.map'}",
                "-o",
                str(libfoo),
                str(tmp_path / "foo.c"),
            ]
        )
        (tmp_path / "libfoo.so").symlink_to(libfoo)

        # Build libbar.so.1 with versioned symbol bar@@BAR_1.0
        (tmp_path / "bar.c").write_text("int bar(void) { return 2; }\n")
        (tmp_path / "bar.map").write_text("BAR_1.0 { global: bar; local: *; };\n")
        libbar = tmp_path / "libbar.so.1"
        subprocess.check_call(
            [
                cc,
                "-shared",
                "-fPIC",
                "-Wl,-soname,libbar.so.1",
                f"-Wl,--version-script,{tmp_path / 'bar.map'}",
                "-o",
                str(libbar),
                str(tmp_path / "bar.c"),
            ]
        )
        (tmp_path / "libbar.so").symlink_to(libbar)

        # Build libm2.so with -nostdlib so .gnu.version_r contains only libfoo.so.1 and libbar.so.1
        (tmp_path / "m2.c").write_text(
            "extern int foo(void); extern int bar(void); int call(void) { return foo() * 10 + bar(); }\n"
        )
        libm2 = tmp_path / "libm2.so"
        subprocess.check_call(
            [
                cc,
                "-shared",
                "-fPIC",
                "-nostdlib",
                "-o",
                str(libm2),
                str(tmp_path / "m2.c"),
                f"-L{tmp_path}",
                "-Wl,--no-as-needed",
                "-lfoo",
                "-lbar",
                f"-Wl,-rpath,{tmp_path}",
            ]
        )

        # Identify which of libfoo.so.1 / libbar.so.1 has the highest vna_other index in .gnu.version_r
        with open(libm2, "r+b") as fh:
            ef = ElfFile(fh)
            overall_max_idx = max(vna.vna_other for ve in ef.verneed_entries for vna in ve.vernaux)
            verneed_by_max_idx = sorted(
                (max(vna.vna_other for vna in ve.vernaux), ve.verneed_name)
                for ve in ef.verneed_entries
                if ve.verneed_name in (b"libfoo.so.1", b"libbar.so.1")
            )
            assert len(verneed_by_max_idx) == 2
            highest_idx, highest_lib = verneed_by_max_idx[-1]
            _, lower_lib = verneed_by_max_idx[0]
            assert highest_idx == overall_max_idx

            # Remove the highest-index versioned library (which previously caused ld.so to SIGSEGV)
            ef.rewrite(needed_removals={highest_lib})
            needed = [get_strtab_entry(ef.dynstr, d.d_ptr_or_val) for d in ef.dyn if d.d_tag == DT_NEEDED]
            assert highest_lib not in needed
            assert lower_lib in needed

        # Load in a subprocess with the removed library preloaded via RTLD_GLOBAL
        preload_path = tmp_path / highest_lib.decode()
        check_code = (
            "import ctypes; "
            f"ctypes.CDLL({str(preload_path)!r}, ctypes.RTLD_GLOBAL); "
            f"m = ctypes.CDLL({str(libm2)!r}); "
            "assert m.call() == 12"
        )
        res = subprocess.run([sys.executable, "-c", check_code], capture_output=True, text=True)
        assert res.returncode == 0, f"Loading patched ELF failed (rc={res.returncode}): {res.stderr}"

        # Also remove the remaining versioned dependency and verify verneed is completely emptied
        with open(libm2, "r+b") as fh:
            ef = ElfFile(fh)
            ef.rewrite(needed_removals={lower_lib})
            assert ef.verneed_entries == []
            dyn_tags = {d.d_tag for d in ef.dyn}
            assert DT_VERNEED not in dyn_tags
            assert DT_VERNEEDNUM not in dyn_tags
            assert DT_VERSYM not in dyn_tags

        check_code_both = (
            "import ctypes; "
            f"ctypes.CDLL({str(libfoo)!r}, ctypes.RTLD_GLOBAL); "
            f"ctypes.CDLL({str(libbar)!r}, ctypes.RTLD_GLOBAL); "
            f"m = ctypes.CDLL({str(libm2)!r}); "
            "assert m.call() == 12"
        )
        res2 = subprocess.run([sys.executable, "-c", check_code_both], capture_output=True, text=True)
        assert res2.returncode == 0, f"Loading patched ELF after second removal failed (rc={res2.returncode}): {res2.stderr}"
