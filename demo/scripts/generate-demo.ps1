param(
    [string]$AppUrl,
    [switch]$SkipNarration,
    [switch]$NarrationOnly,
    [switch]$RecordOnly,
    [switch]$ComposeOnly
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$privateProject = Join-Path $repositoryRoot "infra\private"
$demoRoot = Join-Path $repositoryRoot "demo"
$outputRoot = Join-Path $demoRoot "output"
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$nodePackage = Join-Path $demoRoot "node_modules\playwright\package.json"

if (@($NarrationOnly, $RecordOnly, $ComposeOnly).Where({ $_ }).Count -gt 1) {
    throw "Choose at most one of -NarrationOnly, -RecordOnly, and -ComposeOnly."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "The repository .venv Python interpreter is unavailable."
}
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

function Get-AzdDemoValues {
    $raw = & azd -C $privateProject env get-values --environment "rai-private" --no-prompt 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the existing rai-private azd environment. Confirm it is available in infra\private."
    }
    $selected = @{}
    foreach ($line in $raw) {
        $parts = "$line" -split "=", 2
        if ($parts.Count -ne 2 -or $parts[0] -notin @("AZURE_REDACTION_CHAT_URL", "AZURE_SPEECH_ENDPOINT")) {
            continue
        }
        $value = $parts[1]
        if ($value.StartsWith('"')) {
            try {
                $value = ConvertFrom-Json -InputObject $value -ErrorAction Stop
            } catch {
                throw "The selected azd environment contains an invalid value for $($parts[0])."
            }
        }
        $selected[$parts[0]] = "$value"
    }
    return $selected
}

function Assert-ApplicationHealth([string]$url) {
    try {
        $health = Invoke-RestMethod -Uri "$($url.TrimEnd('/'))/healthz" -Method Get -TimeoutSec 20
        if ($health.status -ne "healthy") {
            throw "not healthy"
        }
    } catch {
        throw "The Sensitive Data Protection application health check failed. Confirm the configured URL and application availability."
    }
}

function Invoke-NarrationGeneration([string[]]$arguments, [string]$speechEndpoint) {
    $previousSpeechEndpoint = $env:AZURE_SPEECH_ENDPOINT
    try {
        if ($speechEndpoint) {
            $env:AZURE_SPEECH_ENDPOINT = $speechEndpoint
        }
        & $python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Narration generation failed; no diagnostic response or source content was recorded."
        }
    } finally {
        if ($null -eq $previousSpeechEndpoint) {
            Remove-Item Env:AZURE_SPEECH_ENDPOINT -ErrorAction SilentlyContinue
        } else {
            $env:AZURE_SPEECH_ENDPOINT = $previousSpeechEndpoint
        }
    }
}

if ($ComposeOnly) {
    & (Join-Path $PSScriptRoot "compose-demo.ps1") -SkipNarration:$true
    exit $LASTEXITCODE
}

$azdValues = @{}
if (-not $ComposeOnly) {
    $azdValues = Get-AzdDemoValues
}

if ($NarrationOnly) {
    $speechEndpoint = $azdValues["AZURE_SPEECH_ENDPOINT"]
    if (-not $speechEndpoint) {
        $speechEndpoint = $env:AZURE_SPEECH_ENDPOINT
    }
    if (-not $speechEndpoint) {
        throw "Missing non-secret configuration AZURE_SPEECH_ENDPOINT in the rai-private azd environment."
    }
    Invoke-NarrationGeneration @((Join-Path $PSScriptRoot "generate-narration.py")) $speechEndpoint
    exit 0
}

$resolvedUrl = $AppUrl
if (-not $resolvedUrl) {
    $resolvedUrl = $azdValues["AZURE_REDACTION_CHAT_URL"]
}
if (-not $resolvedUrl) {
    $resolvedUrl = $env:AZURE_REDACTION_CHAT_URL
}
if (-not $resolvedUrl) {
    throw "Missing non-secret configuration AZURE_REDACTION_CHAT_URL in the rai-private azd environment."
}
$uri = $null
if (-not [Uri]::TryCreate($resolvedUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -notin @("https", "http") -or
    ($uri.Scheme -eq "http" -and $uri.Host -notin @("localhost", "127.0.0.1", "::1")) -or
    $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -notin @("/", "")) {
    throw "The application URL must be an HTTPS base URL without credentials, query, or fragment."
}
$normalizedUrl = $uri.GetLeftPart([UriPartial]::Authority)
Assert-ApplicationHealth $normalizedUrl
if (-not (Test-Path -LiteralPath $nodePackage -PathType Leaf)) {
    throw "Local Playwright is not installed. From demo, run npm ci and npx playwright install chromium."
}
if (-not $RecordOnly) {
    $speechEndpoint = $azdValues["AZURE_SPEECH_ENDPOINT"]
    if (-not $speechEndpoint) {
        $speechEndpoint = $env:AZURE_SPEECH_ENDPOINT
    }
    if (-not $SkipNarration -and -not $speechEndpoint) {
        throw "Missing non-secret configuration AZURE_SPEECH_ENDPOINT in the rai-private azd environment."
    }
    $narrationArgs = @((Join-Path $PSScriptRoot "generate-narration.py"))
    if ($SkipNarration) {
        $narrationArgs += "--skip-narration"
    }
    Invoke-NarrationGeneration $narrationArgs $speechEndpoint
}

$previousAppUrl = $env:DEMO_APP_URL
try {
    $env:DEMO_APP_URL = $normalizedUrl
    & node (Join-Path $PSScriptRoot "record-demo.mjs")
    if ($LASTEXITCODE -ne 0) {
        throw "The Playwright demo failed its UI or privacy checks."
    }
} finally {
    if ($null -eq $previousAppUrl) {
        Remove-Item Env:DEMO_APP_URL -ErrorAction SilentlyContinue
    } else {
        $env:DEMO_APP_URL = $previousAppUrl
    }
}

if (-not $RecordOnly) {
    & (Join-Path $PSScriptRoot "compose-demo.ps1") -SkipNarration:$true
    if ($LASTEXITCODE -ne 0) {
        throw "Media composition failed validation."
    }
}
