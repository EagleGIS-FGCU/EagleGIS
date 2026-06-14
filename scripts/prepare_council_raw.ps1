param(
    [string]$SourceRef = "origin/script",
    [string]$SourceSubdir = "pdfs",
    [string]$OutRoot = "data/raw/council"
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root) {
        throw "Unable to determine git repository root."
    }
    return $root.Trim()
}

function Get-DateFromFilename {
    param([string]$Filename)

    if ($Filename -match '(20\d{2})-(\d{2})-(\d{2})') {
        return "{0}-{1}-{2}" -f $matches[1], $matches[2], $matches[3]
    }
    if ($Filename -match '(20\d{2})(\d{2})-(\d{2})') {
        return "{0}-{1}-{2}" -f $matches[1], $matches[2], $matches[3]
    }
    if ($Filename -match '(20\d{2})(\d{2})(\d{2})') {
        return "{0}-{1}-{2}" -f $matches[1], $matches[2], $matches[3]
    }
    if ($Filename -match '(\d{1,2})(\d{2})(20\d{2})') {
        return "{0}-{1:D2}-{2:D2}" -f $matches[3], [int]$matches[1], [int]$matches[2]
    }
    if ($Filename -match '(\d{2})(\d{2})(\d{2,4})') {
        $year = $matches[3]
        if ($year.Length -eq 2) {
            $year = "20$year"
        }
        return "{0}-{1:D2}-{2:D2}" -f $year, [int]$matches[1], [int]$matches[2]
    }
    return $null
}

function Get-YearFromDate {
    param([string]$IsoDate)

    if ($IsoDate -match '^(\d{4})-\d{2}-\d{2}$') {
        return $matches[1]
    }
    return "unknown"
}

function Test-ValidIsoDate {
    param([string]$IsoDate)

    if (-not $IsoDate) {
        return $false
    }
    try {
        [void][datetime]::ParseExact($IsoDate, 'yyyy-MM-dd', $null)
        return $true
    } catch {
        return $false
    }
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$tmpRoot = Join-Path $repoRoot ".tmp"
$extractRoot = Join-Path $tmpRoot "council-raw-source"
$archivePath = Join-Path $tmpRoot "council-raw-source.tar"
$resolvedOutRoot = Join-Path $repoRoot $OutRoot

New-Item -ItemType Directory -Force $tmpRoot | Out-Null
if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}
New-Item -ItemType Directory -Force $extractRoot | Out-Null

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

