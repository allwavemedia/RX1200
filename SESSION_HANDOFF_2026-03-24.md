# RX1200 MPC Builder Session Handoff

Date: 2026-03-24

## Scope Of This Session

This session continued the transition from an RX1200-specific export tool into a broader MPC expansion-building workflow, while keeping the current RX1200 content as the active test corpus.

Primary goals addressed in this session:

- compare generated expansion layout to recent installed Akai expansions
- fix preview naming for `.xtd` browsing
- remove drum `.xpm` generation from the standalone build
- move drum kits toward a more Akai-like `.xtd` plus `_[TrackData]` structure
- restore a separate public `Samples/` tree for direct sample browsing
- group drum kits, `_[TrackData]`, and browseable samples by collection

## Completed Work

### 1. Expansion structure was refactored

The current build output under `RX-1200 Expansion/` is now:

- `Ambient/`
- `Drum And Bass/`
- `Factory Collection/`
- `Samples/`
- `[Previews]/`
- `Expansion.xml`
- artwork image

Within each collection folder, the build now writes:

- `<Program>.xtd`
- `<Program>_[TrackData]/`

Within `Samples/`, the build now writes:

- `Samples/Ambient/<Program>/...`
- `Samples/Drum And Bass/<Program>/...`
- `Samples/Factory Collection/<Program>/...`

This was done to support both:

- grouped browsing of drum kits by collection
- direct browsing of individual samples through the MPC browser

### 2. Drum `.xpm` files were removed from the standalone output

The current builder no longer emits drum `.xpm` files in the build output.

Current expected drum artifact pattern is:

- grouped `.xtd`
- sibling `_[TrackData]`
- grouped public `Samples/`
- flat `[Previews]/<Program>.xtd.wav`

### 3. Preview naming was changed to match `.xtd`

Preview filenames now follow the full `.xtd` filename convention, for example:

- `[Previews]/Afterglow.xtd.wav`

This aligns with the behavior observed in installed Akai expansions such as `Producer Kit Essentials`, where preview files are named against the full `.xtd` filename.

### 4. Build cleanup was hardened

The builder previously had intermittent trouble removing the output root on this external volume. A more defensive cleanup path was added so rebuilds can recover when:

- `shutil.rmtree(...)` fails
- `rm -rf` also fails to fully remove the build root

### 5. Installed Akai expansion structure was reviewed and used as a reference

Recent Akai expansions under `/Volumes/MPC Content/Expansions` showed a pattern much closer to:

- root or grouped `.xtd`
- sibling `_[TrackData]`
- minimal `Expansion.xml`
- `[Previews]/`
- no drum `.xpm`

This evidence was used to move the project away from the earlier hybrid `Programs/` drum layout.

## Current Builder State

The current builder is `build_mpc_programs.py`.

Current verified behavior:

- organizes drum kits into collection folders
- writes drum `.xtd` files into those collection folders
- writes drum `_[TrackData]` folders beside each `.xtd`
- writes public sample copies under `Samples/<collection>/<program>/`
- writes flat preview files under `[Previews]/<program>.xtd.wav`
- does not emit drum `.xpm` files

## Current Known Issues

### 1. Some pads still appear at `+6.0 dB`

This issue is not fully resolved.

Progress made so far:

- `instrument["mixable"]["volume"]` in generated `.xtd` files is no longer hardcoded blindly to `1.0` for assigned pads
- it now maps from the staged pad volume using `volume / 127.0`

However, there are still reports that some pads appear with a preset level of `+6.0 dB`, which means the remaining cause is likely not limited to `instrument.mixable.volume`.

### 2. Artwork output still needs review

Custom artwork preservation remains inconsistent. The build still ends up with identifier-style artwork naming in the generated expansion, rather than consistently honoring the preferred custom-artwork output target.

### 3. Preview audition is structurally prepared but still needs hardware confirmation

The preview naming and placement are now set up for `.xtd` audition, but this remains hardware-verification work on the MPC XL.

## Research Leads For The `+6.0 dB` Issue

The `tools/` directory now provides useful reference material for deeper `.xtd` research.

### Relevant files in `tools/`

- `tools/akai_mpc_tools-main/BuildXtd.ps1`
- `tools/akai_mpc_tools-main/Template.xtd`
- `tools/xtd_Template.txt`

### What `BuildXtd.ps1` confirms

