<#
Builds the Windows installer: the PyInstaller backend, the LGPL FFmpeg, the frontend, then the
per-user NSIS installer with the Tauri updater files. Everything lands under installer/build and
app/src-tauri/target. Nothing is installed on this machine.

  powershell -File installer/build.ps1 [-Key <path to the updater private key>] [-UpdateBaseUrl <https folder that will hold the installer>] [-Notes <text>] [-Unsigned]

The updater key is taken from TAURI_SIGNING_PRIVATE_KEY (its text or a path) when that is set, else
from -Key. The script never prints it. The files to upload land in installer/build/release: the
installer, its .sig, SHA256SUMS.txt, and with -UpdateBaseUrl (or VST_UPDATE_BASE_URL) latest.json,
which the app's update check reads. Upload them all to that folder. -Unsigned needs no key and makes
only the installer and SHA256SUMS.txt; such a build cannot be offered as an update.
#>
param(
    [string]$Key = (Join-Path $HOME '.tauri/video-subtitle-translator-v2.key'),
    [string]$UpdateBaseUrl = $env:VST_UPDATE_BASE_URL,
    [string]$Notes = '',
    [switch]$Unsigned
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $PSScriptRoot 'build'
$cache = Join-Path $build 'cache'
$env:PATH = "$HOME/.cargo/bin;$env:PATH"
# Windows PowerShell 5.1 downloads many times slower while it draws a progress bar.
$ProgressPreference = 'SilentlyContinue'

# FFmpeg from BtbN's builds, the LGPL variant (no x264, no x265, no nonfree), pinned by hash in
# installer/ffmpeg.json. BtbN deletes daily autobuild tags after a few weeks and keeps the month-end
# ones, so the pin is a month-end tag, with a copy in this repository's releases as the second source
# (installer/mirror_ffmpeg.ps1 puts it there).
$ffmpeg = Get-Content "$PSScriptRoot/ffmpeg.json" -Raw | ConvertFrom-Json

function Invoke-Checked([string]$what, [scriptblock]$run) {
    & $run
    if ($LASTEXITCODE -ne 0) { throw "$what failed with exit code $LASTEXITCODE" }
}

function Test-PinnedFFmpeg([string]$path) {
    (Test-Path $path) -and (Get-FileHash $path -Algorithm SHA256).Hash -eq $ffmpeg.sha256.ToUpper()
}

function Get-PinnedFFmpeg([string]$zip) {
    if (Test-PinnedFFmpeg $zip) { return }
    $sources = @(
        "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/$($ffmpeg.tag)/$($ffmpeg.file)",
        "https://github.com/$($ffmpeg.mirror_repo)/releases/download/$($ffmpeg.mirror_release)/$($ffmpeg.file)"
    )
    $part = "$zip.part"
    $failures = foreach ($url in $sources) {
        try { Invoke-WebRequest $url -OutFile $part -UseBasicParsing } catch { "$url : $($_.Exception.Message)"; continue }
        if (Test-PinnedFFmpeg $part) { Move-Item $part $zip -Force; return }
        "$url : its SHA-256 differs from installer/ffmpeg.json"
    }
    Remove-Item $part -Force -ErrorAction SilentlyContinue
    throw (@("The pinned FFmpeg $($ffmpeg.file) could not be fetched from any source:") + $failures +
        'Pin a newer month-end build in installer/ffmpeg.json as installer/README.md describes.') -join "`n"
}

Remove-Item $build/backend, $build/ffmpeg -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $cache, $build/backend, $build/ffmpeg | Out-Null

# 1. The backend, one folder with vst-backend.exe in it. Onedir starts faster than onefile
#    because nothing is unpacked to %TEMP% on each start (measured: see prs/P14.md).
Push-Location $root
try {
    Invoke-Checked 'uv sync' { uv sync --group build --locked }
    Invoke-Checked 'pyinstaller' {
        uv run --group build pyinstaller installer/sidecar.spec --noconfirm `
            --distpath "$build/pyi" --workpath "$build/pyi-work"
    }
} finally { Pop-Location }
Copy-Item "$build/pyi/vst-backend/*" "$build/backend" -Recurse

# 2. FFmpeg: download, check the hash, check it is really the LGPL build, keep what the app runs.
$zip = Join-Path $cache $ffmpeg.file
Get-PinnedFFmpeg $zip
$unpacked = Join-Path $cache 'ffmpeg'
Remove-Item $unpacked -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip $unpacked
$ffRoot = Get-ChildItem $unpacked -Directory | Select-Object -First 1
$config = [regex]::Match([Text.Encoding]::GetEncoding(28591).GetString([IO.File]::ReadAllBytes("$($ffRoot.FullName)/bin/avutil-60.dll")), '--prefix=[ -~]*').Value
if (-not $config -or $config -match '--enable-(gpl|nonfree)\b') { throw "This FFmpeg is not an LGPL build: $config" }
Set-Content "$build/ffmpeg-configuration.txt" $config
Push-Location $root
try {
    Invoke-Checked 'FFmpeg license check' {
        uv run --no-sync python installer/fetch_ffmpeg_licenses.py --check "$build/ffmpeg-configuration.txt"
    }
} finally { Pop-Location }
foreach ($file in 'ffmpeg.exe', 'ffprobe.exe', 'avcodec-62.dll', 'avdevice-62.dll', 'avfilter-11.dll', 'avformat-62.dll', 'avutil-60.dll', 'swresample-6.dll', 'swscale-9.dll') {
    Copy-Item "$($ffRoot.FullName)/bin/$file" "$build/ffmpeg/"
}
Copy-Item "$($ffRoot.FullName)/LICENSE.txt" "$build/ffmpeg/LICENSE-FFmpeg-LGPL-3.0.txt"
Copy-Item "$PSScriptRoot/licenses/FFmpeg-external-libraries.txt" "$build/ffmpeg/"

# 3. The installer. The updater key stays outside the repository. -Unsigned builds without it and
#    without the updater files, for a build check that holds no secret.
$version = (Get-Content "$root/app/src-tauri/tauri.conf.json" -Raw | ConvertFrom-Json).version
$configs = @('--config', '../installer/tauri.bundle.conf.json')
if ($Unsigned) {
    Set-Content "$build/unsigned.conf.json" '{ "bundle": { "createUpdaterArtifacts": false } }'
    $configs += @('--config', "$build/unsigned.conf.json")
} else {
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
        if (-not (Test-Path $Key)) { throw "Updater private key not found at $Key and TAURI_SIGNING_PRIVATE_KEY is not set (see installer/README.md)" }
        $env:TAURI_SIGNING_PRIVATE_KEY = $Key
    }
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) { $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = '' }
}
Invoke-Checked 'npm ci' { npm --prefix "$root/app" ci }
Push-Location "$root/app"
try { Invoke-Checked 'tauri build' { npx tauri build --bundles nsis @configs } } finally { Pop-Location }

$nsis = Join-Path $root 'app/src-tauri/target/release/bundle/nsis'
$installer = Get-ChildItem $nsis -Filter "*_$($version)_x64-setup.exe" | Select-Object -First 1
if (-not $installer) { throw "No installer for version $version in $nsis" }
$mb = [math]::Round($installer.Length / 1MB, 1)
Set-Content "$build/size.txt" "$($installer.Name) $($installer.Length) bytes ($mb MB), limit 150 MB"
if ($installer.Length -ge 150MB) { throw "Installer is $mb MB; the limit is 150 MB" }

$env:VST_INSTALLER = $installer.FullName
Push-Location $root
try { Invoke-Checked 'package contents test' { uv run pytest tests/test_package_contents.py -q } } finally { Pop-Location }

# 4. The files to upload, in installer/build/release. GitHub turns spaces in a release file's name
#    into dots, so the installer is renamed first and latest.json names it as GitHub will serve it.
$release = Join-Path $build 'release'
Remove-Item $release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $release | Out-Null
$asset = $installer.Name -replace ' ', '-'
Copy-Item $installer.FullName (Join-Path $release $asset)
if (-not $Unsigned) {
    $signature = Join-Path $nsis "$($installer.Name).sig"
    if (-not (Test-Path $signature)) { throw "No $($installer.Name).sig beside the installer; the updater key was not used" }
    Copy-Item $signature (Join-Path $release "$asset.sig")
    if ($UpdateBaseUrl) {
        if ($UpdateBaseUrl -notmatch '^https://') { throw "-UpdateBaseUrl must be an https address" }
        $latest = [ordered]@{
            version  = $version
            notes    = $Notes
            pub_date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
            platforms = [ordered]@{
                'windows-x86_64' = [ordered]@{
                    signature = (Get-Content $signature -Raw).Trim()
                    url       = "$($UpdateBaseUrl.TrimEnd('/'))/$asset"
                }
            }
        }
        # Windows PowerShell's -Encoding utf8 adds a byte-order mark, which serde_json (the updater's
        # parser) does not accept.
        [IO.File]::WriteAllText((Join-Path $release 'latest.json'), ($latest | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
        Write-Host "latest.json written for $version"
    } else {
        Write-Warning "No -UpdateBaseUrl: latest.json was not written, so this build cannot be offered as an update yet."
    }
}
$sums = Get-ChildItem $release -File | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
}
[IO.File]::WriteAllText((Join-Path $release 'SHA256SUMS.txt'), (($sums -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
Write-Host "OK $release ($mb MB installer)"
