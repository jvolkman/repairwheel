import dataclasses
import hashlib
import logging
import math
import os.path
import sys
from typing import BinaryIO
from typing import Iterable
from typing import List
from typing import Optional
from typing import Union
from macholib.MachO import MachO
from macholib.MachO import MachOHeader
from macholib.mach_o import FAT_MAGIC
from macholib.mach_o import FAT_MAGIC_64
from macholib.mach_o import LC_CODE_SIGNATURE
from macholib.mach_o import LC_SEGMENT
from macholib.mach_o import LC_SEGMENT_64
from macholib.mach_o import MH_BUNDLE
from macholib.mach_o import MH_DYLIB
from macholib.mach_o import MH_DYLINKER
from macholib.mach_o import MH_EXECUTE
from macholib.mach_o import MH_PRELOAD
from macholib.mach_o import fat_arch
from macholib.mach_o import fat_arch64
from macholib.mach_o import fat_header
from macholib.mach_o import linkedit_data_command
from macholib.mach_o import load_command
from macholib.ptypes import Structure
from macholib.ptypes import p_uint8
from macholib.ptypes import p_uint32
from macholib.ptypes import p_uint64
from macholib.ptypes import sizeof

from ..fileutil import fmove
from ..fileutil import fzero
from ..fileutil import open_create
from ..fileutil import round_to_multiple

# References:
# https://developer.apple.com/documentation/technotes/tn3126-inside-code-signing-hashes
# https://github.com/thefloweringash/sigtool/blob/main/README.md
# https://github.com/qyang-nj/llios/blob/main/macho_parser/docs/LC_CODE_SIGNATURE.md
# https://medium.com/csit-tech-blog/demystifying-ios-code-signature-309d52c2ff1d
# https://github.com/kabiroberai/macho_edit

LOG = logging.getLogger(__name__)

CODE_DIRECTORY_PAGE_SIZE = 4096  # Seems to be what Apple always uses
SHA256_HASH_SIZE = 32

CSMAGIC_REQUIREMENT = 0xFADE0C00  # single Requirement blob
CSMAGIC_REQUIREMENTS = 0xFADE0C01  # Requirements vector (internal requirements)
CSMAGIC_CODEDIRECTORY = 0xFADE0C02  # CodeDirectory blob
CSMAGIC_EMBEDDED_SIGNATURE = 0xFADE0CC0  # embedded form of signature data
CSMAGIC_DETACHED_SIGNATURE = 0xFADE0CC1  # multi-arch collection of embedded signatures
CSMAGIC_BLOBWRAPPER = 0xFADE0B01  # used for the cms blob

CSSLOT_CODEDIRECTORY = 0  # slot index for CodeDirectory
CSSLOT_INFOSLOT = 1
CSSLOT_REQUIREMENTS = 2
CSSLOT_RESOURCEDIR = 3
CSSLOT_APPLICATION = 4
CSSLOT_ENTITLEMENTS = 5
CSSLOT_SIGNATURESLOT = 0x10000

CS_ADHOC = 0x2

CS_HASHTYPE_SHA256 = 2

CS_EXECSEG_MAIN_BINARY = 0x1


class SigningException(Exception):
    pass


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


class cs_requirements_blob(Structure):
    _endian_ = ">"
    _fields_ = [
        ("magic", p_uint32),
        ("length", p_uint32),
        ("data", p_uint32),
    ]


def log2(val: int) -> int:
    return int(math.log2(val))


def iterate_page_hashes(fh: BinaryIO, offset: int, limit: int) -> Iterable[bytes]:
    read_pos = offset
    while read_pos < limit:
        initial_pos = fh.tell()
        page_size = min(CODE_DIRECTORY_PAGE_SIZE, limit - read_pos)
        fh.seek(read_pos)
        page_bytes = fh.read(page_size)
        read_pos = fh.tell()
        fh.seek(initial_pos)
        yield hashlib.sha256(page_bytes).digest()


