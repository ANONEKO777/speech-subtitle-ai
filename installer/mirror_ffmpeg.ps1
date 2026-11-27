<#
Copies the pinned FFmpeg zip (installer/ffmpeg.json) into a release of this repository, the second
source build.ps1 downloads from once BtbN removes the tag. Run build.ps1 first: it leaves the zip,
hash-checked, in installer/build/cache. Without -Upload the script only says what it would do.

  powershell -File installer/mirror_ffmpeg.ps1 [-Upload]

The release is a pre-release and never "latest", so the updater address
(releases/latest/download/latest.json) keeps pointing at the app's own release. It needs `gh` signed
in with write access to the repository.
#>
param([switch]$Upload)
$ErrorActionPreference = 'Stop'
$ffmpeg = Get-Content "$PSScriptRoot/ffmpeg.json" -Raw | ConvertFrom-Json
$zip = Join-Path $PSScriptRoot "build/cache/$($ffmpeg.file)"
if (-not (Test-Path $zip)) { throw "$zip is missing; run installer/build.ps1 first" }
if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $ffmpeg.sha256.ToUpper()) { throw "$zip differs from the SHA-256 in installer/ffmpeg.json" }

$repo = $ffmpeg.mirror_repo
$release = $ffmpeg.mirror_release
$assets = gh release view $release --repo $repo --json assets --jq '.assets[].name' 2>$null
$exists = $LASTEXITCODE -eq 0
if ($exists -and @($assets) -contains $ffmpeg.file) {
    Write-Host "$repo release $release already holds $($ffmpeg.file)"
    return
}
$notes = "Copy of $($ffmpeg.file) from BtbN/FFmpeg-Builds release $($ffmpeg.tag), SHA-256 $($ffmpeg.sha256). " +
    "FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/$($ffmpeg.source_commit). " +
    "Licenses and the source offer: installer/THIRD_PARTY.md. Used by installer/build.ps1; not an app release."
if ($exists) {
    $command = @('release', 'upload', $release, $zip, '--repo', $repo)
} else {
    $command = @('release', 'create', $release, $zip, '--repo', $repo, '--prerelease', '--latest=false',
        '--title', "FFmpeg $($ffmpeg.tag) (build input)", '--notes', $notes)
}
if (-not $Upload) {
    Write-Host "Would run: gh $($command -join ' ')"
    Write-Host 'Pass -Upload to run it.'
    return
}
& gh @command
if ($LASTEXITCODE -ne 0) { throw "gh $($command[0]) $($command[1]) failed with exit code $LASTEXITCODE" }
