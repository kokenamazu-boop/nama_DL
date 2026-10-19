// Optional real-Chromium UI check: npm install playwright; npx playwright install chromium.
// Use NAMA_TEST_BROWSER to select an existing Chromium executable.
const assert=require('node:assert/strict'),path=require('node:path');
let playwright;try{playwright=require('playwright');}catch{playwright=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');}
const extension=path.join(__dirname,'../extension');
async function stub(page){
 await page.addInitScript(()=>{
  const listeners=[],runtimeListeners=[];window.testSent=[];
  const make=(id,state,media='video')=>({id,url:`https://www.youtube.com/watch?v=abcdefghij${id}`,title:id==='1'?'テスト動画 <img src=x onerror=alert(1)>':'待機中の動画 '+id,state,text:'動画を取得中… 50%',options:{media,clipEnabled:true,clipStart:'00:20',clipEnd:'00:40',normalizeEnabled:true,targetLUFS:'-15'},destination:'D:\\音MAD\\素材',auth:{enabled:false},playlist:false});
  window.testData={status:{text:'動画を取得中… 50%',busy:true},destination:'D:\\音MAD\\素材',hostVersion:'1.13.0',downloadQueue:{jobs:[make('1','active'),make('2','waiting','audio'),make('3','error')],paused:false}};
  window.chrome={
   storage:{local:{async get(){return structuredClone(window.testData);},async set(value){Object.assign(window.testData,structuredClone(value));for(const fn of listeners)await fn();}},onChanged:{addListener(fn){listeners.push(fn);}}},
   runtime:{id:'test-extension',onMessage:{addListener(fn){runtimeListeners.push(fn);}},async sendMessage(m){
    window.testSent.push(structuredClone(m));const q=window.testData.downloadQueue;
    if(m.action==='download')q.jobs.push({...make('4','waiting',m.options.media),title:m.title,options:m.options});
    if(m.action==='queuePause')q.paused=true;
    if(m.action==='queueResume')q.paused=false;
    if(m.action==='queueRemove')q.jobs=q.jobs.filter(j=>j.id!==m.id);
    if(m.action==='queueRetry')q.jobs.find(j=>j.id===m.id).state='waiting';
    if(m.action==='queueClear')q.jobs=q.jobs.filter(j=>['active','waiting'].includes(j.state));
    await chrome.storage.local.set({downloadQueue:q});return {ok:true,id:'4'};
   }},
   tabs:{async query(){return [{id:7,url:'https://www.youtube.com/watch?v=abcdefghijk',title:'テスト動画のタイトル'}];}},
   permissions:{async request(){return true;}},cookies:{async getAllCookieStores(){return [{id:'0',tabIds:[7]}];}}
  };
  window.openTestMenu=()=>new Promise(resolve=>runtimeListeners.forEach(fn=>fn({action:'openNamaMenu'},{},resolve)));
  const attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(options){return attach.call(this,{...options,mode:'open'});};
 });
}
async function exercise(page,content=false){
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await stub(page);
 if(content){
  await page.route('https://www.youtube.com/**',route=>route.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><title>テスト動画 - YouTube</title><body></body>'}));
  await page.goto('https://www.youtube.com/watch?v=abcdefghijk');
  for(const file of ['sites.js','edit-options.js','queue-ui.js','page.js'])await page.addScriptTag({path:path.join(extension,file)});
  await page.evaluate(()=>window.openTestMenu());
 }else await page.goto('file://'+path.join(extension,'popup.html'));
 const start=page.locator('#start');await start.waitFor();assert.equal(await start.isEnabled(),true);assert.equal(await page.locator('#inspect').isEnabled(),false);
 await start.click();await page.locator('[data-message]').filter({hasText:'キューに追加しました。'}).waitFor();
 assert.equal(await page.locator('#queue li').count(),4);assert.equal(await page.locator('#queue img').count(),0);
 const payload=await page.evaluate(()=>testSent.find(m=>m.action==='download'));assert.equal(payload.options.media,'video');assert.ok(!('cookies' in payload));assert.ok(payload.title);
 const toggle=page.locator('[data-toggle]');await toggle.click();assert.equal(await toggle.textContent(),'再開');
 assert.match(await page.locator('[data-hint]').textContent(),/現在の処理が終わったら停止/);
 await toggle.click();assert.equal(await toggle.textContent(),'一時停止');
 const failed=page.locator('#queue li').filter({hasText:'失敗 · MP4'});await failed.getByRole('button',{name:'再試行'}).click();
 assert.equal(await page.locator('#queue li').filter({hasText:'失敗 · MP4'}).count(),0);
 const waiting=page.locator('#queue li').filter({hasText:'待機中 · WAV'});await waiting.getByRole('button',{name:'削除'}).click();assert.equal(await page.locator('#queue li').count(),3);
 await toggle.focus();await page.evaluate(()=>{testData.downloadQueue.jobs[0].text='60%';return chrome.storage.local.set({downloadQueue:testData.downloadQueue});});assert.equal(await toggle.evaluate(el=>el===el.getRootNode().activeElement),true);
 if(!content){const rect=await start.boundingBox();assert.ok(rect.y+rect.height<=600,'Popup footer fits Chrome height');}
 await page.screenshot({path:'/tmp/nama-queue-'+(content?'page':'popup')+'.png'});
 assert.deepEqual(errors,[]);console.log((content?'Page menu':'Popup')+': add while busy, queue actions, text escaping, focus and layout passed');
}
(async()=>{
 const browser=await playwright.chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.NAMA_TEST_BROWSER?{executablePath:process.env.NAMA_TEST_BROWSER}:{})});
 try{for(const content of [false,true]){const p=await browser.newPage({viewport:content?{width:1280,height:900}:{width:400,height:600}});await exercise(p,content);await p.close();}}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
