import os
import subprocess
import sys
from pathlib import Path
from typing import List


def repair(wheel: Path, output_path: Path, lib_path: List[Path], use_sys_paths: bool, verbosity: int = 0) -> None:
    orig_env_path = os.environ["PATH"]
    if not use_sys_paths:
        os.environ["PATH"] = ""

    try:
        args = [
            sys.executable,
            "-m",
            "delvewheel",
            "repair",
            str(wheel),
            "--wheel-dir",
            str(output_path),
            "--no-diagnostic",
        ]

        if lib_path:
            args.extend(
                [
                    "--add-path",
                    os.pathsep.join([str(p) for p in lib_path]),
                ]
            )

        subprocess.check_call(args, env=os.environ)

    finally:
        # Restore os.environ["PATH"]
        if orig_env_path is None:
            if "PATH" in os.environ:
                del os.environ["PATH"]
        else:
            os.environ["PATH"] = orig_env_path
