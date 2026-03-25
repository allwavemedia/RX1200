# MPC Tooling Integration Review for RX1200 Expansion

## Audience

MPC AI Assistant / MPC format and packaging reviewer

## Purpose

This document no longer describes a hypothetical integration path only.

It summarizes:

1. What was discovered from `BuildXtd.ps1` and the bundled MPC resource files.
2. What has already been implemented in the RX1200 conversion pipeline.
3. Which parts are validated structurally.
4. Which remaining areas still require MPC-specific expert judgment.

## Source References Reviewed

The following reference assets were reviewed during the modernization work:

- `tools/akai_mpc_tools-main/BuildXtd.ps1`
- `tools/mpc.app/Contents/Resources/template.xpm`
- `tools/xpm_template.txt`
- `tools/xtd_Template.txt`

## What These References Told Us

### 1. Modern MPC `.xpm` is not purely legacy XML

The reviewed template files showed that modern MPC 3.x program files can include a JSON payload inside `<ProgramPads>` rather than relying only on older-style explicit XML pad metadata.

### 2. Modern MPC `.xtd` is a gzip-compressed text payload

`BuildXtd.ps1` and the local `.xtd` template showed that an `.xtd` file is composed of:

- a plain-text header
- a JSON payload
- full gzip compression of the combined result

### 3. Pad-color logic is sample-name driven

The PowerShell reference uses filename pattern recognition to categorize sounds like kicks, snares, hats, cymbals, and percussion, then assigns color values per category.

### 4. The reference assets implied the original first-pass builder was too old

The original pipeline was structurally useful, but it was not aligned well enough with MPC 3.x expectations around:

- `ProgramPads`
- `.xtd`
- routing semantics
- packaging artifacts
- previews
- track data layout

## Current Implementation Status

The following items are already implemented in the current pipeline.

### Implemented: MPC 3.x-style `ProgramPads`

Status: complete

The builder now emits `.xpm` files using the modern template approach and embeds JSON inside `<ProgramPads>`.

Current behavior:

- drum programs generate `ProgramPads` JSON
- pad colors are populated automatically
- unused pads are represented consistently
- keygroup support remains present in code, though no presets in this library currently classify as `KEYGROUP`

### Implemented: Semantic pad coloring

Status: complete

Logic inspired by `BuildXtd.ps1` was ported into the Python builder.

Current behavior:

- sample names are categorized heuristically
- categories include common drum roles such as kick, snare, closed hat, open hat, clap, tom, cymbal, and percussion-like material
- matching pads receive category colors
- unrecognized material receives fallback palette assignment rather than a flat default everywhere

### Implemented: `.xtd` generation

Status: complete

The builder now emits `.xtd` files for drum programs using the local `tools/xtd_Template.txt` reference.

Current behavior:

- `.xtd` files are generated alongside `.xpm`
- the expected MPC 3.7 header structure is preserved
- the payload is gzip-compressed
- `_[TrackData]` folders are created beside the `.xtd` files
- `.xtd` sample references are copied into those `_[TrackData]` folders

### Implemented: routing correction

Status: complete

This is one of the most important semantic changes.

Earlier in the project, RX `output` grouping was treated as if it should translate to MPC `MuteGroup` behavior.

That is no longer the current implementation.

Current behavior:

- RX `parameters.output` is mapped into MPC routing via `AudioRouteSubIndex`
- MPC `MuteGroup` is forced to `0`

Reason:

- MPC `MuteGroup` is a choke behavior, not an output-bus equivalent
- RX output assignment is closer in meaning to routing/submix selection than choke grouping

### Implemented: relative path packaging discipline

Status: complete

The builder now emits relative paths where packaging semantics require them.

Current behavior:

- `Expansion.xml` uses relative `ProgramPath` entries
- `.xpm` sample references are relative paths
- builder report program and preview paths are relative inside the expansion root

### Implemented: root artwork and package generation

Status: complete

The builder now generates:

- `Artwork.jpg`
- `Expansion.xml`
- `RX-1200 Expansion.xpn`

### Implemented: preview generation

Status: complete, but semantically reviewable

Earlier, preview WAVs were silent placeholders.

Current behavior:

- preview WAVs are now audible
- they are stereo `16-bit PCM`, `44.1 kHz`
- they are generated as short montages built from the kit’s actual staged samples
- they use translated pad volume and pan
- they trim leading silence heuristically
- they clamp segment length using translated decay information
- they normalize the final output to a controlled peak level

Important limitation:

