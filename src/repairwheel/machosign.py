from dataclasses import dataclass
import logging
import os
from typing import Callable
from typing import FrozenSet
from typing import List
from typing import Optional
from typing import Tuple
from typing import TypeVar
from macholib.MachO import MachO
from macholib.MachO import MachOHeader
from macholib.MachO import lc_str_value
from macholib.mach_o import CPU_TYPE_NAMES
from macholib.mach_o import LC_CODE_SIGNATURE
from macholib.mach_o import LC_LAZY_LOAD_DYLIB
from macholib.mach_o import LC_LOAD_DYLIB
from macholib.mach_o import LC_LOAD_UPWARD_DYLIB
from macholib.mach_o import LC_LOAD_WEAK_DYLIB
from macholib.mach_o import LC_REEXPORT_DYLIB
from macholib.mach_o import LC_RPATH
from macholib.mach_o import get_cpu_subtype
from macholib.ptypes import Structure
from macholib.ptypes import p_int32
from macholib.ptypes import p_int64
from macholib.ptypes import p_long
from macholib.ptypes import p_short
from macholib.ptypes import p_uint8
from macholib.ptypes import p_uint32
from macholib.ptypes import p_uint64
from macholib.ptypes import p_ulong
from macholib.ptypes import pypackable
from macholib.ptypes import sizeof
from macholib.util import fileview

from repairwheel.fileutil import open_create



# https://developer.apple.com/documentation/technotes/tn3126-inside-code-signing-hashes
# https://github.com/thefloweringash/sigtool/blob/main/README.md
# https://github.com/qyang-nj/llios/blob/main/macho_parser/docs/LC_CODE_SIGNATURE.md
# https://medium.com/csit-tech-blog/demystifying-ios-code-signature-309d52c2ff1d

LOG = logging.getLogger(__name__)


CSMAGIC_REQUIREMENT	= 0xfade0c00  # single Requirement blob
CSMAGIC_REQUIREMENTS = 0xfade0c01  # Requirements vector (internal requirements)
CSMAGIC_CODEDIRECTORY = 0xfade0c02  # CodeDirectory blob
CSMAGIC_EMBEDDED_SIGNATURE = 0xfade0cc0  # embedded form of signature data
CSMAGIC_DETACHED_SIGNATURE = 0xfade0cc1  # multi-arch collection of embedded signatures

CSSLOT_CODEDIRECTORY = 0  # slot index for CodeDirectory
CSSLOT_INFOSLOT = 1
CSSLOT_REQUIREMENTS = 2
CSSLOT_RESOURCEDIR = 3
CSSLOT_APPLICATION = 4
CSSLOT_ENTITLEMENTS = 5

class cs_blob_index(Structure):
    _endian_ = ">"
    _fields_ = [
        ("type", p_uint32),  # type of entry
        ("offset", p_uint32),  # offset of entry
    ]

class cs_super_blob(Structure):
    _endian_ = ">"
    _fields_ = [
        ("magic", p_uint32),
        ("length", p_uint32),
        ("count", p_uint32),
    ]

class cs_generic_blob(Structure):
    _endian_ = ">"
    _fields_ = [
        ("magic", p_uint32),
        ("length", p_uint32),
    ]

class cs_code_directory(Structure):
    _endian_ = ">"

    # Fields below marked as ">= version" will be garbage when read from a
    # lower-versioned structure.
    _fields_ = [
        ("magic", p_uint32),  # magic number (CSMAGIC_CODEDIRECTORY)
        ("length", p_uint32),  # total length of CodeDirectory blob
        ("version", p_uint32),  # compatibility version
        ("flags", p_uint32),  # setup and mode flags
        ("hashoffset", p_uint32),  # offset of hash slot element at index zero
        ("identoffset", p_uint32),  # offset of identifier string
        ("nspecialslots", p_uint32),  # number of special hash slots
        ("ncodeslots", p_uint32),  # number of ordinary (code) hash slots
        ("codelimit", p_uint32),  # limit to main image signature range
        ("hashsize", p_uint8),  # size of each hash in bytes
        ("hashtype", p_uint8),  # type of hash (cdHashType* constants)
        ("platform", p_uint8),  # platform identifier; zero if not platform binary
        ("pagesize", p_uint8),  # log2(page size in bytes); 0 => infinite
        ("spare2", p_uint32),  # unused (must be zero)

        # Version >= 0x20100
	    ("scatteroffset", p_uint32),  # offset of optional scatter vector

        # Version >= 0x20200
        ("teamoffset", p_uint32),  # offset of optional team identifier
        
        # Version >= 0x20300
        ("spare3", p_uint32),  # unused (must be zero)
        ("codelimit64", p_uint64),  # limit to main image signature range, 64 bits
        
        # Version >= 0x20400
        ("execsegbase", p_uint64),  # offset of executable segment
        ("execseglimit", p_uint64),  # limit of executable segment
        ("execsegflags", p_uint64),  # executable segment flags
    ]
    # followed by dynamic content as located by offset fields above


