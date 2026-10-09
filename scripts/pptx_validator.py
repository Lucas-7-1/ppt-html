#!/usr/bin/env python3
"""Validate native/editable PPTX structure by inspecting OOXML directly.

PowerPoint is not required. The validator reads the ZIP package, follows the
presentation's slide relationships, checks a 16:9 slide size, counts native
``p:sp`` shapes, ``a:t`` text nodes, and ``p:pic`` pictures per slide, and
rejects picture-only or full-slide-raster slides.

Examples:
    python3 scripts/pptx_validator.py deck.pptx
    python3 scripts/pptx_validator.py deck.pptx --expected-pages 8
    python3 scripts/pptx_validator.py deck.pptx --report-json report.json
"""

from __future__ import annotations

import argparse
import json
import math
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
REL_ID = f"{{{NS['r']}}}id"
SLIDE_PATH_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


def natural_slide_key(path: str) -> tuple[int, str]:
    """Sort fallback slide part names numerically."""

    match = SLIDE_PATH_RE.match(path)
    return (int(match.group(1)), path) if match else (sys.maxsize, path)


def add_unique(items: list[str], message: str) -> None:
    """Append a diagnostic once."""

    if message not in items:
        items.append(message)


def parse_xml_part(
    package: zipfile.ZipFile,
    part_name: str,
    errors: list[str],
) -> ET.Element | None:
    """Read and parse one OOXML part while recording package errors."""

    try:
        payload = package.read(part_name)
    except KeyError:
        add_unique(errors, f"missing OOXML part {part_name!r}")
        return None
    except OSError as exc:
        add_unique(errors, f"could not read OOXML part {part_name!r}: {exc}")
        return None
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        add_unique(errors, f"invalid XML in {part_name!r}: {exc}")
        return None


def integer_attribute(element: ET.Element | None, name: str) -> int | None:
    """Read one finite non-negative OOXML integer attribute."""

    if element is None:
        return None
    raw = element.attrib.get(name)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def resolve_slide_parts(
    package: zipfile.ZipFile,
    presentation: ET.Element,
    errors: list[str],
    warnings: list[str],
) -> list[str]:
    """Resolve slide part paths in presentation order through relationships."""

    relationships = parse_xml_part(package, "ppt/_rels/presentation.xml.rels", errors)
    relationship_targets: dict[str, str] = {}
    if relationships is not None:
        for relationship in relationships.findall("pr:Relationship", NS):
            rel_id = relationship.attrib.get("Id")
            target = relationship.attrib.get("Target")
            rel_type = relationship.attrib.get("Type", "")
            target_mode = relationship.attrib.get("TargetMode", "Internal")
            if not rel_id or not target or not rel_type.endswith("/slide"):
                continue
            if target_mode.lower() == "external":
                add_unique(errors, f"slide relationship {rel_id!r} is external")
                continue
            normalized = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join("ppt", target))
            if normalized.startswith("../") or not normalized.startswith("ppt/"):
                add_unique(errors, f"slide relationship {rel_id!r} escapes the ppt package")
                continue
            relationship_targets[rel_id] = normalized

    slide_parts: list[str] = []
    slide_ids = presentation.findall("./p:sldIdLst/p:sldId", NS)
    for index, slide_id in enumerate(slide_ids, start=1):
        rel_id = slide_id.attrib.get(REL_ID)
        if not rel_id:
            add_unique(errors, f"presentation slide {index} has no relationship id")
            continue
        target = relationship_targets.get(rel_id)
        if not target:
            add_unique(errors, f"presentation slide {index} relationship {rel_id!r} is unresolved")
            continue
        slide_parts.append(target)

    actual_parts = sorted(
        (name for name in package.namelist() if SLIDE_PATH_RE.match(name)),
        key=natural_slide_key,
    )
    if not slide_ids and actual_parts:
        add_unique(errors, "presentation.xml has no slide id list despite slide parts in the package")
        slide_parts = actual_parts
    elif not slide_ids:
        add_unique(errors, "presentation contains no slides")

    declared_set = set(slide_parts)
    actual_set = set(actual_parts)
    for missing in sorted(declared_set - actual_set, key=natural_slide_key):
        add_unique(errors, f"declared slide part {missing!r} is missing")
    for orphan in sorted(actual_set - declared_set, key=natural_slide_key):
        add_unique(warnings, f"orphan slide part is not in presentation order: {orphan!r}")
    return slide_parts


