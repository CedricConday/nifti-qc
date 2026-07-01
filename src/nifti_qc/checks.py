"""Affine, orientation and data-integrity checks for NIfTI images.

The headline check is ``qform/sform`` disagreement: NIfTI stores the
world-to-voxel mapping twice (the quaternion ``qform`` and the affine
``sform``). Different tools read different ones -- nibabel and most Python
tooling follow the ``sform`` when its code is set, while some C/registration
tools (e.g. greedy, used by LST-AI) read the ``qform``. When a prior step
(SPM co-registration is the classic culprit) updates only one of them, the two
disagree and downstream results are silently mislocated. See
https://github.com/CompImg/LST-AI/pull/45 for a real-world instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# NIfTI xform codes (nifti1.h). 0 == NIFTI_XFORM_UNKNOWN.
XFORM_LABELS = {
    0: "unknown",
    1: "scanner_anat",
    2: "aligned_anat",
    3: "talairach",
    4: "mni_152",
    5: "template_other",
}

ERROR = "error"
WARN = "warn"
INFO = "info"
_SEVERITY_ORDER = {INFO: 0, WARN: 1, ERROR: 2}


@dataclass
class Finding:
    """A single QC observation about a file (or a pair of files)."""

    code: str
    severity: str
    message: str
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity.upper():5}] {self.code}: {self.message}"


def _rotation_angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    """Magnitude of the rotation (degrees) between two 3x3 direction matrices.

    Normalises out per-axis scaling so pure voxel-size differences do not read
    as rotation, then measures the residual rotation via the trace formula.
    """
    def _dircos(m: np.ndarray) -> np.ndarray:
        out = m.astype(float).copy()
        for i in range(3):
            n = np.linalg.norm(out[:, i])
            if n > 0:
                out[:, i] /= n
        return out

    ra, rb = _dircos(a), _dircos(b)
    # R maps one frame to the other; angle from its trace.
    r = rb @ ra.T
    cos_theta = (np.trace(r) - 1.0) / 2.0
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return float(np.degrees(np.arccos(cos_theta)))


def compare_affines(
    a: np.ndarray, b: np.ndarray
) -> tuple[float, float]:
    """Return (max_translation_mm, rotation_deg) between two 4x4 affines."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    trans = float(np.max(np.abs(a[:3, 3] - b[:3, 3])))
    rot = _rotation_angle_deg(a[:3, :3], b[:3, :3])
    return trans, rot


def check_affine(img, *, trans_tol_mm: float = 1e-3, rot_tol_deg: float = 1e-2) -> list[Finding]:
    """Check the qform/sform consistency and validity of a nibabel image."""
    findings: list[Finding] = []
    hdr = img.header

    qform_code = int(hdr["qform_code"])
    sform_code = int(hdr["sform_code"])

    has_q = qform_code > 0
    has_s = sform_code > 0

    if not has_q and not has_s:
        findings.append(
            Finding(
                "no_valid_affine",
                ERROR,
                "Both qform_code and sform_code are 0 (unknown); world "
                "orientation is undefined and tools will fall back to the "
                "raw data array.",
                {"qform_code": qform_code, "sform_code": sform_code},
            )
        )
        return findings

    if has_q and has_s:
        qform = img.get_qform()
        sform = img.get_sform()
        trans, rot = compare_affines(qform, sform)
        if trans > trans_tol_mm or rot > rot_tol_deg:
            findings.append(
                Finding(
                    "qform_sform_mismatch",
                    ERROR,
                    f"qform and sform disagree: up to {trans:.3f} mm "
                    f"translation and {rot:.3f} deg rotation apart. Tools that "
                    "read the qform (e.g. greedy) and tools that read the "
                    "sform (e.g. nibabel) will place this image differently.",
                    {
                        "max_translation_mm": round(trans, 6),
                        "rotation_deg": round(rot, 6),
                        "qform_code": qform_code,
                        "sform_code": sform_code,
                    },
                )
            )
    elif has_s and not has_q:
        findings.append(
            Finding(
                "qform_unset",
                WARN,
                "sform is set but qform_code is 0. Tools that read the qform "
                "(some C/registration tools) may misplace or reject this image.",
                {"sform_code": sform_code},
            )
        )
    elif has_q and not has_s:
        findings.append(
            Finding(
                "sform_unset",
                WARN,
                "qform is set but sform_code is 0. Most Python tooling prefers "
                "the sform and will fall back to the qform here.",
                {"qform_code": qform_code},
            )
        )

    return findings