- previews are browse and QA summaries, not exact MPC playback renders
- they do not yet fully model pitch shifting, filter response, exact envelope behavior, or sequence timing

## Validation Already Performed

The current pipeline has already been rebuilt and revalidated after the modernization work.

### Verified output counts

- source presets processed: `100`
- organized kits created: `100`
- staged samples copied: `2014`
- MPC programs built: `100`
- `.xtd` files built: `100`
- preview WAVs built: `100`

### Verified structural results

The verifier currently confirms:

- organized kits are complete
- `.xpm` files exist and parse
- built sample copies exist
- `.xtd` files exist and carry the expected gzip/header structure
- `_[TrackData]` folders exist
- `Expansion.xml` exists and uses valid relative program paths
- `Artwork.jpg` exists
- `.xpn` exists and is a valid archive
- preview WAVs are not silent placeholders anymore

### Preview validation now includes

- WAV validity
- stereo channel count
- `44100 Hz` sample rate
- minimum useful duration
- non-silent signal checks using peak and RMS thresholds

## Areas Still Open for Expert Review

These are the questions that still need MPC-specific review.

### 1. Are the current `.xpm` semantics correct for MPC Desktop and standalone hardware?

The files are structurally valid and template-driven, but an MPC expert should confirm that the emitted field set is semantically appropriate for import and runtime behavior.

Questions:

- Is the current `ProgramPads` JSON sufficient?
- Are any expected nodes or metadata still missing?
- Is `Application_Version 3.0.5.69` the right compatibility target in this context?

### 2. Is the routing interpretation now correct?

Current implementation:

- RX `output` -> MPC `AudioRouteSubIndex`
- MPC `MuteGroup` -> `0`

Questions:

- Is this the right semantic mapping for RX1200 output behavior?
- Should any RX behavior still influence choke-group design at all?

### 3. Is the `.xtd` payload semantically complete enough?

The verifier currently proves structural correctness, but not full semantic parity.

Questions:

- Are all relevant drum/instrument properties represented correctly in `.xtd`?
- Is there any missing required track/program metadata beyond current template usage?
- Should `.xtd` become the primary delivery artifact, or remain paired with `.xpm`?

### 4. Are the preview files appropriate for MPC expansion browsing?

Current implementation makes previews audible and useful, but not fully faithful to final playback.

Questions:

- Is an audible montage sufficient for expansion browsing?
- Should preview generation more closely match MPC-rendered program playback?
- Are there expected Akai conventions for preview duration, loudness, or format beyond the current approach?

### 5. Should any presets become `KEYGROUP` instead of `DRUM`?

Current classification result:

- `100 DRUM`
- `0 KEYGROUP`

Questions:

- Is the current heuristic too conservative?
- Should some Ambient programs be promoted to `KEYGROUP` despite the current automatic result?

### 6. Is additional packaging metadata still needed?

Questions:

- Are there missing descriptors, categories, insert settings, artwork variants, or browser metadata needed for a production-grade Akai expansion?
- Is the current `Expansion.xml` sufficient for broad MPC compatibility?

## Suggested Review Focus

If the MPC AI Assistant or specialist wants the fastest path to useful feedback, the most important review targets are:

1. Routing semantics: `AudioRouteSubIndex` versus `MuteGroup`
2. `.xpm` field completeness and import behavior
3. `.xtd` semantic completeness beyond structural validity
4. Preview suitability for actual MPC browsing expectations
5. Whether any kits should really be `KEYGROUP`

## Files to Inspect During Review

Recommended review files:

- `RX-1200 Expansion/builder_report.json`
- `RX-1200 Expansion/Expansion.xml`
- `RX-1200 Expansion/Artwork.jpg`
- `RX-1200 Expansion.xpn`
- `RX-1200 Expansion/Programs/Ambient/Afterglow.xpm`
- `RX-1200 Expansion/Programs/Ambient/Afterglow.xtd`
- `RX-1200 Expansion/[Previews]/Afterglow.wav`
- `_Organized_Kits/Ambient/Afterglow/mpc_manifest.json`
- `_Organized_Kits/Ambient/Afterglow/kit_audit.json`
- `_Organized_Kits/verification_report.json`
- `session_summary_for_mpc_ai_assistant.md`

## Bottom Line

The original proposal to integrate logic from `BuildXtd.ps1` and the bundled MPC resource templates has already been carried out in substantial form.

This project is no longer asking whether modernization is possible.

It is now asking whether the implemented MPC 3.x-oriented output is semantically correct enough for real-world Akai MPC use and what final refinements are still required before treating the RX1200 conversion pipeline as production-ready.
