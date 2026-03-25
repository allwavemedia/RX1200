#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import unescape
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET


COLLECTIONS = ("Ambient", "Factory Collection", "Drum & Bass")
PAD_SEQUENCE = [
    *(f"a{index}" for index in range(1, 9)),
    *(f"b{index}" for index in range(1, 9)),
    *(f"c{index}" for index in range(1, 9)),
    *(f"d{index}" for index in range(1, 9)),
]
PAD_FIELDS = (
    "pitch",
    "decay",
    "level",
    "pan",
    "output",
    "filter",
    "finetune",
    "gain",
    "mono",
    "speed",
)
FILTER_TYPE_MAP = {
    0: "Off",
    1: "LP 12dB",
    2: "LP 24dB",
    3: "Dyn",
}
FILTER_ENVELOPE_AMOUNT_MAP = {
    "Off": 0.0,
    "LP 12dB": 0.18,
    "LP 24dB": 0.24,
    "Dyn": 0.58,
}
SPEED_SEMITONE_MAP = {
    1: 0.0,
    2: 5.45,
    3: 12.0,
    4: 19.02,
}
RX_PITCH_CENTER = 64.0
RX_PITCH_STEPS_PER_SEMITONE = 8.0
DECAY_MIN_MS = 50.0
DECAY_MAX_MS = 8000.0


@dataclass
class ResolveResult:
    source_path: Path | None
    relative_source_path: str | None
    resolved_by: str | None
    error: str | None


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Organize RX1200 presets into MPC-safe per-kit folders.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=root,
        help="Root directory containing the Ambient, Factory Collection, and Drum & Bass folders.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "_Organized_Kits",
        help="Destination root for organized kits.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing destination kit folders.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def sanitize_name(name: str, replacement: str = "_") -> str:
    text = name.replace("&", " and ")
    text = re.sub(r"\s+", replacement, text.strip())
    text = re.sub(r"[^A-Za-z0-9_-]", replacement, text)
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("_-")
    return text or "unnamed"


def unique_name(base_name: str, used_names: set[str]) -> tuple[str, str | None]:
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name, None

    suffix = 2
    while True:
        candidate = f"{base_name}_{suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate, candidate
        suffix += 1


def clamp_int(value: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(value))))


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def pad_to_display(pad_id: str) -> str:
    return f"{pad_id[0].upper()}{pad_id[1:]}"


def pad_to_mpc(pad_id: str) -> str:
    bank = pad_id[0].lower()
    index = int(pad_id[1:])
    if bank == "a":
        return f"A{index:02d}"
    if bank == "b":
        return f"A{index + 8:02d}"
    if bank == "c":
        return f"B{index:02d}"
    if bank == "d":
        return f"B{index + 8:02d}"
    raise ValueError(f"Unsupported pad id: {pad_id}")


def pitch_to_semitones(pitch: float | None) -> float:
    if pitch is None:
        return 0.0
    midi_like_value = round(max(0.0, min(1.0, pitch)) * 127.0)
    return (midi_like_value - RX_PITCH_CENTER) / RX_PITCH_STEPS_PER_SEMITONE


def finetune_to_cents(finetune: float | None) -> float:
    if finetune is None:
        return 0.0
    return (finetune - 0.5) * 100.0


def split_tuning(total_semitones: float) -> tuple[int, int]:
    semi = clamp_int(round(total_semitones), -24, 24)
    fine = clamp_int((total_semitones - semi) * 100.0, -50, 50)
    return semi, fine


def speed_to_semitones(speed: float | None) -> float:
    if speed is None:
        return 0.0
    rounded = int(round(speed))
    return SPEED_SEMITONE_MAP.get(rounded, 0.0)


def level_to_volume(level: float | None) -> int:
    if level is None:
        return 100
    return clamp_int(level * 127.0, 0, 127)


def pan_to_normalized(pan: float | None) -> float:
    if pan is None:
        return 0.5
    return max(0.0, min(1.0, pan))


