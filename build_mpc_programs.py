#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import zipfile
from array import array
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from xml.etree import ElementTree as ET

from rx1200_organizer import PAD_SEQUENCE, clamp_int


EXPANSION_IDENTIFIER = "com.inphonik.rx1200"
EXPANSION_NAME = "RX-1200 Expansion"
EXPANSION_MANUFACTURER = "DJ L. Real"
EXPANSION_VERSION = "1.0.0.0"
EXPANSION_TYPE = "drum"
LEGACY_OUTPUT_ROOT_NAME = "_MPC_Expansion"
CUSTOM_ARTWORK_BASENAME = "rx1200-artwork.png"
DEFAULT_REFERENCE_ARTWORK = Path("reference_docs/rx1200_expansion/Artwork.jpg")
PREVIEWS_DIR_NAME = "[Previews]"
PROGRAMS_DIR_NAME = "Programs"
SAMPLES_DIR_NAME = "Samples"
CUSTOM_ARTWORK_OUTPUT_NAME = "Artwork.png"
DEFAULT_XPM_TEMPLATE = Path("tools/xpm_template.txt")
DEFAULT_XTD_TEMPLATE = Path("tools/xtd_Template.txt")
DRUM_PAD_DEFAULT_COLOR = 65280
KEYGROUP_PAD_COLOR = 5243007
UNRECOGNIZED_COLOR_PALETTE = (
    0x00FFFF,
    0x8080FF,
    0xFF8080,
    0x80FF80,
    0xFFFF80,
    0xFF6060,
    0x60FF60,
    0x6060FF,
    0xC0C0C0,
    0x80FFFF,
    0xFF80FF,
    0xFFCC00,
    0x00CC66,
    0xCC6600,
    0x9966FF,
    0x66CCCC,
)
FILTER_TYPE_TO_INDEX = {
    "Off": 0,
    "LP 12dB": 1,
    "LP 24dB": 2,
    "Dyn": 3,
}
PREVIEW_SAMPLE_RATE = 44100
PREVIEW_CHANNELS = 2
PREVIEW_MAX_SEGMENTS = 8
PREVIEW_MIN_SEGMENT_SECONDS = 0.18
PREVIEW_MAX_SEGMENT_SECONDS = 0.75
PREVIEW_GAP_SECONDS = 0.03
PREVIEW_FADE_SECONDS = 0.01
PREVIEW_SIGNAL_THRESHOLD = 96
PREVIEW_TARGET_PEAK = 0.85
PREVIEW_MAX_GAIN = 4.0
DEFAULT_DRUM_PAD_ROUTE_INDEX = 0
DEFAULT_DRUM_PAD_VOLUME = 1.0
DEFAULT_DRUM_PAD_PAN = 0.5
PAD_COLOR_RULES = {
    1: {
        "color": 0xFF0000,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(kick|kik|kck)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(bass\s*drum|bassdrum)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(bd|kd)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])78k([_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])808[_\-\s\.]*(kick|bass|sub)",
        ),
    },
    2: {
        "color": 0x00FF00,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(snare|snr|snar)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(sn|sd)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(rim\s*shot|rimshot|rim)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])78s([_\-\s\.]|$)",
        ),
    },
    3: {
        "color": 0xFFFF00,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(closed\s*h(i)?hat|closedhh|closedhihat)([_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(hhc|chh|ch)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])78chh([_\-\s\.]|$)",
        ),
    },
    4: {
        "color": 0xFF8000,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(open\s*h(i)?hat|openhh|openhihat)([_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(hho|ohh|oh)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])78ohh([_\-\s\.]|$)",
        ),
    },
    5: {
        "color": 0xFF80C0,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(clap|clp|handclap|hand\s*clap)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(cl|cp)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(snap|finger\s*snap|fingersnap|fingsnap)(\d|[_\-\s\.]|$)",
        ),
    },
    6: {
        "color": 0xFF00FF,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(tom|toms)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(high\s*tom|hightom|hitom)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(mid\s*tom|midtom|medtom)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(low\s*tom|lowtom|lotom|floor\s*tom|floortom)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(ht|mt|lt|ft)(\d|[_\-\s\.]|$)",
        ),
    },
    8: {
        "color": 0xFFFFFF,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(crash|crsh)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(ride|rd)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(cymbal|cym|cy|cr)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(splash|china)(\d|[_\-\s\.]|$)",
        ),
    },
    9: {
        "color": 0x00AAAA,
        "patterns": (
            r"(?i)(^|[_\-\s\.])(cow\s*bell|cowbell|bell)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(shaker|shake)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(tamb|tambourine)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(conga|bongo|bng|perc|percussion)(\d|[_\-\s\.]|$)",
            r"(?i)(^|[_\-\s\.])(wood\s*block|woodblock|block|triangle|tri|clave|claves|guiro|cabasa|maracas)(\d|[_\-\s\.]|$)",
        ),
    },
}


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Build MPC 3.x compatible expansion assets from organized RX1200 manifests.",
    )
    parser.add_argument(
        "--organized-root",
        type=Path,
        default=root / "_Organized_Kits",
        help="Root directory containing organized kit folders and mpc_manifest.json files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Destination root for generated MPC expansion files. Defaults to a folder named after --expansion-name.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Destination path for the builder report. Defaults to <output-root>/builder_report.json.",
    )
    parser.add_argument(
        "--xpm-template",
        type=Path,
        default=root / DEFAULT_XPM_TEMPLATE,
        help="Modern MPC 3.x drum XPM template file.",
    )
    parser.add_argument(
        "--xtd-template",
        type=Path,
        default=root / DEFAULT_XTD_TEMPLATE,
        help="Modern MPC 3.x XTD template file.",
    )
    parser.add_argument(
        "--expansion-name",
        default=EXPANSION_NAME,
        help="Expansion name written into Expansion.xml.",
    )
    parser.add_argument(
        "--identifier",
        default=EXPANSION_IDENTIFIER,
        help="Dot-delimited expansion identifier written into Expansion.xml.",
    )
    parser.add_argument(
        "--artwork-source",
        type=Path,
        help="Optional source image used to generate the expansion artwork JPG.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete and rebuild the output root if it already exists.",
    )
    parser.add_argument(
        "--skip-xtd",
        action="store_true",
        help="Do not generate .xtd track files.",
    )
    parser.add_argument(
        "--skip-xpn",
        action="store_true",
        help="Do not package the expansion root into a .xpn archive.",
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


def force_remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        try:
            if child.is_dir() and not child.is_symlink():
                child.rmdir()
            else:
                child.unlink(missing_ok=True)
        except FileNotFoundError:
            continue
    path.rmdir()


def remove_output_root(path: Path) -> None:
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logging.warning("shutil.rmtree failed for %s: %s; retrying with rm -rf", path, exc)
        try:
            subprocess.run(["rm", "-rf", str(path)], check=True)
        except subprocess.CalledProcessError as rm_exc:
            logging.warning("rm -rf failed for %s: %s; retrying with manual deletion", path, rm_exc)
            force_remove_tree(path)
    if path.exists():
        force_remove_tree(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_xml(path: Path, root: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def bool_text(value: bool) -> str:
    return "True" if value else "False"


def float_text(value: float) -> str:
    return f"{value:.6f}"


def normalized_volume(volume: int) -> float:
    return max(0.0, min(1.0, volume / 127.0))


def normalized_cutoff(filter_cutoff: int) -> float:
    return max(0.0, min(1.0, filter_cutoff / 127.0))


def normalized_decay(decay_ms: int) -> float:
    return max(0.0, min(1.0, (decay_ms - 50.0) / (8000.0 - 50.0)))


def clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def set_child_text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    child.text = value
    return child


def get_instrument_route_index(pad_record: dict[str, Any] | None) -> int:
    return DEFAULT_DRUM_PAD_ROUTE_INDEX


def expansion_relative_path(path: Path, output_root: Path) -> str:
    return PurePosixPath(path.relative_to(output_root)).as_posix()


def windows_relative_path(target: Path, base_dir: Path) -> str:
    relative = os.path.relpath(target, base_dir)
    return str(PureWindowsPath(PurePosixPath(Path(relative).as_posix())))


def sanitize_identifier(identifier: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.]+", ".", identifier)
    cleaned = re.sub(r"\.{2,}", ".", cleaned).strip(".")
    return cleaned or EXPANSION_IDENTIFIER


def sanitize_output_root_name(name: str) -> str:
    cleaned = re.sub(r"[\\/:]+", "-", name).strip()
    return cleaned or EXPANSION_NAME


def expansion_directory_name(identifier: str) -> str:
    return sanitize_identifier(identifier)


def expansion_artwork_name(identifier: str) -> str:
    return f"{expansion_directory_name(identifier)}.jpg"


def resolve_artwork_output_path(output_root: Path, identifier: str, preferred_name: str | None = None) -> Path:
    default_artwork_path = output_root / (preferred_name or expansion_artwork_name(identifier))
    if default_artwork_path.exists():
        return default_artwork_path

    existing_artwork = sorted(
        path
        for path in output_root.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
    )
    if len(existing_artwork) == 1:
        return existing_artwork[0]

    return default_artwork_path


def collection_output_directory_name(collection_name: str | None, fallback_name: str) -> str:
    source_name = collection_name or fallback_name
    display_name = re.sub(r"\s*&\s*", " And ", source_name.strip())
    display_name = re.sub(r"\s+", " ", display_name).strip()
    return display_name or fallback_name


def discover_kits(organized_root: Path) -> list[tuple[Path, Path]]:
    kits: list[tuple[Path, Path]] = []
    for audit_path in sorted(organized_root.rglob("kit_audit.json")):
        manifest_path = audit_path.parent / "mpc_manifest.json"
        if manifest_path.exists():
            kits.append((audit_path, manifest_path))
    return kits


def build_sample_source_map(audit_manifest: dict[str, Any]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for sample in audit_manifest.get("resolved_samples_copied", []):
        source = Path(sample["destination_path"])
        mapping[sample["destination_sample_file"]] = source
    return mapping


def iter_manifest_sample_keys(builder_manifest: dict[str, Any]) -> list[str]:
    sample_keys: list[str] = []
    for pad in builder_manifest.get("pads", []):
        sample_key = pad.get("sample_file")
        if sample_key:
            sample_keys.append(sample_key)
    for keygroup in builder_manifest.get("keygroups", []):
        sample_key = keygroup.get("sample_file")
        if sample_key:
            sample_keys.append(sample_key)
    return sample_keys


def copy_public_samples(
    samples_root: Path,
    builder_manifest: dict[str, Any],
    build_sample_map: dict[str, Path],
) -> dict[str, Path]:
    samples_root.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    for sample_key in iter_manifest_sample_keys(builder_manifest):
        if sample_key in copied:
            continue
        source = build_sample_map[sample_key]
        destination = samples_root / source.name
        shutil.copy2(source, destination)
        copied[sample_key] = destination
    return copied


def read_pcm16_wav(path: Path) -> tuple[int, int, array]:
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError(f"Unsupported sample width for preview source: {path}")
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        raw_frames = handle.readframes(handle.getnframes())

    samples = array("h")
    samples.frombytes(raw_frames)
    if sys.byteorder != "little":
        samples.byteswap()
    return sample_rate, channels, samples


def find_signal_start_frame(samples: array, channels: int, threshold: int = PREVIEW_SIGNAL_THRESHOLD) -> int:
    total_frames = len(samples) // channels
    for frame_index in range(total_frames):
        offset = frame_index * channels
        peak = abs(samples[offset])
        if channels > 1:
            peak = max(peak, abs(samples[offset + 1]))
        if peak >= threshold:
            return frame_index
    return 0


def calculate_pan_gains(pan: float) -> tuple[float, float]:
    clamped_pan = clamp_float(pan, 0.0, 1.0)
    left_gain = 1.0 - max(0.0, (clamped_pan - 0.5) * 2.0)
    right_gain = 1.0 - max(0.0, (0.5 - clamped_pan) * 2.0)
    return left_gain, right_gain


def extract_preview_segment(
    sample_path: Path,
    translated: dict[str, Any],
    target_sample_rate: int,
) -> tuple[list[float], list[float]]:
    source_rate, channels, samples = read_pcm16_wav(sample_path)
    if channels not in (1, 2):
        raise ValueError(f"Unsupported channel count for preview source: {sample_path}")

    total_source_frames = len(samples) // channels
    if total_source_frames <= 0:
        return [], []

    start_frame = find_signal_start_frame(samples, channels)
    available_source_frames = total_source_frames - start_frame
    if available_source_frames <= 0:
        return [], []

    decay_seconds = float(translated.get("amp_decay_ms", 400)) / 1000.0
    segment_seconds = clamp_float(decay_seconds, PREVIEW_MIN_SEGMENT_SECONDS, PREVIEW_MAX_SEGMENT_SECONDS)
    target_frames = max(1, int(round(segment_seconds * target_sample_rate)))
    available_target_frames = max(1, int(available_source_frames * target_sample_rate / source_rate))
    frame_count = min(target_frames, available_target_frames)

    volume_gain = clamp_float(float(translated.get("volume", 127)) / 127.0, 0.0, 1.25)
    left_pan_gain, right_pan_gain = calculate_pan_gains(float(translated.get("pan", 0.5)))
    fade_frames = min(max(1, int(target_sample_rate * PREVIEW_FADE_SECONDS)), max(1, frame_count // 4))

    left: list[float] = []
    right: list[float] = []
    for target_index in range(frame_count):
        source_index = min(
            total_source_frames - 1,
            start_frame + int(target_index * source_rate / target_sample_rate),
        )
        offset = source_index * channels
        sample_left = samples[offset] / 32768.0
        sample_right = sample_left if channels == 1 else samples[offset + 1] / 32768.0

        envelope = 1.0
        if target_index < fade_frames:
            envelope *= target_index / fade_frames
        remaining = frame_count - target_index - 1
        if remaining < fade_frames:
            envelope *= remaining / fade_frames

        left.append(sample_left * volume_gain * left_pan_gain * envelope)
        right.append(sample_right * volume_gain * right_pan_gain * envelope)

    return left, right


def write_preview_wav(preview_path: Path, left: list[float], right: list[float], sample_rate: int) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    peak = max(max((abs(value) for value in left), default=0.0), max((abs(value) for value in right), default=0.0))
    gain = 1.0 if peak <= 0.0 else min(PREVIEW_MAX_GAIN, PREVIEW_TARGET_PEAK / peak)

    pcm = array("h")
    for left_value, right_value in zip(left, right):
        pcm.append(clamp_int(int(round(clamp_float(left_value * gain, -1.0, 1.0) * 32767.0)), -32768, 32767))
        pcm.append(clamp_int(int(round(clamp_float(right_value * gain, -1.0, 1.0) * 32767.0)), -32768, 32767))
    if sys.byteorder != "little":
        pcm.byteswap()

    with wave.open(str(preview_path), "wb") as handle:
        handle.setnchannels(PREVIEW_CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def create_program_preview(
    preview_path: Path,
    builder_manifest: dict[str, Any],
    audit_manifest: dict[str, Any],
    build_sample_map: dict[str, Path],
    sample_rate: int = PREVIEW_SAMPLE_RATE,
) -> None:
    audit_by_mpc = {
        pad["mpc_pad"]: pad
        for pad in audit_manifest.get("pad_mappings", [])
        if isinstance(pad, dict) and pad.get("mpc_pad")
    }

    left: list[float] = []
    right: list[float] = []
    gap_frames = int(sample_rate * PREVIEW_GAP_SECONDS)
    used_sample_files: set[str] = set()

    for manifest_pad in builder_manifest.get("pads", []):
        sample_key = manifest_pad.get("sample_file")
        mpc_pad = manifest_pad.get("mpc_pad")
        if not sample_key or not mpc_pad or sample_key in used_sample_files:
            continue

        source_path = build_sample_map.get(sample_key)
        audit_pad = audit_by_mpc.get(mpc_pad)
        if source_path is None or audit_pad is None:
            continue

        try:
            segment_left, segment_right = extract_preview_segment(
                source_path,
                audit_pad.get("translated", {}),
                sample_rate,
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning("Skipping preview segment for %s: %s", source_path, exc)
            continue

        if not segment_left:
            continue

        if left:
            left.extend([0.0] * gap_frames)
            right.extend([0.0] * gap_frames)
        left.extend(segment_left)
        right.extend(segment_right)
        used_sample_files.add(sample_key)

        if len(used_sample_files) >= PREVIEW_MAX_SEGMENTS:
            break

    if not left:
        raise RuntimeError(f"Unable to synthesize preview audio for {builder_manifest.get('program_name', 'unknown program')}")

    write_preview_wav(preview_path, left, right, sample_rate)


def write_placeholder_ppm(ppm_path: Path, width: int = 1000, height: int = 1000) -> None:
    ppm_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    row = bytes((32, 32, 32, 220, 106, 44)) * (width // 2)
    if len(row) < width * 3:
        row += bytes((220, 106, 44))
    with ppm_path.open("wb") as handle:
        handle.write(header)
        for index in range(height):
            if index < height // 3:
                handle.write(bytes((18, 18, 18)) * width)
            elif index < (2 * height) // 3:
                handle.write(row[: width * 3])
            else:
                handle.write(bytes((240, 240, 240)) * width)


def create_artwork(output_root: Path, source_path: Path | None, identifier: str) -> Path:
    if source_path is None:
        workspace_root = Path(__file__).resolve().parent
        candidate_paths = (
            workspace_root / CUSTOM_ARTWORK_BASENAME,
            workspace_root / DEFAULT_REFERENCE_ARTWORK,
        )
        for candidate in candidate_paths:
            if candidate.exists():
                source_path = candidate
                break

    preferred_name = None
    if source_path is not None and source_path.name == CUSTOM_ARTWORK_BASENAME:
        preferred_name = CUSTOM_ARTWORK_OUTPUT_NAME

    artwork_path = resolve_artwork_output_path(output_root, identifier, preferred_name)

    if source_path:
        source_path = source_path.resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Artwork source not found: {source_path}")
        if source_path.suffix.lower() == ".png" and artwork_path.suffix.lower() == ".png":
            shutil.copy2(source_path, artwork_path)
            return artwork_path
        if shutil.which("sips"):
            subprocess.run(
                [
                    "sips",
                    "-s",
                    "format",
                    "jpeg",
                    "-z",
                    "1000",
                    "1000",
                    str(source_path),
                    "--out",
                    str(artwork_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return artwork_path
        shutil.copy2(source_path, artwork_path)
        return artwork_path

    if shutil.which("sips"):
        with tempfile.TemporaryDirectory() as temp_dir:
            ppm_path = Path(temp_dir) / "placeholder.ppm"
            write_placeholder_ppm(ppm_path)
            subprocess.run(
                [
                    "sips",
                    "-s",
                    "format",
                    "jpeg",
                    str(ppm_path),
                    "--out",
                    str(artwork_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        return artwork_path

    raise RuntimeError("Unable to generate artwork: 'sips' is not available and no artwork source was supplied.")


def load_xpm_template(path: Path) -> ET.Element:
    return ET.fromstring(path.read_text(encoding="utf-8"))


def load_xtd_template(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    start = raw.index("{")
    return raw[:start], json.loads(raw[start:])


def mpc_pad_to_index(mpc_pad: str) -> int:
    bank = mpc_pad[0]
    number = int(mpc_pad[1:])
    if bank == "A":
        return number
    if bank == "B":
        return 16 + number
    raise ValueError(f"Unsupported MPC pad: {mpc_pad}")


def pad_sequence_to_index(pad_id: str) -> int:
    return PAD_SEQUENCE.index(pad_id) + 1


def get_sample_category(file_name: str) -> int:
    lowered = file_name.lower()
    for category, rule in PAD_COLOR_RULES.items():
        for pattern in rule["patterns"]:
            if re.search(pattern, lowered):
                return category
    return 7


def get_file_pattern(file_name: str) -> str:
    base_name = Path(file_name).stem
    pattern = re.sub(r"[_\-\s]?\d+$", "", base_name)
    return (pattern or base_name).lower()


def build_unrecognized_color_map(active_sample_names: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    palette_index = 0
    for sample_name in active_sample_names:
        if get_sample_category(sample_name) != 7:
            continue
        pattern = get_file_pattern(sample_name)
        if pattern not in mapping:
            mapping[pattern] = UNRECOGNIZED_COLOR_PALETTE[palette_index % len(UNRECOGNIZED_COLOR_PALETTE)]
            palette_index += 1
    return mapping


def get_pad_color(file_name: str, unrecognized_map: dict[str, int]) -> int:
    category = get_sample_category(file_name)
    if category in PAD_COLOR_RULES:
        return PAD_COLOR_RULES[category]["color"]
    return unrecognized_map.get(get_file_pattern(file_name), DRUM_PAD_DEFAULT_COLOR)


def build_program_pads_json(program_type: str, pad_sample_names: dict[int, str]) -> str:
    if program_type == "KEYGROUP":
        payload = {
            "ProgramPads": {
                "Universal": {"value0": True},
                "Type": {"value0": 4},
                "universalPad": KEYGROUP_PAD_COLOR,
                "pads": {f"value{index}": KEYGROUP_PAD_COLOR for index in range(128)},
                "UnusedPads": {"value0": 1},
                "PadsFollowTrackColour": {"value0": False},
            }
        }
        return json.dumps(payload, indent=4)

    unrecognized_map = build_unrecognized_color_map(list(pad_sample_names.values()))
    payload = {
        "ProgramPads": {
            "Universal": {"value0": False},
            "Type": {"value0": 5},
            "universalPad": DRUM_PAD_DEFAULT_COLOR,
            "pads": {
                f"value{index}": get_pad_color(pad_sample_names[index + 1], unrecognized_map)
                if (index + 1) in pad_sample_names
                else 0
                for index in range(128)
            },
            "UnusedPads": {"value0": 1},
            "PadsFollowTrackColour": {"value0": False},
        }
    }
    return json.dumps(payload, indent=4)


def ensure_audio_route_xml(parent: ET.Element, route: int, sub_index: int, include_channel_bitmap: bool = True) -> None:
    route_element = parent.find("AudioRoute")
    if route_element is None:
        route_element = ET.Element("AudioRoute")
        parent.insert(0, route_element)
    set_child_text(route_element, "AudioRoute", str(route))
    set_child_text(route_element, "AudioRouteSubIndex", str(sub_index))
    if include_channel_bitmap:
        set_child_text(route_element, "AudioRouteChannelBitmap", "3")
    set_child_text(route_element, "InsertsEnabled", "True")


def configure_xpm_layer(
    layer: ET.Element,
    *,
    active: bool,
    volume: float,
    pan: float,
    sample_name: str,
    sample_file: str,
    keytrack: bool,
) -> None:
    set_child_text(layer, "Active", bool_text(active))
    set_child_text(layer, "Volume", float_text(volume))
    set_child_text(layer, "Pan", float_text(pan))
    set_child_text(layer, "Pitch", float_text(0.0))
    set_child_text(layer, "TuneCoarse", "0")
    set_child_text(layer, "TuneFine", "0")
    set_child_text(layer, "VelStart", "0")
    set_child_text(layer, "VelEnd", "127")
    set_child_text(layer, "SampleStart", "0")
    set_child_text(layer, "SampleEnd", "0")
    set_child_text(layer, "Loop", "False")
    set_child_text(layer, "LoopStart", "0")
    set_child_text(layer, "LoopEnd", "0")
    set_child_text(layer, "LoopCrossfadeLength", "0")
    set_child_text(layer, "LoopTune", "0")
    set_child_text(layer, "Mute", "False")
    set_child_text(layer, "RootNote", "0")
    set_child_text(layer, "KeyTrack", bool_text(keytrack))
    set_child_text(layer, "SampleName", sample_name)
    set_child_text(layer, "SampleFile", sample_file)
    set_child_text(layer, "SliceIndex", "0")
    set_child_text(layer, "Direction", "0")
    set_child_text(layer, "Offset", "0")
    set_child_text(layer, "SliceStart", "0")
    set_child_text(layer, "SliceEnd", "")
    set_child_text(layer, "SliceLoopStart", "0")
    set_child_text(layer, "SliceLoop", "0")
    set_child_text(layer, "SliceLoopCrossFadeLength", "0")


def update_drum_xpm_instrument(
    instrument: ET.Element,
    pad_record: dict[str, Any] | None,
    sample_file: str,
    sample_name: str,
) -> None:
    translated = (pad_record or {}).get("translated", {})
    route_index = get_instrument_route_index(pad_record)
    assigned = bool(sample_file)
    ensure_audio_route_xml(instrument, route=1, sub_index=route_index, include_channel_bitmap=True)
    set_child_text(instrument, "TuneCoarse", str(translated.get("tune_semi", 0)))
    set_child_text(instrument, "TuneFine", str(translated.get("tune_fine", 0)))
    mono = bool(translated.get("mono", False)) if assigned else False
    set_child_text(instrument, "Mono", bool_text(mono))
    set_child_text(instrument, "Polyphony", "1" if mono else "0")
    set_child_text(instrument, "FilterKeytrack", float_text(0.0))
    set_child_text(instrument, "LowNote", "0")
    set_child_text(instrument, "HighNote", "127")
    set_child_text(instrument, "IgnoreBaseNote", "False")
    set_child_text(instrument, "ZonePlay", "1")
    set_child_text(instrument, "MuteGroup", "0")
    for tag in (
        "MuteTarget1",
        "MuteTarget2",
        "MuteTarget3",
        "MuteTarget4",
        "SimultTarget1",
        "SimultTarget2",
        "SimultTarget3",
        "SimultTarget4",
    ):
        set_child_text(instrument, tag, "0")
    set_child_text(instrument, "LfoPitch", float_text(0.0))
    set_child_text(instrument, "LfoCutoff", float_text(0.0))
    set_child_text(instrument, "LfoVolume", float_text(0.0))
    set_child_text(instrument, "LfoPan", float_text(0.0))
    set_child_text(instrument, "OneShot", bool_text(assigned))
    set_child_text(instrument, "FilterType", str(FILTER_TYPE_TO_INDEX.get(translated.get("filter_type", "Off"), 0)))
    set_child_text(instrument, "Cutoff", float_text(normalized_cutoff(translated.get("filter_cutoff", 127))))
    set_child_text(instrument, "Resonance", float_text(0.0))
    set_child_text(instrument, "FilterEnvAmt", float_text(translated.get("filter_env_amount", 0.0)))
    set_child_text(instrument, "AfterTouchToFilter", float_text(0.0))
    set_child_text(instrument, "VelocityToStart", float_text(0.0))
    set_child_text(instrument, "VelocityToFilterAttack", float_text(0.0))
    set_child_text(instrument, "VelocityToFilter", float_text(0.0))
    set_child_text(instrument, "VelocityToFilterEnvelope", float_text(0.0))
    set_child_text(instrument, "FilterAttack", float_text(0.0))
    set_child_text(instrument, "FilterDecay", float_text(normalized_decay(translated.get("amp_decay_ms", 1500))))
    set_child_text(instrument, "FilterSustain", float_text(1.0))
    set_child_text(instrument, "FilterRelease", float_text(0.0))
    set_child_text(instrument, "FilterHold", float_text(0.0))
    set_child_text(instrument, "FilterDecayType", "True")
    set_child_text(instrument, "FilterADEnvelope", "True")
    set_child_text(instrument, "VolumeHold", float_text(0.0))
    set_child_text(instrument, "VolumeDecayType", "True")
    set_child_text(instrument, "VolumeADEnvelope", "True")
    set_child_text(instrument, "VolumeAttack", float_text(0.0))
    set_child_text(instrument, "VolumeDecay", float_text(normalized_decay(translated.get("amp_decay_ms", 1500))))
    set_child_text(instrument, "VolumeSustain", float_text(1.0))
    set_child_text(instrument, "VolumeRelease", float_text(0.0))
    set_child_text(instrument, "VelocityToPitch", float_text(0.0))
    set_child_text(instrument, "VelocityToVolumeAttack", float_text(0.0))
    set_child_text(instrument, "VelocitySensitivity", float_text(1.0))
    set_child_text(instrument, "VelocityToPan", float_text(0.0))
    lfo = instrument.find("LFO")
    if lfo is not None:
        set_child_text(lfo, "Type", "Sine")
        set_child_text(lfo, "Rate", float_text(0.5))
        set_child_text(lfo, "Sync", "0")
        set_child_text(lfo, "Reset", "False")
    set_child_text(instrument, "WarpTempo", float_text(120.0))
    set_child_text(instrument, "BpmLock", "False")
    set_child_text(instrument, "WarpEnable", "False")
    set_child_text(instrument, "StretchPercentage", "100")

    layers = instrument.find("Layers")
    if layers is None:
        raise ValueError("XPM template instrument is missing <Layers>.")
    layer_elements = layers.findall("Layer")
    if not layer_elements:
        raise ValueError("XPM template instrument is missing layer entries.")

    configure_xpm_layer(
        layer_elements[0],
        active=assigned,
        volume=normalized_volume(int(translated.get("volume", 127))) if assigned else DEFAULT_DRUM_PAD_VOLUME,
        pan=DEFAULT_DRUM_PAD_PAN,
        sample_name=sample_name if assigned else "",
        sample_file=sample_file if assigned else "",
        keytrack=False,
    )
    for layer in layer_elements[1:]:
        configure_xpm_layer(
            layer,
            active=False,
            volume=DEFAULT_DRUM_PAD_VOLUME,
            pan=DEFAULT_DRUM_PAD_PAN,
            sample_name="",
            sample_file="",
            keytrack=False,
        )


def build_drum_program(
    xpm_template: ET.Element,
    builder_manifest: dict[str, Any],
    audit_manifest: dict[str, Any],
    program_path: Path,
    public_sample_map: dict[str, Path],
) -> ET.Element:
    root = copy.deepcopy(xpm_template)
    version = root.find("Version")
    if version is None:
        raise ValueError("XPM template is missing <Version>.")
    set_child_text(version, "Application", "MPC")
    set_child_text(version, "Application_Version", "3.0.5.69")
    set_child_text(version, "Platform", "OSX")

    program = root.find("Program")
    if program is None:
        raise ValueError("XPM template is missing <Program>.")
    program.set("type", "Drum")
    set_child_text(program, "ProgramName", builder_manifest["program_name"])
    set_child_text(program, "Pitch", float_text(0.0))
    set_child_text(program, "TuneCoarse", "0")
    set_child_text(program, "TuneFine", "0")
    set_child_text(program, "Mono", "True")
    set_child_text(program, "Program_Polyphony", "16")
    set_child_text(program, "PortamentoTime", float_text(0.0))
    set_child_text(program, "PortamentoLegato", "False")
    set_child_text(program, "PortamentoQuantized", "False")
    set_child_text(program, "Program.Xfader.Route", "0")

    pad_by_rx = {
        pad["rx_pad"]: pad
        for pad in audit_manifest.get("pad_mappings", [])
        if isinstance(pad, dict) and pad.get("rx_pad")
    }
    manifest_by_mpc = {
        pad["mpc_pad"]: pad
        for pad in builder_manifest.get("pads", [])
        if isinstance(pad, dict) and pad.get("mpc_pad")
    }

    pad_sample_names: dict[int, str] = {}
    for pad in builder_manifest.get("pads", []):
        pad_sample_names[mpc_pad_to_index(pad["mpc_pad"])] = Path(pad["sample_file"]).name

    program_pads = program.find("ProgramPads")
    if program_pads is None:
        program_pads = set_child_text(program, "ProgramPads", "")
    program_pads.text = build_program_pads_json("DRUM", pad_sample_names)

    instruments = program.find("Instruments")
    if instruments is None:
        raise ValueError("XPM template is missing <Instruments>.")

    for pad_id in PAD_SEQUENCE:
        instrument_number = pad_sequence_to_index(pad_id)
        instrument = instruments.find(f"./Instrument[@number='{instrument_number}']")
        if instrument is None:
            raise ValueError(f"XPM template is missing instrument {instrument_number}.")
        rx_pad = f"{pad_id[0].upper()}{pad_id[1:]}"
        pad_record = pad_by_rx.get(rx_pad)
        manifest_pad = None
        if pad_record is not None:
            manifest_pad = manifest_by_mpc.get(pad_record["mpc_pad"])
        sample_file = ""
        sample_name = ""
        if manifest_pad and manifest_pad.get("sample_file"):
            sample_output = public_sample_map[manifest_pad["sample_file"]]
            sample_file = windows_relative_path(sample_output, program_path.parent)
            sample_name = sample_output.stem
        update_drum_xpm_instrument(instrument, pad_record if manifest_pad else None, sample_file, sample_name)

    return root


def create_keygroup_program(
    builder_manifest: dict[str, Any],
    program_path: Path,
    sample_map: dict[str, Path],
) -> ET.Element:
    root = ET.Element("MPCVObject")
    version = ET.SubElement(root, "Version")
    set_child_text(version, "File_Version", "2.1")
    set_child_text(version, "Application", "MPC")
    set_child_text(version, "Application_Version", "3.0.5.69")
    set_child_text(version, "Platform", "OSX")

    program = ET.SubElement(root, "Program", {"type": "Keygroup"})
    set_child_text(program, "Name", builder_manifest["program_name"])
    set_child_text(program, "ProgramPads", build_program_pads_json("KEYGROUP", {}))
    set_child_text(program, "Pitch", float_text(0.0))
    set_child_text(program, "TuneCoarse", "0")
    set_child_text(program, "TuneFine", "0")
    set_child_text(program, "Mono", "False")
    set_child_text(program, "Program_Polyphony", "12")

    instruments = ET.SubElement(program, "Instruments")
    for index, keygroup in enumerate(builder_manifest.get("keygroups", []), start=1):
        instrument = ET.SubElement(instruments, "Instrument", {"number": str(index)})
        ensure_audio_route_xml(instrument, route=0, sub_index=0, include_channel_bitmap=True)
        set_child_text(instrument, "TuneCoarse", str(keygroup.get("tune_semi", 0)))
        set_child_text(instrument, "TuneFine", str(keygroup.get("tune_fine", 0)))
        set_child_text(instrument, "Mono", "False")
        set_child_text(instrument, "Polyphony", "0")
        set_child_text(instrument, "FilterKeytrack", float_text(0.0))
        set_child_text(instrument, "LowNote", str(keygroup.get("low_key", 0)))
        set_child_text(instrument, "HighNote", str(keygroup.get("high_key", 127)))
        set_child_text(instrument, "IgnoreBaseNote", "False")
        set_child_text(instrument, "ZonePlay", "1")
        set_child_text(instrument, "MuteGroup", "0")
        for tag in (
            "MuteTarget1",
            "MuteTarget2",
            "MuteTarget3",
            "MuteTarget4",
            "SimultTarget1",
            "SimultTarget2",
            "SimultTarget3",
            "SimultTarget4",
        ):
            set_child_text(instrument, tag, "0")
        set_child_text(instrument, "FilterType", str(FILTER_TYPE_TO_INDEX.get(keygroup.get("filter_type", "Off"), 0)))
        set_child_text(instrument, "Cutoff", float_text(normalized_cutoff(keygroup.get("filter_cutoff", 127))))
        set_child_text(instrument, "Resonance", float_text(0.0))
        set_child_text(instrument, "FilterEnvAmt", float_text(0.0))

        layers = ET.SubElement(instrument, "Layers")
        sample_output = sample_map[keygroup["sample_file"]]
        sample_file = windows_relative_path(sample_output, program_path.parent)
        for layer_number in range(1, 5):
            layer = ET.SubElement(layers, "Layer", {"number": str(layer_number)})
            configure_xpm_layer(
                layer,
                active=layer_number == 1,
                volume=normalized_volume(keygroup.get("volume", 127)) if layer_number == 1 else 1.0,
                pan=0.5,
                sample_name=sample_output.stem if layer_number == 1 else "",
                sample_file=sample_file if layer_number == 1 else "",
                keytrack=layer_number == 1,
            )
    return root


def ensure_xtd_layer(layer: dict[str, Any], *, active: bool, sample_name: str, sample_file: str) -> None:
    layer["active"] = active
    layer["sampleName"] = sample_name
    layer["sampleFile"] = sample_file
    layer["velocityStart"] = 0
    layer["velocityEnd"] = 127
    layer["sampleStart"] = 0
    layer["sampleEnd"] = 0
    layer["loop"] = False
    layer["loopStart"] = 0
    layer["loopEnd"] = 0
    layer["loopCrossfadeLength"] = 0
    layer["loopFineTune"] = 0
    layer["mute"] = False
    layer["rootNote"] = 0
    layer["keyTrackEnable"] = False
    layer["sliceIndex"] = 128
    layer["direction"] = 0
    layer["offset"] = 0
    layer.setdefault("sliceInfo", {})
    layer["sliceInfo"]["Start"] = 0
    layer["sliceInfo"]["End"] = 0
    layer["sliceInfo"]["LoopStart"] = 0
    layer["sliceInfo"]["LoopMode"] = 0
    layer["sliceInfo"]["PulsePosition"] = 0
    layer["sliceInfo"]["LoopCrossfadeLength"] = 0
    layer["sliceInfo"]["LoopCrossfadeType"] = 0
    layer["sliceInfo"]["TailLength"] = 0.0
    layer["sliceInfo"]["TailLoopPosition"] = 0.5
    layer["sliceInfo"]["NumLoopRepeats"] = 0


def copy_trackdata_samples(
    xtd_path: Path,
    builder_manifest: dict[str, Any],
    build_sample_map: dict[str, Path],
) -> tuple[Path, dict[str, str]]:
    trackdata_dir = xtd_path.parent / f"{builder_manifest['program_name']}_[TrackData]"
    trackdata_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for pad in builder_manifest.get("pads", []):
        sample_key = pad.get("sample_file")
        if not sample_key or sample_key in copied:
            continue
        source = build_sample_map[sample_key]
        destination = trackdata_dir / source.name
        shutil.copy2(source, destination)
        copied[sample_key] = destination.name
    return trackdata_dir, copied


def build_drum_xtd(
    xtd_header: str,
    xtd_template: dict[str, Any],
    builder_manifest: dict[str, Any],
    audit_manifest: dict[str, Any],
    build_sample_map: dict[str, Path],
    xtd_path: Path,
) -> None:
    xtd_object = copy.deepcopy(xtd_template)
    data = xtd_object["data"]
    data["name"] = builder_manifest["program_name"]
    data["volume"] = DEFAULT_DRUM_PAD_VOLUME
    data["pan"] = DEFAULT_DRUM_PAD_PAN
    data["muteGroup"] = 0
    data["program"]["name"] = builder_manifest["program_name"]
    data["program"]["programPads"] = json.loads(
        build_program_pads_json(
            "DRUM",
            {mpc_pad_to_index(pad["mpc_pad"]): Path(pad["sample_file"]).name for pad in builder_manifest.get("pads", [])},
        )
    )["ProgramPads"]

    _, trackdata_samples = copy_trackdata_samples(xtd_path, builder_manifest, build_sample_map)

    unique_samples: list[dict[str, Any]] = []
    seen_samples: set[str] = set()
    for pad in builder_manifest.get("pads", []):
        sample_key = pad.get("sample_file")
        if not sample_key or sample_key in seen_samples:
            continue
        seen_samples.add(sample_key)
        sample_path = trackdata_samples[sample_key]
        unique_samples.append(
            {
                "version": 1,
                "name": Path(sample_path).stem,
                "path": sample_path,
                "loadImpl": 0,
                "metadata": {
                    "tempo": 0.0,
                    "rootNote": 60,
                    "tune": 0.0,
                    "key": "C Major",
                },
            }
        )
    data["samples"] = unique_samples

    pad_by_rx = {
        pad["rx_pad"]: pad
        for pad in audit_manifest.get("pad_mappings", [])
        if isinstance(pad, dict) and pad.get("rx_pad")
    }
    manifest_by_mpc = {
        pad["mpc_pad"]: pad
        for pad in builder_manifest.get("pads", [])
        if isinstance(pad, dict) and pad.get("mpc_pad")
    }
    instruments = data["program"]["drum"]["instruments"]
    for pad_id in PAD_SEQUENCE:
        instrument_number = pad_sequence_to_index(pad_id)
        instrument = instruments[instrument_number - 1]
        rx_pad = f"{pad_id[0].upper()}{pad_id[1:]}"
        pad_record = pad_by_rx.get(rx_pad)
        manifest_pad = None
        if pad_record is not None:
            manifest_pad = manifest_by_mpc.get(pad_record["mpc_pad"])
        translated = (pad_record or {}).get("translated", {})
        assigned = bool(manifest_pad and manifest_pad.get("sample_file"))
        sample_name = ""
        sample_file = ""
        if assigned:
            sample_key = manifest_pad["sample_file"]
            sample_file = trackdata_samples[sample_key]
            sample_name = Path(sample_file).stem
        instrument["coarseTune"] = int(translated.get("tune_semi", 0)) if assigned else 0
        instrument["fineTune"] = int(translated.get("tune_fine", 0)) if assigned else 0
        instrument["monophonic"] = bool(translated.get("mono", False)) if assigned else False
        instrument["polyphony"] = 1 if instrument["monophonic"] else 8
        instrument["lowNote"] = 0
        instrument["highNote"] = 127
        instrument["ignoreBaseNote"] = False
        instrument["zonePlayTime"] = 1
        instrument["whichMuteGroup"] = 0
        instrument["mixable"]["audioRoute"]["destination"] = 1
        instrument["mixable"]["audioRoute"]["audioRouteSubIndex"] = get_instrument_route_index(pad_record)
        instrument["mixable"]["audioRoute"]["channelBitmap"]["data"] = 3
        instrument["mixable"]["volume"] = normalized_volume(int(translated.get("volume", 127))) if assigned else DEFAULT_DRUM_PAD_VOLUME
        instrument["mixable"]["pan"] = DEFAULT_DRUM_PAD_PAN
        instrument["mixable"]["automationFilter"] = 1
        instrument["mixable"]["inserts"]["insertsEnabled"] = True
        instrument["warpTempo"] = 120.0
        instrument["bpmLock"] = False
        instrument["warpEnable"] = False
        instrument["stretchPercentage"] = 100
        filter_data = instrument["synthSection"]["filterData"]["value0"]
        filter_data["filterCutoff"] = normalized_cutoff(translated.get("filter_cutoff", 127))
        filter_data["filterEnvelopeAmount"] = float(translated.get("filter_env_amount", 0.0))
        filter_envelope = instrument["synthSection"]["filterEnvelope"]
        filter_envelope["Decay"]["value0"] = normalized_decay(translated.get("amp_decay_ms", 1500))
        amp_envelope = instrument["synthSection"]["ampEnvelope"]
        amp_envelope["Decay"]["value0"] = normalized_decay(translated.get("amp_decay_ms", 1500))

        layers = instrument["layersv"]
        ensure_xtd_layer(layers[0], active=assigned, sample_name=sample_name, sample_file=sample_file)
        layers[0]["volume"]["gainCoefficient"] = DEFAULT_DRUM_PAD_VOLUME
        layers[0]["volume"]["controlValue"] = DEFAULT_DRUM_PAD_VOLUME
        layers[0]["pan"] = DEFAULT_DRUM_PAD_PAN
        for layer in layers[1:]:
            ensure_xtd_layer(layer, active=False, sample_name="", sample_file="")
            layer["volume"]["gainCoefficient"] = DEFAULT_DRUM_PAD_VOLUME
            layer["volume"]["controlValue"] = DEFAULT_DRUM_PAD_VOLUME
            layer["pan"] = DEFAULT_DRUM_PAD_PAN

    raw_content = xtd_header + json.dumps(xtd_object, indent=4) + "\n"
    xtd_path.parent.mkdir(parents=True, exist_ok=True)
    xtd_path.write_bytes(gzip.compress(raw_content.encode("utf-8")))


def build_expansion_manifest(
    output_root: Path,
    expansion_name: str,
    identifier: str,
    artwork_filename: str,
) -> Path:
    root = ET.Element("expansion", {"version": "1.0"})
    set_child_text(root, "identifier", sanitize_identifier(identifier))
    set_child_text(root, "title", expansion_name)
    set_child_text(root, "manufacturer", EXPANSION_MANUFACTURER)
    set_child_text(root, "version", EXPANSION_VERSION)
    set_child_text(root, "type", EXPANSION_TYPE)
    set_child_text(root, "img", artwork_filename)
    set_child_text(root, "directory", expansion_directory_name(identifier))
    set_child_text(root, "separator", "-")
    manifest_path = output_root / "Expansion.xml"
    write_xml(manifest_path, root)
    return manifest_path


def package_xpn(output_root: Path) -> Path:
    xpn_path = output_root.parent / f"{output_root.name}.xpn"
    if xpn_path.exists():
        xpn_path.unlink()
    with zipfile.ZipFile(xpn_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path in sorted(output_root.rglob("*")):
            if not source_path.is_file():
                continue
            archive_path = PurePosixPath(source_path.relative_to(output_root).as_posix())
            archive.write(source_path, arcname=archive_path.as_posix())
    return xpn_path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.output_root is None:
        args.output_root = root / sanitize_output_root_name(args.expansion_name)
    if args.report_path is None:
        args.report_path = args.output_root.parent / f"{args.output_root.name}_builder_report.json"
    args.organized_root = args.organized_root.resolve()
    args.output_root = args.output_root.resolve()
    args.report_path = args.report_path.resolve()
    args.xpm_template = args.xpm_template.resolve()
    args.xtd_template = args.xtd_template.resolve()
    if args.artwork_source:
        args.artwork_source = args.artwork_source.resolve()

    configure_logging(args.verbose)

    if args.output_root.exists() and args.overwrite:
        remove_output_root(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    xpm_template = load_xpm_template(args.xpm_template)
    xtd_header = ""
    xtd_template: dict[str, Any] | None = None
    if not args.skip_xtd:
        xtd_header, xtd_template = load_xtd_template(args.xtd_template)

    kits = discover_kits(args.organized_root)
    report_entries: list[dict[str, Any]] = []

    for audit_path, manifest_path in kits:
        audit_manifest = load_json(audit_path)
        builder_manifest = load_json(manifest_path)
        collection_name = audit_manifest.get("collection_name")
        sanitized_collection = audit_manifest["sanitized_collection_name"]
        collection_directory = collection_output_directory_name(collection_name, sanitized_collection)
        program_name = builder_manifest["program_name"]
        program_type = builder_manifest["program_type"]
        build_sample_map = build_sample_source_map(audit_manifest)
        public_samples_root = args.output_root / SAMPLES_DIR_NAME / collection_directory / program_name

        program_path = None
        xtd_path = None

        if program_type == "DRUM":
            copy_public_samples(public_samples_root, builder_manifest, build_sample_map)
            drum_output_root = args.output_root / collection_directory
            xtd_path = drum_output_root / f"{program_name}.xtd"
        else:
            programs_output_root = args.output_root / PROGRAMS_DIR_NAME / collection_directory
            public_sample_map = copy_public_samples(public_samples_root, builder_manifest, build_sample_map)
            program_path = programs_output_root / f"{program_name}.xpm"
            xml_root = create_keygroup_program(builder_manifest, program_path, public_sample_map)
            write_xml(program_path, xml_root)

        xtd_relative_path = None
        if program_type == "DRUM" and xtd_template is not None:
            build_drum_xtd(xtd_header, xtd_template, builder_manifest, audit_manifest, build_sample_map, xtd_path)
            xtd_relative_path = expansion_relative_path(xtd_path, args.output_root)

        preview_source_name = program_name
        if xtd_relative_path is not None:
            preview_source_name = Path(xtd_relative_path).name
        elif program_path is not None:
            preview_source_name = program_path.name

        preview_path = args.output_root / PREVIEWS_DIR_NAME / f"{preview_source_name}.wav"
        create_program_preview(preview_path, builder_manifest, audit_manifest, build_sample_map)

        report_entries.append(
            {
                "source_rx1200_path": audit_manifest["source_rx1200_path"],
                "collection_name": collection_name,
                "collection_directory": collection_directory,
                "sanitized_collection_name": sanitized_collection,
                "program_name": program_name,
                "program_type": program_type,
                "program_path": expansion_relative_path(program_path, args.output_root) if program_path else None,
                "preview_path": expansion_relative_path(preview_path, args.output_root),
                "xtd_path": xtd_relative_path,
                "sample_count": len(build_sample_map),
            }
        )
        logging.info("Built %s program %s", program_type, xtd_path if program_type == "DRUM" else program_path)

    artwork_path = create_artwork(args.output_root, args.artwork_source, args.identifier)
    manifest_path = build_expansion_manifest(
        args.output_root,
        args.expansion_name,
        args.identifier,
        artwork_path.name,
    )

    xpn_path = None
    if not args.skip_xpn:
        xpn_path = package_xpn(args.output_root)

    write_json(
        args.report_path,
        {
            "organized_root": args.organized_root.as_posix(),
            "output_root": args.output_root.as_posix(),
            "expansion_name": args.expansion_name,
            "identifier": sanitize_identifier(args.identifier),
            "artwork_path": expansion_relative_path(artwork_path, args.output_root),
            "expansion_manifest_path": expansion_relative_path(manifest_path, args.output_root),
            "xpn_path": xpn_path.as_posix() if xpn_path else None,
            "total_programs_built": len(report_entries),
            "programs": report_entries,
        },
    )
    logging.info("Built %s MPC programs", len(report_entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())