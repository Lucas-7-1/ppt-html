#!/usr/bin/env python3
"""Validate SVG slide artifacts, optionally enforcing PPTX-safe SVG.

Default mode preserves the original delivery contract: valid XML, an ``svg``
root, a 1280x720 viewBox, optional matching width/height, and no scripts.
``--pptx-safe`` adds a conservative allowlist for SVG that can be converted to
native editable PowerPoint shapes without a raster fallback.

Examples:
    python3 scripts/svg_validator.py OUTPUT_DIR/svg --expected-pages 8
    python3 scripts/svg_validator.py slide-1.svg --pptx-safe
    python3 scripts/svg_validator.py slide-1.svg --pptx-safe --report-json report.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_VIEWBOX = (0.0, 0.0, 1280.0, 720.0)
EXPECTED_VIEWBOX_TEXT = "0 0 1280 720"
VIEWBOX_RE = re.compile(r"[\s,]+")
DIMENSION_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?:px)?\s*$",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
PATH_TOKEN_RE = re.compile(
    r"([mMzZlLhHvVcCsSqQtTaA])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
)
URL_FUNCTION_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
REMOTE_SCHEMES = {"http", "https", "ftp", "ftps", "ws", "wss"}
XLINK_NS = "http://www.w3.org/1999/xlink"

PPTX_SAFE_ELEMENTS = {
    "svg",
    "g",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "rect",
    "text",
    "tspan",
    "circle",
    "ellipse",
    "line",
    "path",
    "polygon",
    "polyline",
    "image",
    "use",
}
HARMLESS_METADATA_ELEMENTS = {"title", "desc", "metadata"}
BANNED_ELEMENTS = {
    "foreignObject",
    "script",
    "filter",
    "mask",
    "clipPath",
    "pattern",
    "style",
}
UNSUPPORTED_EFFECT_ATTRIBUTES = {
    "clip-path",
    "filter",
    "mask",
    "marker-start",
    "marker-mid",
    "marker-end",
    "vector-effect",
}
TEXT_HINT_ATTRIBUTES = {"data-text", "data-label"}
SUPPORTED_DATA_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/bmp",
    "image/tiff",
}


def natural_key(path: Path) -> list[object]:
    """Return a natural filename sorting key."""

    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    ]


def local_name(tag: object) -> str:
    """Return an XML local name and tolerate comments or processing nodes."""

    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def parse_numbers(raw: str) -> tuple[float, ...] | None:
    """Parse a comma/whitespace-separated number list."""

    parts = [part for part in VIEWBOX_RE.split(raw.strip()) if part]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        return None
    return values if all(math.isfinite(value) for value in values) else None


def dimension_value(raw: str | None) -> float | None:
    """Parse a unitless or px SVG length."""

    if raw is None:
        return None
    match = DIMENSION_RE.fullmatch(raw)
    if not match:
        return None
    value = float(match.group(1))
    return value if math.isfinite(value) else None


def add_unique(items: list[str], message: str) -> None:
    """Append one diagnostic while suppressing exact duplicates."""

    if message not in items:
        items.append(message)


def element_label(element: ET.Element) -> str:
    """Build a concise element label for diagnostics."""

    tag = local_name(element.tag) or "unknown"
    identifier = element.attrib.get("id")
    return f"<{tag} id={identifier!r}>" if identifier else f"<{tag}>"


def href_value(element: ET.Element) -> str:
    """Return SVG2 or legacy xlink href content."""

    return element.attrib.get("href") or element.attrib.get(f"{{{XLINK_NS}}}href", "")


def parse_style(raw: str) -> dict[str, str]:
    """Parse enough inline CSS to identify hidden elements safely."""

    result: dict[str, str] = {}
    for declaration in raw.split(";"):
        if ":" not in declaration:
            continue
        key, value = declaration.split(":", 1)
        result[key.strip().lower()] = value.strip().lower()
    return result


def is_hidden(element: ET.Element, inherited_hidden: bool = False) -> bool:
    """Return whether presentation attributes make an element non-visible."""

    if inherited_hidden:
        return True
    style = parse_style(element.attrib.get("style", ""))
    display = element.attrib.get("display", style.get("display", "")).strip().lower()
    visibility = element.attrib.get("visibility", style.get("visibility", "")).strip().lower()
    opacity_raw = element.attrib.get("opacity", style.get("opacity", "1"))
    try:
        opacity = float(opacity_raw)
    except ValueError:
        opacity = 1.0
    return display == "none" or visibility in {"hidden", "collapse"} or opacity <= 0


def parse_safe_transform(raw: str, tag: str) -> tuple[float, float, float] | None:
    """Parse the simple transforms faithfully supported by ``svg2pptx.py``."""

    text = raw.strip()
    if not text:
        return (0.0, 0.0, 1.0)

    match = re.fullmatch(r"(translate|scale)\s*\(([^()]*)\)", text)
    if not match or tag != "g":
        return None
    kind, body = match.groups()
    numbers = [float(value) for value in NUMBER_RE.findall(body)]
    residue = NUMBER_RE.sub("", body).replace(",", "").strip()
    if residue or not all(math.isfinite(value) for value in numbers):
        return None

    if kind == "translate" and len(numbers) in {1, 2}:
        return (numbers[0], numbers[1] if len(numbers) == 2 else 0.0, 1.0)
    if kind == "scale" and len(numbers) == 1 and numbers[0] > 0:
        return (0.0, 0.0, numbers[0])
    return None


def validate_uri(
    element: ET.Element,
    attr_name: str,
    value: str,
    errors: list[str],
) -> None:
    """Reject remote, executable, and non-local URL references."""

    label = element_label(element)
    stripped = value.strip()
    if not stripped:
        return

    for match in URL_FUNCTION_RE.finditer(stripped):
        target = match.group(2).strip()
        if not target.startswith("#"):
            add_unique(errors, f"{label} {attr_name} contains non-local url({target!r})")

    if local_name(attr_name) not in {"href", "src"}:
        return
    if stripped.startswith("//"):
        add_unique(errors, f"{label} {attr_name} uses a remote protocol-relative URL")
        return
    parsed = urllib.parse.urlparse(stripped)
    scheme = parsed.scheme.lower()
    if scheme in REMOTE_SCHEMES or scheme == "javascript":
        add_unique(errors, f"{label} {attr_name} uses unsupported remote/executable URL {stripped!r}")
    elif scheme and scheme not in {"data", "file"}:
        add_unique(errors, f"{label} {attr_name} uses unsupported URL scheme {scheme!r}")


def validate_image_reference(path: Path, element: ET.Element, errors: list[str]) -> None:
    """Validate one image reference and require local, convertible image data."""

    label = element_label(element)
    href = href_value(element).strip()
    if not href:
        add_unique(errors, f"{label} must declare href or xlink:href")
        return
    if href.startswith("data:"):
        match = re.match(r"data:([^;,]+);base64,", href, re.IGNORECASE)
        if not match:
            add_unique(errors, f"{label} data URI must be base64-encoded image data")
            return
        media_type = match.group(1).lower()
        if media_type not in SUPPORTED_DATA_IMAGE_TYPES:
            add_unique(errors, f"{label} uses unsupported embedded image type {media_type!r}")
        return

    parsed = urllib.parse.urlparse(href)
    if parsed.scheme.lower() in REMOTE_SCHEMES or href.startswith("//"):
        return  # A generic URL diagnostic is already emitted.
    if parsed.scheme and parsed.scheme.lower() not in {"file"}:
        return

    if parsed.scheme.lower() == "file":
        decoded = urllib.parse.unquote(parsed.path)
        if parsed.netloc:
            decoded = f"//{parsed.netloc}{decoded}"
        if re.match(r"^/[A-Za-z]:/", decoded):
            decoded = decoded[1:]
        image_path = Path(decoded)
    else:
        decoded = urllib.parse.unquote(href.split("#", 1)[0])
        image_path = Path(decoded)
        if not image_path.is_absolute():
            image_path = path.parent / image_path
    if not image_path.is_file():
        add_unique(errors, f"{label} references missing local image {href!r}")


def validate_preserve_aspect_ratio(element: ET.Element, errors: list[str]) -> None:
    """Accept image aspect-ratio modes implemented by the converter."""

    raw = element.attrib.get("preserveAspectRatio")
    if raw is None:
        return
    value = " ".join(raw.split())
    if value == "none":
        return
    if re.fullmatch(r"x(?:Min|Mid|Max)Y(?:Min|Mid|Max)(?: (?:meet|slice))?", value):
        return
    add_unique(
        errors,
        f"{element_label(element)} has unsupported preserveAspectRatio={raw!r}",
    )


def validate_path_data(element: ET.Element, errors: list[str]) -> None:
    """Reject malformed paths; fontTools handles all SVG path commands."""

    d = element.attrib.get("d", "")
    label = element_label(element)
    if not d.strip():
        add_unique(errors, f"{label} must declare non-empty path data")
        return
    tokens = PATH_TOKEN_RE.findall(d)
    residue = PATH_TOKEN_RE.sub("", d)
    residue = re.sub(r"[\s,]", "", residue)
    if residue:
        add_unique(errors, f"{label} contains unsupported or malformed path data near {residue[:24]!r}")
    try:
        from fontTools.svgLib.path import parse_path
        from fontTools.pens.recordingPen import RecordingPen
        parse_path(d, RecordingPen())
    except (ValueError, IndexError, AssertionError) as exc:
        add_unique(errors, f"{label} has invalid path data: {exc}")


def validate_pptx_safe(
    path: Path,
    root: ET.Element,
    raw_text: str,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Apply conservative SVG-to-native-PPTX compatibility checks."""

    counts: Counter[str] = Counter()
    ids: dict[str, ET.Element] = {}
    duplicate_ids: set[str] = set()
    native_text_elements = 0
    native_text_characters = 0
    visible_native_text_characters = 0
    full_slide_images = 0
    full_slide_image_labels: list[str] = []
    meaningful_native_graphics = 0
    root_content_children = [
        child
        for child in list(root)
        if local_name(child.tag) not in {"defs", "title", "desc", "metadata"}
        and not is_hidden(child)
    ]

    if root.attrib.get("viewBox", "").strip() != EXPECTED_VIEWBOX_TEXT:
        add_unique(errors, f'PPTX-safe mode requires exact viewBox="{EXPECTED_VIEWBOX_TEXT}"')
    if re.search(r"<\?xml-stylesheet\b", raw_text, re.IGNORECASE):
        add_unique(errors, "external XML stylesheets are not allowed in PPTX-safe SVG")
    if re.search(r"@import\b", raw_text, re.IGNORECASE):
        add_unique(errors, "CSS @import is not allowed in PPTX-safe SVG")

    def walk(
        element: ET.Element,
        *,
        in_metadata: bool = False,
        in_text: bool = False,
        hidden: bool = False,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        scale: float = 1.0,
    ) -> None:
        nonlocal native_text_elements, native_text_characters, visible_native_text_characters
        nonlocal full_slide_images
        nonlocal meaningful_native_graphics

        tag = local_name(element.tag)
        if not tag:
            return
        counts[tag] += 1
        label = element_label(element)
        metadata_here = in_metadata or tag == "metadata"
        text_here = in_text or tag in {"text", "tspan"}
        hidden_here = is_hidden(element, hidden)

        identifier = element.attrib.get("id")
        if identifier:
            if identifier in ids:
                duplicate_ids.add(identifier)
            else:
                ids[identifier] = element

        if tag in BANNED_ELEMENTS:
            add_unique(errors, f"{label} is forbidden in PPTX-safe SVG")
        elif not metadata_here and tag not in PPTX_SAFE_ELEMENTS and tag not in HARMLESS_METADATA_ELEMENTS:
            add_unique(errors, f"{label} is not in the PPTX-safe element allowlist")

        style_attr = element.attrib.get("style")
        if style_attr is not None:
            add_unique(errors, f"{label} uses a style attribute; use SVG presentation attributes")

        for raw_name, value in element.attrib.items():
            name = local_name(raw_name)
            lower_name = name.lower()
            if lower_name.startswith("on"):
                add_unique(errors, f"{label} uses forbidden event handler attribute {name!r}")
            if name in UNSUPPORTED_EFFECT_ATTRIBUTES:
                add_unique(errors, f"{label} uses unsupported attribute {name!r}")
            if name == "class":
                add_unique(warnings, f"{label} class names are not used during PPTX conversion")
            validate_uri(element, raw_name, value, errors)

        transform = element.attrib.get("transform")
        local_transform = (0.0, 0.0, 1.0)
        if transform:
            local_transform = parse_safe_transform(transform, tag)  # type: ignore[assignment]
            if local_transform is None:
                add_unique(
                    errors,
                    f"{label} has unsupported/complex transform={transform!r}; "
                    "only one g translate or positive uniform scale is allowed; "
                    "matrix, skew, rotate, negative/non-uniform scale, and transform chains are rejected",
                )
                local_transform = (0.0, 0.0, 1.0)
            elif (
                tag == "g"
                and re.match(r"\s*scale\s*\(", transform)
                and len(root_content_children) == 1
                and root_content_children[0] is element
            ):
                add_unique(errors, f"{label} uses a forbidden whole-slide scale wrapper")

        dx, dy, local_scale = local_transform
        child_offset_x = offset_x + dx * scale
        child_offset_y = offset_y + dy * scale
        child_scale = scale * local_scale

        if tag in {"text", "tspan"}:
            native_text_elements += 1
            text_value = "".join(element.itertext()).strip() if tag == "text" else (element.text or "").strip()
            native_text_characters += len(text_value)
            if not hidden_here:
                visible_native_text_characters += len(text_value)
            for attr in ("dx", "rotate", "textPath"):
                if attr in element.attrib:
                    add_unique(errors, f"{label} uses unsupported text positioning attribute {attr!r}")
            if "dy" in element.attrib and dimension_value(element.attrib.get("dy")) is None:
                add_unique(errors, f"{label} dy must be one finite unitless/px value")
        elif element.text and element.text.strip() and not metadata_here:
            add_unique(errors, f"textual content in {label} must remain inside <text>/<tspan>")

        if tag in {"path", "polygon", "polyline", "image", "use"}:
            if any(element.attrib.get(name, "").strip() for name in TEXT_HINT_ATTRIBUTES) or element.attrib.get("role") == "text":
                add_unique(errors, f"{label} appears to encode text graphically; keep it as <text>/<tspan>")

        if tag == "path":
            validate_path_data(element, errors)
            if not hidden_here:
                meaningful_native_graphics += 1
        elif tag in {"polygon", "polyline"}:
            values = [float(value) for value in NUMBER_RE.findall(element.attrib.get("points", ""))]
            minimum = 6 if tag == "polygon" else 4
            if len(values) < minimum or len(values) % 2:
                add_unique(errors, f"{label} has invalid points data")
            elif not hidden_here:
                meaningful_native_graphics += 1
        elif tag == "rect":
            x = dimension_value(element.attrib.get("x", "0"))
            y = dimension_value(element.attrib.get("y", "0"))
            width = dimension_value(element.attrib.get("width"))
            height = dimension_value(element.attrib.get("height"))
            if x is None or y is None or width is None or height is None or width <= 0 or height <= 0:
                add_unique(errors, f"{label} requires finite numeric x/y/width/height values")
            elif not hidden_here:
                final_x = offset_x + x * scale
                final_y = offset_y + y * scale
                final_width = width * scale
                final_height = height * scale
                is_canvas_background = (
                    final_x <= 25.6 and final_y <= 14.4
                    and final_width >= 1216 and final_height >= 684
                )
                if not is_canvas_background:
                    meaningful_native_graphics += 1
        elif tag in {"circle", "ellipse", "line"} and not hidden_here:
            meaningful_native_graphics += 1
        elif tag == "image":
            validate_image_reference(path, element, errors)
            validate_preserve_aspect_ratio(element, errors)
            x = dimension_value(element.attrib.get("x", "0"))
            y = dimension_value(element.attrib.get("y", "0"))
            width = dimension_value(element.attrib.get("width"))
            height = dimension_value(element.attrib.get("height"))
            if x is None or y is None or width is None or height is None or width <= 0 or height <= 0:
                add_unique(errors, f"{label} requires finite numeric x/y/width/height values")
            else:
                final_x = offset_x + x * scale
                final_y = offset_y + y * scale
                final_width = width * scale
                final_height = height * scale
                covers_slide = (
                    final_x <= 25.6
                    and final_y <= 14.4
                    and final_width >= 1216
                    and final_height >= 684
                )
                if covers_slide and not hidden_here:
                    full_slide_images += 1
                    full_slide_image_labels.append(label)
        elif tag == "use":
            href = href_value(element).strip()
            if not href.startswith("#"):
                add_unique(errors, f"{label} must use a local fragment href")
        elif tag in {"linearGradient", "radialGradient"}:
            for attr in ("gradientTransform", "spreadMethod"):
                if attr in element.attrib:
                    add_unique(errors, f"{label} uses unsupported gradient attribute {attr!r}")

        for child in list(element):
            child_tag = local_name(child.tag)
            if text_here and child_tag not in {"tspan", "title", "desc"}:
                add_unique(errors, f"<{child_tag}> is not valid native text content inside {label}")
            walk(
                child,
                in_metadata=metadata_here,
                in_text=text_here,
                hidden=hidden_here,
                offset_x=child_offset_x,
                offset_y=child_offset_y,
                scale=child_scale,
            )
            if child.tail and child.tail.strip() and not text_here and not metadata_here:
                add_unique(errors, f"textual tail content under {label} must remain inside <text>/<tspan>")

    walk(root)

    for identifier in sorted(duplicate_ids):
        add_unique(errors, f"duplicate SVG id {identifier!r} makes references and shape names ambiguous")
    for element in root.iter():
        if local_name(element.tag) != "use":
            continue
        href = href_value(element).strip()
        if href.startswith("#") and href[1:] not in ids:
            add_unique(errors, f"{element_label(element)} references missing id {href[1:]!r}")

    if native_text_elements == 0:
        add_unique(warnings, "no native <text>/<tspan> elements were detected")
    if full_slide_images:
        if visible_native_text_characters > 0 or meaningful_native_graphics > 0:
            add_unique(
                warnings,
                "full-slide image is treated as a background because native editable overlay exists",
            )
        else:
            for label in full_slide_image_labels:
                add_unique(errors, f"{label} is a full-slide raster wrapper without native editable content")

    return {
        "element_counts": dict(sorted(counts.items())),
        "native_text_elements": native_text_elements,
        "native_text_characters": native_text_characters,
        "visible_native_text_characters": visible_native_text_characters,
        "images": counts.get("image", 0),
        "full_slide_images": full_slide_images,
        "meaningful_native_graphics": meaningful_native_graphics,
        "semantic_ids": len(ids),
    }


