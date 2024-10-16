import argparse
import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, NoReturn, Set
import glob

from packaging.utils import parse_wheel_filename

from . import __version__
from .linux.repair import repair as linux_repair
from .macos.repair import repair as macos_repair
from .windows.repair import repair as windows_repair
from .wheel import write_canonical_wheel


def fatal(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("wheels", nargs="+", help="wheel file(s) to repair, supports glob patterns)")
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("-l", "--lib-dir", type=Path, action="append")
    parser.add_argument("--no-sys-paths", action="store_true", help="do not search libraries in system paths")
    parser.add_argument("-V", "--version", action="version", version=__version__)

    return parser


def get_wheel_platforms(wheel: Path) -> Set[str]:
    result = set()
    _, _, _, tags = parse_wheel_filename(wheel.name)
    for tag in tags:
        if tag.platform == "any":
            result.add("any")
        elif tag.platform.startswith("linux") or tag.platform.startswith("manylinux"):
            result.add("linux")
        elif tag.platform.startswith("macos"):
            result.add("macos")
        elif tag.platform.startswith("win"):
            result.add("windows")

    return result


def find_written_wheel(wheel_dir: Path) -> Path:
    files = list(wheel_dir.glob("*.whl"))
    if not files:
        fatal("No patched wheels were produced!")
    elif len(files) > 1:
        fatal(f"Multiple patched wheels were produced: {', '.join(f.name for f in files)}")
    return files[0]


def noop_repair(wheel: Path, output_path: Path, _lib_path: List[Path], _use_sys_paths: bool, _verbosity: int = 0) -> None:
    # Simply copy the input wheel to the output directory.
    copied_location = output_path / wheel.name
    shutil.copyfile(wheel, copied_location)


def main():
    parser = make_parser()
    args = parser.parse_args()

    if "SOURCE_DATE_EPOCH" in os.environ:
        try:
            epoch = int(os.environ["SOURCE_DATE_EPOCH"])
            mtime = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
        except ValueError:
            fatal(f"SOURCE_DATE_EPOCH value cannot be parsed as a number: {os.environ['SOURCE_DATE_EPOCH']}")
    else:
        mtime = None

    out_dir: Path = args.output_dir.resolve()
    lib_path: List[Path] = [lp.resolve() for lp in (args.lib_dir or [])]
    use_sys_paths: bool = not args.no_sys_paths

    wheel_files = []
    for wheel_pattern in args.wheels:
        wheel_files.extend(glob.glob(wheel_pattern))

    if not wheel_files:
        fatal("No wheel files found matching the provided patterns.")

    for original_wheel in wheel_files:
        original_wheel = Path(original_wheel).resolve()
        if not original_wheel.is_file():
            fatal(f"File does not exist: {original_wheel}")

        platforms = get_wheel_platforms(original_wheel)
        if not platforms:
            fatal(f"No platforms detected in wheel name: {original_wheel.name}")

        if len(platforms) > 1:
            fatal(f"Multiple platforms detected in wheel name ({','.join(platforms)}); not sure what to do")

        platform = platforms.pop()

        fn = {
            "linux": linux_repair,
            "macos": macos_repair,
            "windows": windows_repair,
            "any": noop_repair,
        }[platform]

        with tempfile.TemporaryDirectory(prefix="repairwheel") as temp_wheel_dir:
            temp_wheel_dir = Path(temp_wheel_dir)
            fn(original_wheel, temp_wheel_dir, lib_path, use_sys_paths)
            patched_wheel = find_written_wheel(temp_wheel_dir)

            out_dir.mkdir(parents=True, exist_ok=True)
            out_wheel = write_canonical_wheel(original_wheel, patched_wheel, out_dir, mtime=mtime)

        print("Wrote", out_wheel)
    print("All wheels repaired. Output directory:", out_dir)


if __name__ == "__main__":
    main()
