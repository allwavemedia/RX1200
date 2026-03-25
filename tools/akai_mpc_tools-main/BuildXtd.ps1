<#
.SYNOPSIS
Creates a new MPC 3.x compatible .XTD from a folder of WAV files, using a template.

.PARAMETER WavFolder
Folder containing WAV files to map to pads.

.PARAMETER TemplateXtd
Path to an existing template file (e.g., your "BoomT Kit" file) to use as a template.

.PARAMETER OutXtd
Output .XTD path. Default: <WavFolderName>.xtd in the WAV folder.

.PARAMETER KitName
Kit/program name written into the XTD. Default: folder name.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$WavFolder,

    [Parameter(Mandatory = $true)]
    [string]$TemplateXtd,

    [string]$OutXtd,

    [string]$KitName
)

# ============================================================
# CONFIGURATION - Fill in these variables for debugging
# ============================================================
# $WavFolder    = ""   # e.g., "C:\Samples\MyKit"
# $TemplateXtd  = ""   # Template with correct pad color settings
# $OutXtd       = ""   # e.g., "C:\Output\MyKit.xtd" (leave empty for auto-naming)
# $KitName      = ""   # e.g., "My Custom Kit" (leave empty to use folder name)
# ============================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

if (-not (Test-Path -LiteralPath $WavFolder)) {
    throw "WavFolder not found: $WavFolder"
}
if (-not (Test-Path -LiteralPath $TemplateXtd)) {
    throw "TemplateXtd not found: $TemplateXtd"
}

$wavFolderLeaf = Split-Path -Leaf (Resolve-Path -LiteralPath $WavFolder)
if ([string]::IsNullOrWhiteSpace("$KitName")) {
    $KitName = $wavFolderLeaf
}
if ([string]::IsNullOrWhiteSpace($OutXtd)) {
    $OutXtd = Join-Path $WavFolder ("$wavFolderLeaf.xtd")
}

# Read template as raw text (uncompressed)
$raw = Get-Content -LiteralPath $TemplateXtd -Raw -Encoding UTF8

# Split header + JSON (JSON starts at first '{')
$idx = $raw.IndexOf("{")
if ($idx -lt 0) {
    throw "Template does not appear to contain JSON (no '{' found)."
}
$header = $raw.Substring(0, $idx)      # keep exactly as-is (includes trailing newlines)
$jsonText = $raw.Substring($idx)

# Parse JSON
$obj = $jsonText | ConvertFrom-Json

# Enumerate WAVs
$wavFiles = @(Get-ChildItem -LiteralPath $WavFolder -File |
    Where-Object { $_.Extension -match '^\.(wav|wave)$' })

if ($wavFiles.Count -eq 0) {
    throw "No WAV files found in: $WavFolder"
}

# =============================================================================
# AI-ENHANCED SAMPLE RECOGNITION
# Uses semantic pattern matching to identify drum samples by full words,
# abbreviations, and common naming conventions across different sample packs.
# =============================================================================

