"""File-level entry points: load NIfTI images and run the checks."""

from __future__ import annotations

from dataclasses import dataclass, field

import nibabel as nib

from .checks import (
    Finding,
    check_alignment,
    check_image,
    orientation_label,
)


@dataclass
class FileReport:
    path: str
    orientation: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    @property
    def n_errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def n_warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")


@dataclass
class Report:
    files: list[FileReport] = field(default_factory=list)
    alignment: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(fr.ok for fr in self.files) and not any(
            f.severity == "error" for f in self.alignment
        )

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "files": [
                {
                    "path": fr.path,
                    "orientation": fr.orientation,
                    "ok": fr.ok,
                    "findings": [
                        {
                            "code": f.code,
                            "severity": f.severity,
                            "message": f.message,
                            "detail": f.detail,
                        }
                        for f in fr.findings
                    ],
                }
                for fr in self.files
            ],
            "alignment": [
                {
                    "code": f.code,
                    "severity": f.severity,
                    "message": f.message,
                    "detail": f.detail,
                }
                for f in self.alignment
            ],
        }


def scan_file(path: str) -> FileReport:
    """QC a single NIfTI file."""
    img = nib.load(path)
    return FileReport(
        path=path,
        orientation=orientation_label(img),
        findings=check_image(img, filename=path),
    )


def scan(paths: list[str], *, check_align: bool = True) -> Report:
    """QC one or more files; when several are given, also check their alignment.

    Images are loaded once and reused for both the per-file and the alignment
    passes.
    """
    imgs = [nib.load(p) for p in paths]
    files = [
        FileReport(
            path=p,
            orientation=orientation_label(img),
            findings=check_image(img, filename=p),
        )
        for p, img in zip(paths, imgs)
    ]
    alignment: list[Finding] = []
    if check_align and len(imgs) > 1:
        alignment = check_alignment(imgs, labels=paths)
    return Report(files=files, alignment=alignment)
