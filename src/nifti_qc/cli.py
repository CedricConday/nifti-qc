"""Command-line interface for nifti-qc.

    nifti-qc scan t1.nii.gz                 # QC one file
    nifti-qc scan t1.nii.gz flair.nii.gz    # QC each + check they align
    nifti-qc scan *.nii.gz --json           # machine-readable output

Exit status is 0 when clean, 1 when any error-severity finding is present, so
it drops into CI and pre-processing scripts as a gate.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import scan


_COLORS = {"error": "\033[31m", "warn": "\033[33m", "info": "\033[36m"}
_RESET = "\033[0m"


def _sev(severity: str, use_color: bool) -> str:
    label = f"{severity.upper():5}"
    if use_color and severity in _COLORS:
        return f"{_COLORS[severity]}{label}{_RESET}"
    return label


def _print_human(report, use_color: bool) -> None:
    for fr in report.files:
        header = f"{fr.path}  [{fr.orientation}]"
        if fr.ok and not fr.findings:
            print(f"{header}  ok")
            continue
        print(header)
        for f in fr.findings:
            print(f"  {_sev(f.severity, use_color)}  {f.code}: {f.message}")
    if report.alignment:
        print("alignment")
        for f in report.alignment:
            print(f"  {_sev(f.severity, use_color)}  {f.code}: {f.message}")

    n_err = sum(fr.n_errors for fr in report.files) + sum(
        1 for f in report.alignment if f.severity == "error"
    )
    n_warn = sum(fr.n_warnings for fr in report.files) + sum(
        1 for f in report.alignment if f.severity == "warn"
    )
    summary = "clean" if report.ok else "PROBLEMS"
    print(f"\n{summary}: {n_err} error(s), {n_warn} warning(s) across "
          f"{len(report.files)} file(s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nifti-qc",
        description="Catch silently-broken NIfTI geometry (qform/sform "
        "mismatch, bad affines, misaligned inputs) before it ruins results.",
    )
    parser.add_argument("--version", action="version", version=f"nifti-qc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="QC one or more NIfTI files")
    scan_p.add_argument("paths", nargs="+", help="NIfTI file(s) (.nii/.nii.gz)")
    scan_p.add_argument("--json", action="store_true", help="emit JSON")
    scan_p.add_argument(
        "--no-align",
        action="store_true",
        help="skip the cross-file alignment check",
    )
    scan_p.add_argument("--no-color", action="store_true", help="disable ANSI color")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan":
        report = scan(args.paths, check_align=not args.no_align)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            use_color = (not args.no_color) and sys.stdout.isatty()
            _print_human(report, use_color)
        return 0 if report.ok else 1

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    raise SystemExit(main())
