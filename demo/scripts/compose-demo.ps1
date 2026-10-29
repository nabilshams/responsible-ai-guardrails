param(
    [switch]$SkipNarration
)

$ErrorActionPreference = "Stop"
$demoRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $demoRoot "output"
$python = Join-Path (Split-Path -Parent $demoRoot) ".venv\Scripts\python.exe"
$webm = Join-Path $outputRoot "sensitive-data-protection-demo.webm"
$narration = Join-Path $outputRoot "narration.wav"
$sequence = Join-Path $outputRoot "recording-sequence.json"
$temporaryMp4 = Join-Path $outputRoot "sensitive-data-protection-demo.pending.mp4"
$finalMp4 = Join-Path $outputRoot "sensitive-data-protection-demo.mp4"

foreach ($required in @($webm, $sequence)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required browser asset is missing. Record the browser sequence before composing."
    }
}
$expectedScreenshots = @(
    "01-landing.png",
    "02-capabilities.png",
    "03-redacted-text.png",
    "04-redacted-document.png",
    "05-redacted-image.png",
    "06-ecosystem.png",
    "07-responsible-use.png"
)
$screenshotsRoot = Join-Path $outputRoot "screenshots"
foreach ($screenshot in $expectedScreenshots) {
    $screenshotPath = Join-Path $screenshotsRoot $screenshot
    if (-not (Test-Path -LiteralPath $screenshotPath -PathType Leaf) -or
        (Get-Item -LiteralPath $screenshotPath).Length -eq 0) {
        throw "The reusable browser screenshots are incomplete."
    }
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "The repository .venv Python interpreter is unavailable."
}
$ffmpeg = $null
$ffprobe = $null
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    $ffmpeg = (Get-Command ffmpeg).Source
}
if (Get-Command ffprobe -ErrorAction SilentlyContinue) {
    $ffprobe = (Get-Command ffprobe).Source
}
if (-not $ffmpeg -or -not $ffprobe) {
    $packageJson = Join-Path $demoRoot "package.json"
    if (-not (Test-Path -LiteralPath $packageJson -PathType Leaf)) {
        throw "Project-local FFmpeg is unavailable. From demo, run npm ci."
    }
    $toolPaths = & node -e "const p=require('ffprobe-static'); console.log(JSON.stringify({ffmpeg:require('ffmpeg-static'),ffprobe:typeof p==='string'?p:p.path}))" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Project-local FFmpeg is unavailable. From demo, run npm ci."
    }
    try {
        $tools = $toolPaths | ConvertFrom-Json
        if (-not $ffmpeg) { $ffmpeg = $tools.ffmpeg }
        if (-not $ffprobe) { $ffprobe = $tools.ffprobe }
    } catch {
        throw "Project-local FFmpeg paths could not be resolved."
    }
}
if (-not $ffmpeg -or -not (Test-Path -LiteralPath $ffmpeg -PathType Leaf) -or
    -not $ffprobe -or -not (Test-Path -LiteralPath $ffprobe -PathType Leaf)) {
    throw "FFmpeg and ffprobe binaries are required. From demo, run npm ci."
}

$arguments = @(
    (Join-Path $PSScriptRoot "generate-narration.py"),
    "--assemble",
    "--sequence",
    $sequence
)
if ($SkipNarration) {
    $arguments += "--skip-narration"
}
& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Narration assembly or subtitle generation failed."
}
try {
    $scriptText = (Get-Content -LiteralPath (Join-Path $demoRoot "narration\script.txt") -Raw).Trim()
    $transcriptText = (Get-Content -LiteralPath (Join-Path $outputRoot "transcript.txt") -Raw).Trim()
    $captionText = Get-Content -LiteralPath (Join-Path $outputRoot "sensitive-data-protection-demo.vtt") -Raw
    $cueCount = [regex]::Matches($captionText, "(?m)^\d+$").Count
    if ($scriptText -ne $transcriptText -or
        $captionText -notmatch "^WEBVTT(?:`r?`n)" -or
        $cueCount -ne 7) {
        throw "Captions and transcript validation failed."
    }
} catch {
    throw "The WebVTT subtitles or narration transcript failed validation."
}
if (-not (Test-Path -LiteralPath $narration -PathType Leaf)) {
    throw "The assembled narration track is missing."
}

if (Test-Path -LiteralPath $temporaryMp4) {
    Remove-Item -LiteralPath $temporaryMp4 -Force
}
& $ffmpeg -hide_banner -loglevel error -y `
    -i $webm `
    -i $narration `
    -map 0:v:0 -map 1:a:0 `
    -map_metadata -1 -map_chapters -1 `
    -vf "tpad=stop_mode=clone:stop_duration=2" `
    -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p `
    -c:a aac -b:a 192k -movflags +faststart `
    -shortest $temporaryMp4
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $temporaryMp4 -PathType Leaf)) {
    if (Test-Path -LiteralPath $temporaryMp4) {
        Remove-Item -LiteralPath $temporaryMp4 -Force
    }
    throw "FFmpeg could not create the MP4."
}

$probeOutput = & $ffprobe -v error -show_entries stream=codec_type,width,height -show_entries format=duration -of json $temporaryMp4
if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $temporaryMp4 -Force
    throw "ffprobe could not validate the MP4."
}
try {
    $probe = $probeOutput | ConvertFrom-Json
    $streams = @($probe.streams)
    $videoStreams = @($streams | Where-Object { $_.codec_type -eq "video" })
    $audioStreams = @($streams | Where-Object { $_.codec_type -eq "audio" })
    $duration = [double]$probe.format.duration
    $valid = $streams.Count -eq 2 -and
        $videoStreams.Count -eq 1 -and
        $audioStreams.Count -eq 1 -and
        $videoStreams[0].width -eq 1920 -and
        $videoStreams[0].height -eq 1080 -and
        $duration -ge 195 -and
        $duration -le 240
} catch {
    $valid = $false
}
if (-not $valid) {
    Remove-Item -LiteralPath $temporaryMp4 -Force
    throw "The MP4 must contain one 1920x1080 video stream, one audio stream, and a three-to-four-minute duration."
}

Move-Item -LiteralPath $temporaryMp4 -Destination $finalMp4 -Force
Write-Host "The MP4, WebVTT, transcript, and screenshots were validated in demo\output."
