<#
.SYNOPSIS
  Install LocalDrop on Windows from a GitHub release.

.DESCRIPTION
  Downloads the release archive, verifies its SHA-256 against the published
  SHA256SUMS file, unpacks it to Program Files, creates the data directory,
  adds Start Menu (and optionally desktop) shortcuts, and runs `localdrop
  --check` to prove the install works.

  The easiest path is the signed installer instead:
      https://github.com/Abhi-Subedi/LocalDrop/releases

.EXAMPLE
  irm https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.ps1 | iex

.EXAMPLE
  .\install.ps1 -Version 1.1.0

.EXAMPLE
  .\install.ps1 -NoShortcuts -StartServer
#>
[CmdletBinding()]
param(
  # stable | latest | an exact version such as 1.1.0
  [string]$Version = 'stable',
  # Install location. Default: $env:LOCALAPPDATA\LocalDrop (no admin needed).
  [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'LocalDrop'),
  # Where files, the database and thumbnails live.
  [string]$DataDir = (Join-Path $env:LOCALAPPDATA 'LocalDrop\data'),
  [switch]$NoShortcuts,
  [switch]$StartServer,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Repo        = 'Abhi-Subedi/LocalDrop'
$BaseUrl     = "https://github.com/$Repo"
$RawBase     = "https://raw.githubusercontent.com/$Repo"
$ToolName    = 'localdrop'
$ExeName     = 'localdrop.exe'

function Write-Step   { param($m) Write-Host "`n== $m" -ForegroundColor Cyan }
function Write-Ok     { param($m) Write-Host "  $m" -ForegroundColor Green }
function Write-Info   { param($m) Write-Host "  $m" }
function Write-Warn2  { param($m) Write-Host "  $m" -ForegroundColor Yellow }
function Fail         { param($m) Write-Host "`n  ERROR: $m`n" -ForegroundColor Red; exit 1 }

# --- resolve "stable" / "latest" to a real version -------------------------
# Two sources, tried in order:
#
#   1. The releases API. "latest" there is by definition a published,
#      non-prerelease release, so it can never name a version whose assets do
#      not exist. That correctness is the whole reason it goes first.
#   2. The VERSION file on main. Kept as a fallback because networks are
#      uneven: some reach raw.githubusercontent.com and not api.github.com,
#      some the reverse. Depending on a single host made every install hostage
#      to that host.
#
# This previously read only the VERSION file, so a 404 from
# raw.githubusercontent.com aborted with a bare "404" and no clue which host had
# failed or what to do about it.
if ($Version -in @('stable', 'latest', '')) {
  Write-Step 'Resolving the current release'

  $apiBase = if ($env:LOCALDROP_API_URL) { $env:LOCALDROP_API_URL } else { 'https://api.github.com' }
  $headers = @{ 'User-Agent' = 'localdrop-installer' }
  if ($env:GITHUB_TOKEN) { $headers['Authorization'] = "Bearer $env:GITHUB_TOKEN" }

  $resolved = $null
  $why = @()

  try {
    $release = Invoke-RestMethod "$apiBase/repos/$Repo/releases/latest" -Headers $headers -TimeoutSec 30
    $resolved = ($release.tag_name -replace '^v', '').Trim()
  } catch {
    $why += "releases API ($apiBase): $($_.Exception.Message)"
  }

  if (-not $resolved) {
    # $RawBase is the repo root; raw.githubusercontent.com needs the ref, so
    # this is .../LocalDrop/main/VERSION. Omitting "/main" is a silent 404 -
    # the URL looks right and there is no such file at the root.
    try {
      $resolved = (Invoke-RestMethod "$RawBase/main/VERSION" -TimeoutSec 30).Trim()
    } catch {
      $why += "VERSION file ($RawBase/main/VERSION): $($_.Exception.Message)"
    }
  }

  if ($resolved -notmatch '^\d+\.\d+\.\d+$') {
    $detail = if ($why) { "`n  tried:`n" + (($why | ForEach-Object { "    - $_" }) -join "`n") } else { '' }
    Fail "could not resolve the current stable version.$detail`n`n  Look up the newest version at $BaseUrl/releases, then pin it:`n    irm https://raw.githubusercontent.com/$Repo/main/install.ps1 -OutFile install.ps1`n    .\install.ps1 -Version 1.1.0"
  }

  $Version = $resolved
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "unexpected version '$Version'" }

# LocalDrop ships x64 only; arm64 Windows runs it under emulation.
$arch = if ([System.Environment]::Is64BitOperatingSystem) { 'x64' } else { 'x86' }
if ($arch -eq 'x86') { Fail 'LocalDrop requires 64-bit Windows 10 or later.' }

$asset = "LocalDrop-$Version-windows-$arch.zip"
$releaseUrl = "$BaseUrl/releases/download/v$Version"
Write-Info "version $Version  ·  windows-$arch  ·  $asset"

# --- download + verify -----------------------------------------------------
Write-Step 'Downloading and verifying'
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("localdrop-install-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
try {
  $archive = Join-Path $tmp $asset
  $sums    = Join-Path $tmp 'SHA256SUMS'

  try {
    Invoke-WebRequest "$releaseUrl/$asset" -OutFile $archive -UseBasicParsing -TimeoutSec 600
    Invoke-WebRequest "$releaseUrl/SHA256SUMS" -OutFile $sums    -UseBasicParsing -TimeoutSec 120
  } catch {
    Fail "download failed: $($_.Exception.Message)`n  Check the release exists: $BaseUrl/releases/tag/v$Version"
  }

  # Verify before unpacking anything. A truncated or tampered archive must
  # never reach Program Files.
  $line = Select-String -Path $sums -Pattern ([regex]::Escape($asset) + '$') | Select-Object -First 1
  if (-not $line) { Fail "$asset is not listed in SHA256SUMS - refusing to install" }
  $expected = ($line.Line -split '\s+')[0].ToLowerInvariant()
  $actual   = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) {
    Fail "checksum mismatch for $asset`n  expected $expected`n  got      $actual"
  }
  Write-Ok 'sha256 verified'

  # --- install -------------------------------------------------------------
  Write-Step "Installing to $InstallDir"
  if (Test-Path $InstallDir) {
    $running = Get-Process -Name 'localdrop' -ErrorAction SilentlyContinue
    if ($running) {
      Write-Info 'stopping the running server'
      $running | Stop-Process -Force
      Start-Sleep -Milliseconds 800
    }
    if ($Force) {
      Remove-Item $InstallDir -Recurse -Force
    } else {
      # Keep the _internal payload in place; overwrite file by file.
      Write-Info 'existing install found; overwriting (use -Force to replace it)'
    }
  }
  New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

  Expand-Archive -Path $archive -DestinationPath $tmp -Force
  $extracted = Join-Path $tmp 'localdrop'
  if (-not (Test-Path (Join-Path $extracted $ExeName))) {
    Fail "archive did not contain $ExeName"
  }
  Copy-Item -Path (Join-Path $extracted '*') -Destination $InstallDir -Recurse -Force

  $exe = Join-Path $InstallDir $ExeName
  if (-not (Test-Path $exe)) { Fail "install failed: $exe is missing" }
  Write-Ok "$ExeName installed"

  # --- data directory ------------------------------------------------------
  New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $DataDir 'backups') -Force | Out-Null
  Write-Ok "data directory: $DataDir"

  # --- shortcuts -----------------------------------------------------------
  if (-not $NoShortcuts) {
    Write-Step 'Creating shortcuts'
    $programs = [Environment]::GetFolderPath('Programs')
    $desktop  = [Environment]::GetFolderPath('Desktop')
    $ws = New-Object -ComObject WScript.Shell
    foreach ($dir in @($programs, $desktop)) {
      if (-not $dir -or -not (Test-Path $dir)) { continue }
      $lnk = Join-Path $dir 'LocalDrop.lnk'
      $sc  = $ws.CreateShortcut($lnk)
      $sc.TargetPath       = $exe
      $sc.Arguments        = '--no-browser'
      $sc.WorkingDirectory = $DataDir
      $sc.Description      = 'LocalDrop - self-hosted file sharing'
      $sc.Save()
      Write-Ok "  $(Split-Path $lnk -Leaf) in $dir"
    }
  }

  # --- prove it works ------------------------------------------------------
  Write-Step 'Verifying the install'
  $env:LOCALDROP_DATA_DIR = $DataDir
  $check = & $exe '--check' 2>&1
  $check | ForEach-Object { Write-Info $_ }
  if ($LASTEXITCODE -ne 0) { Fail 'the install did not pass its self-check' }
  Write-Ok 'self-check passed'

  # --- optionally start ----------------------------------------------------
  if ($StartServer) {
    Write-Step 'Starting LocalDrop'
    $port = 8080
    $proc = Start-Process -FilePath $exe -ArgumentList '--no-browser' -PassThru -WindowStyle Hidden
    Write-Ok "started (pid $($proc.Id)) on port $port"
  }

  $url = "http://127.0.0.1:8080"
  Write-Host @"

  ---------------------------------------------------------------
   LocalDrop $Version installed.
  ---------------------------------------------------------------

   Web UI   $url
   Binary   $exe
   Data     $DataDir

  Finish setup:

    1. Open $url
    2. Get the one-time setup token:
         $exe --setup-token
    3. Paste it in, create your owner account, start dropping files.

  Start later:   Start Menu -> LocalDrop
  Uninstall:     Settings -> Apps -> LocalDrop

"@ -ForegroundColor Green
}
finally {
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
