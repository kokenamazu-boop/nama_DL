$ErrorActionPreference = 'Stop'
try {
 Add-Type -AssemblyName System.Windows.Forms
 $dest = Join-Path $env:LOCALAPPDATA 'VideoButton'
 if (-not (Test-Path "$dest\python\python.exe")) { throw 'Run Setup.cmd first.' }
 $dialog = New-Object System.Windows.Forms.OpenFileDialog
 $dialog.Title = 'MP4に変換する動画を選択（複数選択できます）'
 $dialog.Filter = 'Video|*.mkv;*.mp4;*.webm;*.mov;*.avi;*.ts|All files|*.*'
 $dialog.Multiselect = $true
 $dialog.InitialDirectory = Join-Path $env:USERPROFILE 'Videos\VideoButton'
 if ($dialog.ShowDialog() -eq 'OK') { & "$dest\python\python.exe" -u "$dest\host.py" --convert @($dialog.FileNames) }
} catch { Write-Host $_ -ForegroundColor Red; exit 1 }