# Function to categorize a WAV file using AI-enhanced pattern recognition
function Get-SampleCategory($fileName) {
    $fn = $fileName.ToLower()
    
    # ==========================================================================
    # CATEGORY 1: KICK / BASS DRUM
    # Common patterns: BD, KD, K, Kick, Bass, BassDrum, BD1, Kick01, etc.
    # Roland R-8: 78K, GATEK, HARDK, PUNCHK, SQUASK, VIDEOK (ends with K)
    # Roland 707: BassDrum1, BassDrum2
    # ==========================================================================
    $kickPatterns = @(
        '(?i)(^|[_\-\s\.])(kick|kik|kck)(\d|[_\-\s\.]|$)',  # Full word variations
        '(?i)(^|[_\-\s\.])(bass\s*drum|bassdrum)(\d|[_\-\s\.]|$)',  # Full name (707 style)
        '(?i)(^|[_\-\s\.])BD(\d|[_\-\s\.]|$)',  # BD abbreviation
        '(?i)(^|[_\-\s\.])KD(\d|[_\-\s\.]|$)',  # KD abbreviation
        '(?i)(^|[_\-\s\.])K(\d)([_\-\s\.]|$)',  # K followed by number (K1, K2)
        '(?i)(^|[_\-\s\.])808[_\-\s\.]*(kick|bass|sub)',  # 808 kick/bass
        '(?i)(^|[_\-\s\.])(sub|boom|thump)([_\-\s\.]|$)',  # Descriptive bass sounds
        '(?i)(^|[_\-\s\.])78K([_\-\s\.]|$)',    # Roland 78K pattern
        '(?i)(GATE|HARD|PUNCH|SQUAS|VIDEO|FAT|DRY|WET|SOFT|DEEP|TIGHT|DANCE|HOUSE|TECHNO|ELECTRO)K(\d|[_\-\s\.]|$)'  # Descriptive + K suffix
    )
    foreach ($pattern in $kickPatterns) {
        if ($fn -match $pattern) { return 1 }
    }
    
    # ==========================================================================
    # CATEGORY 2: SNARE
    # Common patterns: SN, SD, S, Snare, Snr, Rim, RimShot, etc.
    # Roland R-8: 78S, FATS, SPARK, VIDEOS (ends with S but descriptive prefix)
    # Roland 707: Snare1, Snare2, RimShot
    # ==========================================================================
    $snarePatterns = @(
        '(?i)(^|[_\-\s\.])(snare|snr|snar)(\d|[_\-\s\.]|$)',  # Full word variations
        '(?i)(^|[_\-\s\.])SN(\d|[_\-\s\.]|$)',  # SN abbreviation
        '(?i)(^|[_\-\s\.])SD(\d|[_\-\s\.]|$)',  # SD abbreviation
        '(?i)(^|[_\-\s\.])S(\d)([_\-\s\.]|$)',  # S followed by number
        '(?i)(^|[_\-\s\.])(rim\s*shot|rimshot|rim)(\d|[_\-\s\.]|$)',  # Rim shots (snare family)
        '(?i)(^|[_\-\s\.])78S([_\-\s\.]|$)',    # Roland 78S pattern
        '(?i)(FAT|VIDEO|GATE|HARD|PUNCH|DRY|WET|TIGHT|CRISP|BRIGHT|DARK|WARM|COLD)S(\d|[_\-\s\.]|$)',  # Descriptive + S suffix
        '(?i)(^|[_\-\s\.])SPARK(\d|[_\-\s\.]|$)'  # SPARK snare (Roland R-8)
    )
    foreach ($pattern in $snarePatterns) {
        if ($fn -match $pattern) { return 2 }
    }
    
    # ==========================================================================
    # CATEGORY 3: CLOSED HIHAT
    # Common patterns: CH, HH, HHC, HiHatC, ClosedHH, Hat Closed, HhC, etc.
    # Roland R-8: 78CHH
    # Roland 707: HhC
    # ==========================================================================
    $closedHatPatterns = @(
        '(?i)(^|[_\-\s\.])(closed\s*h(i)?hat|closedhh|closedhihat)([_\-\s\.]|$)',  # Full word
        '(?i)(^|[_\-\s\.])HHC(\d|[_\-\s\.]|$)',             # HHC abbreviation
        '(?i)(^|[_\-\s\.])CHH(\d|[_\-\s\.]|$)',             # CHH abbreviation
        '(?i)(^|[_\-\s\.])CH(\d|[_\-\s\.]|$)',              # CH abbreviation
        '(?i)(^|[_\-\s\.])HhC([_\-\s\.]|$)',                # HhC pattern (707 style)
        '(?i)(^|[_\-\s\.])(pedal\s*hat|pedalhat)([_\-\s\.]|$)',  # Pedal hihat
        '(?i)(^|[_\-\s\.])(tight\s*hat|tighthat)([_\-\s\.]|$)',  # Tight hihat
        '(?i)(^|[_\-\s\.])78CHH([_\-\s\.]|$)',              # Roland 78CHH pattern
        '(?i)\d+CHH([_\-\s\.]|$)'                           # Any number prefix + CHH
    )
    foreach ($pattern in $closedHatPatterns) {
        if ($fn -match $pattern) { return 3 }
    }
    
    # ==========================================================================
    # CATEGORY 4: OPEN HIHAT
    # Common patterns: OH, HHO, OpenHH, Hat Open, HhO, etc.
    # Roland R-8: 78OHH
    # Roland 707: HhO
    # ==========================================================================
    $openHatPatterns = @(
        '(?i)(^|[_\-\s\.])(open\s*h(i)?hat|openhh|openhihat)([_\-\s\.]|$)',  # Full word
        '(?i)(^|[_\-\s\.])HHO(\d|[_\-\s\.]|$)',            # HHO abbreviation
        '(?i)(^|[_\-\s\.])OHH(\d|[_\-\s\.]|$)',            # OHH abbreviation
        '(?i)(^|[_\-\s\.])OH(\d|[_\-\s\.]|$)',             # OH abbreviation
        '(?i)(^|[_\-\s\.])HhO([_\-\s\.]|$)',               # HhO pattern (707 style)
        '(?i)(^|[_\-\s\.])(loose\s*hat|loosehat)([_\-\s\.]|$)',  # Loose hihat
        '(?i)(^|[_\-\s\.])78OHH([_\-\s\.]|$)',             # Roland 78OHH pattern
        '(?i)\d+OHH([_\-\s\.]|$)'                          # Any number prefix + OHH
    )
    foreach ($pattern in $openHatPatterns) {
        if ($fn -match $pattern) { return 4 }
    }
    
    # ==========================================================================
    # CATEGORY 5: CLAP / HAND PERCUSSION
    # Common patterns: CL, Clap, HandClap, Clp, Snap, Finger, etc.
    # Roland R-8: DRYCLAP, FINGSNAP
    # Roland 707: HandClap
    # ==========================================================================
    $clapPatterns = @(
        '(?i)(^|[_\-\s\.])(clap|clp|handclap|hand\s*clap)(\d|[_\-\s\.]|$)',  # Full word variations
        '(?i)(^|[_\-\s\.])CL(\d|[_\-\s\.]|$)',             # CL abbreviation
        '(?i)(^|[_\-\s\.])CP(\d|[_\-\s\.]|$)',             # CP abbreviation
        '(?i)(^|[_\-\s\.])(snap|finger\s*snap|fingersnap|fingsnap)(\d|[_\-\s\.]|$)',  # Snap sounds
        '(?i)(DRY|WET|FAT|HARD|SOFT|BIG|TIGHT)CLAP',       # Descriptive + CLAP
        '(?i)CLAP(DRY|WET|FAT|HARD|SOFT|BIG|TIGHT)',       # CLAP + descriptive
        '(?i)(FING|FINGER)(SNAP|SNP)'                       # Finger snap variations
    )
    foreach ($pattern in $clapPatterns) {
        if ($fn -match $pattern) { return 5 }
    }
    
    # ==========================================================================
    # CATEGORY 6: TOMS
    # Common patterns: HT, MT, LT, Tom, HighTom, LowTom, FloorTom, etc.
    # Roland 707: HiTom, MedTom, LowTom
    # ==========================================================================
    $tomPatterns = @(
        '(?i)(^|[_\-\s\.])(tom|toms)(\d|[_\-\s\.]|$)',     # Tom word
        '(?i)(^|[_\-\s\.])(high\s*tom|hightom|hitom)(\d|[_\-\s\.]|$)',  # High tom
        '(?i)(^|[_\-\s\.])(mid\s*tom|midtom|medtom)(\d|[_\-\s\.]|$)',   # Mid tom
        '(?i)(^|[_\-\s\.])(low\s*tom|lowtom|lotom)(\d|[_\-\s\.]|$)',    # Low tom
        '(?i)(^|[_\-\s\.])(floor\s*tom|floortom)(\d|[_\-\s\.]|$)',      # Floor tom
        '(?i)(^|[_\-\s\.])HT(\d|[_\-\s\.]|$)',             # HT abbreviation
        '(?i)(^|[_\-\s\.])MT(\d|[_\-\s\.]|$)',             # MT abbreviation
        '(?i)(^|[_\-\s\.])LT(\d|[_\-\s\.]|$)',             # LT abbreviation
        '(?i)(^|[_\-\s\.])FT(\d|[_\-\s\.]|$)',             # FT abbreviation
        '(?i)(^|[_\-\s\.])(roto\s*tom|rototom)(\d|[_\-\s\.]|$)',  # Roto tom
        '(?i)(^|[_\-\s\.])(timbal|timbale)(\d|[_\-\s\.]|$)'  # Timbales
    )
    foreach ($pattern in $tomPatterns) {
        if ($fn -match $pattern) { return 6 }
    }
    
    # ==========================================================================
    # CATEGORY 8: CYMBAL / CRASH / RIDE
    # Common patterns: Crash, Ride, Cymbal, Cym, CY, etc.
    # Roland 707: Crash, Ride
    # ==========================================================================
    $cymbalPatterns = @(
        '(?i)(^|[_\-\s\.])(crash|crsh)(\d|[_\-\s\.]|$)',   # Crash
        '(?i)(^|[_\-\s\.])(ride|rd)(\d|[_\-\s\.]|$)',      # Ride
        '(?i)(^|[_\-\s\.])(cymbal|cym)(\d|[_\-\s\.]|$)',   # Cymbal
        '(?i)(^|[_\-\s\.])CY(\d|[_\-\s\.]|$)',             # CY abbreviation
        '(?i)(^|[_\-\s\.])CR(\d|[_\-\s\.]|$)',             # CR abbreviation
        '(?i)(^|[_\-\s\.])(splash|china)(\d|[_\-\s\.]|$)'  # Other cymbal types
    )
    foreach ($pattern in $cymbalPatterns) {
        if ($fn -match $pattern) { return 8 }
    }
    
    # ==========================================================================
    # CATEGORY 9: PERCUSSION (Cowbell, Shaker, Tambourine, etc.)
    # Roland R-8: 78COW, 78GUIR, LNGGUI, SHOGUI, 78MARC, CABASA, 78TAMB, 78BNG
    # Roland 707: CowBell, Tamb
    # ==========================================================================
    $percPatterns = @(
        '(?i)(^|[_\-\s\.])(cow\s*bell|cowbell)(\d|[_\-\s\.]|$)',  # Cowbell
        '(?i)(^|[_\-\s\.])(bell)(\d|[_\-\s\.]|$)',          # Bell
        '(?i)(^|[_\-\s\.])\d*COW([_\-\s\.]|$)',            # COW abbreviation (78COW)
        '(?i)(^|[_\-\s\.])(shaker|shake)(\d|[_\-\s\.]|$)',  # Shaker
        '(?i)(^|[_\-\s\.])(tamb|tambourine)(\d|[_\-\s\.]|$)',  # Tambourine
        '(?i)(^|[_\-\s\.])\d*TAMB([_\-\s\.]|$)',           # TAMB abbreviation (78TAMB)
        '(?i)(^|[_\-\s\.])(conga|bongo|bng)(\d|[_\-\s\.]|$)',  # Congas/Bongos
        '(?i)(^|[_\-\s\.])\d*BNG([_\-\s\.]|$)',            # BNG abbreviation (78BNG)
        '(?i)(^|[_\-\s\.])(perc|percussion)(\d|[_\-\s\.]|$)',  # Generic percussion
        '(?i)(^|[_\-\s\.])(wood\s*block|woodblock|block)(\d|[_\-\s\.]|$)',  # Wood block
        '(?i)(^|[_\-\s\.])(triangle|tri)(\d|[_\-\s\.]|$)',  # Triangle
        '(?i)(^|[_\-\s\.])(clave|claves)(\d|[_\-\s\.]|$)',  # Claves
        '(?i)(^|[_\-\s\.])(agogo|guiro|cabasa)(\d|[_\-\s\.]|$)',  # Latin percussion
        '(?i)(^|[_\-\s\.])\d*GUIR([_\-\s\.]|$)',           # GUIR abbreviation (78GUIR)
        '(?i)(^|[_\-\s\.])(LNG|SHO)GUI([_\-\s\.]|$)',      # Long/Short Guiro
        '(?i)(^|[_\-\s\.])\d*MARC([_\-\s\.]|$)',           # MARC = Maracas (78MARC)
        '(?i)(^|[_\-\s\.])(maracas|maraca|marc)(\d|[_\-\s\.]|$)',  # Maracas
        '(?i)(^|[_\-\s\.])(cabasa|cabas)(\d|[_\-\s\.]|$)',  # Cabasa
        '(?i)(^|[_\-\s\.])CABASA([_\-\s\.]|$)',            # CABASA pattern
        '(?i)(^|[_\-\s\.])(mbeat|metronome|click)(\d|[_\-\s\.]|$)',  # Metronome beats
        '(?i)(^|[_\-\s\.])\d*MBEAT([_\-\s\.]|$)',          # MBEAT pattern (78MBEAT)
        '(?i)(^|[_\-\s\.])(djembe|djemb|tabla|darbuka)(\d|[_\-\s\.]|$)',  # World percussion
        '(?i)(^|[_\-\s\.])(vibraslap|vibra)(\d|[_\-\s\.]|$)',  # Vibraslap
        '(?i)(OPEN|MUTE)DI([_\-\s\.]|$)'                   # Open/Mute Didgeridoo or similar
    )
    foreach ($pattern in $percPatterns) {
        if ($fn -match $pattern) { return 9 }
    }
    
    # ==========================================================================
    # CATEGORY 7: OTHER / UNRECOGNIZED
    # ==========================================================================
    return 7
}

