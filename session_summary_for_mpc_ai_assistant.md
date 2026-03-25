# RX1200 to MPC Expansion Current State Summary

## Purpose

This document reflects the current on-disk state of the RX1200-to-MPC workspace after reviewing:

- source collections
- organized kit outputs
- current builder and verifier code
- current build artifacts under `RX-1200 Expansion`
- current verification reports
- repository memory notes

It is intended to separate what is currently verified from what is still provisional, stale, undocumented, or in need of MPC-specific review.

Last refreshed: `2026-03-23`

## Workspace Scope

- Workspace root: `/Volumes/Music Production/MPC/User_Expansions/RX1200`
- Source collections:
  - `Ambient`
  - `Factory Collection`
  - `Drum & Bass`
- Source preset count: `100`
  - `Ambient`: `25`
  - `Factory Collection`: `50`
  - `Drum & Bass`: `25`

## Current Verified State

The current workspace verifies cleanly against the actual build root `RX-1200 Expansion`.

Verified on `2026-03-23` by running:

```bash
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" verify_rx1200_organized_kits.py --build-root "RX-1200 Expansion" --baseline-report _Organized_Kits/verification_report.json --report-path _Organized_Kits/verification_report_latest.json
```

Current verified totals:

- `100` source presets discovered
- `100` kit audit manifests present
- `100` organized kits present
- `2014` staged samples copied
- `100` `.xpm` programs present
- `100` `.xtd` files present
- `100` preview WAVs present
- `100` per-program manifest copies present under `RX-1200 Expansion/Manifests`
- `0` verification failures
- `0` build artifact check failures
- `0` baseline regressions in `verification_report_latest.json`

The refreshed verifier report now points at the current build root:

- `build_root`: `/Volumes/Music Production/MPC/User_Expansions/RX1200/RX-1200 Expansion`
- `status`: `passed`

## Current Project Components

### Source and staging

- `rx1200_organizer.py`
  - Parses `.rx1200` XML presets.
  - Resolves sample references.
  - Copies kits into `_Organized_Kits`.
  - Emits `mpc_manifest.json`, `kit_audit.json`, and `master_summary.json`.

- `_Organized_Kits`
  - Current organized-kit staging root.
  - Contains per-kit staged presets, copied samples, strict manifests, and audit manifests.

### Build and package generation

- `build_mpc_programs.py`
  - Builds the current MPC expansion into `RX-1200 Expansion`.
  - Generates `.xpm`, `.xtd`, `_[TrackData]` folders, preview WAVs, artwork, `Expansion.xml`, and `builder_report.json`.
  - Packages the build as `RX-1200 Expansion.xpn`.

- `RX-1200 Expansion`
  - Current authoritative build root.
  - Contains:
    - `Programs/`
    - `Samples/`
    - `Manifests/`
    - `[Previews]/`
    - `Artwork.jpg`
    - `Expansion.xml`
    - `builder_report.json`
    - `rx1200-artwork.png`

### Verification

- `verify_rx1200_organized_kits.py`
  - Verifies organized kits and built MPC artifacts.
  - Auto-prefers `RX-1200 Expansion` as the default build root.
  - Retains compatibility fallback for legacy `_MPC_Expansion` if present.

### Documentation and supporting files

- `README_rx1200_organizer.md`
- `rx1200_schema_summary.md`
- `mpc_tools_integration_proposal.md`
- `session_summary_for_mpc_ai_assistant.md`

## Confirmed Implementation Semantics

The following items are confirmed from the current Python source, not inferred from older notes.

### Output root behavior

- The builder default expansion name is `RX-1200 Expansion`.
- The builder still defines `LEGACY_OUTPUT_ROOT_NAME = "_MPC_Expansion"` for compatibility-related logic.
- The verifier prefers `RX-1200 Expansion` and only falls back to `_MPC_Expansion` if the preferred root does not exist.

This means the current project has effectively migrated to `RX-1200 Expansion`, but legacy naming assumptions still exist in code for backward compatibility.

### Pad and routing behavior

- RX pads are still translated with the fixed RX-to-MPC pad mapping:
  - `a1-a8 -> A01-A08`
  - `b1-b8 -> A09-A16`
  - `c1-c8 -> B01-B08`
  - `d1-d8 -> B09-B16`

- Current builder behavior for routing and choke groups is:
  - MPC `MuteGroup` is forced to `0` in generated drum instruments.
  - RX output information is used to derive `AudioRouteSubIndex`.
  - The XTD JSON payload also writes `whichMuteGroup = 0` and sets `audioRouteSubIndex` from the translated pad record.

This confirms the current implementation is routing-based, not choke-group-based.

### Preview generation behavior

- Preview WAVs are generated from actual staged sample content.
- Output format is stereo `16-bit PCM` at `44100 Hz`.
- Current builder constants confirm the montage-style preview strategy:
  - up to `8` segments
  - short fades and gaps
  - duration clamps per segment
  - peak normalization target

- Current verifier behavior confirms previews are validated for:
  - WAV structure
  - stereo channel count
  - `44100 Hz` sample rate
  - minimum duration
  - non-silent signal using peak and RMS thresholds

### Program type classification

- Current corpus result remains:
  - `100` `DRUM`
  - `0` `KEYGROUP`

The builder still has keygroup support in principle, but the present RX1200 library did not trigger it.

## Current Artifacts and Observed Drift

