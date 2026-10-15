from collections.abc import Callable, Generator
from contextlib import contextmanager
import functools
import os
import stat
from typing import Any, BinaryIO, IO

BUFSIZE = 8192


def open_create(name: str, flags: int) -> IO:
    return os.open(name, flags | os.O_CREAT)


@contextmanager
def writable_file(path: str | os.PathLike) -> Generator[None, None, None]:
    orig_mode = os.stat(path).st_mode
    if not (orig_mode & stat.S_IWUSR):
        os.chmod(path, orig_mode | stat.S_IWUSR)
        try:
            yield
        finally:
            os.chmod(path, orig_mode)
    else:
        yield


def ensure_writable[F: Callable[..., Any]](fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(filename: str | os.PathLike, *args: Any, **kwargs: Any) -> Any:
        with writable_file(filename):
            return fn(filename, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def fzero(fh: BinaryIO, offset: int, length: int, bufsize: int = BUFSIZE) -> None:
    if length <= 0:
        return
    fh.seek(offset)
    zeros = b"\0" * bufsize
    while length > 0:
        write_size = min(length, bufsize)
        written = fh.write(zeros[:write_size])
        length -= written


def fmove(fh: BinaryIO, dst: int, src: int, length: int, bufsize: int = BUFSIZE) -> None:
    if dst == src or length <= 0:
        return

    if dst < src:
        while length != 0:
            to_move = min(length, bufsize)
            fh.seek(src)
            buf = fh.read(to_move)
            if len(buf) != to_move:
                raise EOFError("Unexpected EOF while moving file data")
            fh.seek(dst)
            written = fh.write(buf)

            length -= written
            src += written
            dst += written

    else:
        while length != 0:
            to_move = min(length, bufsize)
            fh.seek(src + length - to_move)
            buf = fh.read(to_move)
            if len(buf) != to_move:
                raise EOFError("Unexpected EOF while moving file data")
            fh.seek(dst + length - to_move)
            written = fh.write(buf)

            length -= written


def round_to_multiple(num: int, multiple: int) -> int:
    return ((num + multiple - 1) // multiple) * multiple