# Group WAVs by category, then interleave by round
# Order: 1=Kick, 2=Snare, 3=Closed Hat, 4=Open Hat, 5=Clap, 6=Tom, 7=Other, 8=Cymbal, 9=Percussion
$categorized = $wavFiles | ForEach-Object {
    [pscustomobject]@{
        File = $_
        Category = Get-SampleCategory $_.Name
    }
}

# Group by category and sort each group by name
$groups = @{}
for ($cat = 1; $cat -le 9; $cat++) {
    $groups[$cat] = @($categorized | Where-Object { $_.Category -eq $cat } | Sort-Object { $_.File.Name } | ForEach-Object { $_.File })
}

# Interleave: round 1 of each category, then round 2, etc.
$wavs = @()
$maxCount = ($groups.Values | ForEach-Object { $_.Count } | Measure-Object -Maximum).Maximum
for ($round = 0; $round -lt $maxCount; $round++) {
    for ($cat = 1; $cat -le 9; $cat++) {
        if ($round -lt $groups[$cat].Count) {
            $wavs += $groups[$cat][$round]
        }
    }
}

# Update names
$obj.data.name = $KitName
if ($null -ne $obj.data.program -and $null -ne $obj.data.program.name) {
    $obj.data.program.name = $KitName
}

# Set drum-level to poly mode (note: the JSON uses "poliphony" with a typo)
$obj.data.program.drum.monophonic = $false
if ($null -ne $obj.data.program.drum.poliphony) {
    $obj.data.program.drum.poliphony = 0  # 0 = Poly mode
}

