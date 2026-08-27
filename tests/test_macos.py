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
