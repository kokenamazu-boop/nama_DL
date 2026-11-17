$ErrorActionPreference = 'Stop'
try {
 $dest = Join-Path $env:LOCALAPPDATA 'VideoButton'
 if (-not (Test-Path "$dest\python\python.exe")) { throw 'Run Setup.cmd first.' }
 Copy-Item "$PSScriptRoot\host\host.py" "$dest\host.py" -Force
 Copy-Item "$PSScriptRoot\host\pick_folder.ps1" "$dest\pick_folder.ps1" -Force
 $fixedExtensionId = 'ngakcifeaboajdppldnpgngofjblpnfk'
 $nativeManifest = @{name='com.videobutton.ytdlp';description='nama_DL local downloader';path="$dest\host.cmd";type='stdio';allowed_origins=@("chrome-extension://$fixedExtensionId/")}
 [IO.File]::WriteAllText("$dest\manifest.json",($nativeManifest|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
 foreach ($browserKey in @('BraveSoftware\Brave-Browser','Google\Chrome')) {
  $key = "HKCU:\Software\$browserKey\NativeMessagingHosts\com.videobutton.ytdlp"
  New-Item -Path $key -Force | Out-Null
  Set-Item -Path $key -Value "$dest\manifest.json"
 }
 & "$dest\bin\yt-dlp.exe" -U
 if ($LASTEXITCODE -ne 0) { Write-Warning 'yt-dlp update failed. Run Update.cmd again before retrying.' }
 Write-Host 'Host updated to v1.14.0. Reload the extension in brave://extensions.' -ForegroundColor Green
} catch { Write-Host $_ -ForegroundColor Red; exit 1 }