# Set programPads settings for proper color display
# Universal = false: Single pad selection for colors (not all pads same color)
# Type = 4: Dim pads - velocity
# UnusedPads = 0: Show unused pads normally
$obj.data.program.programPads.Universal.value0 = $false
$obj.data.program.programPads.Type.value0 = 4
$obj.data.program.programPads.UnusedPads.value0 = 0
$obj.data.program.programPads.PadsFollowTrackColour.value0 = $false

# Build data.samples array with full metadata
$samples = @()
foreach ($w in $wavs) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($w.Name)
    $samples += [pscustomobject]@{
        version  = 1
        name     = $baseName
        path     = $w.Name
        loadImpl = 0
        metadata = [pscustomobject]@{
            tempo    = 0.0
            rootNote = 60
            tune     = 0.0
            key      = "C Major"
        }
    }
}
$obj.data.samples = $samples

# Map WAVs onto pads (instruments[0..127]), using first layer
$instruments = $obj.data.program.drum.instruments
if ($null -eq $instruments) {
    throw "Template JSON missing: data.program.drum.instruments"
}
if ($instruments.Count -ne 128) {
    Write-Warning "Template has $($instruments.Count) instruments (expected 128). Script will still proceed."
}

for ($i = 0; $i -lt $instruments.Count; $i++) {
    $inst = $instruments[$i]

    # Helper to clear/deactivate a layer
    function Disable-Layer($layer) {
        $layer.active = $false
        $layer.sampleName = ""
        $layer.sampleFile = ""
        $layer.sampleStart = 0
        $layer.sampleEnd = 0
    }

    # Support both old format (layers.value0/1/2/3) and new format (layersv array)
    if ($null -ne $inst.layersv) {
        # New format: layersv is an array
        $layer0 = $inst.layersv[0]
        $layer1 = if ($inst.layersv.Count -gt 1) { $inst.layersv[1] } else { $null }
        $layer2 = if ($inst.layersv.Count -gt 2) { $inst.layersv[2] } else { $null }
        $layer3 = if ($inst.layersv.Count -gt 3) { $inst.layersv[3] } else { $null }
    } else {
        # Old format: layers is an object with value0/1/2/3
        $layer0 = $inst.layers.value0
        $layer1 = $inst.layers.value1
        $layer2 = $inst.layers.value2
        $layer3 = $inst.layers.value3
    }

    if ($i -lt $wavs.Count) {
        $wav = $wavs[$i]
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($wav.Name)

        $layer0.active = $true
        $layer0.sampleName = $baseName
        $layer0.sampleFile = $wav.Name
        $layer0.sampleStart = 0
        $layer0.sampleEnd = 0
        
        # Keep sliceInfo.Start at 0, but don't reset sliceInfo.End 
        # Let MPC auto-detect sample boundaries when loading
        if ($null -ne $layer0.sliceInfo) {
            $layer0.sliceInfo.Start = 0
            $layer0.sliceInfo.LoopStart = 0
            # Don't reset End - MPC will detect it from the actual WAV file
        }
    }
    else {
        Disable-Layer $layer0
    }

    # Disable velocity layers (1-3)
    if ($null -ne $layer1) { Disable-Layer $layer1 }
    if ($null -ne $layer2) { Disable-Layer $layer2 }
    if ($null -ne $layer3) { Disable-Layer $layer3 }
    
    # Set polyphony (poly mode for all) and mute groups
    $inst.monophonic = $false
    $inst.polyphony = 8  # Poly mode
    
    if ($i -lt $wavs.Count) {
        $category = Get-SampleCategory $wavs[$i].Name
        # Hihats (closed=3, open=4) share mute group 1 so they cancel each other
        if ($category -eq 3 -or $category -eq 4) {
            $inst.whichMuteGroup = 1
        } else {
            $inst.whichMuteGroup = 0  # No mute group
        }
    } else {
        $inst.whichMuteGroup = 0
    }
}

