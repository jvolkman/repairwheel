# get_install_names :: otool -L -> list of strings, ignoring self
# get_install_id :: otool -D  -> single install id. Fail if different archs have different ids
# set_install_name :: install_name_tool -change oldname newname. & adhoc sign
# set_install_id :: install_name_tool -id. & adhoc sign
# get_rpaths :: otool -l -> list of paths. Fail if diff per arch
# add_rpath :: install_name_tool -add_rpath. & adhoc sign
# get_archs :: lipo -info -> frozenset
# lipo_fuse :: create fat binary. & adhoc sign
# replace_signature :: adhoc sign
# validate_signature :: adhoc sign if current signature is invalid

from typing import Callable
from typing import Tuple
from typing import TypeVar
from macholib.MachO import MachO
from macholib.MachO import MachOHeader

T = TypeVar("T")

def _all_arches_same_value(macho: MachO, fn: Callable[[MachOHeader], T]) -> T:
    val = fn(macho.headers[0])
    for header in macho.headers[1:]:
        next_val = fn(header)
        if next_val != val:
            raise NotImplementedError(
                "This function does not support separate values per-architecture"
            )
        val = next_val

    return val


def get_install_names(filename: str) -> Tuple[str, ...]:
    """Return install names from library named in `filename`

    Returns tuple of install names

    tuple will be empty if no install names, or if this is not an object file.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    install_names : tuple
        tuple of install names for library `filename`

    Raises
    ------
    NotImplementedError
        If ``filename`` has different install names per-architecture.
    InstallNameError
        On any unexpected output from ``otool``.
    """
    def _val(header: MachOHeader) -> Tuple[str]:
        return tuple(r[2] for r in header.walkRelocatables())

    macho = MachO(filename)
    return _all_arches_same_value(macho, _val)


def get_install_id(filename: str) -> Optional[str]:
    """Return install id from library named in `filename`

    Returns None if no install id, or if this is not an object file.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    install_id : str
        install id of library `filename`, or None if no install id

    Raises
    ------
    NotImplementedError
        If ``filename`` has different install ids per-architecture.
    """
    def _val(header: MachOHeader) -> Optional[str]:
        

    raise NotImplementedError


def set_install_name(
    filename: str, oldname: str, newname: str, ad_hoc_sign: bool = True
) -> None:
    """Set install name `oldname` to `newname` in library filename

    Parameters
    ----------
    filename : str
        filename of library
    oldname : str
        current install name in library
    newname : str
        replacement name for `oldname`
    ad_hoc_sign : {True, False}, optional
        If True, sign library with ad-hoc signature
    """
    raise NotImplementedError


def set_install_id(filename: str, install_id: str, ad_hoc_sign: bool = True):
    """Set install id for library named in `filename`

    Parameters
    ----------
    filename : str
        filename of library
    install_id : str
        install id for library `filename`
    ad_hoc_sign : {True, False}, optional
        If True, sign library with ad-hoc signature

    Raises
    ------
    RuntimeError if `filename` has not install id
    """
    raise NotImplementedError


def get_rpaths(filename: str) -> Tuple[str, ...]:
    """Return a tuple of rpaths from the library `filename`.

    If `filename` is not a library then the returned tuple will be empty.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    rpath : tuple
        rpath paths in `filename`

    Raises
    ------
    NotImplementedError
        If ``filename`` has different rpaths per-architecture.
    InstallNameError
        On any unexpected output from ``otool``.
    """
    raise NotImplementedError


def add_rpath(filename: str, newpath: str, ad_hoc_sign: bool = True) -> None:
    """Add rpath `newpath` to library `filename`

    Parameters
    ----------
    filename : str
        filename of library
    newpath : str
        rpath to add
    ad_hoc_sign : {True, False}, optional
        If True, sign file with ad-hoc signature
    """
    raise NotImplementedError


def get_archs(libname: str) -> FrozenSet[str]:
    """Return architecture types from library `libname`

    Parameters
    ----------
    libname : str
        filename of binary for which to return arch codes

    Returns
    -------
    arch_names : frozenset
        Empty (frozen)set if no arch codes.  If not empty, contains one or more
        of 'ppc', 'ppc64', 'i386', 'x86_64', 'arm64'.
    """
    raise NotImplementedError


def lipo_fuse(
    in_fname1: str, in_fname2: str, out_fname: str, ad_hoc_sign: bool = True
) -> str:
    """Use lipo to merge libs `filename1`, `filename2`, store in `out_fname`

    Parameters
    ----------
    in_fname1 : str
        filename of library
    in_fname2 : str
        filename of library
    out_fname : str
        filename to which to write new fused library
    ad_hoc_sign : {True, False}, optional
        If True, sign file with ad-hoc signature

    Raises
    ------
    RuntimeError
        If the lipo command exits with an error.
    """
    raise NotImplementedError


def replace_signature(filename: str, identity: str) -> None:
    """Replace the signature of a binary file using `identity`

    See the codesign documentation for more info

    Parameters
    ----------
    filename : str
        Filepath to a binary file.
    identity : str
        The signing identity to use.
    """
    raise NotImplementedError


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

