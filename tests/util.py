import os
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename


@dataclass
class TestWheel:
    __test__ = False  # Tell pytest to ignore this
    tag: str
    wheel: Path
    lib_dir: Optional[Path] = None


def patch_wheel(wheel: Path, lib_dir: Optional[Path], out_dir: Path, env: Optional[Dict[str, str]] = None) -> None:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "repairwheel",
            str(wheel),
            "--output-dir",
            str(out_dir),
        ]
        + (
            [
                "--lib-dir",
                str(lib_dir),
            ]
            if lib_dir
            else []
        ),
        env=dict(os.environ, **(env or {})),
    )


def get_patched_wheel(testwheel: TestWheel, patched_wheel_area: Path, env: Optional[Dict[str, str]] = None) -> Path:
    out_dir = patched_wheel_area / testwheel.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_wheel(testwheel.wheel, testwheel.lib_dir, out_dir, env)
    files = list(out_dir.glob("*.whl"))
    assert len(files) == 1, f"Found {len(files)} wheels in {out_dir}"
    return files[0]


def _call_new_python(context, *py_args, **kwargs) -> bytes:
    # Copied from stdlib venv module, but this version returns the output.
    env_exec_cmd = context.env_exe
    if sys.platform == "win32":
        real_env_exe = os.path.realpath(context.env_exe)
        if os.path.normcase(real_env_exe) != os.path.normcase(context.env_exe):
            context.env_exec_cmd = real_env_exe

    args = [env_exec_cmd, *py_args]
    kwargs["env"] = env = os.environ.copy()
    env["VIRTUAL_ENV"] = context.env_dir
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    kwargs["cwd"] = context.env_dir
    kwargs["executable"] = env_exec_cmd
    return subprocess.check_output(args, **kwargs)


def is_wheel_compatible(wheel: Path) -> bool:
    _, _, _, wheel_tags = parse_wheel_filename(wheel.name)
    for sys_tag in sys_tags():
        if sys_tag in wheel_tags:
            return True
    return False


def check_wheel_installs_and_runs(wheel: Path) -> None:
    """Returns False if the wheel is not for the current platform."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = venv.EnvBuilder(with_pip=True)
        env.create(tmpdir)
        context = env.ensure_directories(tmpdir)
        _call_new_python(context, "-m", "pip", "install", str(wheel))
        answer = _call_new_python(context, "-c", "from testwheel import testwheel; print(testwheel.get_answer())")
        assert answer.strip() == b"42"
        doc = _call_new_python(context, "-c", "from testwheel import testwheel; print(testwheel.__doc__)")
        assert doc.strip() == b"A test wheel."

    return True
