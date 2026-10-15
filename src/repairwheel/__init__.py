# SPDX-License-Identifier: MIT

"""
repairwheel
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

try:
    __version__ = version("repairwheel")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+unknown"