def decay_to_ms(decay: float | None) -> int:
    if decay is None:
        return 1500
    bounded = max(0.0, min(1.0, decay))
    scaled = DECAY_MIN_MS * ((DECAY_MAX_MS / DECAY_MIN_MS) ** bounded)
    return clamp_int(scaled, int(DECAY_MIN_MS), int(DECAY_MAX_MS))


def output_to_mute_group(output_value: float | None) -> int:
    if output_value is None:
        return 1
    return clamp_int(output_value + 1.0, 1, 8)


def filter_to_manifest(filter_value: float | None) -> tuple[str, int, float]:
    if filter_value is None:
        return "Off", 127, 0.0
    filter_index = int(round(filter_value))
    filter_type = FILTER_TYPE_MAP.get(filter_index, "Off")
    if filter_type == "Off":
        return filter_type, 127, FILTER_ENVELOPE_AMOUNT_MAP[filter_type]
    if filter_type == "LP 12dB":
        return filter_type, 96, FILTER_ENVELOPE_AMOUNT_MAP[filter_type]
    if filter_type == "LP 24dB":
        return filter_type, 84, FILTER_ENVELOPE_AMOUNT_MAP[filter_type]
    return filter_type, 108, FILTER_ENVELOPE_AMOUNT_MAP[filter_type]