# Define pad colors (RGB as integer) for recognized categories
$colorRed       = 0xFF0000   # Red for kick/bass drum
$colorGreen     = 0x00FF00   # Green for snares
$colorYellow    = 0xFFFF00   # Yellow for closed hihats
$colorOrange    = 0xFF8000   # Orange for open hihats
$colorPink      = 0xFF80C0   # Pink for claps
$colorPurple    = 0xFF00FF   # Purple for toms
$colorWhite     = 0xFFFFFF   # White for cymbals/crash/ride
$colorTeal      = 0x00AAAA   # Teal for percussion (cowbell, shaker, etc.)

# Define a palette of distinct colors for unrecognized (category 7) pattern-based assignment
$unrecognizedColorPalette = @(
    0x00FFFF,   # Cyan
    0x8080FF,   # Light Blue
    0xFF8080,   # Light Red/Salmon
    0x80FF80,   # Light Green
    0xFFFF80,   # Light Yellow
    0xFF6060,   # Coral
    0x60FF60,   # Lime
    0x6060FF,   # Periwinkle
    0xC0C0C0,   # Silver
    0x80FFFF,   # Light Cyan
    0xFF80FF,   # Light Magenta
    0xFFCC00,   # Gold
    0x00CC66,   # Sea Green
    0xCC6600,   # Brown
    0x9966FF,   # Violet
    0x66CCCC    # Dusty Teal
)