`BuildXtd.ps1` is a template-driven `.xtd` construction script for MPC 3.x. It confirms a useful workflow pattern:

- keep the `.xtd` header intact
- parse the JSON payload separately
- mutate only the relevant fields
- preserve the rest of the template structure

This is useful because the remaining gain issue may depend on fields that were previously treated as static template defaults.

### What `Template.xtd` suggests should be investigated

From `tools/akai_mpc_tools-main/Template.xtd`, the following fields are especially relevant:

- top-level `data.volume`
- instrument-level `mixable.volume`
- layer-level `volume.gainCoefficient`
- layer-level `volume.controlValue`
- `inserts.insertsEnabled`
- `effects` arrays
- `padEffects` and `padEffectsData`

Notable observations from the template:

- template-level `mixable.volume` appears around `0.7079457640647888`, not `1.0`
- many layer entries still carry:
  - `gainCoefficient = 1.0`
  - `controlValue = 1.0`
- effect structures are present even when the template stores `effects: []`
- pad effect containers also exist in the structure

### Recommended remediation path for the `+6.0 dB` issue

Future work should compare three sources side by side for the same kit/pad:

1. staged manifest values in `_Organized_Kits/.../mpc_manifest.json`
2. current generated `.xtd`
3. reference or Akai-generated `.xtd` files from known-good content

Fields to inspect in particular:

- `data.volume`
- `instrument.mixable.volume`
- `layers[0].volume.gainCoefficient`
- `layers[0].volume.controlValue`
- any other per-layer or per-pad gain staging fields exposed in the template

It is likely that the remaining `+6.0 dB` behavior comes from one of these conditions:

- `mixable.volume` is correct, but layer gain fields still imply unity gain that MPC renders as `+6.0 dB`
- template defaults are carrying over a boosted effective state elsewhere in the signal chain
- MPC UI is surfacing one field while the builder is currently adjusting a different one

## Future Development Requirements

### 1. Embed effects and effect parameters in `.xtd` or `.xty`

Future development should support writing effects into:

- track insert chains
- pad effects
- effect parameter values
- routing-related effect configuration if exposed by the underlying format

The discovered template structures in `Template.xtd` suggest this is feasible, because the schema already contains:

- `inserts`
- `effects`
- `padEffects`
- `padEffectsData`

Required next step:

- locate a known-good `.xtd` or `.xty` containing configured effects
- diff it against a dry template
- identify which parameter blocks correspond to each effect and its settings

### 2. Generalize the project into a full MPC Expansion Builder alternative

This project should no longer be treated as only an RX1200 emulator export path.

Future intended direction:

- become a general-purpose MPC Expansion Builder alternative
- support arbitrary source kits and sample libraries
- support `.xtd`, `.xty`, and potentially related MPC 3.x track/program formats
- support artwork, previews, grouping, metadata, sample exports, and effects authoring
- support building standalone-ready expansion folders directly

This implies future work in at least four layers:

1. content ingestion
2. MPC file synthesis
3. expansion packaging and metadata
4. validation and reverse-engineering support tooling

## Suggested Immediate Next Tasks

1. Hardware test the current grouped build on the MPC XL.
2. Confirm whether grouped `.xtd` browsing auditions previews correctly.
3. Inspect one or more known-good `.xtd` files with explicit non-default pad levels.
4. Determine which `.xtd` fields actually control the MPC UI pad gain readout.
5. Fix artwork preservation behavior.
6. Begin a small research spike around embedding effects into `.xtd` and `.xty`.

## Files Most Relevant For Continuation

- `build_mpc_programs.py`
- `rx1200_organizer.py`
- `verify_rx1200_organized_kits.py`
- `RX-1200 Expansion_builder_report.json`
- `_Organized_Kits/master_summary.json`
- `_Organized_Kits/verification_report_latest.json`
- `tools/akai_mpc_tools-main/BuildXtd.ps1`
- `tools/akai_mpc_tools-main/Template.xtd`
- `tools/xtd_Template.txt`

## End State At Session Close

At the end of this session, the repository contains a rebuilt grouped standalone expansion layout and the codebase is materially closer to a generalized MPC expansion-generation workflow than it was at the start of the session.

The major unresolved technical issue is the remaining `+6.0 dB` pad-level behavior.

The major strategic direction going forward is to evolve this repository into a full MPC Expansion Builder alternative with support for richer MPC 3.x structures, including future effects embedding.