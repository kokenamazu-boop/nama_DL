$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
 if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
 $extensionId = (Read-Host 'nama_DLの拡張機能ID（32文字）を貼り付けてEnter').Trim()
 if ($extensionId -cnotmatch '^[a-p]{32}$') { throw 'IDが正しくありません。nama_DLの初回セットアップ欄からIDをコピーしてください。' }
 $dest = Join-Path $env:LOCALAPPDATA 'VideoButton'
 $bin = Join-Path $dest 'bin'
 New-Item -ItemType Directory -Force $dest,$bin | Out-Null
 $temp = Join-Path ([IO.Path]::GetTempPath()) ('VideoButton-setup-'+[Guid]::NewGuid())
 New-Item -ItemType Directory $temp | Out-Null
 function Fetch($url,$path) { Write-Host "Downloading: $url"; Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $path }
 Fetch 'https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip' "$temp\python.zip"
 Expand-Archive "$temp\python.zip" "$dest\python" -Force
 Fetch 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' "$bin\yt-dlp.exe"
 Fetch 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' "$temp\ffmpeg.zip"
 Expand-Archive "$temp\ffmpeg.zip" "$temp\ffmpeg" -Force
 Get-ChildItem "$temp\ffmpeg" -Recurse -Filter '*.exe' | Where-Object { $_.Name -in @('ffmpeg.exe','ffprobe.exe') } | Copy-Item -Destination $bin -Force
 Fetch 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' "$temp\deno.zip"
 Expand-Archive "$temp\deno.zip" $bin -Force
 foreach ($exe in @('yt-dlp.exe','ffmpeg.exe','ffprobe.exe','deno.exe')) { if (-not (Test-Path "$bin\$exe")) { throw "Missing: $exe" } }
 Copy-Item "$PSScriptRoot\host\host.py" "$dest\host.py" -Force
 Copy-Item "$PSScriptRoot\host\pick_folder.ps1" "$dest\pick_folder.ps1" -Force
 $launcher = '@echo off'+"`r`n"+'"%~dp0python\python.exe" -u "%~dp0host.py"'+"`r`n"
 [IO.File]::WriteAllText("$dest\host.cmd",$launcher,[Text.Encoding]::ASCII)
 $manifest = @{name='com.videobutton.ytdlp';description='nama_DL local downloader';path="$dest\host.cmd";type='stdio';allowed_origins=@("chrome-extension://$extensionId/")}
 [IO.File]::WriteAllText("$dest\manifest.json",($manifest|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
 foreach ($browserKey in @('BraveSoftware\Brave-Browser','Google\Chrome')) {
  $key = "HKCU:\Software\$browserKey\NativeMessagingHosts\com.videobutton.ytdlp"
  New-Item -Path $key -Force | Out-Null
  Set-Item -Path $key -Value "$dest\manifest.json"
 }
 Remove-Item $temp -Recurse -Force
 Write-Host 'Setup complete. Open a video in Brave, then click nama_DL.' -ForegroundColor Green
 Write-Host 'Files are saved to your user profile: Videos\VideoButton'
} catch { Write-Host $_ -ForegroundColor Red; exit 1 }