# Extract the base pattern from a filename (removes trailing numbers and extensions)
# e.g., "BD_808_01.wav" -> "BD_808", "Kick2.wav" -> "Kick", "78K.wav" -> "78K"
function Get-FilePattern($fileName) {
    # Get name without extension
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($fileName)
    
    # Remove trailing numbers (with optional separator like _, -, or space before them)
    # This groups files like "Kick1", "Kick2", "Kick_01", "Kick-02" together as pattern "Kick"
    $pattern = $baseName -replace '[_\-\s]?\d+$', ''
    
    # If the entire name was numbers, use the original name
    if ([string]::IsNullOrWhiteSpace($pattern)) {
        $pattern = $baseName
    }
    
    # Normalize to lowercase for consistent matching
    return $pattern.ToLower()
}

# Build a mapping of file patterns to colors for UNRECOGNIZED samples only
$unrecognizedPatternColorMap = @{}
$unrecognizedPatternIndex = 0

foreach ($wav in $wavs) {
    $category = Get-SampleCategory $wav.Name
    if ($category -eq 7) {
        $pattern = Get-FilePattern $wav.Name
        if (-not $unrecognizedPatternColorMap.ContainsKey($pattern)) {
            # Assign next color from palette (cycles if more patterns than colors)
            $unrecognizedPatternColorMap[$pattern] = $unrecognizedColorPalette[$unrecognizedPatternIndex % $unrecognizedColorPalette.Count]
            $unrecognizedPatternIndex++
        }
    }
}