@dataclasses.dataclass
class SuperBlob:
    code_limit: int
    identifier: str
    exec_start: int
    exec_end: int
    is_executable: bool

    @property
    def page_count(self) -> int:
        return math.ceil(self.code_limit / CODE_DIRECTORY_PAGE_SIZE)

    @property
    def length(self) -> int:
        # To compute the length, we just write the whole structure to a
        # fake io object that tracks position. Page hashes are null, but
        # the proper length.
        class _CountingIO:
            def __init__(self):
                self.pos = 0

            def write(self, data: bytes) -> int:
                self.pos += len(data)
                return len(data)

            def seek(self, pos: int) -> int:
                self.pos = pos
                return pos

            def tell(self) -> int:
                return self.pos

        counting = _CountingIO()
        hashes = ("\0" * SHA256_HASH_SIZE for _ in range(self.page_count))
        self.write(counting, hashes)
        return counting.tell()

    def write(self, fh: BinaryIO, hashes: Iterable[bytes]):
        # remember our starting position
        super_blob_offset = fh.tell()

        # Generate an empty requirements blob and its hash, which we'll use later.
        requirements_bytes = cs_requirements_blob(
            magic=CSMAGIC_REQUIREMENTS,
            length=sizeof(cs_requirements_blob),
            data=0,
        ).to_str()
        requirements_hash = hashlib.sha256(requirements_bytes).digest()
        assert len(requirements_hash) == SHA256_HASH_SIZE

        # Setup the super blob structure. Length will be added later.
        super = cs_super_blob(
            magic=CSMAGIC_EMBEDDED_SIGNATURE,
            count=3,  # code directory, requirements, wrapper
        )

        # Super blob indexes that store offsets to the following sections
        index_dir = cs_blob_index(type=CSSLOT_CODEDIRECTORY)
        index_requirements = cs_blob_index(type=CSSLOT_REQUIREMENTS)
        index_wrapper = cs_blob_index(type=CSSLOT_SIGNATURESLOT)

        # Record the code directory offset which follows the super blob header and
        # index entries. There are three entries: the code directory, an empty
        # requirements blob, and the final wrapper blob.
        dir_offset = super_blob_offset + sizeof(cs_super_blob) + sizeof(cs_blob_index) * 3

        # The offset stored in the index entry is relative to the start of the super blob.
        index_dir.offset = dir_offset - super_blob_offset

        # Setup the code directory
        dir = cs_code_directory(
            magic=CSMAGIC_CODEDIRECTORY,
            version=0x20400,
            flags=CS_ADHOC,
            nspecialslots=2,  # Just the requirements blob + empty Info.plist hash
            ncodeslots=self.page_count,
            hashsize=SHA256_HASH_SIZE,
            hashtype=CS_HASHTYPE_SHA256,
            platform=0,
            pagesize=log2(CODE_DIRECTORY_PAGE_SIZE),
            spare2=0,
            scatteroffset=0,
            teamoffset=0,
            spare3=0,
            execsegbase=self.exec_start,
            execseglimit=self.exec_end,
            execsegflags=CS_EXECSEG_MAIN_BINARY if self.is_executable else 0,
        )

        if self.code_limit <= 2**32:
            dir.codelimit = self.code_limit
            dir.codelimit64 = 0
        else:
            dir.codelimit = 0
            dir.codelimit64 = self.code_limit

        # Skip over the directory structure while we write the data after it.
        fh.seek(dir_offset + sizeof(cs_code_directory))

        # Write the identifier string
        dir.identoffset = fh.tell() - dir_offset
        fh.write(self.identifier.encode("utf-8"))
        fh.write(b"\0")  # null terminator

        # Write our two special hashes: the requirements hash and the null Info.plist hash
        fh.write(requirements_hash)
        fh.write(b"\0" * SHA256_HASH_SIZE)

        dir.hashoffset = fh.tell() - dir_offset

        # Write the code page hashes
        page_count = self.page_count
        for i, hash in enumerate(hashes):
            # Some sanity checks
            assert i < page_count, f"Too many hashes provided: expected {page_count}"
            assert len(hash) == SHA256_HASH_SIZE, f"Hash is the wrong size: got {len(hash)}, expected {SHA256_HASH_SIZE}"
            fh.write(hash)

        # Record the final directory length. We'll write the directory structure later.
        dir.length = fh.tell() - dir_offset

        # Write the resources blob and record its offset
        index_requirements.offset = fh.tell() - super_blob_offset
        fh.write(requirements_bytes)

        # Write the trailing wrapper blob and record its offset
        index_wrapper.offset = fh.tell() - super_blob_offset
        cs_generic_blob(
            magic=CSMAGIC_BLOBWRAPPER,
            length=sizeof(cs_generic_blob),
        ).to_fileobj(fh)

        # Record the final length of the super blob.
        end = fh.tell()
        super.length = end - super_blob_offset

        # Now skip back to the start of the super blob and write it, the index
        # entries, and the code directory structure.
        fh.seek(super_blob_offset)
        super.to_fileobj(fh)
        index_dir.to_fileobj(fh)
        index_requirements.to_fileobj(fh)
        index_wrapper.to_fileobj(fh)
        dir.to_fileobj(fh)

        # Leave fh at the end of the whole thing.
        fh.seek(end)