def object_bounds(element: ET.Element) -> tuple[int, int, int, int] | None:
    """Return direct picture/shape x/y/width/height in EMUs when available."""

    transform = element.find("./p:spPr/a:xfrm", NS)
    if transform is None:
        transform = element.find(".//a:xfrm", NS)
    if transform is None:
        return None
    offset = transform.find("a:off", NS)
    extent = transform.find("a:ext", NS)
    x = integer_attribute(offset, "x")
    y = integer_attribute(offset, "y")
    width = integer_attribute(extent, "cx")
    height = integer_attribute(extent, "cy")
    if None in {x, y, width, height}:
        return None
    return int(x), int(y), int(width), int(height)


def is_full_slide_picture(
    bounds: tuple[int, int, int, int],
    slide_width: int,
    slide_height: int,
) -> bool:
    """Detect a picture covering essentially the entire slide canvas."""

    x, y, width, height = bounds
    if slide_width <= 0 or slide_height <= 0 or width <= 0 or height <= 0:
        return False
    right = x + width
    bottom = y + height
    return (
        x <= slide_width * 0.02
        and y <= slide_height * 0.02
        and right >= slide_width * 0.98
        and bottom >= slide_height * 0.98
        and width >= slide_width * 0.95
        and height >= slide_height * 0.95
    )


def inspect_slide(
    package: zipfile.ZipFile,
    part_name: str,
    slide_number: int,
    slide_width: int,
    slide_height: int,
) -> dict[str, Any]:
    """Inspect one slide part and return per-slide counts and diagnostics."""

    errors: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {
        "slide": slide_number,
        "part": part_name,
        "ok": False,
        "counts": {
            "shapes": 0,
            "meaningful_native_shapes": 0,
            "text_nodes": 0,
            "text_characters": 0,
            "pictures": 0,
        },
        "full_slide_pictures": [],
        "errors": errors,
        "warnings": warnings,
    }

    root = parse_xml_part(package, part_name, errors)
    if root is None:
        return report

    shapes = root.findall(".//p:sp", NS)
    text_nodes = root.findall(".//a:t", NS)
    pictures = root.findall(".//p:pic", NS)
    text_characters = sum(len(node.text or "") for node in text_nodes)
    meaningful_native_shapes = 0
    for shape in shapes:
        shape_text = "".join(node.text or "" for node in shape.findall(".//a:t", NS)).strip()
        bounds = object_bounds(shape)
        if shape_text or bounds is None or not is_full_slide_picture(bounds, slide_width, slide_height):
            meaningful_native_shapes += 1
    report["counts"] = {
        "shapes": len(shapes),
        "meaningful_native_shapes": meaningful_native_shapes,
        "text_nodes": len(text_nodes),
        "text_characters": text_characters,
        "pictures": len(pictures),
    }

    full_slide_pictures: list[dict[str, int]] = []
    for picture_index, picture in enumerate(pictures, start=1):
        bounds = object_bounds(picture)
        if bounds is None:
            add_unique(warnings, f"picture {picture_index} has no readable xfrm bounds")
            continue
        if is_full_slide_picture(bounds, slide_width, slide_height):
            x, y, width, height = bounds
            full_slide_pictures.append(
                {
                    "picture": picture_index,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                }
            )
    report["full_slide_pictures"] = full_slide_pictures

    if pictures and not shapes:
        errors.append("slide is picture-only and has no native <p:sp> shapes")
    elif not shapes:
        errors.append("slide has no native <p:sp> shapes")
    if full_slide_pictures:
        if meaningful_native_shapes > 0 or text_characters > 0:
            warnings.append("slide uses a full-slide picture as a background with native editable overlay")
        else:
            errors.append("slide is a full-slide raster without meaningful native editable content")
    if not text_nodes:
        warnings.append("slide has no native <a:t> text nodes")

    report["ok"] = not errors
    return report


