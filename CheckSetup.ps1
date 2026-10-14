$ErrorActionPreference = 'Continue'
$root = Join-Path $env:LOCALAPPDATA 'VideoButton'
$bad = 0
Write-Host 'nama_DL 接続・必要ソフトの確認' -ForegroundColor Cyan
Write-Host ''
$items = @(
 @{ label='Python'; path=(Join-Path $root 'python\python.exe'); arguments=@('--version') },
 @{ label='yt-dlp'; path=(Join-Path $root 'bin\yt-dlp.exe'); arguments=@('--version') },
 @{ label='FFmpeg'; path=(Join-Path $root 'bin\ffmpeg.exe'); arguments=@('-version') },
 @{ label='FFprobe'; path=(Join-Path $root 'bin\ffprobe.exe'); arguments=@('-version') },
 @{ label='Deno'; path=(Join-Path $root 'bin\deno.exe'); arguments=@('--version') }
)
foreach ($item in $items) {
 if (Test-Path -LiteralPath $item.path) {
  $exe = $item.path
  $versionArguments = $item.arguments
  $lines = & $exe @versionArguments 2>&1
  if ($LASTEXITCODE -eq 0) { Write-Host ('OK  ' + $item.label + ': ' + ($lines | Select-Object -First 1)) -ForegroundColor Green }
  else { Write-Host ('NG  ' + $item.label + ': 実行できませんでした。') -ForegroundColor Red; $bad++ }
 } else { Write-Host ('NG  ' + $item.label + ': 未導入です。') -ForegroundColor Red; $bad++ }
}
$manifestFile = Join-Path $root 'manifest.json'
if (Test-Path -LiteralPath $manifestFile) {
 try {
  $native = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
  Write-Host ('登録された拡張機能ID: ' + (($native.allowed_origins -replace '^chrome-extension://','') -replace '/$',''))
  Write-Host 'このIDがブラウザーのnama_DLと一致しているか確認してください。'
 } catch { Write-Host 'NG  接続設定を読み取れません。Setup.cmdを実行してください。' -ForegroundColor Red; $bad++ }
} else { Write-Host 'NG  接続設定がありません。Setup.cmdを実行してください。' -ForegroundColor Red; $bad++ }
$hostFile = Join-Path $root 'host.py'
if (Test-Path -LiteralPath $hostFile) {
 $match = [regex]::Match((Get-Content -LiteralPath $hostFile -Raw -Encoding UTF8), "version='([0-9.]+)'")
 if ($match.Success) { Write-Host ('PC側のバージョン: ' + $match.Groups[1].Value) }
}
foreach ($browser in @('BraveSoftware\Brave-Browser','Google\Chrome')) {
 $key = 'HKCU:\Software\' + $browser + '\NativeMessagingHosts\com.videobutton.ytdlp'
 if (Test-Path $key) { Write-Host ('OK  接続登録: ' + $browser) -ForegroundColor Green }
 else { Write-Host ('接続登録なし: ' + $browser) -ForegroundColor Yellow }
}
Write-Host ''
if ($bad -eq 0) { Write-Host '必要ソフトは確認できました。動画取得の成否は、対象サイトとログイン状態にも依存します。' -ForegroundColor Green }
else { Write-Host '未導入の場合はSetup.cmd、更新済みで接続しない場合は拡張機能IDを再確認してください。' -ForegroundColor Yellow }
exit $bad