@dataclasses.dataclass
class FatInfo:
    header: fat_header
    archs: List[Union[fat_arch, fat_arch64]]


@dataclasses.dataclass
class SigInfo:
    signature_bytes: bytes
    hash_offset: int


@dataclasses.dataclass
class ArchInfo:
    signature_needed: bool = False
    original_offset: int = 0
    original_size: int = 0
    new_offset: int = 0
    new_size: int = 0
    new_linkedit_size: int = 0
    signature_command_index: Optional[int] = None
    super_blob: SuperBlob = None
    code_signature_offset: int = None
    code_signature_size: int = None


def _load_fat(fh: BinaryIO) -> FatInfo:
    info = FatInfo(header=fat_header.from_fileobj(fh), archs=None)

    if info.header.magic == FAT_MAGIC:
        info.archs = [fat_arch.from_fileobj(fh) for _ in range(info.header.nfat_arch)]
    elif info.header.magic == FAT_MAGIC_64:
        info.archs = [fat_arch64.from_fileobj(fh) for _ in range(info.header.fat.nfat_arch)]
    else:
        raise ValueError("Unknown fat header magic: %r" % (info.header.magic))

    return info


def _prepare_arch(header: MachOHeader, identifier: str) -> ArchInfo:
    info = ArchInfo()
    info.signature_needed = header.header.filetype in [
        MH_EXECUTE,
        MH_DYLIB,
        MH_DYLINKER,
        MH_BUNDLE,
        MH_PRELOAD,
    ]
    info.original_offset = header.offset
    info.original_size = header.size

    # if we don't need to sign this one, we don't need to continue.
    if not info.signature_needed:
        info.new_size = header.size
        return info

    # Iterate through commands and pull out things we're interested in.
    code_signature_offset = 0
    last_linkedit_offset = 0
    exec_base = 0
    exec_limit = 0
    original_linkedit_size = 0
    original_linkedit_end = 0
    original_signature_size = 0
    for i, (load, cmd, _) in enumerate(header.commands):
        if load.cmd in (LC_SEGMENT, LC_SEGMENT_64) and cmd.segname.rstrip(b"\0") == b"__TEXT":
            exec_base = cmd.fileoff
            exec_limit = cmd.filesize

        if load.cmd in (LC_SEGMENT, LC_SEGMENT_64) and cmd.segname.rstrip(b"\0") == b"__LINKEDIT":
            original_linkedit_size = cmd.filesize
            original_linkedit_end = cmd.fileoff + cmd.filesize

        elif load.cmd == LC_CODE_SIGNATURE:
            code_signature_offset = cmd.dataoff
            original_signature_size = cmd.datasize
            info.signature_command_index = i

        if isinstance(cmd, linkedit_data_command):
            if cmd.dataoff > last_linkedit_offset:
                last_linkedit_offset = cmd.dataoff

    if code_signature_offset and code_signature_offset < last_linkedit_offset:
        raise SigningException("Code signature is not the last __LINKEDIT section; cannot modify")

    info.code_signature_offset = code_signature_offset or original_linkedit_end
    if not info.code_signature_offset:
        raise SigningException("Missing __LINKEDIT section; cannot add signature")

    if info.signature_command_index is None:
        # We need to add a new load command for the signature. Make sure there's enough space.
        command_len = sizeof(load_command) + sizeof(linkedit_data_command)
        available = header.low_offset - header.total_size
        if command_len > available:
            raise SigningException(
                f"Not enough space to insert LC_CODE_SIGNATURE command: need {command_len}, have {available}"
            )

    info.super_blob = SuperBlob(
        code_limit=info.code_signature_offset,
        identifier=identifier,
        exec_start=exec_base,
        exec_end=exec_limit,
        is_executable=header.header.filetype == MH_EXECUTE,
    )

    new_signature_size = info.super_blob.length
    info.code_signature_size = new_signature_size
    info.new_linkedit_size = original_linkedit_size - original_signature_size + new_signature_size
    info.new_size = info.code_signature_offset + new_signature_size

    return info