def validate_pptx(path: Path, expected_pages: int | None = None) -> dict[str, Any]:
    """Validate a PPTX package and return a JSON-serializable report."""

    errors: list[str] = []
    warnings: list[str] = []
    report: dict[str, Any] = {
        "command": "pptx-validator",
        "path": str(path),
        "ok": False,
        "expected_pages": expected_pages,
        "summary": {
            "slides": 0,
            "slide_width": None,
            "slide_height": None,
            "aspect_ratio": None,
            "shapes": 0,
            "meaningful_native_shapes": 0,
            "text_nodes": 0,
            "text_characters": 0,
            "pictures": 0,
            "errors": 0,
            "warnings": 0,
        },
        "slides": [],
        "errors": errors,
        "warnings": warnings,
    }

    if not path.is_file():
        errors.append("PPTX file does not exist")
        report["summary"]["errors"] = 1
        return report
    if path.stat().st_size == 0:
        errors.append("PPTX file is empty")
        report["summary"]["errors"] = 1
        return report

    try:
        package = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"invalid PPTX/ZIP package: {exc}")
        report["summary"]["errors"] = 1
        return report

    with package:
        presentation = parse_xml_part(package, "ppt/presentation.xml", errors)
        if presentation is None:
            report["summary"]["errors"] = len(errors)
            return report

        slide_size = presentation.find("p:sldSz", NS)
        slide_width = integer_attribute(slide_size, "cx")
        slide_height = integer_attribute(slide_size, "cy")
        if not slide_width or not slide_height:
            errors.append("presentation has no valid <p:sldSz> dimensions")
            slide_width = slide_width or 0
            slide_height = slide_height or 0
        else:
            ratio = slide_width / slide_height
            report["summary"]["aspect_ratio"] = ratio
            if not math.isclose(ratio, 16 / 9, rel_tol=0.0, abs_tol=1e-6):
                errors.append(
                    f"presentation must be widescreen 16:9, got {slide_width}x{slide_height} ({ratio:.6f}:1)"
                )
        report["summary"]["slide_width"] = slide_width
        report["summary"]["slide_height"] = slide_height

        slide_parts = resolve_slide_parts(package, presentation, errors, warnings)
        report["summary"]["slides"] = len(slide_parts)
        if expected_pages is not None and len(slide_parts) != expected_pages:
            errors.append(f"expected {expected_pages} slide(s), found {len(slide_parts)}")

        for slide_number, part_name in enumerate(slide_parts, start=1):
            slide_report = inspect_slide(
                package,
                part_name,
                slide_number,
                slide_width,
                slide_height,
            )
            report["slides"].append(slide_report)
            for message in slide_report["errors"]:
                errors.append(f"slide {slide_number}: {message}")
            for message in slide_report["warnings"]:
                warnings.append(f"slide {slide_number}: {message}")

    totals = report["summary"]
    for slide_report in report["slides"]:
        counts = slide_report["counts"]
        totals["shapes"] += counts["shapes"]
        totals["meaningful_native_shapes"] += counts["meaningful_native_shapes"]
        totals["text_nodes"] += counts["text_nodes"]
        totals["text_characters"] += counts["text_characters"]
        totals["pictures"] += counts["pictures"]
    if totals["text_nodes"] == 0:
        add_unique(warnings, "presentation contains no native <a:t> text nodes")

    totals["errors"] = len(errors)
    totals["warnings"] = len(warnings)
    report["ok"] = not errors
    return report


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    """Write an indented UTF-8 JSON report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def positive_int(raw: str) -> int:
    """Parse a positive expected-page count."""

    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description="Validate native PPTX OOXML without PowerPoint")
    parser.add_argument("pptx", help="PPTX file to inspect")
    parser.add_argument("--expected-pages", type=positive_int, default=None)
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Optional path for a machine-readable JSON report",
    )
    return parser


def print_report(report: dict[str, Any]) -> None:
    """Print concise human-readable validation results."""

    summary = report["summary"]
    for slide in report["slides"]:
        counts = slide["counts"]
        state = "PASS" if slide["ok"] else "FAIL"
        print(
            f"[{state}] slide {slide['slide']}: "
            f"shapes={counts['shapes']} text={counts['text_nodes']} pictures={counts['pictures']}"
        )
        for error in slide["errors"]:
            print(f"  - {error}")
        for warning in slide["warnings"]:
            print(f"  - WARN: {warning}")
    for error in report["errors"]:
        if not error.startswith("slide "):
            print(f"ERROR: {error}")
    for warning in report["warnings"]:
        if not warning.startswith("slide "):
            print(f"WARN: {warning}")
    print(
        "PPTX validation: "
        f"slides={summary['slides']} shapes={summary['shapes']} "
        f"text={summary['text_nodes']} pictures={summary['pictures']} "
        f"errors={summary['errors']} warnings={summary['warnings']}"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the PPTX validator CLI."""

    args = build_parser().parse_args(argv)
    report = validate_pptx(Path(args.pptx), args.expected_pages)
    print_report(report)
    if args.report_json:
        try:
            write_json_report(args.report_json, report)
        except OSError as exc:
            print(f"ERROR: could not write JSON report {args.report_json}: {exc}", file=sys.stderr)
            return 1
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
