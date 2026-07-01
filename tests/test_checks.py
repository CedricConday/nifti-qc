import numpy as np
import nibabel as nib
import pytest

from nifti_qc import (
    check_affine,
    check_alignment,
    check_data,
    check_geometry,
    check_image,
    compare_affines,
)
from conftest import make_img


def codes(findings):
    return {f.code for f in findings}


# --- qform/sform (the headline check) -------------------------------------

def test_qform_sform_mismatch_detected():
    # sform translated 10mm, qform at origin -> the #44/#45 trap.
    sform = np.eye(4)
    sform[:3, 3] = [10, 0, 0]
    img = make_img(qform=np.eye(4), sform=sform, qcode=1, scode=2)
    findings = check_affine(img)
    assert "qform_sform_mismatch" in codes(findings)
    f = next(f for f in findings if f.code == "qform_sform_mismatch")
    assert f.severity == "error"
    assert f.detail["max_translation_mm"] == pytest.approx(10.0, abs=1e-3)


def test_qform_sform_agree_is_clean():
    affine = np.eye(4)
    affine[:3, 3] = [3, 4, 5]
    img = make_img(qform=affine, sform=affine, qcode=1, scode=1)
    assert "qform_sform_mismatch" not in codes(check_affine(img))


def test_rotation_only_mismatch_detected():
    # Same origin, but sform rotated 90deg about z relative to qform.
    rot = np.eye(4)
    rot[:3, :3] = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    img = make_img(qform=np.eye(4), sform=rot, qcode=1, scode=2)
    findings = check_affine(img)
    f = next(f for f in findings if f.code == "qform_sform_mismatch")
    assert f.detail["rotation_deg"] == pytest.approx(90.0, abs=1e-2)


def test_no_valid_affine_when_both_codes_zero():
    img = make_img(qcode=0, scode=0)
    findings = check_affine(img)
    assert "no_valid_affine" in codes(findings)
    assert findings[0].severity == "error"


def test_sform_only_warns():
    img = make_img(qcode=0, scode=2)
    assert "qform_unset" in codes(check_affine(img))


def test_qform_only_warns():
    img = make_img(qcode=1, scode=0)
    assert "sform_unset" in codes(check_affine(img))


# --- geometry --------------------------------------------------------------

def test_extreme_anisotropy():
    img = make_img(zooms=(1.0, 1.0, 6.0))
    assert "extreme_anisotropy" in codes(check_geometry(img))


def test_isotropic_is_clean():
    img = make_img(zooms=(1.0, 1.0, 1.0))
    assert codes(check_geometry(img)) == set()


def test_shear_direction_flagged():
    sheared = np.eye(4)
    sheared[0, 1] = 0.5  # x depends on y -> non-orthogonal columns
    img = make_img(sform=sheared, qform=sheared, qcode=1, scode=1)
    assert "non_orthonormal_direction" in codes(check_geometry(img))


# --- data ------------------------------------------------------------------

def test_non_finite_data_flagged():
    data = np.ones((8, 8, 8), dtype=np.float32)
    data[0, 0, 0] = np.nan
    data[1, 1, 1] = np.inf
    img = make_img(data=data)
    findings = check_data(img)
    f = next(f for f in findings if f.code == "non_finite_data")
    assert f.severity == "error"
    assert f.detail["count"] == 2


def test_empty_volume_flagged():
    img = make_img(data=np.zeros((8, 8, 8), dtype=np.float32))
    assert "empty_volume" in codes(check_data(img))


def test_normal_data_clean():
    img = make_img(data=np.random.default_rng(0).random((8, 8, 8)).astype(np.float32))
    assert codes(check_data(img)) == set()


# --- alignment -------------------------------------------------------------

def test_grid_shape_mismatch():
    a = make_img(data=np.ones((8, 8, 8), dtype=np.float32))
    b = make_img(data=np.ones((6, 6, 6), dtype=np.float32))
    assert "grid_shape_mismatch" in codes(check_alignment([a, b]))


def test_voxel_size_mismatch():
    a = make_img(zooms=(1.0, 1.0, 1.0))
    b = make_img(zooms=(2.0, 2.0, 2.0))
    assert "voxel_size_mismatch" in codes(check_alignment([a, b]))


def test_world_space_mismatch():
    a = make_img(sform=np.eye(4), qform=np.eye(4))
    off = np.eye(4)
    off[:3, 3] = [20, 0, 0]
    b = make_img(sform=off, qform=off)
    assert "world_space_mismatch" in codes(check_alignment([a, b]))


def test_aligned_pair_clean():
    affine = np.eye(4)
    a = make_img(sform=affine, qform=affine)
    b = make_img(sform=affine, qform=affine)
    assert codes(check_alignment([a, b])) == set()


def test_single_image_alignment_is_empty():
    assert check_alignment([make_img()]) == []


# --- helpers / integration -------------------------------------------------

def test_compare_affines_pure_translation():
    a = np.eye(4)
    b = np.eye(4)
    b[:3, 3] = [0, 3, 4]
    trans, rot = compare_affines(a, b)
    assert trans == pytest.approx(4.0)
    assert rot == pytest.approx(0.0, abs=1e-9)


def test_check_image_sorts_errors_first():
    sform = np.eye(4)
    sform[:3, 3] = [10, 0, 0]
    data = np.ones((8, 8, 8), dtype=np.float32)
    data[0, 0, 0] = np.nan
    img = make_img(data=data, qform=np.eye(4), sform=sform, qcode=1, scode=2)
    findings = check_image(img)
    assert findings[0].severity == "error"


def test_scan_file_roundtrip(write_img):
    from nifti_qc import scan_file

    sform = np.eye(4)
    sform[:3, 3] = [10, 0, 0]
    path = write_img("bad.nii.gz", make_img(qform=np.eye(4), sform=sform, qcode=1, scode=2))
    report = scan_file(path)
    assert not report.ok
    assert report.n_errors >= 1