cmd /c "git archive $SourceRef $SourceSubdir > `"$archivePath`""
tar -xf $archivePath -C $extractRoot

$sourceDir = Join-Path $extractRoot $SourceSubdir
$legacyCsvPath = Join-Path $sourceDir "Estero_Meetings_Final.csv"
if (-not (Test-Path -LiteralPath $legacyCsvPath)) {
    throw "Missing legacy source CSV at $legacyCsvPath"
}

$legacyRows = Import-Csv $legacyCsvPath
$legacyByFilename = @{}
foreach ($row in $legacyRows) {
    $url = $row.MinutesURL
    if (-not $url) {
        continue
    }
    $filename = [System.Uri]::UnescapeDataString(($url -split "/")[-1])
    if (-not $legacyByFilename.ContainsKey($filename)) {
        $legacyByFilename[$filename] = New-Object System.Collections.Generic.List[object]
    }
    $legacyByFilename[$filename].Add($row)
}

if (Test-Path -LiteralPath $resolvedOutRoot) {
    Remove-Item -LiteralPath $resolvedOutRoot -Recurse -Force
}
New-Item -ItemType Directory -Force $resolvedOutRoot | Out-Null

$manifestRows = New-Object System.Collections.Generic.List[object]
$pdfFiles = Get-ChildItem -LiteralPath $sourceDir -Filter *.pdf | Sort-Object Name

foreach ($pdf in $pdfFiles) {
    $matchingRows = $legacyByFilename[$pdf.Name]
    $legacyRow = if ($matchingRows -and $matchingRows.Count -gt 0) { $matchingRows[0] } else { $null }

    $legacyMeetingDate = if ($legacyRow) { $legacyRow.MeetingDate } else { $null }
    $meetingDate = if (Test-ValidIsoDate $legacyMeetingDate) { $legacyMeetingDate } else { Get-DateFromFilename $pdf.Name }
    $year = Get-YearFromDate $meetingDate
    $yearDir = Join-Path $resolvedOutRoot $year
    New-Item -ItemType Directory -Force $yearDir | Out-Null

    $destPath = Join-Path $yearDir $pdf.Name
    Copy-Item -LiteralPath $pdf.FullName -Destination $destPath -Force

    $manifestRows.Add([pscustomobject]@{
        year = $year
        meeting_date = $meetingDate
        meeting_type = if ($legacyRow) { $legacyRow.MeetingType } else { "" }
        title = if ($legacyRow) { $legacyRow.Title } else { "" }
        source_filename = $pdf.Name
        source_branch_path = "$SourceSubdir/$($pdf.Name)"
        minutes_url = if ($legacyRow) { $legacyRow.MinutesURL } else { "" }
        output_path = ($destPath.Substring($repoRoot.Length + 1) -replace '\\', '/')
    }) | Out-Null
}

$manifestPath = Join-Path $resolvedOutRoot "manifest_council.csv"
$manifestRows |
    Sort-Object meeting_date, source_filename |
    Export-Csv -NoTypeInformation -Encoding UTF8 $manifestPath

$yearCounts = $manifestRows |
    Group-Object year |
    Sort-Object Name |
    ForEach-Object { "- $($_.Name): $($_.Count) PDFs" }

$readmePath = Join-Path $resolvedOutRoot "README.md"
$readmeLines = New-Object System.Collections.Generic.List[string]
$readmeLines.Add("# Village Council raw corpus") | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add([string]::Format('Village Council meeting-minutes PDFs prepared from `{0}:{1}` for offline extraction work.', $SourceRef, $SourceSubdir)) | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add("## Scope") | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add("- **Board:** Village Council") | Out-Null
$readmeLines.Add([string]::Format('- **Source ref:** `{0}`', $SourceRef)) | Out-Null
$readmeLines.Add([string]::Format('- **PDF count:** {0}', $pdfFiles.Count)) | Out-Null
$readmeLines.Add('- **Layout:** year-scoped folders under `data/raw/council/`') | Out-Null
$readmeLines.Add('- **Manifest:** `manifest_council.csv`') | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add("## Year counts") | Out-Null
$readmeLines.Add("") | Out-Null
foreach ($line in $yearCounts) {
    $readmeLines.Add($line) | Out-Null
}
$readmeLines.Add("") | Out-Null
$readmeLines.Add("## Rebuild") | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add("From repo root:") | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add('```powershell') | Out-Null
$readmeLines.Add("powershell -ExecutionPolicy Bypass -File scripts/prepare_council_raw.ps1") | Out-Null
$readmeLines.Add('```') | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add("## Notes") | Out-Null
$readmeLines.Add("") | Out-Null
$readmeLines.Add("- Files keep their original branch filenames; the manifest supplies canonical meeting dates and metadata.") | Out-Null
$readmeLines.Add("- This folder is ignored by git on the current branch, so it is treated as a local working corpus unless that policy changes.") | Out-Null
$readmeLines | Set-Content -LiteralPath $readmePath -Encoding UTF8

Remove-Item -LiteralPath $extractRoot -Recurse -Force
Remove-Item -LiteralPath $archivePath -Force

Write-Host "Prepared Council corpus at $OutRoot"
Write-Host "PDFs: $($pdfFiles.Count)"
Write-Host "Manifest: $($manifestRows.Count) rows"
