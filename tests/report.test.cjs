const {test}=require('node:test');
const assert=require('node:assert/strict');
require('../extension/report.js');
const report=globalThis.namaDLReport;

test('report masks the local user name in Windows paths',()=>{
 const text=report.build({extensionVersion:'1.14.0',hostVersion:'1.14.0',userAgent:'UA',url:'https://www.youtube.com/watch?v=abc',title:'T',destination:'C:\\Users\\someone\\Videos\\VideoButton',statusText:'保存しました: C:\\Users\\someone\\Videos\\VideoButton\\movie.mp4',queue:{jobs:[],paused:false}});
 assert.ok(!text.includes('someone'));
 assert.ok(text.includes('C:\\Users\\***\\Videos\\VideoButton'));
 assert.ok(text.includes('拡張機能 1.14.0 / PC側 1.14.0'));
 assert.ok(text.includes('https://www.youtube.com/watch?v=abc'));
});

test('report summarizes queue states and pause',()=>{
 const text=report.build({queue:{paused:true,jobs:[{state:'active'},{state:'waiting'},{state:'waiting'},{state:'error'}]}});
 assert.ok(text.includes('全4件'));
 assert.ok(text.includes('実行中 1件'));
 assert.ok(text.includes('待機 2件'));
 assert.ok(text.includes('失敗 1件'));
 assert.ok(text.includes('一時停止中'));
});

test('report handles empty info and truncates long status text',()=>{
 const text=report.build({statusText:'x'.repeat(5000)});
 assert.ok(text.includes('対象URL: （なし）'));
 assert.ok(text.includes('キュー: なし'));
 assert.ok(text.length<2600);
});
