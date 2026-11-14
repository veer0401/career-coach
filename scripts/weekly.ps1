# Runs the weekly review headless. Needs the `claude` CLI on PATH and a logged-in session.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path "data\weekly" | Out-Null
$out = "data\weekly\run-$(Get-Date -Format yyyy-MM-dd).log"
claude -p "/coach-week" --allowedTools "Bash(python -I coach.py:*)" "WebSearch" "WebFetch" "Read" "Write" "Edit" 2>&1 | Tee-Object -FilePath $out
