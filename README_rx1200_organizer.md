# RX1200 Organizer

This workspace now includes a Python staging tool, `rx1200_organizer.py`, that scans the RX1200 source collections, resolves the WAV references used by each preset, and creates self-contained per-kit folders under `_Organized_Kits` for later MPC Expansion conversion.

It also now includes an MPC program builder, `build_mpc_programs.py`, that consumes the staged manifests and emits `.xpm`-style MPC program XML plus an expansion scaffold under `RX-1200 Expansion`.

It also now includes a verification tool, `verify_rx1200_organized_kits.py`, that checks the generated kits against the source presets and the manifest contract.

## What the script does

For each `.rx1200` preset in these source folders:

- `Ambient`
- `Factory Collection`
- `Drum & Bass`

the script:

1. Parses the preset as XML.
2. Extracts pad/sample assignments and pad-level parameters.
3. Resolves each sample reference against the local `Samples` folder in the same source collection.
4. Sanitizes collection names, preset names, copied preset filenames, and copied WAV filenames for MPC-safe paths.
5. Creates a self-contained kit folder under `_Organized_Kits/<Sanitized_Collection>/<Sanitized_Preset>/`.
6. Copies the preset and all resolved samples into that folder.
7. Writes two JSON files:
   - `mpc_manifest.json` — strict downstream builder manifest
   - `kit_audit.json` — richer traceability and parsing report
8. Writes a root-level summary report to `_Organized_Kits/master_summary.json`.
9. Logs actions to `_Organized_Kits/organizer.log`.

## Output layout

The script writes kit folders under:

`/Volumes/Music Production/MPC/User_Expansions/RX1200/_Organized_Kits`

Example:

```text
_Organized_Kits/
  Ambient/
    Afterglow/
      Afterglow.rx1200
      mpc_manifest.json
      kit_audit.json
      samples/
        kick_aurora.wav
        ...
  Factory_Collection/
    Beat_Professor/
      Beat_Professor.rx1200
      ...
  Drum_and_Bass/
    174bpm_Breaks/
      174bpm_Breaks.rx1200
      ...
  master_summary.json
  organizer.log
```

## Running the script

Use the workspace virtual environment interpreter:

```bash
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" rx1200_organizer.py
```

Optional flags:

```bash
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" rx1200_organizer.py --dry-run
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" rx1200_organizer.py --verbose
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" rx1200_organizer.py --overwrite
```

## Verifying the generated kits

Run the verifier after generating or regenerating `_Organized_Kits`:

```bash
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" verify_rx1200_organized_kits.py
```

Optional flags:

```bash
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" verify_rx1200_organized_kits.py --verbose
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" verify_rx1200_organized_kits.py --report-path /custom/path/verification_report.json
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" verify_rx1200_organized_kits.py --build-root "RX-1200 Expansion"
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" verify_rx1200_organized_kits.py --baseline-report _Organized_Kits/verification_report.json --report-path _Organized_Kits/verification_report_latest.json
```

The verifier writes a machine-readable report to:

`/Volumes/Music Production/MPC/User_Expansions/RX1200/_Organized_Kits/verification_report.json`

Current checks include:

1. Every source preset has a matching `kit_audit.json`.
2. Every kit contains the copied `.rx1200` file, `mpc_manifest.json`, and `samples/` directory.
3. The builder manifest pad count matches the number of non-empty source pads for drum kits.
4. The fixed RX-to-MPC pad mapping is intact.
5. Builder `sample_file` values match the audit manifest pad mappings.
6. Resolved copied sample destinations actually exist.
7. Root `master_summary.json` totals match the current source inventory.
8. If `RX-1200 Expansion` exists, the expected built `.xpm` program and copied sample files exist and the program XML type matches the manifest.
9. If `--baseline-report` is supplied, new failures and program-type regressions are surfaced explicitly.

## Building MPC programs

Run the builder after regenerating `_Organized_Kits`:

```bash
"/Volumes/Music Production/MPC/User_Expansions/RX1200/.venv/bin/python" build_mpc_programs.py --overwrite
```

This writes:

- `RX-1200 Expansion/Programs/<Collection>/<Program>.xpm`
- `RX-1200 Expansion/Samples/<Collection>/<Program>/...`
- `RX-1200 Expansion/Manifests/<Collection>/<Program>/mpc_manifest.json`
- `RX-1200 Expansion/Expansion.xml`
- `RX-1200 Expansion/builder_report.json`

The builder uses the staged `mpc_manifest.json` as the contract and the sibling `kit_audit.json` as supplemental context for pad pan, mono, and sample-copy details.

## Default behavior

