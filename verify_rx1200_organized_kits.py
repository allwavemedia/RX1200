#!/usr/bin/env python3

from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import wave
import zipfile
from array import array
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from rx1200_organizer import (
    COLLECTIONS,
    collect_presets,
    extract_params,
    extract_samples,
    load_xml,
    pad_to_display,
    pad_to_mpc,
)


EXPECTED_PREVIEW_SAMPLE_RATE = 44100
EXPECTED_PREVIEW_CHANNELS = 2
MIN_PREVIEW_DURATION_SECONDS = 0.25
MIN_PREVIEW_PEAK = 64
MIN_PREVIEW_RMS = 8.0
DEFAULT_BUILD_ROOT_NAME = "RX-1200 Expansion"
LEGACY_BUILD_ROOT_NAME = "_MPC_Expansion"


def default_build_root(root: Path) -> Path:
    preferred = root / DEFAULT_BUILD_ROOT_NAME
    legacy = root / LEGACY_BUILD_ROOT_NAME
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Verify organized RX1200 kit outputs against the source presets.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=root,
        help="Root directory containing the RX1200 source collections.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "_Organized_Kits",
        help="Root directory containing generated organized kits.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=root / "_Organized_Kits" / "verification_report.json",
        help="Destination path for the verification report.",
    )
    parser.add_argument(
        "--build-root",
        type=Path,
        default=default_build_root(root),
        help="Optional root directory containing generated MPC program files and copied samples.",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        help="Optional prior verification report to compare against for regression detection.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_relative_report_path(value: Any) -> bool:
    return isinstance(value, str) and value != "" and not Path(value).is_absolute()


def collection_output_directory_name(collection_name: str | None, fallback_name: str) -> str:
    if isinstance(collection_name, str) and collection_name.strip():
        return collection_name.replace("&", "And").replace("  ", " ").strip()
    return fallback_name


def read_builder_report(build_root: Path) -> tuple[dict[str, Any] | None, Path | None]:
    candidate_paths = (
        build_root.parent / f"{build_root.name}_builder_report.json",
        build_root / "builder_report.json",
    )
    for report_path in candidate_paths:
        if report_path.exists():
            return load_json(report_path), report_path
    return None, None


def index_builder_report(builder_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in builder_report.get("programs", []):
        source_path = entry.get("source_rx1200_path")
        if isinstance(source_path, str):
            indexed[source_path] = entry
    return indexed


def inspect_preview_wav(path: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    detail: dict[str, Any] = {}
    if not path.exists():
        return [f"preview file is missing: {path}"], detail

    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            raw_frames = handle.readframes(frame_count)
    except wave.Error as exc:
        return [f"preview file is not a valid WAV: {path} ({exc})"], detail

    detail["channels"] = channels
    detail["sample_width"] = sample_width
    detail["sample_rate"] = sample_rate
    detail["frame_count"] = frame_count
    detail["duration_seconds"] = round(frame_count / sample_rate, 4) if sample_rate else 0.0

    if frame_count <= 0:
        issues.append(f"preview WAV has no audio frames: {path}")
        return issues, detail
    if sample_width != 2:
        issues.append(f"preview WAV sample width is not 16-bit PCM: {path}")
        return issues, detail
    if channels != EXPECTED_PREVIEW_CHANNELS:
        issues.append(f"preview WAV channel count is {channels}, expected {EXPECTED_PREVIEW_CHANNELS}: {path}")
    if sample_rate != EXPECTED_PREVIEW_SAMPLE_RATE:
        issues.append(f"preview WAV sample rate is {sample_rate}, expected {EXPECTED_PREVIEW_SAMPLE_RATE}: {path}")
    if detail["duration_seconds"] < MIN_PREVIEW_DURATION_SECONDS:
        issues.append(f"preview WAV is too short to be a useful preview: {path}")

    samples = array("h")
    samples.frombytes(raw_frames)
    peak = max((abs(value) for value in samples), default=0)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0
    detail["peak_sample"] = peak
    detail["rms"] = round(rms, 4)

    if peak < MIN_PREVIEW_PEAK or rms < MIN_PREVIEW_RMS:
        issues.append(f"preview WAV appears silent or near-silent: {path}")

    return issues, detail


def validate_preview_wav(path: Path) -> list[str]:
    issues, _ = inspect_preview_wav(path)
    return issues


def validate_xtd_file(path: Path) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"xtd file is missing: {path}"]
    try:
        raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        return [f"xtd file is not a valid gzip-compressed text payload: {path} ({exc})"]

    lines = raw.splitlines()
    expected_prefix = ["ACVS", "3.7.0.38", "SerialisableTrackData", "json", "Linux"]
    if lines[:5] != expected_prefix:
        issues.append(f"xtd header does not match expected MPC 3.x header: {path}")
    try:
        payload = json.loads(raw[raw.index("{") :])
    except Exception as exc:  # noqa: BLE001
        issues.append(f"xtd JSON payload could not be parsed: {path} ({exc})")
        return issues

    data = payload.get("data", {})
    program = data.get("program", {})
    drum = program.get("drum", {})
    instruments = drum.get("instruments")
    if not isinstance(instruments, list) or len(instruments) != 128:
        issues.append(f"xtd drum instrument list is missing or not 128 entries: {path}")
    return issues


def validate_xpn_package(path: Path, archive_root: str, expected_preview_paths: set[str]) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"xpn package is missing: {path}"]
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        return [f"xpn package is not a valid ZIP archive: {path} ({exc})"]

    if not any(name.endswith("Expansion.xml") for name in names):
        issues.append(f"xpn package does not contain Expansion.xml: {path}")
    if not any("[Previews]/" in name for name in names):
        issues.append(f"xpn package does not contain preview assets: {path}")
    for preview_path in expected_preview_paths:
        rooted_archive_member = f"{archive_root}/{preview_path}"
        if preview_path not in names and rooted_archive_member not in names:
            issues.append(f"xpn package is missing preview asset {preview_path}: {path}")
    return issues


def validate_artwork(path: Path) -> list[str]:
    if not path.exists():
        return [f"artwork file is missing: {path}"]
    if path.suffix.lower() != ".jpg":
        return [f"artwork file is not a .jpg: {path}"]
    return []


def validate_expansion_manifest(build_root: Path, path: Path, builder_report: dict[str, Any] | None) -> list[str]:
    issues: list[str] = []
    if not path.exists():
        return [f"Expansion.xml is missing: {path}"]
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"Expansion.xml is not valid XML: {path} ({exc})"]

    identifier = root.findtext("Identifier") or root.findtext("identifier")
    if not identifier or "." not in identifier:
        issues.append("Expansion.xml Identifier is missing or not dot-delimited")

    directory = root.findtext("directory")
    if directory is not None and (not directory.strip() or "." not in directory):
        issues.append("Expansion.xml directory is missing or not dot-delimited")

    programs_node = root.find("Programs")
    if programs_node is not None:
        program_nodes = programs_node.findall("Program")
        if builder_report is not None and len(program_nodes) != len(builder_report.get("programs", [])):
            issues.append(
                "Expansion.xml program count does not match builder_report program count"
            )

        for program_node in program_nodes:
            program_path = program_node.findtext("ProgramPath")
            if not is_relative_report_path(program_path):
                issues.append(f"Expansion.xml ProgramPath is not relative: {program_path}")
                continue
            if not (build_root / program_path).exists():
                issues.append(f"Expansion.xml ProgramPath does not exist on disk: {program_path}")
    return issues


