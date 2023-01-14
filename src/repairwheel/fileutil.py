import os
from typing import BinaryIO
from typing import IO

BUFSIZE = 8192


def open_create(name: str, flags: int) -> IO:
    return os.open(name, flags | os.O_CREAT)


def fzero(fh: BinaryIO, offset: int, len: int, bufsize: int = BUFSIZE) -> None:
    fh.seek(offset)
    zeros = b'0' * bufsize
    while len != 0:
        size = min(len, bufsize)
        if size == len:
            fh.write(zeros)
        else:
            fh.write(zeros[:size])
        len -= size


def fmove(fh: BinaryIO, dst: int, src: int, len: int, bufsize: int = BUFSIZE) -> None:
    if dst == src:
        return

    buf = bytearray()

    if dst < src:
        while len != 0:
            size = min(len, bufsize)
            fh.seek(src)
            buf = fh.read(bufsize)
            fh.seek(dst)
            fh.write(buf)

            len -= size
            src += size
            dst += size

    else:
        while len != 0:
            size = min(len, bufsize)
            fh.seek(src + len - size)
            buf = fh.read(size)
            fh.seek(dst + len - size)
            fh.write(buf)

            len -= size


def fcpy(fdst: BinaryIO, dst: int, fsrc: BinaryIO, src: int, len: int, bufsize: int = BUFSIZE) -> None:
    fdst.seek(dst)
    fsrc.seek(src)

    while len != 0:
        size = min(len, bufsize)
        buf = fsrc.read(size)
        fdst.write(buf)

        len -= size
