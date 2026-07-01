"""nifti-qc: catch silently-broken NIfTI geometry before it ruins your results.

The headline check is qform/sform disagreement -- the same class of bug that
mislocates segmentations in MS-lesion pipelines. See the README for details.
"""

from .checks import (
    ERROR,
    INFO,
    WARN,
    Finding,
    check_affine,
    check_alignment,
    check_data,
    check_geometry,
    check_image,
    compare_affines,
    orientation_label,
)
from .core import FileReport, Report, scan, scan_file

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ERROR",
    "WARN",
    "INFO",
    "Finding",
    "FileReport",
    "Report",
    "scan",
    "scan_file",
    "check_affine",
    "check_geometry",
    "check_data",
    "check_image",
    "check_alignment",
    "compare_affines",
    "orientation_label",
]