# Function to determine pad color based on category (or pattern for unrecognized)
function Get-PadColor($fileName) {
    $category = Get-SampleCategory $fileName
    switch ($category) {
        1 { return $colorRed }        # Kick
        2 { return $colorGreen }      # Snare
        3 { return $colorYellow }     # Closed Hat
        4 { return $colorOrange }     # Open Hat
        5 { return $colorPink }       # Clap
        6 { return $colorPurple }     # Tom
        8 { return $colorWhite }      # Cymbal/Crash/Ride
        9 { return $colorTeal }       # Percussion
        default {
            # Category 7 (unrecognized) - use pattern-based color
            $pattern = Get-FilePattern $fileName
            if ($unrecognizedPatternColorMap.ContainsKey($pattern)) {
                return $unrecognizedPatternColorMap[$pattern]
            }
            return 0x00FFFF  # Fallback cyan
        }
    }
}

# Helper to get category name for logging
function Get-CategoryName($category) {
    switch ($category) {
        1 { return "Kick" }
        2 { return "Snare" }
        3 { return "CH" }
        4 { return "OH" }
        5 { return "Clap" }
        6 { return "Tom" }
        8 { return "Cymbal" }
        9 { return "Perc" }
        default { return "Other" }
    }
}

# Helper to get color as hex string for logging
function Get-ColorHex($color) {
    return "0x{0:X6}" -f $color
}