def check_geometry(
    img,
    *,
    anisotropy_ratio: float = 5.0,
    orthonormal_tol: float = 1e-3,
) -> list[Finding]:
    """Check voxel sizes, anisotropy and direction-cosine orthonormality."""
    findings: list[Finding] = []
    zooms = np.asarray(img.header.get_zooms()[:3], dtype=float)

    if np.any(zooms <= 0):
        findings.append(
            Finding(
                "nonpositive_voxel_size",
                ERROR,
                f"Voxel size has a zero/negative dimension: {zooms.tolist()} mm.",
                {"zooms_mm": zooms.tolist()},
            )
        )
    else:
        ratio = float(zooms.max() / zooms.min())
        if ratio >= anisotropy_ratio:
            findings.append(
                Finding(
                    "extreme_anisotropy",
                    WARN,
                    f"Highly anisotropic voxels (ratio {ratio:.1f}:1, "
                    f"{zooms.tolist()} mm); many CNN models assume near-isotropic input.",
                    {"zooms_mm": zooms.tolist(), "ratio": round(ratio, 3)},
                )
            )

    # Direction cosines orthonormal? Shear/skew indicates a malformed affine.
    dircos = img.affine[:3, :3].astype(float).copy()
    norms = np.linalg.norm(dircos, axis=0)
    if np.all(norms > 0):
        dircos /= norms
        gram = dircos.T @ dircos
        off = gram - np.eye(3)
        if np.max(np.abs(off)) > orthonormal_tol:
            findings.append(
                Finding(
                    "non_orthonormal_direction",
                    WARN,
                    "Direction cosines are not orthogonal (the affine encodes "
                    "shear). Unusual for anatomical MRI and may indicate a "
                    "corrupted header.",
                    {"max_off_orthogonal": round(float(np.max(np.abs(off))), 6)},
                )
            )

    return findings


def check_data(img, *, sample_max_voxels: int = 4_000_000) -> list[Finding]:
    """Check for non-finite values and empty volumes.

    For large volumes the data is sampled (strided) to stay fast; the sample
    size is reported so the check is never silently partial.
    """
    findings: list[Finding] = []
    data = np.asarray(img.dataobj)  # unscaled read is fine for finiteness/zero

    n = data.size
    if n > sample_max_voxels and n > 0:
        step = int(np.ceil(n / sample_max_voxels))
        flat = data.reshape(-1)[::step]
        sampled = True
    else:
        flat = data.reshape(-1)
        sampled = False

    n_nonfinite = int(np.count_nonzero(~np.isfinite(flat)))
    if n_nonfinite > 0:
        findings.append(
            Finding(
                "non_finite_data",
                ERROR,
                f"{n_nonfinite} non-finite voxel(s) (NaN/Inf) found"
                + (" in a strided sample" if sampled else "") + ".",
                {"count": n_nonfinite, "sampled": sampled},
            )
        )

    if np.all(flat == 0):
        findings.append(
            Finding(
                "empty_volume",
                WARN,
                "All sampled voxels are zero; the volume may be empty."
                if sampled
                else "The volume is entirely zero.",
                {"sampled": sampled},
            )
        )

    return findings


def orientation_label(img) -> str:
    """Human-readable anatomical orientation, e.g. 'RAS'."""
    import nibabel as nib

    return "".join(nib.aff2axcodes(img.affine))


def check_image(img, *, filename: Optional[str] = None) -> list[Finding]:
    """Run every single-image check and return all findings, worst-first."""
    findings: list[Finding] = []
    findings += check_affine(img)
    findings += check_geometry(img)
    findings += check_data(img)
    findings.sort(key=lambda f: -_SEVERITY_ORDER[f.severity])
    return findings


def check_alignment(images: list, *, labels: Optional[list[str]] = None) -> list[Finding]:
    """Check whether several images share a voxel grid and world space.

    This is the T1+FLAIR situation LST-AI faces: the tools assume the inputs
    describe the same anatomy in a compatible space. Mismatched grids need
    resampling; mismatched world placement means they are not co-registered.
    """
    findings: list[Finding] = []
    if len(images) < 2:
        return findings

    if labels is None:
        labels = [f"image[{i}]" for i in range(len(images))]

    ref = images[0]
    ref_shape = ref.shape[:3]
    ref_zooms = np.asarray(ref.header.get_zooms()[:3], dtype=float)

    for i in range(1, len(images)):
        other = images[i]
        pair = f"{labels[0]} vs {labels[i]}"

        if other.shape[:3] != ref_shape:
            findings.append(
                Finding(
                    "grid_shape_mismatch",
                    WARN,
                    f"{pair}: voxel grids differ ({ref_shape} vs "
                    f"{other.shape[:3]}); resampling is required before "
                    "voxelwise operations.",
                    {"ref_shape": list(ref_shape), "other_shape": list(other.shape[:3])},
                )
            )

        other_zooms = np.asarray(other.header.get_zooms()[:3], dtype=float)
        if not np.allclose(ref_zooms, other_zooms, atol=1e-3):
            findings.append(
                Finding(
                    "voxel_size_mismatch",
                    WARN,
                    f"{pair}: voxel sizes differ ({ref_zooms.tolist()} vs "
                    f"{other_zooms.tolist()} mm).",
                    {"ref_zooms": ref_zooms.tolist(), "other_zooms": other_zooms.tolist()},
                )
            )

        trans, rot = compare_affines(ref.affine, other.affine)
        if trans > 1.0 or rot > 1.0:
            findings.append(
                Finding(
                    "world_space_mismatch",
                    INFO,
                    f"{pair}: affines place the images {trans:.1f} mm / "
                    f"{rot:.1f} deg apart in world space; if they are meant to "
                    "be co-registered, they are not.",
                    {"max_translation_mm": round(trans, 3), "rotation_deg": round(rot, 3)},
                )
            )

    findings.sort(key=lambda f: -_SEVERITY_ORDER[f.severity])
    return findings
