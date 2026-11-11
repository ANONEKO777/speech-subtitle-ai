<#
Builds the Windows installer: the PyInstaller backend, the LGPL FFmpeg, the frontend, then the
per-user NSIS installer with the Tauri updater files. Everything lands under installer/build and
app/src-tauri/target. Nothing is installed on this machine.

  powershell -File installer/build.ps1 [-Key <path to the updater private key>] [-UpdateBaseUrl <https folder that will hold the installer>] [-Notes <text>]

The updater key is taken from TAURI_SIGNING_PRIVATE_KEY (its text or a path) when that is set, else
from -Key. The script never prints it. With -UpdateBaseUrl (or VST_UPDATE_BASE_URL) it also writes
installer/build/latest.json, which the app's update check reads: upload it and the installer to that folder.
#>
param(
    [string]$Key = (Join-Path $HOME '.tauri/video-subtitle-translator.key'),
    [string]$UpdateBaseUrl = $env:VST_UPDATE_BASE_URL,
    [string]$Notes = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $PSScriptRoot 'build'
$cache = Join-Path $build 'cache'
$env:PATH = "$HOME/.cargo/bin;$env:PATH"

# FFmpeg from BtbN's builds, the LGPL variant (no x264, no x265, no nonfree). Pinned by hash: the
# SHA-256 is the one GitHub shows for the release asset. BtbN deletes most daily autobuild tags after
# a few weeks (it keeps the month-end ones), so the zip stays in installer/build/cache. If it is gone,
# move to a month-end tag, then rerun installer/fetch_ffmpeg_licenses.py and update THIRD_PARTY.md.
$ffmpegTag = 'autobuild-2026-11-06-12-50'
$ffmpegZip = 'ffmpeg-n8.1.3-34-ga35157abb9-win64-lgpl-shared-8.1.zip'
$ffmpegSha = '08897c3d53909d8fde6bd5eb9324e7ca41324890d2b03e22c2f9f31025789ee2'

function Invoke-Checked([string]$what, [scriptblock]$run) {
    & $run
    if ($LASTEXITCODE -ne 0) { throw "$what failed with exit code $LASTEXITCODE" }
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
$zip = Join-Path $cache $ffmpegZip
if (-not (Test-Path $zip)) {
    Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/$ffmpegTag/$ffmpegZip" -OutFile $zip
}
if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $ffmpegSha.ToUpper()) { throw "FFmpeg zip hash differs from the pinned one" }
$unpacked = Join-Path $cache 'ffmpeg'
Remove-Item $unpacked -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip $unpacked
$ffRoot = Get-ChildItem $unpacked -Directory | Select-Object -First 1
$config = [regex]::Match([Text.Encoding]::GetEncoding(28591).GetString([IO.File]::ReadAllBytes("$($ffRoot.FullName)/bin/avutil-60.dll")), '--prefix=[ -~]*').Value
if (-not $config -or $config -match '--enable-(gpl|nonfree)\b') { throw "This FFmpeg is not an LGPL build: $config" }
Set-Content "$build/ffmpeg-configuration.txt" $config
foreach ($file in 'ffmpeg.exe', 'ffprobe.exe', 'avcodec-62.dll', 'avdevice-62.dll', 'avfilter-11.dll', 'avformat-62.dll', 'avutil-60.dll', 'swresample-6.dll', 'swscale-9.dll') {
    Copy-Item "$($ffRoot.FullName)/bin/$file" "$build/ffmpeg/"
}
Copy-Item "$($ffRoot.FullName)/LICENSE.txt" "$build/ffmpeg/LICENSE-FFmpeg-LGPL-3.0.txt"
Copy-Item "$PSScriptRoot/licenses/FFmpeg-external-libraries.txt" "$build/ffmpeg/"

# 3. The installer. The updater key stays outside the repository.
if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
    if (-not (Test-Path $Key)) { throw "Updater private key not found at $Key and TAURI_SIGNING_PRIVATE_KEY is not set (see installer/README.md)" }
    $env:TAURI_SIGNING_PRIVATE_KEY = $Key
}
if (-not $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) { $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = '' }
Invoke-Checked 'npm ci' { npm --prefix "$root/app" ci }
Push-Location "$root/app"
try { Invoke-Checked 'tauri build' { npx tauri build --bundles nsis --config ../installer/tauri.bundle.conf.json } } finally { Pop-Location }

$nsis = Join-Path $root 'app/src-tauri/target/release/bundle/nsis'
$installer = Get-ChildItem $nsis -Filter '*-setup.exe' | Select-Object -First 1
$mb = [math]::Round($installer.Length / 1MB, 1)
Set-Content "$build/size.txt" "$($installer.Name) $($installer.Length) bytes ($mb MB), limit 150 MB"
if ($installer.Length -ge 150MB) { throw "Installer is $mb MB; the limit is 150 MB" }

# latest.json for the updater: the version, the installer's address and the .sig text.
$signature = Join-Path $nsis "$($installer.Name).sig"
if (-not (Test-Path $signature)) { throw "No $($installer.Name).sig beside the installer; the updater key was not used" }
if ($UpdateBaseUrl) {
    if ($UpdateBaseUrl -notmatch '^https://') { throw "-UpdateBaseUrl must be an https address" }
    $version = (Get-Content "$root/app/src-tauri/tauri.conf.json" -Raw | ConvertFrom-Json).version
    $latest = [ordered]@{
        version  = $version
        notes    = $Notes
        pub_date = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        platforms = [ordered]@{
            'windows-x86_64' = [ordered]@{
                signature = (Get-Content $signature -Raw).Trim()
                url       = "$($UpdateBaseUrl.TrimEnd('/'))/$([uri]::EscapeDataString($installer.Name))"
            }
        }
    }
    $latest | ConvertTo-Json -Depth 5 | Set-Content "$build/latest.json" -Encoding utf8
    Write-Host "latest.json written for $version at $build/latest.json"
} else {
    Write-Warning "No -UpdateBaseUrl: latest.json was not written, so this build cannot be offered as an update yet."
}

$env:VST_INSTALLER = $installer.FullName
Push-Location $root
try { Invoke-Checked 'package contents test' { uv run pytest tests/test_package_contents.py -q } } finally { Pop-Location }
Write-Host "OK $($installer.FullName) ($mb MB)"