The workspace review found several places where generated artifacts, documentation, and memory were not fully aligned.

### 1. Verification report drift has now been corrected

Earlier workspace state suggested the latest verification report still referenced `_MPC_Expansion`.

After re-running verification against the actual build root, the current file:

- `_Organized_Kits/verification_report_latest.json`

now correctly references:

- `/Volumes/Music Production/MPC/User_Expansions/RX1200/RX-1200 Expansion`

and still reports `0` failures and `0` regressions.

### 2. README documentation is currently stale in one important area

`README_rx1200_organizer.md` still describes RX `output_*` values as driving MPC `mute_group` values.

That is no longer true in the current builder implementation.

Current code behavior is:

- `MuteGroup = 0`
- routing derived through `AudioRouteSubIndex`

This is the most important documentation mismatch currently present in the workspace.

### 3. Repository memory was stale about the build root

The repository memory file previously described builder output under `_MPC_Expansion`.

That no longer reflects the current default build root and should be treated as historical context unless updated.

### 4. Two root `.xpn` packages currently exist

The workspace root currently contains both:

- `RX-1200 Expansion.xpn`
- `rx1200_expansion.xpn`

Important current facts:

- they are both large package artifacts
- they are not byte-identical
- the current builder report and verifier both reference `RX-1200 Expansion.xpn`
- the lowercase `rx1200_expansion.xpn` is not referenced by current builder output, current verification output, or current documentation

This makes `rx1200_expansion.xpn` a likely legacy or alternate package artifact whose provenance should be clarified before treating the workspace as release-clean.

## What Has Been Developed

At this point the project is more than a parser or staging utility. It currently includes:

1. RX1200 preset parsing from XML source files.
2. Sample reference resolution across three source collections.
3. Sanitized, self-contained kit staging under `_Organized_Kits`.
4. Strict builder manifests plus richer audit manifests.
5. MPC expansion generation under `RX-1200 Expansion`.
6. MPC 3.x-oriented `.xpm` generation using template-driven output.
7. `.xtd` generation with gzip-compressed MPC-style payloads.
8. Sibling `_[TrackData]` asset generation.
9. Preview WAV montage generation from actual source audio.
10. Artwork generation and packaging manifest generation.
11. `.xpn` packaging.
12. Automated verification for staging and built artifacts.
13. Baseline comparison support for regression tracking.

## What Still Needs Further Revision

The pipeline runs and verifies structurally, but several areas still need deliberate follow-up before this should be treated as production-final.

### 1. Documentation synchronization

The summary, README, and repository memory need to stay aligned with the actual codebase.

Immediate cleanup target:

- remove or correct the obsolete README description that maps RX output to MPC mute groups

### 2. Package artifact cleanup

The workspace should decide whether `rx1200_expansion.xpn` is:

- a stale artifact to remove
- an alternate export to preserve intentionally
- or evidence of a packaging-path inconsistency that should be formalized

Right now it is ambiguous.

### 3. MPC semantic fidelity review

The largest remaining risk is not pipeline execution. It is semantic faithfulness.

Still open for MPC specialist review:

1. Whether the generated `.xpm` files import cleanly on MPC Desktop 3.x and standalone hardware.
2. Whether the current routing interpretation of RX `output` is the right musical mapping.
3. Whether tune, decay, speed, and filter approximations are musically appropriate.
4. Whether any RX1200 presets should be promoted from `DRUM` to `KEYGROUP` with a more permissive heuristic.
5. Whether the current `.xtd` payload is semantically complete enough beyond structural validation.
6. Whether the current preview montage strategy is sufficient for browsing, or should emulate playback more closely.
7. Whether any additional MPC metadata, category tags, inserts, descriptors, or packaging members are still missing.

### 4. Real-device validation

The project currently has strong structural verification, but this is still not the same as confirmed import and browsing behavior on:

- MPC Desktop 3.x
- current standalone MPC hardware

That should be treated as the next hard validation gate.

## Current Best Evidence Files

For the most current state, use these files as the primary references:

- `_Organized_Kits/master_summary.json`
- `_Organized_Kits/verification_report_latest.json`
- `RX-1200 Expansion/builder_report.json`
- `RX-1200 Expansion/Expansion.xml`
- `RX-1200 Expansion/Programs/Ambient/Afterglow.xpm`
- `RX-1200 Expansion/Programs/Ambient/Afterglow.xtd`
- `RX-1200 Expansion/[Previews]/Afterglow.wav`
- `README_rx1200_organizer.md`
- `build_mpc_programs.py`
- `verify_rx1200_organized_kits.py`

## Tree Snapshots Added

The workspace now also includes current markdown snapshots of:

- `rx1200_expansion_file_tree.md`
- `workspace_file_tree.md`

These were generated from the current on-disk workspace state. The workspace tree excludes only `.venv` and `__pycache__` directories.

## Bottom Line

The current project state is stronger than an experimental conversion pass.

It is now a working RX1200-to-MPC build pipeline with:

- source parsing
- organized staging
- manifest generation
- MPC build output generation
- preview generation
- artwork generation
- `.xpn` packaging
- automated verification with regression comparison

The main remaining risk is no longer whether the pipeline executes.

The main remaining risk is whether the current semantics, metadata, and generated artifacts are fully faithful to real MPC Desktop and standalone behavior, and whether the remaining documentation and artifact drift is cleaned up before release.