def validate_build_artifacts(build_root: Path) -> tuple[list[str], dict[str, Any], dict[str, dict[str, Any]]]:
    issues: list[str] = []
    detail: dict[str, Any] = {"build_root_present": build_root.exists()}
    if not build_root.exists():
        return issues, detail, {}

    builder_report, builder_report_path = read_builder_report(build_root)
    if builder_report is None:
        issues.append("builder report is missing")
        return issues, detail, {}

    detail["builder_report_path"] = builder_report_path.as_posix() if builder_report_path else None
    detail["builder_report_program_count"] = len(builder_report.get("programs", []))
    preview_paths: list[str] = []
    for entry in builder_report.get("programs", []):
        preview_path = entry.get("preview_path")
        if not is_relative_report_path(preview_path):
            issues.append(f"builder report preview_path is not relative: {preview_path}")
            continue
        preview_paths.append(preview_path)
    if len(preview_paths) != len(set(preview_paths)):
        issues.append("builder report contains duplicate preview_path values")
    detail["preview_count"] = len(preview_paths)

    artwork_path_value = builder_report.get("artwork_path")
    expansion_manifest_value = builder_report.get("expansion_manifest_path")
    xpn_path_value = builder_report.get("xpn_path")

    if not is_relative_report_path(artwork_path_value):
        issues.append(f"builder report artwork_path is not relative: {artwork_path_value}")
    else:
        issues.extend(validate_artwork(build_root / artwork_path_value))
        detail["artwork_path"] = artwork_path_value

    if not is_relative_report_path(expansion_manifest_value):
        issues.append(
            f"builder report expansion_manifest_path is not relative: {expansion_manifest_value}"
        )
    else:
        issues.extend(validate_expansion_manifest(build_root, build_root / expansion_manifest_value, builder_report))
        detail["expansion_manifest_path"] = expansion_manifest_value

    if not isinstance(xpn_path_value, str) or xpn_path_value == "":
        issues.append("builder report xpn_path is missing")
    else:
        issues.extend(validate_xpn_package(Path(xpn_path_value), build_root.name, set(preview_paths)))
        detail["xpn_path"] = xpn_path_value

    return issues, detail, index_builder_report(builder_report)


