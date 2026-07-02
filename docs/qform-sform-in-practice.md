# The qform/sform trap: how a NIfTI silently lands in the wrong place

*A worked example of the single most common silent geometry bug in
neuroimaging pipelines — why it happens, how to see it, and how to decide the
fix — using MS-lesion segmentation as the stakes.*

## Two transforms, one image

Every NIfTI image carries its voxel→world mapping **twice**:

- the **`sform`** — a full 4×4 affine (`srow_*`), and
- the **`qform`** — a rigid transform stored as a quaternion plus offset
  (`quatern_*`, `qoffset_*`, `pixdim`).

Each has an independent *code* (`sform_code`, `qform_code`) saying whether it's
set and what space it refers to. The format allows both — and **does not
require them to agree.**

Different tools trust different ones. [nibabel](https://nipy.org/nibabel/) and
most Python tooling use the `sform` when its code is non-zero; several
C/registration tools (FSL utilities, `greedy`, and others) read the `qform`.
As long as the two encode the same mapping, nobody notices which is used.

## How they diverge

The classic culprit is a processing step that rewrites **only one** of the two.
SPM co-registration, some resampling utilities, and hand-rolled header edits
update the `sform` and leave the `qform` untouched (or vice-versa). Now:

```python
import numpy as np, nibabel as nib

data = np.zeros((182, 218, 182), np.float32)
img = nib.Nifti1Image(data, np.eye(4))

# a co-registration step writes a corrected sform...
sform = np.eye(4); sform[:3, 3] = [10.0, 0.0, 0.0]   # 10 mm shift
img.set_sform(sform, code=2)
# ...but the qform still says the old position
img.set_qform(np.eye(4), code=1)

nib.save(img, "flair.nii.gz")
```

This file is now **10 mm apart depending on who reads it.** No error, no
warning, no crash. A Python tool places it here; a C tool places it 10 mm over.

## Why this is dangerous in an MS-lesion pipeline

Lesion segmentation runs a model on a FLAIR volume and writes a mask in that
volume's space. If the FLAIR's `qform`/`sform` disagree, the mask can be
generated in one interpretation and overlaid in the other — so lesions render
shifted off the white-matter tracts they belong to. Lesion **counts** and
**volumes**, the numbers that drive MS monitoring, come out subtly wrong, and
nothing in the run flags it. This is not hypothetical: it was a real fix in the
LST-AI lesion pipeline
([CompImg/LST-AI#45](https://github.com/CompImg/LST-AI/pull/45)).

## Seeing it in seconds

The whole point is that the bug is *silent*, so you need an explicit check.
[`nifti-qc`](https://github.com/CedricConday/nifti-qc) compares the two
transforms and reports the magnitude of any disagreement:

```console
$ nifti-qc scan flair.nii.gz
flair.nii.gz  [RAS]
  ERROR  qform_sform_mismatch: qform and sform disagree: up to 10.000 mm
         translation and 0.000 deg rotation apart. Tools that read the qform
         (e.g. greedy) and tools that read the sform (e.g. nibabel) will place
         this image differently.

PROBLEMS: 1 error(s), 0 warning(s) across 1 file(s)
```

It exits non-zero on any error, so it works as a gate at the top of a pipeline
or in CI:

```yaml
- uses: CedricConday/nifti-qc@main
  with:
    paths: sub-*/anat/*FLAIR.nii.gz
```

## Deciding the fix (detection ≠ repair)

There is no universally correct auto-repair, which is why `nifti-qc` reports
but does not rewrite. The decision is: **which transform is authoritative?**

- If the last *correct* step wrote the `sform` (the usual SPM case), copy the
  `sform` into the `qform`:

  ```python
  img.set_qform(img.get_sform(), code=int(img.header["sform_code"]))
  ```

- If instead the `qform` is the trustworthy one, do the reverse.

The right answer depends on which upstream tool you trust for *this* dataset —
which is exactly why it's a human decision, not a silent default. Harmonize
once, re-run the check, and the pipeline is back on solid ground.

## Takeaways

1. A NIfTI stores geometry twice; the format lets the copies disagree.
2. Tools split on which copy they read, so a one-sided edit mislocates the
   image with no error.
3. In lesion work this corrupts counts and volumes invisibly.
4. Check explicitly and early; repair by choosing the authoritative transform.
