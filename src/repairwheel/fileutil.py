import os
from typing import BinaryIO
from typing import IO

BUFSIZE = 8192


def open_create(name: str, flags: int) -> IO:
    return os.open(name, flags | os.O_CREAT)


def fzero(fh: BinaryIO, offset: int, length: int, bufsize: int = BUFSIZE) -> None:
    fh.seek(offset)
    zeros = b"\0" * bufsize
    while length > 0:
        write_size = min(length, bufsize)
        written = fh.write(zeros[:write_size])
        length -= written


def fmove(fh: BinaryIO, dst: int, src: int, length: int, bufsize: int = BUFSIZE) -> None:
    if dst == src:
        return

    buf = bytearray()

    if dst < src:
        while length != 0:
            to_move = min(length, bufsize)
            fh.seek(src)
            buf = fh.read(to_move)
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
            fh.seek(dst + length - to_move)
            written = fh.write(buf)

            length -= written


def round_to_multiple(num: int, multiple: int) -> int:
    return ((num + multiple - 1) // multiple) * multiple
