# nama_DL

<img src="extension/icons/nama_DL.png" alt="nama_DL" width="128">

YouTube・ニコニコ動画の一覧やプレイヤーから、動画・音声・サムネイルを保存するWindows向けブラウザー拡張機能です。

**現在のバージョン：1.10.0** · Windows 10/11 x64 · Brave / Google Chrome

## ダウンロード

[配布用ZIPをダウンロード](https://github.com/kokenamazu-boop/nama_DL/raw/refs/heads/main/downloads/nama_DL-Windows-v1.10.0.zip)

上のリンクから **`nama_DL-Windows-v1.10.0.zip`** を保存し、「すべて展開」したフォルダーの **`START_HERE.html`** を開いてください。

## 主な機能

- 動画一覧のカードから、動画ページを開かずに保存。
- 動画プレイヤーの操作バーからダウンロードメニューを表示。
- ニコニコのマイリスト、YouTubeの再生リスト全体を一括保存。
- 動画は取得できる最高解像度・フレームレートを優先し、H.264/AACのMP4に保存。
- 対応するH.264/AACは再圧縮せず高速保存。その他は高品質設定で変換。
- 音声のみは24bit PCMのWAV、サムネイルのみはPNG。
- サムネイル・メタデータの埋め込み、保存先のフォルダー選択。
- ファイル名は動画タイトル。同名の場合は連番で保存。
- MP4の確認に成功した後、作業用ファイル・元MKVを整理。

動画カードのボタンはその1本、リストのボタンはリスト全体を保存します。ページ内ボタンの配色はYouTubeのダーク／ライトに追従します。

## 初回導入

1. 配布用ZIPを右クリックして「すべて展開」。移動しない場所に置きます。
2. Braveは `brave://extensions`、Chromeは `chrome://extensions` を開きます。
3. デベロッパーモードをONにし、「パッケージ化されていない拡張機能を読み込む」から `extension` フォルダーを選びます。
4. ツールバーのnama_DLを開き、「初回セットアップ・接続確認」→「IDをコピー」。
5. `Setup.cmd` を実行し、IDを貼り付けてEnter。
6. セットアップ完了後、拡張機能とPC側が両方 `1.10.0` であることを確認し、対象サイトを再読み込みします。

Python専用版・yt-dlp・FFmpeg・FFprobe・Denoはセットアップ時に自動取得します。初回はインターネット接続と数百MBの空き容量が必要です。管理者権限や別途Pythonの導入は不要です。

ニコニコのログインが必要な動画やプレミアム画質には、使用するブラウザーでログインし、「このサイトのログイン情報を使う」を有効にしてください。

## 更新

処理が終わってから拡張機能をOFFにし、以前のフォルダーへ新しい内容を上書きします。`ApplyUpdate.cmd` を実行して、拡張機能をON・再読み込みし、サイトもF5で再読み込みします。以前のフォルダーの場所は変えないでください。

## 困ったとき

- 接続・必要ソフトの確認：`CheckSetup.cmd`
- PC側のコード更新：`ApplyUpdate.cmd`
- yt-dlpの更新：`Update.cmd`
- 保存済み動画のMP4変換：`ConvertToMP4.cmd`
- 詳しい使い方：[はじめに.txt](はじめに.txt)
- 更新履歴：[更新内容.txt](更新内容.txt)

不具合の報告には、バージョン、対象の動画／リストのURL、表示されたエラー、使用ブラウザーを添えてください。ログに個人の保存先がある場合は、ユーザー名を伏せてください。

## 保存形式・データの扱い

変換が必要な動画は再圧縮が入ります。解像度は縮小せず、HDRはSDR、可変フレームレートは固定へ変換します。実際に取得できる画質は、サイト・元動画・ログイン状態に依存します。

ログイン情報の使用をONにしたサイトのCookieをPC側のyt-dlpへ渡します。Cookieを設定・ログへ保存せず、一時Cookieファイルは通常の完了・中止で削除します。独自の外部中継サーバーは使用しません。

## 構成と依存ソフト

- `extension/`：Manifest V3拡張機能
- `host/`：PythonのNative Messaging連携、Windowsフォルダー選択
- `.cmd` / `.ps1`：セットアップ・更新・確認等の補助ツール

依存ソフトは配布ZIPに同梱せず、セットアップで各配布元から取得します。

- [Python](https://www.python.org/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/) / [Windowsビルド](https://www.gyan.dev/ffmpeg/builds/)
- [Deno](https://github.com/denoland/deno)

ページ内の新しい配置は模擬ページで検証しています。サイトの表示変更により、ボタンの位置や検出が変わる場合があります。