def validate_svg_report(path: Path, *, pptx_safe: bool = False) -> dict[str, Any]:
    """Validate one SVG and return a JSON-serializable report."""

    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "bytes": 0,
        "viewBox": None,
        "width": None,
        "height": None,
    }
    report: dict[str, Any] = {
        "path": str(path),
        "pptx_safe": pptx_safe,
        "ok": False,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }

    if not path.is_file():
        errors.append("file does not exist")
        return report
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        errors.append(f"could not read file: {exc}")
        return report
    summary["bytes"] = len(raw_bytes)
    if not raw_bytes:
        errors.append("file is empty")
        return report

    try:
        root = ET.fromstring(raw_bytes)
    except (ET.ParseError, ValueError) as exc:
        errors.append(f"invalid XML/SVG: {exc}")
        return report

    root_tag = local_name(root.tag)
    summary["root"] = root_tag
    if root_tag != "svg":
        errors.append(f"root element must be <svg>, got <{root_tag}>")

    view_box = root.attrib.get("viewBox")
    summary["viewBox"] = view_box
    if not view_box:
        errors.append(f'missing required viewBox="{EXPECTED_VIEWBOX_TEXT}"')
    else:
        values = parse_numbers(view_box)
        if values != EXPECTED_VIEWBOX:
            errors.append(f'viewBox must be "{EXPECTED_VIEWBOX_TEXT}", got {view_box!r}')

    for attr, expected in (("width", 1280.0), ("height", 720.0)):
        raw = root.attrib.get(attr)
        summary[attr] = raw
        if raw is None:
            continue
        actual = dimension_value(raw)
        if actual != expected:
            errors.append(
                f"{attr} must be {int(expected)} or {int(expected)}px when declared, got {raw!r}"
            )

    if not pptx_safe:
        if any(local_name(element.tag) == "script" for element in root.iter()):
            errors.append("script elements are not allowed in the SVG intermediate")
    else:
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        summary.update(validate_pptx_safe(path, root, raw_text, errors, warnings))

    report["ok"] = not errors
    return report


