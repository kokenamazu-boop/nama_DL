@echo off
powershell.exe -NoProfile -Command "Remove-Item 'HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.videobutton.ytdlp','HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.videobutton.ytdlp' -Recurse -ErrorAction SilentlyContinue; Remove-Item (Join-Path $env:LOCALAPPDATA 'VideoButton') -Recurse -Force -ErrorAction SilentlyContinue"
echo Saved videos and the extension folder are not removed.
pause
