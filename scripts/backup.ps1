# Nightly backup: commit everything in this folder and push it to the PRIVATE repo (origin).
# Scheduled by Windows Task Scheduler ("CareerCoach Backup"). Log: scripts\backup.log (not committed).
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$log = Join-Path $PSScriptRoot "backup.log"
"--- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -Append -Encoding utf8 $log
git add -A *>> $log
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -q -m "Daily backup $(Get-Date -Format yyyy-MM-dd)" *>> $log
}
git push -q origin HEAD *>> $log
if ($LASTEXITCODE -eq 0) { "pushed" | Out-File -Append -Encoding utf8 $log } else { "PUSH FAILED" | Out-File -Append -Encoding utf8 $log }