# Show unrecognized pattern color mapping if any exist
if ($unrecognizedPatternColorMap.Count -gt 0) {
    Write-Host "`n=== Unrecognized Pattern Color Mapping ===" -ForegroundColor Yellow
    Write-Host ("{0,-20} {1,-12}" -f "Pattern", "Color")
    Write-Host ("{0,-20} {1,-12}" -f "-------", "-----")
    foreach ($pattern in ($unrecognizedPatternColorMap.Keys | Sort-Object)) {
        $colorHex = Get-ColorHex $unrecognizedPatternColorMap[$pattern]
        Write-Host ("{0,-20} {1,-12}" -f $pattern, $colorHex)
    }
}

# Assign colors to pads and log assignments
Write-Host "`n=== Sample Assignments ===" -ForegroundColor Cyan
Write-Host ("{0,-4} {1,-25} {2,-8} {3,-12}" -f "Pad", "Sample", "Category", "Color")
Write-Host ("{0,-4} {1,-25} {2,-8} {3,-12}" -f "---", "------", "--------", "-----")

$pads = $obj.data.program.programPads.pads
for ($i = 0; $i -lt $wavs.Count; $i++) {
    $sampleName = [System.IO.Path]::GetFileNameWithoutExtension($wavs[$i].Name)
    $category = Get-SampleCategory $wavs[$i].Name
    $categoryName = Get-CategoryName $category
    $color = Get-PadColor $wavs[$i].Name
    $colorHex = Get-ColorHex $color
    
    Write-Host ("{0,-4} {1,-25} {2,-8} {3,-12}" -f $i, $sampleName, $categoryName, $colorHex)
    
    $padProp = "value$i"
    $pads.$padProp = $color
}
Write-Host ""

# Write JSON back (deep!)
$jsonOut = $obj | ConvertTo-Json -Depth 50

# Recombine header + JSON
$outContent = $header + $jsonOut + "`n"

# Compress using GZip (MPC format)
$textBytes = [System.Text.Encoding]::UTF8.GetBytes($outContent)
$ms = [System.IO.MemoryStream]::new()
$gzip = [System.IO.Compression.GZipStream]::new($ms, [System.IO.Compression.CompressionLevel]::Optimal)
$gzip.Write($textBytes, 0, $textBytes.Length)
$gzip.Close()
$compressedBytes = $ms.ToArray()
$ms.Close()

[System.IO.File]::WriteAllBytes($OutXtd, $compressedBytes)

# Create TrackData folder and copy WAV files
$outFolder = Split-Path -Parent $OutXtd
$trackDataFolder = Join-Path $outFolder "${KitName}_[TrackData]"
if (-not (Test-Path -LiteralPath $trackDataFolder)) {
    New-Item -ItemType Directory -Path $trackDataFolder -Force | Out-Null
}
foreach ($wav in $wavs) {
    $destPath = Join-Path $trackDataFolder $wav.Name
    if (-not (Test-Path -LiteralPath $destPath)) {
        Copy-Item -LiteralPath $wav.FullName -Destination $destPath
    }
}

Write-Host "Wrote XTD: $OutXtd"
Write-Host "KitName: $KitName"
Write-Host "WAVs mapped: $($wavs.Count) (to first pads/instruments in template order)"
Write-Host "TrackData folder: $trackDataFolder"