@dataclass
class CodeDirectory:
    header: cs_code_directory
    identity: str
    hashes: List[bytes]


def _get_code_directory(filename: str, header: MachOHeader) -> Optional[Tuple[cs_code_directory, int]]:
    for entry in header.commands:
        lc, cmd, _ = entry
        if lc.cmd == LC_CODE_SIGNATURE:
            break
    else:
        # No code signature
        return None

    with open(filename, "rb") as fh:
        fh = fileview(fh, header.offset, header.size)
        fh.seek(cmd.dataoff)
        blob = cs_super_blob.from_fileobj(fh)

        if blob.magic != CSMAGIC_EMBEDDED_SIGNATURE:
            LOG.warning("Unexpected magic %s (expected %s)", hex(blob.magic), hex(CSMAGIC_EMBEDDED_SIGNATURE))
            return None
    
        for _ in range(blob.count):
            blob_index = cs_blob_index.from_fileobj(fh)
            if blob_index.type == CSSLOT_CODEDIRECTORY:
                break
        else:
            # No code directory slot found
            return None

        fh.seek(cmd.dataoff + blob_index.offset)
        blob = cs_code_directory.from_fileobj(fh)
        if blob.magic != CSMAGIC_CODEDIRECTORY:
            LOG.warning("Unexpected magic %s (expected %s)", hex(blob.magic), hex(CSMAGIC_CODEDIRECTORY))
            return None

        return blob, cmd.dataoff + blob_index.offset


def _validate_thin_entry(filename: str, header: MachOHeader) -> bool:
    code_directory_and_offset = _get_code_directory(filename, header)
    if not code_directory_and_offset:
        return False

    code_directory, offset = code_directory
    print(code_directory)

    with open(filename, 'rb') as fh:
        fh = fileview(fh, header.offset, header.size)

        hashes = []
        fh.seek(offset + code_directory.hashoffset)
        for _ in range(code_directory.nspecialslots + code_directory.ncodeslots):
            hashes.append(fh.read())
            

    # for entry in header.commands:
    #     lc, cmd, _ = entry
    #     if lc.cmd == LC_CODE_SIGNATURE:
    #         break
    # else:
    #     # No code signature
    #     return True

    # with open(filename, "rb") as fh:
    #     fh = fileview(fh, header.offset, header.size)
    #     fh.seek(cmd.dataoff)
    #     blob = cs_super_blob.from_fileobj(fh)

    #     if blob.magic != CSMAGIC_EMBEDDED_SIGNATURE:
    #         LOG.warning("Unexpected magic %s (expected %s)", blob.magic, CSMAGIC_EMBEDDED_SIGNATURE)
    #         return False
    
    #     index = []
    #     for _ in range(blob.count):
    #         index.append(cs_blob_index.from_fileobj(fh))

    #     blobs: List[Tuple[cs_generic_blob, bytes]] = []
    #     for blob_index_entry in index:
    #         fh.seek(cmd.dataoff + blob_index_entry.offset)
    #         blob = cs_generic_blob.from_fileobj(fh)
    #         # The specific blob structures also include cs_generic_blob fields, so seek back.
    #         fh.seek(cmd.dataoff + blob_index_entry.offset)
    #         data = fh.read(blob.length)
    #         blobs.append((blob, data))

    #     # Should be:
    #     # CSMAGIC_CODEDIRECTORY, CSMAGIC_REQUIREMENTS, CSMAGIC_BLOBWRAPPER
    #     print(list(hex(blob.magic) for blob, _ in blobs))

    #     for blob, data in blobs:
    #         print(blob, data)
    #         if blob.magic == CSMAGIC_CODEDIRECTORY:
    #             dir = cs_code_directory.from_str(data[:sizeof(cs_code_directory)])
    #             print(dir)
    #             print(hex(dir.magic))

    return True

def _do_validate_signature(filename: str) -> bool:
    macho = MachO(filename)
    for header in macho.headers:
        if not _validate_thin_entry(filename, header):
            return False
    
    return True


def ad_hoc_sign(filename: str) -> None:
    macho = MachO(filename)
    with open(filename, 'r+', opener=open_create) as fh:
        fh.seek(0)
        if macho.fat:
            # MachO doesn't hold on to the FAT specifics, so we read them again



def validate_signature(filename: str) -> None:
    """Remove invalid signatures from a binary file

    If the file signature is missing or valid then it will be ignored

    Invalid signatures are replaced with an ad-hoc signature.  This is the
    closest you can get to removing a signature on MacOS

    Parameters
    ----------
    filename : str
        Filepath to a binary file
    """
    raise NotImplementedError
