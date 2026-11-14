# Daily reminder: shows today's minimum task as a Windows notification, only if today is not counted yet.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$status = python -I coach.py today
if ($status -match "already counted") { exit 0 }
$msg = python -I coach.py today --short
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.ShowBalloonTip(15000, "20 minutes. That's the whole deal.", $msg, [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 16
$n.Dispose()