def _ad_hoc_sign(filename: str, fh: BinaryIO) -> None:
    identifier = os.path.basename(filename)
    macho = MachO(filename)
    fh.seek(0)
    if macho.fat:
        fat_info = _load_fat(fh)
    else:
        fat_info = None

    arch_infos = [_prepare_arch(header, identifier) for header in macho.headers]

    # The first arch's offset won't change.
    arch_infos[0].new_offset = arch_infos[0].original_offset

    if fat_info:
        # First thing we need to do is expand or contract the fat structure based
        # on new arch sizes. If we add a signature to an arch that didn't have one,
        # or shorten or lengthen the signature of an arch that did, the overall
        # structure of the universal binary may need to change.

        # For each additional arch, compute its new offset based on the end position of
        # the previous.
        for i in range(1, len(arch_infos)):
            align_bytes = 2 ** fat_info.archs[i].align
            arch_infos[i].new_offset = round_to_multiple(
                arch_infos[i - 1].new_offset + arch_infos[i - 1].new_size, align_bytes
            )

        # Move each arch around, in reverse order
        for arch in reversed(arch_infos):
            fmove(fh, arch.new_offset, arch.original_offset, arch.new_size)

        # Zero out the spaces between archs
        for i in range(len(arch_infos) - 1):
            start = arch_infos[i].new_offset + arch_infos[i].new_size
            end = arch_infos[i + 1].new_offset
            fzero(fh, start, end - start)

        # Update the fat structures
        for arch, fat_info_arch in zip(arch_infos, fat_info.archs):
            fat_info_arch.offset = arch.new_offset
            fat_info_arch.size = arch.new_size

        # Rewrite the fat structure
        fh.seek(0)
        fat_info.header.to_fileobj(fh)
        for arch in fat_info.archs:
            arch.to_fileobj(fh)

    # Truncate the file to the new end of the last arch.
    fh.truncate(arch_infos[-1].new_offset + arch_infos[-1].new_size)

    # Now with the fat structure possibly changed, we reload our mach headers.
    macho = MachO(filename)

    for arch, header in zip(arch_infos, macho.headers):
        if not arch.signature_needed:
            continue

        for load, cmd, _ in header.commands:
            if load.cmd in (LC_SEGMENT, LC_SEGMENT_64) and cmd.segname.rstrip(b"\0") == b"__LINKEDIT":
                cmd.filesize = arch.new_linkedit_size
                break

        if arch.signature_command_index:
            # Adjust the superblob length in the original LC_CODE_SIGNATURE command.
            _, cmd, _ = header.commands[arch.signature_command_index]
            cmd.datasize = arch.code_signature_size
        else:
            # Add a new load command and increase the ncmds and sizeofcmds values.
            # Note that we must specify proper endianness for these commands.
            load = load_command(
                cmd=LC_CODE_SIGNATURE, cmdsize=sizeof(load_command) + sizeof(linkedit_data_command), _endian_=header.endian
            )
            cmd = linkedit_data_command(
                dataoff=arch.code_signature_offset, datasize=arch.code_signature_size, _endian_=header.endian
            )
            header.commands.append((load, cmd, b""))
            header.header.ncmds += 1
            header.changedHeaderSizeBy(load.cmdsize)

    # Write our header changes.
    fh.seek(0)
    macho.write(fh)

    # Lastly, write our actual signatures.
    for arch in arch_infos:
        if not arch.signature_needed:
            continue

        signature_offset = arch.new_offset + arch.code_signature_offset
        hashes = iterate_page_hashes(fh, arch.new_offset, signature_offset)
        fh.seek(signature_offset)
        arch.super_blob.write(fh, hashes)

        # Zero out the remainder of the the code signature section
        zero_len = arch.code_signature_size - (fh.tell() - signature_offset)
        fzero(fh, fh.tell(), zero_len)


def ad_hoc_sign(filename: str) -> None:
    with open(filename, "rb+", opener=open_create) as fh:
        _ad_hoc_sign(filename, fh)


if __name__ == "__main__":
    ad_hoc_sign(sys.argv[1])
