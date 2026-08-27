import os
import re
import zipfile


def is_mangled(filename: str) -> bool:
    """Return True if filename is a name-mangled DLL name, False otherwise."""
    return re.match(r"^[^-]+-[0-9a-f]{32}\.dll$", filename.lower()) is not None


def test_testwheel(patched_windows_x86_64_wheel):
    """Basic repair for the testwheel package"""
    with zipfile.ZipFile(patched_windows_x86_64_wheel) as wheel:
        for info in wheel.infolist():
            if info.filename.startswith("testwheel.libs/"):
                name = os.path.basename(info.filename)
                if name.startswith("testdep-"):
                    assert is_mangled(name), f"{name} is mangled"
                    break
        else:
            raise AssertionError("did not find testdep dll")


def test_exclude_prevents_bundling(orig_windows_x86_64_wheel, tmp_path):
    import subprocess
    import sys

    out_dir = tmp_path / "excluded"
    out_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repairwheel",
            str(orig_windows_x86_64_wheel.wheel),
            "--output-dir",
            str(out_dir),
            "--lib-dir",
            str(orig_windows_x86_64_wheel.lib_dir),
            "--exclude",
            "testdep.dll",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"repairwheel failed:\n{result.stdout}\n{result.stderr}"
    wheels = list(out_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        assert not any("testdep" in name.lower() for name in wheel.namelist())


def test_exclude_glob_prevents_bundling(orig_windows_x86_64_wheel, tmp_path):
    import subprocess
    import sys

    out_dir = tmp_path / "excluded_glob"
    out_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repairwheel",
            str(orig_windows_x86_64_wheel.wheel),
            "--output-dir",
            str(out_dir),
            "--lib-dir",
            str(orig_windows_x86_64_wheel.lib_dir),
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


def test_windows_repair_passes_no_dll(monkeypatch, tmp_path):
    import subprocess
    from repairwheel.windows import repair as win_repair

    recorded_args = []

    def fake_check_call(args, **kwargs):
        recorded_args.append(list(args))

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    fake_wheel = tmp_path / "test-1.0.0-cp310-cp310-win_amd64.whl"
    fake_wheel.write_text("")
    win_repair.repair(
        fake_wheel,
        tmp_path / "out",
        [tmp_path / "lib"],
        use_sys_paths=True,
        exclude=["libfoo.dll", "bar*"],
    )

    assert recorded_args
    cmd = recorded_args[0]
    no_dll_indices = [i for i, arg in enumerate(cmd) if arg == "--no-dll"]
    assert len(no_dll_indices) == 2
    assert cmd[no_dll_indices[0] + 1] == "libfoo.dll"
    assert cmd[no_dll_indices[1] + 1] == "bar*"