- Existing kit folders are skipped by default.
- `--overwrite` is required if you want to replace already-created destination kit folders.
- The script only scans the three target RX1200 collections.
- Image files and other unrelated assets are ignored.
- Missing or unresolved sample references are logged and recorded in both `kit_audit.json` and `master_summary.json`.

## Sanitization rules

Before any destination paths are created, the organizer sanitizes:

- collection folder names
- preset folder names
- copied `.rx1200` filenames
- copied `.wav` filenames

Applied rules:

1. Replace `&` with `and`.
2. Replace whitespace with underscores.
3. Replace all remaining non `[A-Za-z0-9_-]` characters with underscores.
4. Collapse repeated underscores and trim leading/trailing separators.
5. Add stable numeric suffixes when sanitization would otherwise create collisions.

Examples:

- `Drum & Bass` -> `Drum_and_Bass`
- `Drum Kit Stadium` -> `Drum_Kit_Stadium`

## Manifest roles

### `mpc_manifest.json`

This file follows the strict builder schema expected by the downstream MPC program builder:

- `program_name`
- `program_type`
- `original_rx_file`
- `pads` or `keygroups`

For drum programs, each pad entry includes:

- `rx_pad`
- `mpc_pad`
- `sample_file`
- `volume`
- `tune_semi`
- `tune_fine`
- `amp_decay_ms`
- `mute_group`
- `filter_type`
- `filter_cutoff`

### `kit_audit.json`

This file is intentionally richer than the builder manifest. It preserves:

- source and destination paths
- raw referenced sample values from the preset XML
- resolved source sample paths and copy destinations
- unresolved references and error reasons
- full per-pad parameter maps
- extracted sample metadata
- heuristic reasoning for `program_type`
- warnings for provisional translation logic

## Locked pad mapping

The script injects the fixed MPC pad mapping requested for downstream conversion:

- RX `a1-a8` -> MPC `A01-A08`
- RX `b1-b8` -> MPC `A09-A16`
- RX `c1-c8` -> MPC `B01-B08`
- RX `d1-d8` -> MPC `B09-B16`

## Output to mute-group mapping

RX `output_*` values are translated into MPC `mute_group` values.

Current behavior:

- RX outputs are treated as zero-based values found in the preset files.
- The builder manifest writes `mute_group = output + 1`.
- Pads sharing the same RX output therefore share the same MPC mute group.

## Program type logic

The organizer defaults `program_type` to `DRUM` unless a preset is conservatively flagged as melodic.

Current heuristic:

- the preset must have at least 4 non-empty pads
- all non-empty pads must reference the same sample
- those pads must use at least 4 distinct pitch/fine-tune combinations

If that condition is met, the builder manifest uses `KEYGROUP`; otherwise it uses `DRUM`.

## Provisional translation formulas

Some RX1200 parameters map cleanly to the builder manifest. Others require a best-effort approximation because the reference docs describe the target fields but do not define the exact numerical conversion formula.

Current provisional mappings:

- `volume`: `level * 127`
- `tune_semi`: `round(pitch * 127)` is treated as an RX coarse-tune value centered at `64`, using `8` stored steps per semitone before splitting to semi/fine
- `tune_fine`: `(finetune - 0.5) * 100` cents is merged into the total semitone value before final semi/fine splitting
- `speed` offsets: enum mapping `{1: 0, 2: +5.45, 3: +12.0, 4: +19.02}` semitones
- `amp_decay_ms`: exponential mapping from `0..1` to `50..8000` ms so short decays keep more resolution
- `filter_cutoff`: type-derived defaults with an additional filter-envelope amount for `Dyn`

These formulas are documented again in `kit_audit.json` for each pad so they can be revisited later without reparsing source presets.

## Known ambiguities preserved explicitly

- `polyphony` appears in inspected presets as `polyphony_1` through `polyphony_8`, not pad-keyed values like `polyphony_a1`. The script preserves these raw values in `kit_audit.json` rather than inventing a pad mapping.
- Filter cutoff is provisional because no separate cutoff parameter was found in the inspected XML.
- Speed-to-pitch translation is provisional and should be refined if the exact RX1200 speed math is documented elsewhere.

## Verification expectations

The expected source inventory is:

- 25 presets in `Ambient`
- 50 presets in `Factory Collection`
- 25 presets in `Drum & Bass`
- 100 presets total

After a run, verify:

1. `_Organized_Kits/master_summary.json` reports 100 processed presets.
2. Spot-check one kit from each collection.
3. Confirm `Factory_Collection/Orient_Station` or another partial kit omits empty pads from `mpc_manifest.json`.
4. Confirm a Drum & Bass kit resolves `Drum & Bass` XML references correctly into local samples.
5. Run `verify_rx1200_organized_kits.py` and confirm `_Organized_Kits/verification_report.json` reports `"status": "passed"`.
