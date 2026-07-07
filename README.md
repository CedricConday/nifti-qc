# nifti-qc

**Catch silently-broken NIfTI geometry before it ruins your results.**

A NIfTI file stores its world→voxel mapping *twice* — the quaternion
`qform` and the affine `sform`. Different tools trust different ones:
[nibabel](https://nipy.org/nibabel/) and most Python tooling follow the
`sform`; some C/registration tools (e.g. `greedy`) read the `qform`. When an
earlier step updates only one of them — SPM co-registration is the classic
culprit — the two disagree and **your image is silently mislocated in world
space.** No error, no crash: just a segmentation, overlay, or registration
that lands in the wrong place.

`nifti-qc` is a tiny, dependency-light QC gate that catches that trap and a
handful of related geometry/data problems, so you find them in seconds instead
of in a downstream result three steps later.

> This tool grew out of a real fix for exactly this bug in the MS-lesion
> segmentation pipeline **LST-AI**
> ([CompImg/LST-AI#45](https://github.com/CompImg/LST-AI/pull/45)), where a
> qform/sform mismatch mislocated lesion masks in FLAIR space.

📖 **Deep dive:** [The qform/sform trap in practice](docs/qform-sform-in-practice.md) —
why the bug happens, a runnable reproduction, and how to decide the fix.

## Install

```bash
pip install nifti-qc
# or from source:
pip install -e .
```

Requires only `nibabel` and `numpy`.

## Use it on the command line

```bash
# QC a single file
nifti-qc scan t1.nii.gz

# QC each file AND check they share a grid / world space (e.g. T1 + FLAIR)
nifti-qc scan t1.nii.gz flair.nii.gz

# machine-readable, for CI / pipelines
nifti-qc scan *.nii.gz --json
```

Example output:

```
sub-01_flair.nii.gz  [RAS]
  ERROR  qform_sform_mismatch: qform and sform disagree: up to 10.000 mm
         translation and 0.000 deg rotation apart. Tools that read the qform
         (e.g. greedy) and tools that read the sform (e.g. nibabel) will place
         this image differently.

PROBLEMS: 1 error(s), 0 warning(s) across 1 file(s)
```

The command **exits non-zero when any error-severity problem is found**, so it
drops straight into a CI step or a pre-processing script as a gate:

```bash
nifti-qc scan "$T1" "$FLAIR" || { echo "fix your inputs first"; exit 1; }
```

## Use it in CI (GitHub Action)

A composite Action ships with the repo, so a workflow can gate on NIfTI
geometry with no setup — the job fails if any file has an error-severity
problem:

```yaml
- uses: CedricConday/nifti-qc@main
  with:
    paths: data/*.nii.gz
    # args: "--no-align"   # optional flags for `nifti-qc scan`
```

## Use it as a library

```python
import nifti_qc

report = nifti_qc.scan(["t1.nii.gz", "flair.nii.gz"])
if not report.ok:
    for fr in report.files:
        for f in fr.findings:
            print(fr.path, f.code, f.severity, f.message)
    for f in report.alignment:
        print("align", f.code, f.message)
```

Every check is also importable on its own (`check_affine`, `check_geometry`,
`check_data`, `check_alignment`) and returns plain `Finding` dataclasses.

## What it checks

| Check | Severity | What it means |
|---|---|---|
| `qform_sform_mismatch` | error | qform and sform disagree — the silent-mislocation trap |
| `no_valid_affine` | error | both codes are 0; world orientation undefined |
| `qform_unset` / `sform_unset` | warn | only one transform is set; some tools will misread |
| `nonpositive_voxel_size` | error | a voxel dimension is ≤ 0 |
| `extreme_anisotropy` | warn | very non-isotropic voxels (default ≥ 5:1) |
| `non_orthonormal_direction` | warn | affine encodes shear — usually a corrupt header |
| `non_finite_data` | error | NaN/Inf voxels |
| `empty_volume` | warn | volume is all zeros |
| `grid_shape_mismatch` | warn | inputs live on different voxel grids (resampling needed) |
| `voxel_size_mismatch` | warn | inputs have different voxel sizes |
| `world_space_mismatch` | info | inputs are not co-registered in world space |

Each finding carries a machine-readable `detail` dict (e.g. the exact
translation in mm and rotation in degrees) for programmatic use.

## Why trust the numbers

Every check has a unit test that builds a synthetic NIfTI *designed* to trigger
it and asserts on the reported magnitude — the qform/sform mismatch test
constructs a 10 mm offset and asserts the tool reports 10 mm. Run them:

```bash
pip install -e ".[test]"
pytest -q
```

## Scope

`nifti-qc` reports problems; it does not fix them. To *repair* a qform/sform
mismatch you decide which transform is authoritative and harmonize to it — see
the LST-AI fix linked above for one approach. Keeping detection and repair
separate is deliberate: the right fix depends on which upstream tool you trust.

## License

MIT © Cedric Conday
