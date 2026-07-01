"""Synthetic NIfTI fixtures. Every check has a construction that triggers it,
so the tests are oracle-verified rather than asserting on opaque real files.
"""

import numpy as np
import nibabel as nib
import pytest


def make_img(
    data=None,
    *,
    qform=None,
    sform=None,
    qcode=1,
    scode=1,
    zooms=None,
):
    """Build a Nifti1Image with explicit qform/sform codes and matrices."""
    if data is None:
        data = np.ones((8, 8, 8), dtype=np.float32)
    affine = np.eye(4) if sform is None else sform
    img = nib.Nifti1Image(data, affine=affine)
    if qform is not None or qcode is not None:
        img.set_qform(qform if qform is not None else np.eye(4), code=qcode)
    if sform is not None or scode is not None:
        img.set_sform(sform if sform is not None else np.eye(4), code=scode)
    if zooms is not None:
        img.header.set_zooms(zooms)
    return img


@pytest.fixture
def write_img(tmp_path):
    def _write(name, img):
        p = tmp_path / name
        nib.save(img, str(p))
        return str(p)

    return _write
