import argparse
import base64
import csv
import hashlib
import operator
import os
import sys
import tempfile
import zipfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import BinaryIO, List, NoReturn, Set, Tuple
from zipfile import ZipFile, ZipInfo

from packaging.utils import parse_wheel_filename

from .linux.repair import repair as linux_repair
from .macos.repair import repair as macos_repair
from .windows.repair import repair as windows_repair


DEFAULT_MTIME = datetime.fromisoformat("1980-01-01T00:00:00")
# Taken from shutil in 3.8+
COPY_BUFSIZE = 1024 * 1024 if os.name == "nt" else 64 * 1024


def fatal(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("wheel", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("-l", "--lib-dir", type=Path, action="append")

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


def sorted_zip_entries(file: ZipFile) -> List[ZipInfo]:
    # Sort zip entries lexicographically, and place dist-info files at the end as suggested by PEP-427.
    # Filters out the RECORD and DELVEWHEEL files.
    wheel_name = Path(file.filename).name
    dist_name, dist_version, _, _ = parse_wheel_filename(wheel_name)
    dist_info_prefix = f"{dist_name}-{dist_version}.dist-info/"

    skip_files = {
        f"{dist_info_prefix}RECORD",  # Skip the record file; we'll write our own.
        f"{dist_info_prefix}DELVEWHEEL",  # This file contains non-reproducible text.
    }

    dist_info_infos = []
    other_infos = []
    for info in file.infolist():
        if info.filename in skip_files:
            continue
        elif info.filename.startswith(dist_info_prefix):
            dist_info_infos.append(info)
        else:
            other_infos.append(info)

    sort_key = operator.attrgetter("filename")
    return sorted(other_infos, key=sort_key) + sorted(dist_info_infos, key=sort_key)


def copy_and_hash(fsrc: BinaryIO, fdst: BinaryIO) -> Tuple[str, int]:
    # Localize variable access to minimize overhead.
    fsrc_read = fsrc.read
    fdst_write = fdst.write
    hash = hashlib.sha256()
    length = 0
    while True:
        buf = fsrc_read(COPY_BUFSIZE)
        if not buf:
            break
        length += len(buf)
        hash.update(buf)
        fdst_write(buf)
    return (
        "sha256=" + base64.urlsafe_b64encode(hash.digest()).rstrip(b"=").decode("utf-8"),  # PEP 376
        length,
    )


def write_canonical_wheel(
    original_wheel: Path,
    patched_wheel: Path,
    out_dir: Path,
    default_file_mode: int = 0o644,
    default_dir_mode: int = 0o755,
    mtime: datetime = DEFAULT_MTIME,
    compression: int = zipfile.ZIP_DEFLATED,
) -> Path:
    """This function rewrites a wheel in a canonical form.

    * File and directory entries are lexicographically ordered
    * File data is written in the same order as corresponding names
    * All timestamps are set to a constant value

    Because Windows doesn't support posix file modes, we use corresponding modes in the original file if they exist.
    Else we use the default mode.
    """
    out_wheel = out_dir / patched_wheel.name
    dist_name, dist_version, _, _ = parse_wheel_filename(patched_wheel.name)

    with ZipFile(original_wheel) as original_wheel_zip:
        original_modes = {zi.filename: (zi.external_attr >> 16) & 0xFFFF for zi in original_wheel_zip.infolist()}

    mtime_args = mtime.timetuple()[:6]
    with ZipFile(patched_wheel) as patched_wheel_zip, ZipFile(out_wheel, mode="w", compression=compression) as out_wheel_zip:
        records = []
        for patched_info in sorted_zip_entries(patched_wheel_zip):
            out_info = ZipInfo(patched_info.filename, mtime_args)
            if patched_info.is_dir():
                out_info.file_size = 0
                mode = original_modes.get(patched_info.filename, default_dir_mode)
                out_info.external_attr = (mode & 0xFFFF) << 16
                out_info.external_attr |= 0x10  # MS-DOS directory flag
                out_wheel_zip.writestr(out_info, b"")
            else:
                out_info.file_size = patched_info.file_size
                out_info.compress_type = compression
                mode = original_modes.get(patched_info.filename, default_file_mode)
                out_info.external_attr = (mode & 0xFFFF) << 16
                with patched_wheel_zip.open(patched_info) as in_file, out_wheel_zip.open(out_info, "w") as out_file:
                    hash, size = copy_and_hash(in_file, out_file)
                    records.append((patched_info.filename, hash, size))

        # Write a new RECORD file at the end.
        record_name = f"{dist_name}-{dist_version}.dist-info/RECORD"
        out_info = ZipInfo(record_name, mtime_args)
        out_info.compress_type = compression
        mode = original_modes.get(patched_info.filename, default_file_mode)
        out_info.external_attr = (mode & 0xFFFF) << 16

        record_buf = StringIO()
        record_writer = csv.writer(record_buf, delimiter=",", quotechar='"', lineterminator="\n")
        record_writer.writerows(records)
        record_writer.writerow((record_name, "", ""))

        record_bytes = record_buf.getvalue().encode("utf-8")
        record_buf.close()

        out_info.file_size = len(record_bytes)
        with out_wheel_zip.open(out_info, "w") as out_file:
            out_file.write(record_bytes)

    return out_wheel


def main():
    parser = make_parser()
    args = parser.parse_args()

    original_wheel: Path = args.wheel.resolve()
    out_dir: Path = args.output_dir.resolve()
    lib_path: List[Path] = [lp.resolve() for lp in args.lib_dir]

    if not original_wheel.is_file():
        fatal(f"File does not exist: {original_wheel}")

    platforms = get_wheel_platforms(original_wheel)
    if not platforms:
        fatal(f"No platforms detected in wheel name: {original_wheel.name}")

    if len(platforms) > 1:
        fatal(f"Multiple platforms detected in wheel name ({','.join(platforms)}); not sure what to do")

    platform = platforms.pop()
    if platform == "any":
        print("Nothing to do for any wheel")
        return

    fn = {
        "linux": linux_repair,
        "macos": macos_repair,
        "windows": windows_repair,
    }[platform]

    with tempfile.TemporaryDirectory(prefix="repairwheel") as temp_wheel_dir:
        temp_wheel_dir = Path(temp_wheel_dir)
        fn(original_wheel, temp_wheel_dir, lib_path)
        patched_wheel = find_written_wheel(temp_wheel_dir)

        out_dir.mkdir(parents=True, exist_ok=True)
        out_wheel = write_canonical_wheel(original_wheel, patched_wheel, out_dir)

    print("Wrote", out_wheel)


if __name__ == "__main__":
    main()
