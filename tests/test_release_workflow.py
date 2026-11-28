"""Guards in the release pipeline that only review protected before: release.yml's draft and secret
gating, and build.ps1's refusal of an FFmpeg zip whose hash is not the pinned one."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
BUILD = ROOT / "installer" / "build.ps1"
PUSH_ONLY = "github.event_name == 'push'"
RELEASE_ON_PUSH = "${{ github.event_name == 'push' && 'release' || '' }}"


def _lines() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    stripped = (re.sub(r"(^|\s)#.*$", "", line).rstrip() for line in text.splitlines())
    return [line for line in stripped if line.strip()]


def _blocks(lines: list[str], indent: int) -> dict[str, list[str]]:
    """The keys at exactly `indent` spaces, each with its own line and the lines under it."""
    out: dict[str, list[str]] = {}
    key = None
    for line in lines:
        match = re.match(rf"^ {{{indent}}}([\w-]+):", line)
        if match:
            key = match.group(1)
            out[key] = []
        if key is not None:
            out[key].append(line)
    return out


def _jobs() -> dict[str, list[str]]:
    return _blocks(_blocks(_lines(), 0)["jobs"][1:], 2)


def _steps(job: list[str]) -> list[list[str]]:
    steps: list[list[str]] = []
    for line in job:
        if line.startswith("      - "):
            steps.append([])
        if steps:
            steps[-1].append(line)
    return steps


JOB_KEY = "    "
STEP_KEY = "(?:      - |        )"


def _value(lines: list[str], indent: str, key: str) -> str | None:
    """The value of `key` set on this job (indent JOB_KEY) or this step (indent STEP_KEY)."""
    for line in lines:
        match = re.match(rf"^{indent}{key}: (.*)$", line)
        if match:
            return match.group(1).strip()
    return None


def test_the_release_is_a_draft_of_a_tag_that_exists() -> None:
    commands = " ".join(_lines()).replace("\\ ", " ").split("gh release create")[1:]
    assert commands, "release.yml creates no release"
    for command in commands:
        assert re.search(r"\s--draft(\s|$)", command), "the release must stay a draft"
        assert re.search(r"\s--verify-tag(\s|$)", command), "the release must name an existing tag"


def test_the_workflow_runs_only_on_v_tags_and_pull_requests() -> None:
    triggers = _blocks(_blocks(_lines(), 0)["on"][1:], 2)
    assert set(triggers) == {"push", "pull_request"}
    assert triggers["push"][1:] == ['    tags: ["v*"]']


def test_only_jobs_in_the_release_environment_see_the_secrets() -> None:
    top = _blocks(_lines(), 0)
    outside = [line for key, lines in top.items() if key != "jobs" for line in lines]
    assert not [line for line in outside if "secrets." in line]
    assert not [line for line in _lines() if re.search(r"secrets:\s*inherit", line)]
    seeing = {name: job for name, job in _jobs().items() if any("secrets." in s for s in job)}
    assert seeing, "no job reads the signing secrets"
    for name, job in seeing.items():
        assert _value(job, JOB_KEY, "environment") in {"release", RELEASE_ON_PUSH}, name


def test_no_pull_request_run_reaches_the_secrets() -> None:
    for name, job in _jobs().items():
        job_if = _value(job, JOB_KEY, "if") or ""
        for step in _steps(job):
            if any("secrets." in line for line in step):
                step_if = _value(step, STEP_KEY, "if") or ""
                assert PUSH_ONLY in f"{job_if} {step_if}", f"{name}: {step[0].strip()}"


POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

# Loads build.ps1's FFmpeg functions by its own parser, with a download that serves $Served.
HARNESS = r"""
param([string]$BuildPs1, [string]$Dir, [string]$Served, [string]$Pin)
$ErrorActionPreference = 'Stop'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($BuildPs1, [ref]$null, [ref]$null)
$found = $ast.FindAll({
    param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $n.Name -like '*-PinnedFFmpeg'
}, $true)
foreach ($f in $found) { . ([scriptblock]::Create($f.Extent.Text)) }
$ffmpeg = Get-Content (Join-Path (Split-Path $BuildPs1) 'ffmpeg.json') -Raw | ConvertFrom-Json
if ($Pin) { $ffmpeg.sha256 = $Pin }
function Invoke-WebRequest($Uri, $OutFile, [switch]$UseBasicParsing) {
    [IO.File]::WriteAllText($OutFile, $Served)
}
$zip = Join-Path $Dir $ffmpeg.file
try { Get-PinnedFFmpeg $zip; "ACCEPTED $(Test-Path $zip)" }
catch { "REFUSED $($_.Exception.Message)" }
"LEFT $((Get-ChildItem $Dir -Exclude harness.ps1).Name -join ',')"
"""


def _fetch(tmp_path: Path, served: str, pin: str = "") -> str:
    assert POWERSHELL
    script = tmp_path / "harness.ps1"
    script.write_text(HARNESS, encoding="utf-8")
    args = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]
    args += [str(script), "-BuildPs1", str(BUILD), "-Dir", str(tmp_path), "-Served", served]
    if pin:
        args += ["-Pin", pin]
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.skipif(POWERSHELL is None, reason="build.ps1 needs PowerShell")
def test_build_refuses_an_ffmpeg_zip_whose_hash_is_not_pinned(tmp_path: Path) -> None:
    out = _fetch(tmp_path, "not the pinned zip")
    assert "REFUSED The pinned FFmpeg" in out
    assert out.count("its SHA-256 differs from installer/ffmpeg.json") == 2
    assert "LEFT \n" in out or out.rstrip().endswith("LEFT")


@pytest.mark.skipif(POWERSHELL is None, reason="build.ps1 needs PowerShell")
def test_build_keeps_an_ffmpeg_zip_with_the_pinned_hash(tmp_path: Path) -> None:
    served = "the pinned zip"
    out = _fetch(tmp_path, served, hashlib.sha256(served.encode()).hexdigest())
    assert "ACCEPTED True" in out
