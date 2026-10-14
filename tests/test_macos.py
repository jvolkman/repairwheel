import subprocess
import sys
import zipfile
from pathlib import Path

from repairwheel.macos.repair import make_copy_filt_func


class TestMakeCopyFiltFunc:
    def test_system_libraries_always_filtered(self):
        filt = make_copy_filt_func()
        assert not filt("/usr/lib/libSystem.B.dylib")
        assert not filt("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    def test_normal_library_allowed_by_default(self):
        filt = make_copy_filt_func()
        assert filt("/opt/homebrew/lib/libfoo.dylib")

    def test_exact_name_excluded(self):
        filt = make_copy_filt_func(exclude=["libfoo.dylib"])
        assert not filt("/opt/homebrew/lib/libfoo.dylib")
        assert filt("/opt/homebrew/lib/libbar.dylib")

    def test_glob_name_excluded(self):
        filt = make_copy_filt_func(exclude=["libfoo*.dylib"])
        assert not filt("/opt/homebrew/lib/libfoo.1.dylib")
        assert not filt("/opt/homebrew/lib/libfoo.dylib")
        assert filt("/opt/homebrew/lib/libbar.dylib")

    def test_path_glob_excluded(self):
        filt = make_copy_filt_func(exclude=["/opt/custom/*"])
        assert not filt("/opt/custom/libbar.dylib")
        assert filt("/opt/other/libbar.dylib")


def test_macos_exclude_prevents_bundling(orig_macos_arm64_wheel, tmp_path: Path):
    out_dir = tmp_path / "excluded"
    out_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repairwheel",
            str(orig_macos_arm64_wheel.wheel),
            "--output-dir",
            str(out_dir),
            "--lib-dir",
            str(orig_macos_arm64_wheel.lib_dir),
            "--exclude",
            "libtestdep.dylib",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"repairwheel failed:\n{result.stdout}\n{result.stderr}"
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        assert not any("testdep" in name.lower() for name in wheel.namelist())


def test_macos_exclude_glob_prevents_bundling(orig_macos_arm64_wheel, tmp_path: Path):
    out_dir = tmp_path / "excluded_glob"
    out_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repairwheel",
            str(orig_macos_arm64_wheel.wheel),
            "--output-dir",
            str(out_dir),
            "--lib-dir",
            str(orig_macos_arm64_wheel.lib_dir),
            "--exclude",
            "*testdep*",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"repairwheel failed:\n{result.stdout}\n{result.stderr}"
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        assert not any("testdep" in name.lower() for name in wheel.namelist())


class TestMachoToolsAndSign:
    """Unit tests for machotools and machosign binary patchers."""

    def test_machotools_rpath_and_install_name_ops(self, orig_macos_arm64_wheel, tmp_path: Path):
        import shutil
        import stat
        import pytest
        from repairwheel._vendor.delocate.tools import InstallNameError
        from repairwheel.macos import machotools

        dylib_src = orig_macos_arm64_wheel.lib_dir / "libtestdep.dylib"
        dylib = tmp_path / "libtestdep.dylib"
        shutil.copyfile(dylib_src, dylib)

        # Make read-only to verify @ensure_writable
        dylib.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        # Install ID operations
        orig_ids = machotools._get_install_ids(dylib)
        assert orig_ids == {"": "libtestdep.dylib"}
        machotools.set_install_id(dylib, "@rpath/libtestdep_renamed.dylib")
        assert machotools._get_install_ids(dylib) == {"": "@rpath/libtestdep_renamed.dylib"}
        assert (dylib.stat().st_mode & 0o777) == 0o444

        # RPATH operations
        assert machotools._get_rpaths(dylib) == {"": []}
        machotools.add_rpath(dylib, "@loader_path/.dylibs")
        with pytest.raises(InstallNameError):
            machotools.add_rpath(dylib, "@loader_path/.dylibs")
        machotools.add_rpath(dylib, "/unsanitary/abs/rpath")
        assert machotools._get_rpaths(dylib) == {"": ["@loader_path/.dylibs", "/unsanitary/abs/rpath"]}
        machotools._delete_rpaths(dylib, ["/unsanitary/abs/rpath"])
        assert machotools._get_rpaths(dylib) == {"": ["@loader_path/.dylibs"]}

        # Install name operations and error handling
        with pytest.raises(InstallNameError):
            machotools.set_install_name(dylib, "/nonexistent/lib.dylib", "@loader_path/lib.dylib")

        orig_names = machotools._get_install_names(dylib)[""]
        assert orig_names
        machotools.set_install_name(dylib, orig_names[0], "@loader_path/libSystem.B.dylib")
        assert "@loader_path/libSystem.B.dylib" in machotools._get_install_names(dylib)[""]

    def test_machosign_fat_and_fat64_slice_relocation(self, orig_macos_x86_64_wheel, orig_macos_arm64_wheel, tmp_path: Path):
        import hashlib
        import struct
        from macholib.MachO import MachO
        from macholib.mach_o import FAT_MAGIC, FAT_MAGIC_64, LC_CODE_SIGNATURE, LC_SEGMENT_64, fat_arch, fat_arch64, fat_header
        from repairwheel.fileutil import round_to_multiple
        from repairwheel.macos import machosign, machotools

        x86_bytes = (orig_macos_x86_64_wheel.lib_dir / "libtestdep.dylib").read_bytes()
        arm_bytes = (orig_macos_arm64_wheel.lib_dir / "libtestdep.dylib").read_bytes()
        x86_hdr = MachO(orig_macos_x86_64_wheel.lib_dir / "libtestdep.dylib").headers[0].header
        arm_hdr = MachO(orig_macos_arm64_wheel.lib_dir / "libtestdep.dylib").headers[0].header

        def verify_signatures(path: Path) -> None:
            data = path.read_bytes()
            macho = MachO(path)
            assert len(macho.headers) == 2
            for h in macho.headers:
                off, size = h.offset, h.size
                sl = data[off : off + size]
                cs = [c for lc, c, _ in h.commands if lc.cmd == LC_CODE_SIGNATURE]
                assert cs, "missing LC_CODE_SIGNATURE"
                dataoff, datasize = cs[0].dataoff, cs[0].datasize
                assert dataoff % 16 == 0, f"dataoff {dataoff} not 16-byte aligned"
                assert dataoff + datasize <= size
                le = next(c for lc, c, _ in h.commands if lc.cmd == LC_SEGMENT_64 and c.segname.rstrip(b"\0") == b"__LINKEDIT")
                assert le.fileoff + le.filesize == dataoff + datasize
                sb = sl[dataoff : dataoff + datasize]
                sb_magic, _, count = struct.unpack(">III", sb[:12])
                assert sb_magic == 0xFADE0CC0
                cd_off = None
                for i in range(count):
                    _, o = struct.unpack(">II", sb[12 + 8 * i : 20 + 8 * i])
                    if struct.unpack(">I", sb[o : o + 4])[0] == 0xFADE0C02:
                        cd_off = o
                assert cd_off is not None
                (
                    _,
                    _,
                    _,
                    _,
                    hashoff,
                    _,
                    _,
                    ncode,
                    codelimit,
                    hashsize,
                    _,
                    _,
                    pagesize,
                ) = struct.unpack(">IIIIIIIIIBBBB", sb[cd_off : cd_off + 40])
                assert codelimit == dataoff
                ps = 1 << pagesize
                for p in range(ncode):
                    page = sl[p * ps : min((p + 1) * ps, codelimit)]
                    exp = sb[cd_off + hashoff + p * hashsize : cd_off + hashoff + (p + 1) * hashsize]
                    assert hashlib.sha256(page).digest()[:hashsize] == exp

        for magic, arch_cls in [(FAT_MAGIC, fat_arch), (FAT_MAGIC_64, fat_arch64)]:
            # Test both left-shift (gap=1 with 16K alignment) and right-shift (tight 8B alignment)
            for align_bits, gap in [(14, 1), (3, 0)]:
                fat_path = tmp_path / f"libuniversal_{magic:x}_{align_bits}_{gap}.dylib"
                align_bytes = 1 << align_bits
                off0 = round_to_multiple(8 + 2 * 32, align_bytes)
                off1 = round_to_multiple(off0 + len(x86_bytes), align_bytes) + gap * align_bytes

                fhdr = fat_header(magic=magic, nfat_arch=2, _endian_=">")
                fa0 = arch_cls(
                    cputype=x86_hdr.cputype,
                    cpusubtype=x86_hdr.cpusubtype,
                    offset=off0,
                    size=len(x86_bytes),
                    align=align_bits,
                    _endian_=">",
                )
                fa1 = arch_cls(
                    cputype=arm_hdr.cputype,
                    cpusubtype=arm_hdr.cpusubtype,
                    offset=off1,
                    size=len(arm_bytes),
                    align=align_bits,
                    _endian_=">",
                )

                with open(fat_path, "wb") as f:
                    fhdr.to_fileobj(f)
                    fa0.to_fileobj(f)
                    fa1.to_fileobj(f)
                    f.seek(off0)
                    f.write(x86_bytes)
                    f.seek(off1)
                    f.write(arm_bytes)

                assert machotools.get_archs(fat_path) == frozenset(["x86_64", "arm64"])
                machosign.ad_hoc_sign(fat_path)
                verify_signatures(fat_path)

                # Re-sign and re-verify
                machosign.ad_hoc_sign(fat_path)
                verify_signatures(fat_path)