def validate_svg(path: Path) -> list[str]:
    """Preserve the original import API by returning default-mode errors."""

    return list(validate_svg_report(path)["errors"])


def collect_targets(target: Path) -> list[Path]:
    """Collect one SVG or the workflow's ``slide-*.svg`` directory files."""

    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(target.glob("slide-*.svg"), key=natural_key)
    return []


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    """Write an indented UTF-8 JSON report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def nonnegative_int(raw: str) -> int:
    """Parse a non-negative integer CLI value."""

    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the validator command-line parser."""

    parser = argparse.ArgumentParser(description="Validate PPTX-safe SVG slide intermediates")
    parser.add_argument("target", help="SVG file or directory containing slide-*.svg")
    parser.add_argument("--expected-pages", type=nonnegative_int, default=None)
    parser.add_argument(
        "--pptx-safe",
        action="store_true",
        help="Require conservative SVG features supported as native PowerPoint objects",
    )
    parser.add_argument(
        "--report-json",
        "--report",
        dest="report_json",
        type=Path,
        help="Optional path for a machine-readable JSON report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the SVG validator CLI."""

    args = build_parser().parse_args(argv)
    target = Path(args.target)
    files = collect_targets(target)
    global_errors: list[str] = []
    reports: list[dict[str, Any]] = []

    if not files:
        message = f"no SVG files found at {target}"
        global_errors.append(message)
        print(f"ERROR: {message}", file=sys.stderr)
    else:
        for path in files:
            report = validate_svg_report(path, pptx_safe=args.pptx_safe)
            reports.append(report)
            if report["errors"]:
                print(f"[FAIL] {path}")
                for error in report["errors"]:
                    print(f"  - {error}")
            else:
                print(f"[PASS] {path}")
            for warning in report["warnings"]:
                print(f"  - WARN: {warning}")

    if args.expected_pages is not None and len(files) != args.expected_pages:
        message = f"expected {args.expected_pages} SVG pages, found {len(files)}"
        global_errors.append(message)
        print(f"[FAIL] {message}")

    failed_files = sum(1 for report in reports if report["errors"])
    ok = not global_errors and failed_files == 0
    payload = {
        "command": "svg-validator",
        "ok": ok,
        "target": str(target),
        "pptx_safe": bool(args.pptx_safe),
        "expected_pages": args.expected_pages,
        "summary": {
            "files": len(files),
            "passed": len(reports) - failed_files,
            "failed": failed_files,
            "errors": len(global_errors) + sum(len(report["errors"]) for report in reports),
            "warnings": sum(len(report["warnings"]) for report in reports),
        },
        "files": reports,
        "errors": global_errors,
        "warnings": [],
    }

    if args.report_json:
        try:
            write_json_report(args.report_json, payload)
        except OSError as exc:
            print(f"ERROR: could not write JSON report {args.report_json}: {exc}", file=sys.stderr)
            ok = False

    print(f"SVG validation: {len(files)} file(s), FAIL={failed_files + len(global_errors)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