def discover_audit_manifests(output_root: Path) -> dict[str, Path]:
    manifests: dict[str, Path] = {}
    for path in output_root.rglob("kit_audit.json"):
        try:
            payload = load_json(path)
        except Exception as exc:  # noqa: BLE001
            logging.error("Unable to read audit manifest %s: %s", path, exc)
            continue
        source_path = payload.get("source_rx1200_path")
        if not isinstance(source_path, str):
            continue
        manifests[source_path] = path
    return manifests


def validate_builder_pad_map(builder_manifest: dict[str, Any], audit_manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if builder_manifest.get("program_type") == "KEYGROUP":
        keygroups = builder_manifest.get("keygroups")
        if not isinstance(keygroups, list) or not keygroups:
            issues.append("KEYGROUP manifest is missing a non-empty keygroups array")
        return issues

    pads = builder_manifest.get("pads")
    if not isinstance(pads, list):
        return ["DRUM manifest is missing a pads array"]

    audit_pad_map = {
        pad.get("rx_pad"): pad
        for pad in audit_manifest.get("pad_mappings", [])
        if isinstance(pad, dict) and pad.get("rx_pad")
    }
    for pad in pads:
        rx_pad = pad.get("rx_pad")
        mpc_pad = pad.get("mpc_pad")
        sample_file = pad.get("sample_file")
        if rx_pad not in audit_pad_map:
            issues.append(f"builder manifest pad {rx_pad!r} is missing from audit pad_mappings")
            continue
        expected_mpc_pad = audit_pad_map[rx_pad].get("mpc_pad")
        if expected_mpc_pad != mpc_pad:
            issues.append(
                f"builder manifest pad {rx_pad} has mpc_pad {mpc_pad}, expected {expected_mpc_pad}"
            )
        expected_sample_file = audit_pad_map[rx_pad].get("copied_sample_file")
        if expected_sample_file != sample_file:
            issues.append(
                f"builder manifest pad {rx_pad} has sample_file {sample_file}, expected {expected_sample_file}"
            )
        if mpc_pad != pad_to_mpc(rx_pad[0].lower() + rx_pad[1:]):
            issues.append(f"builder manifest pad {rx_pad} has invalid fixed MPC pad mapping {mpc_pad}")
    return issues


def validate_built_program(
    build_root: Path,
    builder_manifest: dict[str, Any],
    audit_manifest: dict[str, Any],
    builder_report_entry: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    detail: dict[str, Any] = {}
    if not build_root.exists():
        detail["build_root_present"] = False
        return issues, detail

    detail["build_root_present"] = True
    sanitized_collection = audit_manifest.get("sanitized_collection_name")
    collection_name = audit_manifest.get("collection_name")
    program_name = builder_manifest.get("program_name")
    if not isinstance(sanitized_collection, str) or not isinstance(program_name, str):
        issues.append("cannot derive built program path because collection or program name is missing")
        return issues, detail

    collection_directory = collection_output_directory_name(collection_name, sanitized_collection)
    collection_root = build_root / collection_directory
    detail["collection_root"] = collection_root.as_posix()

    if builder_report_entry is None:
        issues.append("builder report entry is missing for preset")
        return issues, detail

    report_collection_directory = builder_report_entry.get("collection_directory")
    if isinstance(report_collection_directory, str) and report_collection_directory:
        if report_collection_directory != collection_directory:
            issues.append(
                f"builder report collection_directory {report_collection_directory!r} does not match derived collection directory {collection_directory!r}"
            )

    if builder_manifest.get("program_type") == "DRUM":
        report_program_path = builder_report_entry.get("program_path")
        if report_program_path:
            issues.append("builder report program_path should be empty for DRUM programs")

        report_xtd_path = builder_report_entry.get("xtd_path")
        if not is_relative_report_path(report_xtd_path):
            issues.append(f"builder report xtd_path is not relative: {report_xtd_path}")
        else:
            xtd_path = build_root / report_xtd_path
            detail["xtd_path"] = xtd_path.as_posix()
            expected_xtd_path = collection_root / f"{program_name}.xtd"
            if xtd_path != expected_xtd_path:
                issues.append(
                    f"builder report xtd_path {report_xtd_path} does not match derived drum path"
                )
            issues.extend(validate_xtd_file(xtd_path))
            trackdata_dir = xtd_path.with_name(f"{xtd_path.stem}_[TrackData]")
            detail["xtd_trackdata_path"] = trackdata_dir.as_posix()
            if not trackdata_dir.exists():
                issues.append(f"xtd TrackData folder is missing: {trackdata_dir}")
            for resolved in audit_manifest.get("resolved_samples_copied", []):
                sample_name = Path(resolved.get("destination_sample_file", "")).name
                if not sample_name:
                    issues.append("resolved sample entry is missing destination_sample_file")
                    continue
                destination = trackdata_dir / sample_name
                if not destination.exists():
                    issues.append(f"xtd TrackData sample is missing: {destination}")
    else:
        program_path = collection_root / f"{program_name}.xpm"
        detail["program_path"] = program_path.as_posix()
        if not program_path.exists():
            issues.append(f"built program is missing: {program_path}")
            return issues, detail

        try:
            xml_root = ET.parse(program_path).getroot()
        except ET.ParseError as exc:
            issues.append(f"built program is not valid XML: {exc}")
            return issues, detail

        program_node = xml_root.find("Program")
        if program_node is None:
            issues.append("built program is missing the Program XML node")
            return issues, detail

        expected_program_type = builder_manifest.get("program_type", "").title()
        actual_program_type = program_node.attrib.get("type")
        detail["built_program_type"] = actual_program_type
        if actual_program_type != expected_program_type:
            issues.append(
                f"built program type {actual_program_type!r} does not match manifest program_type {expected_program_type!r}"
            )

        report_program_path = builder_report_entry.get("program_path")
        if not is_relative_report_path(report_program_path):
            issues.append(f"builder report program_path is not relative: {report_program_path}")
        else:
            expected_program_path = build_root / report_program_path
            if expected_program_path != program_path:
                issues.append(
                    f"builder report program_path {report_program_path} does not match derived program path"
                )

        report_xtd_path = builder_report_entry.get("xtd_path")
        if report_xtd_path:
            issues.append("builder report xtd_path should be empty for non-DRUM programs")

    report_preview_path = builder_report_entry.get("preview_path")
    if not is_relative_report_path(report_preview_path):
        issues.append(f"builder report preview_path is not relative: {report_preview_path}")
    else:
        preview_path = build_root / report_preview_path
        detail["preview_path"] = preview_path.as_posix()
        preview_issues, preview_detail = inspect_preview_wav(preview_path)
        issues.extend(preview_issues)
        detail["preview_analysis"] = preview_detail

    return issues, detail


def compare_reports(current_report: dict[str, Any], baseline_report: dict[str, Any]) -> dict[str, Any]:
    comparison: dict[str, Any] = {
        "baseline_report_path": baseline_report.get("report_path"),
        "new_failures": [],
        "resolved_failures": [],
        "changed_program_types": [],
        "changed_issue_counts": [],
        "regressions": [],
    }

    current_failures = {
        item["source_rx1200_path"]: item.get("issues", [])
        for item in current_report.get("failures", [])
        if isinstance(item, dict) and item.get("source_rx1200_path")
    }
    baseline_failures = {
        item["source_rx1200_path"]: item.get("issues", [])
        for item in baseline_report.get("failures", [])
        if isinstance(item, dict) and item.get("source_rx1200_path")
    }

    for source_path in sorted(current_failures):
        if source_path not in baseline_failures:
            comparison["new_failures"].append({
                "source_rx1200_path": source_path,
                "issues": current_failures[source_path],
            })
    for source_path in sorted(baseline_failures):
        if source_path not in current_failures:
            comparison["resolved_failures"].append({
                "source_rx1200_path": source_path,
                "issues": baseline_failures[source_path],
            })

    current_results = {
        item["source_rx1200_path"]: item
        for item in current_report.get("preset_results", [])
        if isinstance(item, dict) and item.get("source_rx1200_path")
    }
    baseline_results = {
        item["source_rx1200_path"]: item
        for item in baseline_report.get("preset_results", [])
        if isinstance(item, dict) and item.get("source_rx1200_path")
    }

    for source_path in sorted(set(current_results) & set(baseline_results)):
        current_result = current_results[source_path]
        baseline_result = baseline_results[source_path]
        if current_result.get("program_type") != baseline_result.get("program_type"):
            comparison["changed_program_types"].append({
                "source_rx1200_path": source_path,
                "before": baseline_result.get("program_type"),
                "after": current_result.get("program_type"),
            })
        if current_result.get("issue_count") != baseline_result.get("issue_count"):
            comparison["changed_issue_counts"].append({
                "source_rx1200_path": source_path,
                "before": baseline_result.get("issue_count"),
                "after": current_result.get("issue_count"),
            })

    if comparison["new_failures"]:
        comparison["regressions"].append("new preset verification failures were introduced")
    if current_report.get("master_summary_checks") and not baseline_report.get("master_summary_checks"):
        comparison["regressions"].append("master_summary checks regressed from clean to failing")
    if comparison["changed_program_types"]:
        comparison["regressions"].append("program_type changed for one or more presets")

    return comparison


def verify_preset(
    preset_path: Path,
    audit_manifest_path: Path | None,
    output_root: Path,
    build_root: Path,
    builder_report_index: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    detail: dict[str, Any] = {
        "source_rx1200_path": preset_path.as_posix(),
        "issues": issues,
    }

    root = load_xml(preset_path)
    _, _, _ = extract_params(root)
    samples = extract_samples(root)
    non_empty_samples = {
        pad_id: sample
        for pad_id, sample in samples.items()
        if not sample.get("is_empty") and sample.get("raw_reference")
    }

    detail["expected_non_empty_pad_count"] = len(non_empty_samples)
    detail["expected_raw_reference_count"] = len(non_empty_samples)

    if audit_manifest_path is None:
        issues.append("missing kit_audit.json for source preset")
        return issues, detail

    if not audit_manifest_path.exists():
        issues.append(f"audit manifest path does not exist: {audit_manifest_path}")
        return issues, detail

    audit_manifest = load_json(audit_manifest_path)
    kit_dir = audit_manifest_path.parent
    builder_manifest_path = kit_dir / "mpc_manifest.json"
    detail["kit_directory"] = kit_dir.as_posix()
    detail["audit_manifest_path"] = audit_manifest_path.as_posix()
    detail["builder_manifest_path"] = builder_manifest_path.as_posix()

    if audit_manifest.get("source_rx1200_path") != preset_path.as_posix():
        issues.append("audit manifest source_rx1200_path does not match source preset path")

    copied_rx1200_path = Path(audit_manifest.get("copied_rx1200_path", ""))
    if not copied_rx1200_path.exists():
        issues.append(f"copied preset is missing: {copied_rx1200_path}")

    referenced_samples_raw = audit_manifest.get("referenced_samples_raw", [])
    if len(referenced_samples_raw) != len(non_empty_samples):
        issues.append(
            f"referenced_samples_raw count {len(referenced_samples_raw)} != expected non-empty source sample count {len(non_empty_samples)}"
        )

    unresolved = audit_manifest.get("unresolved_or_missing_samples", [])
    if unresolved:
        issues.append(f"audit manifest reports {len(unresolved)} unresolved or missing samples")

    if not builder_manifest_path.exists():
        issues.append("builder manifest is missing")
        return issues, detail

    builder_manifest = load_json(builder_manifest_path)
    detail["program_type"] = builder_manifest.get("program_type")
    if builder_manifest.get("original_rx_file") != preset_path.name:
        issues.append("builder manifest original_rx_file does not match source preset filename")

    issues.extend(validate_builder_pad_map(builder_manifest, audit_manifest))
    built_program_issues, built_program_detail = validate_built_program(
        build_root,
        builder_manifest,
        audit_manifest,
        builder_report_index.get(preset_path.as_posix()),
    )
    issues.extend(built_program_issues)
    if built_program_detail:
        detail["built_program"] = built_program_detail

    if builder_manifest.get("program_type") == "DRUM":
        pads = builder_manifest.get("pads", [])
        if len(pads) != len(non_empty_samples):
            issues.append(
                f"builder manifest pads count {len(pads)} != expected non-empty source sample count {len(non_empty_samples)}"
            )
        expected_rx_pads = {pad_to_display(pad_id) for pad_id in non_empty_samples}
        actual_rx_pads = {pad.get("rx_pad") for pad in pads if isinstance(pad, dict)}
        if expected_rx_pads != actual_rx_pads:
            issues.append("builder manifest rx_pad set does not match non-empty source pads")

    for resolved in audit_manifest.get("resolved_samples_copied", []):
        destination_path = resolved.get("destination_path")
        if not destination_path:
            issues.append("resolved sample entry is missing destination_path")
            continue
        if not Path(destination_path).exists():
            issues.append(f"resolved sample destination is missing: {destination_path}")

    sample_dir = kit_dir / "samples"
    if not sample_dir.exists():
        issues.append("samples directory is missing")

    detail["resolved_samples_copied_count"] = len(audit_manifest.get("resolved_samples_copied", []))
    detail["issue_count"] = len(issues)
    return issues, detail


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.source_root = args.source_root.resolve()
    args.output_root = args.output_root.resolve()
    args.report_path = args.report_path.resolve()
    args.build_root = args.build_root.resolve()
    if args.baseline_report:
        args.baseline_report = args.baseline_report.resolve()
    configure_logging(args.verbose)

    presets = collect_presets(args.source_root)
    audit_by_source = discover_audit_manifests(args.output_root)
    master_summary_path = args.output_root / "master_summary.json"

    report: dict[str, Any] = {
        "source_root": args.source_root.as_posix(),
        "output_root": args.output_root.as_posix(),
        "build_root": args.build_root.as_posix(),
        "total_source_presets": len(presets),
        "total_audit_manifests_found": len(audit_by_source),
        "master_summary_path": master_summary_path.as_posix(),
        "master_summary_checks": [],
        "build_artifact_checks": [],
        "preset_results": [],
        "failures": [],
    }

    build_artifact_issues, build_artifact_detail, builder_report_index = validate_build_artifacts(args.build_root)
    report["build_artifact_checks"] = build_artifact_issues
    report["build_artifacts"] = build_artifact_detail

    if master_summary_path.exists():
        master_summary = load_json(master_summary_path)
        if master_summary.get("total_rx1200_files_processed") != len(presets):
            report["master_summary_checks"].append(
                "master_summary total_rx1200_files_processed does not match current source preset count"
            )
        if master_summary.get("total_kits_created") != len(presets):
            report["master_summary_checks"].append(
                "master_summary total_kits_created does not match current source preset count"
            )
    else:
        report["master_summary_checks"].append("master_summary.json is missing")

    for preset_path in presets:
        audit_manifest_path = audit_by_source.get(preset_path.as_posix())
        issues, detail = verify_preset(
            preset_path,
            audit_manifest_path,
            args.output_root,
            args.build_root,
            builder_report_index,
        )
        report["preset_results"].append(detail)
        if issues:
            report["failures"].append({
                "source_rx1200_path": preset_path.as_posix(),
                "issues": issues,
            })

    report["total_failures"] = len(report["failures"])
    if args.baseline_report:
        baseline_report = load_json(args.baseline_report)
        baseline_report["report_path"] = args.baseline_report.as_posix()
        report["comparison"] = compare_reports(report, baseline_report)
    else:
        report["comparison"] = None

    has_regressions = bool(report["comparison"] and report["comparison"].get("regressions"))
    report["status"] = "passed" if not report["failures"] and not report["master_summary_checks"] and not report["build_artifact_checks"] and not has_regressions else "failed"
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    logging.info("Verified %s source presets", len(presets))
    logging.info("Verification failures: %s", report["total_failures"])
    if report["master_summary_checks"]:
        logging.warning("Master summary checks reported %s issues", len(report["master_summary_checks"]))
    if report["build_artifact_checks"]:
        logging.warning("Build artifact checks reported %s issues", len(report["build_artifact_checks"]))
    if report["failures"]:
        return 1
    if report["master_summary_checks"]:
        return 1
    if report["build_artifact_checks"]:
        return 1
    if has_regressions:
        logging.warning("Comparison detected %s regressions", len(report["comparison"]["regressions"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())