def is_probably_melodic(pad_records: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    non_empty = [record for record in pad_records if record["raw_reference"]]
    if len(non_empty) < 4:
        return False, {"reason": "not_enough_non_empty_pads"}

    counts = Counter(record["raw_reference"] for record in non_empty)
    if len(counts) != 1:
        return False, {
            "reason": "multiple_unique_samples",
            "unique_sample_count": len(counts),
        }

    pitch_variants = {
        (
            round(record["parameters"].get("pitch") or 0.0, 6),
            round(record["parameters"].get("finetune") or 0.0, 6),
        )
        for record in non_empty
    }
    if len(pitch_variants) < 4:
        return False, {
            "reason": "insufficient_pitch_variants",
            "pitch_variant_count": len(pitch_variants),
        }

    return True, {
        "reason": "single_sample_reused_with_multiple_tunings",
        "pitch_variant_count": len(pitch_variants),
        "shared_sample": next(iter(counts)),
        "pad_count": len(non_empty),
    }


def load_xml(path: Path) -> ET.Element:
    tree = ET.parse(path)
    return tree.getroot()


def extract_params(root: ET.Element) -> tuple[dict[str, float | str], dict[str, dict[str, float | str]], dict[str, float | str]]:
    raw_params: dict[str, float | str] = {}
    pad_params: dict[str, dict[str, float | str]] = {pad: {} for pad in PAD_SEQUENCE}
    leftover_params: dict[str, float | str] = {}

    for param in root.findall("PARAM"):
        param_id = param.attrib.get("id", "")
        value_attr = param.attrib.get("value")
        numeric_value = to_float(value_attr)
        value: float | str = numeric_value if numeric_value is not None else (value_attr or "")
        raw_params[param_id] = value

        matched = False
        for field in PAD_FIELDS:
            field_prefix = f"{field}_"
            if not param_id.startswith(field_prefix):
                continue
            suffix = param_id[len(field_prefix):]
            if suffix in pad_params:
                pad_params[suffix][field] = value
                matched = True
                break
        if matched:
            continue
        leftover_params[param_id] = value

    return raw_params, pad_params, leftover_params


def extract_samples(root: ET.Element) -> dict[str, dict[str, Any]]:
    samples: dict[str, dict[str, Any]] = {}
    samples_parent = root.find("SAMPLES")
    if samples_parent is None:
        return samples

    for sample in samples_parent.findall("SAMPLE"):
        pad_id = sample.attrib.get("id", "")
        if not pad_id:
            continue
        reference = sample.find("./REFERENCES/REFERENCE")
        raw_reference = reference.attrib.get("value") if reference is not None else None
        samples[pad_id] = {
            "pad_id": pad_id,
            "reversed": sample.attrib.get("reversed"),
            "gain": to_float(sample.attrib.get("gain")),
            "start": int(float(sample.attrib.get("start", "0"))),
            "end": int(float(sample.attrib.get("end", "0"))),
            "reference_type": reference.attrib.get("type") if reference is not None else None,
            "raw_reference": unescape(raw_reference) if raw_reference else None,
            "is_empty": int(float(sample.attrib.get("end", "0"))) == 0 and reference is None,
        }
    return samples


def resolve_reference(raw_reference: str | None, collection_dir: Path) -> ResolveResult:
    if not raw_reference:
        return ResolveResult(None, None, None, "empty_reference")

    decoded = unescape(raw_reference)
    posix_path = PurePosixPath(decoded)
    parts = list(posix_path.parts)
    try:
        samples_index = parts.index("Samples")
    except ValueError:
        return ResolveResult(None, None, None, "missing_samples_segment")

    relative_parts = parts[samples_index + 1:]
    if not relative_parts:
        return ResolveResult(None, None, None, "missing_relative_sample_path")

    relative_path = Path(*relative_parts)
    exact_path = collection_dir / "Samples" / relative_path
    if exact_path.exists():
        return ResolveResult(exact_path, relative_path.as_posix(), "exact", None)

    filename = relative_path.name.casefold()
    candidates = [
        candidate
        for candidate in (collection_dir / "Samples").rglob("*")
        if candidate.is_file() and candidate.name.casefold() == filename
    ]
    if len(candidates) == 1:
        candidate = candidates[0]
        return ResolveResult(
            candidate,
            candidate.relative_to(collection_dir / "Samples").as_posix(),
            "filename_fallback",
            None,
        )
    if len(candidates) > 1:
        return ResolveResult(None, None, None, "ambiguous_filename_match")
    return ResolveResult(None, None, None, "missing_source_sample")


def copy_file(source: Path, destination: Path, dry_run: bool) -> None:
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def ensure_directory(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def safe_path_string(path: Path) -> str:
    return path.as_posix()


def build_keygroups(pad_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    melodic_records = [record for record in pad_records if record["copied_sample_file"]]
    if not melodic_records:
        return []

    unique_records: dict[tuple[str, int, int], dict[str, Any]] = {}
    for record in melodic_records:
        key = (
            record["copied_sample_file"],
            record["translated"]["tune_semi"],
            record["translated"]["tune_fine"],
        )
        unique_records.setdefault(key, record)

    ordered = sorted(
        unique_records.values(),
        key=lambda record: record["translated"]["absolute_semitones"],
    )
    root_notes = [
        clamp_int(round(60 + record["translated"]["absolute_semitones"]), 0, 127)
        for record in ordered
    ]

    keygroups: list[dict[str, Any]] = []
    for index, record in enumerate(ordered):
        root_note = root_notes[index]
        previous_root = root_notes[index - 1] if index > 0 else 0
        next_root = root_notes[index + 1] if index + 1 < len(root_notes) else 127
        if index == 0:
            low_key = 0
        else:
            low_key = clamp_int(math.floor((previous_root + root_note) / 2.0) + 1, 0, 127)
        if index == len(root_notes) - 1:
            high_key = 127
        else:
            high_key = clamp_int(math.floor((root_note + next_root) / 2.0), 0, 127)
        if low_key > high_key:
            low_key = high_key = root_note

        keygroups.append({
            "source_pad": record["rx_pad"],
            "low_key": low_key,
            "high_key": high_key,
            "root_note": root_note,
            "sample_file": record["copied_sample_file"],
            "volume": record["translated"]["volume"],
            "tune_semi": record["translated"]["tune_semi"],
            "tune_fine": record["translated"]["tune_fine"],
            "amp_decay_ms": record["translated"]["amp_decay_ms"],
            "mute_group": record["translated"]["mute_group"],
            "filter_type": record["translated"]["filter_type"],
            "filter_cutoff": record["translated"]["filter_cutoff"],
        })

    return keygroups


def create_builder_manifest(
    program_name: str,
    original_rx_file: str,
    program_type: str,
    pad_records: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "program_name": program_name,
        "program_type": program_type,
        "original_rx_file": original_rx_file,
    }
    if program_type == "KEYGROUP":
        manifest["keygroups"] = build_keygroups(pad_records)
        return manifest

    manifest["pads"] = [
        {
            "rx_pad": record["rx_pad"],
            "mpc_pad": record["mpc_pad"],
            "sample_file": record["copied_sample_file"],
            "volume": record["translated"]["volume"],
            "tune_semi": record["translated"]["tune_semi"],
            "tune_fine": record["translated"]["tune_fine"],
            "amp_decay_ms": record["translated"]["amp_decay_ms"],
            "mute_group": record["translated"]["mute_group"],
            "filter_type": record["translated"]["filter_type"],
            "filter_cutoff": record["translated"]["filter_cutoff"],
        }
        for record in pad_records
        if record["copied_sample_file"]
    ]
    return manifest


def build_pad_record(
    pad_id: str,
    pad_params: dict[str, float | str],
    sample_info: dict[str, Any] | None,
    resolve_result: ResolveResult,
    copied_sample_file: str | None,
) -> dict[str, Any]:
    pitch = to_float(str(pad_params.get("pitch"))) if "pitch" in pad_params else None
    finetune = to_float(str(pad_params.get("finetune"))) if "finetune" in pad_params else None
    level = to_float(str(pad_params.get("level"))) if "level" in pad_params else None
    decay = to_float(str(pad_params.get("decay"))) if "decay" in pad_params else None
    output_value = to_float(str(pad_params.get("output"))) if "output" in pad_params else None
    filter_value = to_float(str(pad_params.get("filter"))) if "filter" in pad_params else None
    speed = to_float(str(pad_params.get("speed"))) if "speed" in pad_params else None
    pan = to_float(str(pad_params.get("pan"))) if "pan" in pad_params else None
    mono = to_float(str(pad_params.get("mono"))) if "mono" in pad_params else None

    total_semitones = pitch_to_semitones(pitch) + speed_to_semitones(speed) + (finetune_to_cents(finetune) / 100.0)
    semi, fine = split_tuning(total_semitones)
    filter_type, filter_cutoff, filter_env_amount = filter_to_manifest(filter_value)

    return {
        "pad_id": pad_id,
        "rx_pad": pad_to_display(pad_id),
        "mpc_pad": pad_to_mpc(pad_id),
        "parameters": {key: pad_params[key] for key in sorted(pad_params)},
        "sample": sample_info,
        "raw_reference": sample_info["raw_reference"] if sample_info else None,
        "resolve": {
            "source_path": safe_path_string(resolve_result.source_path) if resolve_result.source_path else None,
            "relative_source_path": resolve_result.relative_source_path,
            "resolved_by": resolve_result.resolved_by,
            "error": resolve_result.error,
        },
        "copied_sample_file": copied_sample_file,
        "translated": {
            "volume": level_to_volume(level),
            "pan": round(pan_to_normalized(pan), 6),
            "tune_semi": semi,
            "tune_fine": fine,
            "absolute_semitones": round(total_semitones, 4),
            "amp_decay_ms": decay_to_ms(decay),
            "mute_group": output_to_mute_group(output_value),
            "filter_type": filter_type,
            "filter_cutoff": filter_cutoff,
            "filter_env_amount": round(filter_env_amount, 6),
            "mono": bool(round(mono)) if mono is not None else False,
            "translation_notes": {
                "pitch_formula": "round(pitch * 127) is treated as an RX coarse-tune value centered at 64 with 8 stored steps per semitone",
                "finetune_formula": "(finetune - 0.5) * 100 cents is merged into the total tune before semi/fine splitting",
                "speed_formula": "speed enum mapped provisionally to semitone offsets {1:0,2:5.45,3:12,4:19.02}",
                "decay_formula": "exponential mapping from 0..1 to 50..8000 ms to preserve finer control at short decays",
                "filter_cutoff_formula": "type-derived cutoff defaults with extra envelope amount for Dyn filter approximation",
            },
        },
    }


def summarize_duplicates(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"sample": sample, "count": count}
        for sample, count in sorted(counter.items())
        if count > 1
    ]


def configure_logging(output_root: Path, verbose: bool, dry_run: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if not dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(output_root / "organizer.log", encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def collect_presets(source_root: Path) -> list[Path]:
    presets: list[Path] = []
    for collection_name in COLLECTIONS:
        collection_dir = source_root / collection_name
        presets.extend(sorted(collection_dir.glob("*.rx1200")))
    return presets


def process_preset(
    preset_path: Path,
    output_root: Path,
    overwrite: bool,
    dry_run: bool,
    collection_name_map: dict[str, str],
    summary: dict[str, Any],
) -> None:
    collection_name = preset_path.parent.name
    collection_dir = preset_path.parent
    sanitized_collection_name = collection_name_map[collection_name]

    preset_name = preset_path.stem
    base_preset_name = sanitize_name(preset_name)
    collection_output_dir = output_root / sanitized_collection_name

    if "preset_name_registry" not in summary:
        summary["preset_name_registry"] = defaultdict(set)
    preset_used = summary["preset_name_registry"][sanitized_collection_name]
    sanitized_preset_name, preset_collision = unique_name(base_preset_name, preset_used)
    if preset_collision:
        summary["sanitization_collisions"].append({
            "type": "preset",
            "collection": collection_name,
            "source_name": preset_name,
            "sanitized_name": sanitized_preset_name,
        })

    kit_dir = collection_output_dir / sanitized_preset_name
    if kit_dir.exists() and not overwrite:
        logging.info("Skipping existing kit folder: %s", kit_dir)
        summary["skipped_kits"].append({
            "preset": preset_name,
            "source_rx1200_path": safe_path_string(preset_path),
            "destination_kit_path": safe_path_string(kit_dir),
        })
        return
    if kit_dir.exists() and overwrite and not dry_run:
        shutil.rmtree(kit_dir)

    root = load_xml(preset_path)
    raw_params, pad_params, leftover_params = extract_params(root)
    samples = extract_samples(root)
    preset_metadata = {
        "preset_name": root.attrib.get("name", preset_name),
        "author": root.attrib.get("author"),
        "comment": root.attrib.get("comment"),
    }

    ensure_directory(kit_dir / "samples", dry_run)

    sample_used_names: set[str] = set()
    copied_sources: dict[Path, str] = {}
    pad_records: list[dict[str, Any]] = []
    referenced_samples_raw: list[dict[str, Any]] = []
    resolved_samples_copied: list[dict[str, Any]] = []
    unresolved_samples: list[dict[str, Any]] = []

    for pad_id in PAD_SEQUENCE:
        sample_info = samples.get(pad_id)
        if sample_info and sample_info["is_empty"]:
            resolve_result = ResolveResult(None, None, None, "empty_pad")
            pad_records.append(build_pad_record(pad_id, pad_params.get(pad_id, {}), sample_info, resolve_result, None))
            continue

        raw_reference = sample_info["raw_reference"] if sample_info else None
        if raw_reference:
            referenced_samples_raw.append({
                "pad_id": pad_id,
                "rx_pad": pad_to_display(pad_id),
                "reference_type": sample_info["reference_type"] if sample_info else None,
                "reference_value_raw": raw_reference,
            })
        resolve_result = resolve_reference(raw_reference, collection_dir)
        copied_sample_file = None

        if resolve_result.source_path:
            if resolve_result.source_path in copied_sources:
                copied_sample_file = copied_sources[resolve_result.source_path]
            else:
                sanitized_sample_name = sanitize_name(resolve_result.source_path.stem) + resolve_result.source_path.suffix.lower()
                unique_sample_name, sample_collision = unique_name(sanitized_sample_name, sample_used_names)
                if sample_collision:
                    summary["sanitization_collisions"].append({
                        "type": "sample",
                        "collection": collection_name,
                        "preset": preset_name,
                        "source_name": resolve_result.source_path.name,
                        "sanitized_name": unique_sample_name,
                    })
                destination_sample = kit_dir / "samples" / unique_sample_name
                if len(safe_path_string(destination_sample)) >= 255:
                    raise ValueError(f"Destination path exceeds MPC-safe limit: {destination_sample}")
                copy_file(resolve_result.source_path, destination_sample, dry_run)
                copied_sample_file = Path("samples") / unique_sample_name
                copied_sources[resolve_result.source_path] = copied_sample_file.as_posix()
                resolved_samples_copied.append({
                    "source_path": safe_path_string(resolve_result.source_path),
                    "relative_source_path": resolve_result.relative_source_path,
                    "destination_path": safe_path_string(destination_sample),
                    "destination_sample_file": copied_sample_file.as_posix(),
                    "resolved_by": resolve_result.resolved_by,
                })
                summary["total_samples_copied"] += 1
            copied_sample_file = copied_sources[resolve_result.source_path]
            summary["duplicate_source_sample_usage"][safe_path_string(resolve_result.source_path)].append(
                {
                    "collection": collection_name,
                    "preset": preset_name,
                    "pad": pad_to_display(pad_id),
                }
            )
        elif raw_reference:
            unresolved_samples.append({
                "pad_id": pad_id,
                "rx_pad": pad_to_display(pad_id),
                "reference_value_raw": raw_reference,
                "error": resolve_result.error,
            })
            summary["missing_unresolved_samples"].append({
                "collection": collection_name,
                "preset": preset_name,
                "pad": pad_to_display(pad_id),
                "reference_value_raw": raw_reference,
                "error": resolve_result.error,
            })

        pad_records.append(
            build_pad_record(
                pad_id,
                pad_params.get(pad_id, {}),
                sample_info,
                resolve_result,
                copied_sample_file,
            )
        )

    melodic, melodic_reason = is_probably_melodic(pad_records)
    program_type = "KEYGROUP" if melodic else "DRUM"
    if melodic:
        summary["melodic_presets"].append({
            "collection": collection_name,
            "preset": preset_name,
            "reason": melodic_reason,
        })

    copied_preset_name = sanitize_name(preset_name) + preset_path.suffix.lower()
    copied_preset_path = kit_dir / copied_preset_name
    if len(safe_path_string(copied_preset_path)) >= 255:
        raise ValueError(f"Destination path exceeds MPC-safe limit: {copied_preset_path}")
    copy_file(preset_path, copied_preset_path, dry_run)

    builder_manifest = create_builder_manifest(
        program_name=sanitized_preset_name,
        original_rx_file=preset_path.name,
        program_type=program_type,
        pad_records=pad_records,
    )
    builder_manifest_path = kit_dir / "mpc_manifest.json"
    audit_manifest_path = kit_dir / "kit_audit.json"

    audit_manifest = {
        "preset_name": preset_metadata["preset_name"],
        "sanitized_preset_name": sanitized_preset_name,
        "source_rx1200_path": safe_path_string(preset_path),
        "copied_rx1200_path": safe_path_string(copied_preset_path),
        "collection_name": collection_name,
        "sanitized_collection_name": sanitized_collection_name,
        "destination_kit_path": safe_path_string(kit_dir),
        "builder_manifest_path": safe_path_string(builder_manifest_path),
        "program_type": program_type,
        "program_type_reason": melodic_reason,
        "preset_metadata": preset_metadata,
        "referenced_samples_raw": referenced_samples_raw,
        "resolved_samples_copied": resolved_samples_copied,
        "unresolved_or_missing_samples": unresolved_samples,
        "duplicate_sample_references_within_kit": summarize_duplicates(
            Counter(item["reference_value_raw"] for item in referenced_samples_raw)
        ),
        "pad_mappings": pad_records,
        "raw_parameter_map": raw_params,
        "unmapped_parameter_map": leftover_params,
        "warnings": [],
    }

    if any(record["translated"]["filter_type"] != "Off" for record in pad_records):
        audit_manifest["warnings"].append(
            "filter_cutoff values are provisional because the RX1200 source exposes filter type but not a separate cutoff parameter in the inspected schema"
        )
    if any((record["parameters"].get("speed") or 0) not in (0, 1) for record in pad_records):
        audit_manifest["warnings"].append(
            "speed-derived tune offsets use a provisional enum-to-semitone mapping documented in the organizer README"
        )
    if any(key.startswith("polyphony_") for key in leftover_params):
        audit_manifest["warnings"].append(
            "polyphony parameters were preserved raw because the inspected schema exposes them as polyphony_1..polyphony_8 rather than pad-keyed values"
        )

    write_json(builder_manifest_path, builder_manifest, dry_run)
    write_json(audit_manifest_path, audit_manifest, dry_run)

    summary["kits_created"].append({
        "collection": collection_name,
        "preset": preset_name,
        "destination_kit_path": safe_path_string(kit_dir),
        "program_type": program_type,
    })
    logging.info("Organized preset %s -> %s", preset_path.name, kit_dir)


def finalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    duplicate_refs_across_kits = []
    for source_path, usages in sorted(summary["duplicate_source_sample_usage"].items()):
        kits = {(item["collection"], item["preset"]) for item in usages}
        if len(kits) > 1:
            duplicate_refs_across_kits.append({
                "source_path": source_path,
                "kit_count": len(kits),
                "usage_count": len(usages),
                "kits": [
                    {"collection": collection, "preset": preset}
                    for collection, preset in sorted(kits)
                ],
            })

    return {
        "total_rx1200_files_processed": summary["total_rx1200_files_processed"],
        "total_kits_created": len(summary["kits_created"]),
        "total_kits_skipped": len(summary["skipped_kits"]),
        "total_samples_copied": summary["total_samples_copied"],
        "duplicate_sample_references_across_kits": duplicate_refs_across_kits,
        "missing_unresolved_sample_references": summary["missing_unresolved_samples"],
        "parse_failures": summary["parse_failures"],
        "skipped_kits": summary["skipped_kits"],
        "sanitization_collisions": summary["sanitization_collisions"],
        "melodic_presets": summary["melodic_presets"],
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.output_root, args.verbose, args.dry_run)
    presets = collect_presets(args.source_root)
    collection_name_map: dict[str, str] = {}
    used_collection_names: set[str] = set()
    for collection_name in COLLECTIONS:
        sanitized_name, collision_name = unique_name(sanitize_name(collection_name), used_collection_names)
        collection_name_map[collection_name] = sanitized_name
        if collision_name:
            summary_collision = {
                "type": "collection",
                "source_name": collection_name,
                "sanitized_name": sanitized_name,
            }
            logging.warning("Collection sanitization collision: %s", summary_collision)

    summary: dict[str, Any] = {
        "total_rx1200_files_processed": len(presets),
        "kits_created": [],
        "skipped_kits": [],
        "total_samples_copied": 0,
        "duplicate_source_sample_usage": defaultdict(list),
        "missing_unresolved_samples": [],
        "parse_failures": [],
        "sanitization_collisions": [],
        "melodic_presets": [],
    }

    for preset_path in presets:
        try:
            process_preset(
                preset_path=preset_path,
                output_root=args.output_root,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                collection_name_map=collection_name_map,
                summary=summary,
            )
        except Exception as exc:  # noqa: BLE001
            logging.exception("Failed to process preset: %s", preset_path)
            summary["parse_failures"].append({
                "preset": preset_path.name,
                "source_rx1200_path": safe_path_string(preset_path),
                "error": str(exc),
            })

    final_summary = finalize_summary(summary)
    summary_path = args.output_root / "master_summary.json"
    write_json(summary_path, final_summary, args.dry_run)
    logging.info("Processed %s presets", final_summary["total_rx1200_files_processed"])
    logging.info("Created %s kits", final_summary["total_kits_created"])
    logging.info("Skipped %s kits", final_summary["total_kits_skipped"])
    logging.info("Copied %s samples", final_summary["total_samples_copied"])
    if final_summary["parse_failures"]:
        logging.warning("Encountered %s parse failures", len(final_summary["parse_failures"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())