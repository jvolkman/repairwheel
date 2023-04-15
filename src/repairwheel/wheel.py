import base64
import csv
import hashlib
import operator
import os
import zipfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import BinaryIO, List, Tuple
from zipfile import ZipFile, ZipInfo

from packaging.utils import parse_wheel_filename


DEFAULT_MTIME = datetime.fromisoformat("1980-01-01T00:00:00")
# Taken from shutil in 3.8+
COPY_BUFSIZE = 1024 * 1024 if os.name == "nt" else 64 * 1024


def _sorted_zip_entries(file: ZipFile) -> List[ZipInfo]:
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


def _copy_and_hash(fsrc: BinaryIO, fdst: BinaryIO) -> Tuple[str, int]:
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
    default_file_mode: int = 0o664,
    default_dir_mode: int = 0o775,
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

    def new_info(filename: str, is_dir: bool = False) -> ZipInfo:
        result = ZipInfo(filename, mtime_args)
        result.create_system = 3  # Always set the create system to be 'unixy'
        result.file_size = 0  # Caller should set this for files
        if is_dir:
            mode = original_modes.get(filename, default_dir_mode)
            result.external_attr = (mode & 0xFFFF) << 16
            result.external_attr |= 0x10  # MS-DOS directory flag
        else:
            result.compress_type = compression
            mode = original_modes.get(filename, default_file_mode)
            result.external_attr = (mode & 0xFFFF) << 16

        return result

    with ZipFile(patched_wheel) as patched_wheel_zip, ZipFile(out_wheel, mode="w", compression=compression) as out_wheel_zip:
        records = []
        for patched_info in _sorted_zip_entries(patched_wheel_zip):
            if patched_info.is_dir():
                out_info = new_info(patched_info.filename, True)
                out_wheel_zip.writestr(out_info, b"")
            else:
                out_info = new_info(patched_info.filename)
                out_info.file_size = patched_info.file_size
                with patched_wheel_zip.open(patched_info) as in_file, out_wheel_zip.open(out_info, "w") as out_file:
                    hash, size = _copy_and_hash(in_file, out_file)
                    records.append((patched_info.filename, hash, size))

        # Write a new RECORD file at the end.
        record_name = f"{dist_name}-{dist_version}.dist-info/RECORD"
        record_info = new_info(record_name)

        record_buf = StringIO(newline="\n")
        record_writer = csv.writer(record_buf, delimiter=",", quotechar='"', lineterminator="\n")
        record_writer.writerows(records)
        record_writer.writerow((record_name, "", ""))

        record_bytes = record_buf.getvalue().encode("utf-8")
        record_buf.close()

        record_info.file_size = len(record_bytes)
        with out_wheel_zip.open(record_info, "w") as record_file:
            record_file.write(record_bytes)

    return out_wheel
