# Changelog

All notable changes to **nifti-qc** are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [0.1.0] - 2026-07-02

Initial release.

### Added
- Geometry QC for NIfTI files: `qform`/`sform` mismatch detection (the silent
  world-space mislocation trap), undefined/invalid affines, non-positive voxel
  sizes, extreme anisotropy, and non-orthonormal (shear) direction matrices.
- Data checks: non-finite (NaN/Inf) voxels and empty volumes.
- Cross-file alignment checks: grid-shape, voxel-size, and world-space mismatch.
- `nifti-qc scan` CLI (human-readable and `--json` output) that exits non-zero
  on any error-severity finding, so it drops into a CI step or pre-processing
  script as a gate.
- Importable library API (`scan`, `check_affine`, `check_geometry`,
  `check_data`, `check_alignment`, `orientation_label`) returning `Finding`
  dataclasses with machine-readable `detail`.
- Reusable composite GitHub Action for running the geometry gate in CI.
- PEP 561 typing marker (`py.typed`); sources are mypy-checked in CI.

[0.1.0]: https://github.com/CedricConday/nifti-qc/releases/tag/v0.1.0
