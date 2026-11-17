// Support-report text builder for the popup. Pure functions, shared
// with the tests. Never includes cookies or account data; the local
// user name inside file paths is masked before anything is copied.
globalThis.namaDLReport = {
mask(text) {
return String(text?? '')
.replace(/([A-Za-z]:\\Users\\)[^\\/:*?"<>|\r\n]+/gi, '$1***')
.replace(/(\/Users\/)[^/\r\n]+/g, '$1***')
.replace(/(\/home\/)[^/\r\n]+/g, '$1***');
},
summarizeQueue(queue) {
const jobs = Array.isArray(queue?.jobs)? queue.jobs: [];
if (!jobs.length) return 'なし';
const counts = {};
for (const job of jobs) counts[job.state] = (counts[job.state] || 0) + 1;
const labels = {waiting: '待機', active: '実行中', done: '完了', error: '失敗', cancelled: '中止', interrupted: '接続中断'};
const parts = Object.entries(counts).map(([state, n]) => `${labels[state] || state} ${n}件`);
return `全${jobs.length}件（${parts.join('、')}）${queue.paused? '、一時停止中': ''}`;
},
build(info) {
const lines = [
'',
`バージョン: 拡張機能 ${info.extensionVersion || '不明'} / PC側 ${info.hostVersion || '未確認'}`,
`ブラウザー: ${info.userAgent || '不明'}`,
`対象URL: ${info.url || '（なし）'}`,
`ページタイトル: ${info.title || '（なし）'}`,
`保存先: ${info.destination || '標準（ビデオ / VideoButton）'}`,
`キュー: ${this.summarizeQueue(info.queue)}`,
'状態・エラーの内容:',
String(info.statusText || '（なし）').slice(0, 2000),
'',
'※Cookie・アカウント情報は含まれません。保存先パスのユーザー名は *** に置き換えています。',
];
return this.mask(lines.join('\n'));
},
};
