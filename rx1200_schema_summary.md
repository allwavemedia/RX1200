# RX1200 Schema Summary

This document records the `.rx1200` fields the organizer currently uses for asset staging and manifest generation.

## Root structure

Inspected presets use an XML root element named:

`com.inphonik.RX1200`

Observed root attributes:

- `name`
- `author`
- `comment`

Representative source:

- `Ambient/Afterglow.rx1200`
- `Factory Collection/Orient Station.rx1200`
- `Drum & Bass/Cold Precision.rx1200`

## PARAM elements

Most pad-level control data is stored as flat `PARAM` nodes with `id` and `value` attributes.

### Verified pad-keyed fields

These were observed with pad suffixes like `a1`, `b4`, `d8`:

- `pitch_a1`
- `decay_a1`
- `level_a1`
- `pan_a1`
- `output_a1`
- `filter_a1`
- `finetune_a1`
- `gain_a1`
- `mono_a1`
- `speed_a1`

The organizer currently extracts these into per-pad parameter maps for all pads `a1` through `d8`.

### Additional non-pad-keyed or differently-keyed fields

Observed examples include:

- `polyphony_1` through `polyphony_8`
- `volume`
- `velocity`
- `layout`
- `a1_play_range_start`
- `a1_play_range_end`

These are preserved in raw form in `kit_audit.json`.

## SAMPLES block

Sample assignments are stored under a `SAMPLES` container with one `SAMPLE` child per active or potential RX pad.

Observed `SAMPLE` attributes:

- `id`
- `reversed`
- `gain`
- `start`
- `end`

Typical non-empty example:

```xml
<SAMPLE id="a1" reversed="false" gain="1.0" start="0" end="15412">
  <REFERENCES>
    <REFERENCE type="productUserData" value="/Collections/Drum &amp; Bass/Samples/1. Kicks/kick_precision.wav"/>
  </REFERENCES>
</SAMPLE>
```

## REFERENCE nodes

The source sample path is stored on a nested `REFERENCE` node.

Observed fields:

- `type`
- `value`

Observed `type` values:

- `productCommonData`
- `productUserData`

Observed `value` format:

`/Collections/<Collection Name>/Samples/<Category>/<filename>.wav`

The organizer treats the `REFERENCE.value` field as the source of truth for preset-to-sample linkage.

## Empty pad behavior

Some presets intentionally leave pads unused.

Observed empty-pad pattern:

```xml
<SAMPLE id="c2" reversed="false" gain="1.0" start="0" end="0" />
```

No nested `REFERENCE` is present in this case.

Current organizer behavior:

- treat these entries as unused pads
- do not mark them as parse failures
- omit them from `mpc_manifest.json`
- preserve them in `kit_audit.json` as empty-pad records

## XML entity decoding

Drum & Bass presets use XML-escaped collection names inside `REFERENCE.value` fields.

Example:

`/Collections/Drum &amp; Bass/Samples/...`

Current organizer behavior:

- XML-decode the value before filesystem resolution
- resolve against the local `Drum & Bass/Samples` tree

## Path resolution strategy

The organizer resolves sample references in two stages:

1. Exact resolution:
   - strip the leading `/Collections/.../Samples/` prefix
   - resolve the remainder against the local collection `Samples` folder
2. Filename fallback:
   - if the exact path does not exist, search the collection `Samples` tree for a unique filename match

If no unique match exists, the sample is recorded as unresolved.

## Sanitization model

Before any writes, the organizer sanitizes:

- destination collection names
- preset folder names
- copied `.rx1200` filenames
- copied `.wav` filenames

Applied rules:

- `&` becomes `and`
- whitespace becomes `_`
- all other non `[A-Za-z0-9_-]` characters become `_`
- repeated separators collapse
- collisions receive stable numeric suffixes

## Fixed RX to MPC pad mapping

The builder manifest injects this mapping:

- `A1-A8` -> `A01-A08`
- `B1-B8` -> `A09-A16`
- `C1-C8` -> `B01-B08`
- `D1-D8` -> `B09-B16`

## Fields used directly in the builder manifest

Per non-empty pad, the organizer emits:

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

## Translation notes

The following builder values are best-effort translations rather than authoritative RX1200 formulas:

- `volume` from `level`
- `tune_semi` from `pitch` plus `speed`
- `tune_fine` from `finetune` plus residual semitone fraction
- `amp_decay_ms` from `decay`
- `filter_cutoff` from a type-derived default

The script records the exact provisional formulas inside each pad entry in `kit_audit.json`.

## Ambiguities and unresolved issues

### Polyphony mapping

Observed values are keyed as `polyphony_1` through `polyphony_8`, not `polyphony_a1` through `polyphony_d8`.

Current handling:

- preserved raw in `kit_audit.json`
- not forced into a per-pad mapping

### Filter cutoff

Inspected presets expose `filter_*` values with observed enum-like values `0`, `1`, `2`, and `3`.

Current interpretation:

- `0` -> `Off`
- `1` -> `LP 12dB`
- `2` -> `LP 24dB`
- `3` -> `Dyn`

No separate cutoff parameter was found in the inspected XML, so cutoff values in the builder manifest are provisional placeholders.

### Speed-to-pitch math

The organizer currently uses a provisional enum-to-semitone map:

- `1` -> `0.0`
- `2` -> `+5.45`
- `3` -> `+12.0`
- `4` -> `+19.02`

This should be revisited if exact RX1200 speed behavior is documented more precisely.

### Keygroup detection

The organizer defaults presets to `DRUM` and only flags `KEYGROUP` when:

- all non-empty pads reference the same sample
- at least four non-empty pads exist
- at least four distinct pitch/fine-tune combinations exist

This is intentionally conservative.
