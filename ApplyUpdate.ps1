$ErrorActionPreference = 'Stop'
try {
 $dest = Join-Path $env:LOCALAPPDATA 'VideoButton'
 if (-not (Test-Path "$dest\python\python.exe")) { throw 'Run Setup.cmd first.' }
 Copy-Item "$PSScriptRoot\host\host.py" "$dest\host.py" -Force
 Copy-Item "$PSScriptRoot\host\pick_folder.ps1" "$dest\pick_folder.ps1" -Force
 & "$dest\bin\yt-dlp.exe" -U
 if ($LASTEXITCODE -ne 0) { Write-Warning 'yt-dlp update failed. Run Update.cmd again before retrying.' }
 Write-Host 'Host updated to v1.12.0. Reload the extension in brave://extensions.' -ForegroundColor Green
} catch { Write-Host $_ -ForegroundColor Red; exit 1 }
