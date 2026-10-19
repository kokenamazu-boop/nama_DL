importScripts('sites.js');
const VERSION='1.13.0',KEY='downloadQueue',finished=new Set(['done','error','cancelled','interrupted']);
let port=null,connection=null,queue={jobs:[],paused:false},active=null,inspect=null,activeDestination='',serial=Promise.resolve(),progressTimer=null,pendingProgress=null;
function connectionError(reason){return /not found|specified native messaging host/i.test(reason||'')?'初回セットアップが必要です。「初回セットアップ・接続確認」からIDをコピーしてSetup.cmdを実行してください。':'PC側へ接続できません。CheckSetup.cmdを実行し、必要ならApplyUpdate.cmdで更新してください。'+(reason?'\n'+reason:'');}
function transaction(fn){const result=serial.then(()=>ready).then(fn);serial=result.catch(()=>{});return result;}
function status(text){return chrome.storage.local.set({status:{text,busy:!!(active||inspect),jobId:active?.id||inspect?.id||null}});}
function trimHistory(){const history=queue.jobs.filter(j=>finished.has(j.state));const keep=new Set(history.slice(-20).map(j=>j.id));queue.jobs=queue.jobs.filter(j=>!finished.has(j.state)||keep.has(j.id));}
async function save(){trimHistory();await chrome.storage.local.set({[KEY]:queue});}
const ready=(async()=>{
 const data=await chrome.storage.local.get(KEY),stored=data[KEY];
 if(stored&&Array.isArray(stored.jobs))queue={jobs:stored.jobs,paused:!!stored.paused};
 let interrupted=false;
 for(const j of queue.jobs)if(j.state==='active'){j.state='interrupted';j.text='ブラウザーや拡張機能との接続が終了しました。保存済みファイルを確認してから、必要なら再試行してください。';j.endedAt=Date.now();interrupted=true;}
 if(interrupted)queue.paused=true;
 await save();await status(interrupted?'処理が中断されました。キューを確認してください。':'待機中');
})();
function clearProgress(){clearTimeout(progressTimer);progressTimer=null;pendingProgress=null;}
function progress(m){
 if(!m.jobId||m.jobId!==(active?.id||inspect?.id))return;
 pendingProgress=m;
 if(!progressTimer)progressTimer=setTimeout(()=>{progressTimer=null;const value=pendingProgress;pendingProgress=null;if(value)transaction(async()=>{
  if(value.jobId!==(active?.id||inspect?.id))return;
  // Progress only writes the small status record, not the entire queue.
  if(active)active.text=String(value.text||'').slice(-6000);
  await status(String(value.text||'').slice(-6000));
 }).catch(()=>{});},500);
}
async function terminal(m){
 if(!m.jobId||(m.jobId!==active?.id&&m.jobId!==inspect?.id))return;
 clearProgress();
 if(active){active.state=m.type;active.text=String(m.text||'').slice(-12000);active.endedAt=Date.now();active=null;await save();}
 else inspect=null;
 await status(m.text||'');await pump();
}
function connect(){
 if(connection)return connection;
 const p=chrome.runtime.connectNative('com.videobutton.ytdlp');port=p;
 connection=new Promise((resolve,reject)=>{
  let settled=false;
  const fail=()=>{chrome.storage.local.set({hostVersion:'更新が必要'});reject(Error('PC側の更新を確認できません。ApplyUpdate.cmdを実行し、拡張機能を再読み込みしてください。'));};
  const timer=setTimeout(()=>{if(!settled){settled=true;fail();}},4000);
  p.onMessage.addListener(m=>{
   if(port!==p)return;
   if(m.type==='hello'){
    chrome.storage.local.set({hostVersion:m.version});
    if(!settled){settled=true;clearTimeout(timer);if(m.version===VERSION)resolve(p);else fail();}return;
   }
   if(m.type==='folderSelected'){chrome.storage.local.set({destination:m.path,folderMessage:'保存先を設定しました。次の追加から適用します。'});return;}
   if(m.type==='folderNotice'){chrome.storage.local.set({folderMessage:m.text});return;}
   if(['done','error','cancelled'].includes(m.type)){transaction(()=>terminal(m)).catch(()=>{});return;}
   if(m.type==='progress'){progress(m);return;}
   if(m.text)transaction(()=>status(m.text)).catch(()=>{});
  });
  p.onDisconnect.addListener(()=>{
   const reason=chrome.runtime.lastError?.message;
   clearTimeout(timer);if(!settled){settled=true;reject(Error(connectionError(reason)));}
   if(port!==p)return;port=null;connection=null;
   transaction(async()=>{
    clearProgress();
    if(active){active.state='interrupted';active.text='PC側との接続が終了しました。保存済みファイルを確認してから再試行してください。';active.endedAt=Date.now();active=null;queue.paused=true;}
    inspect=null;await save();await chrome.storage.local.set({hostVersion:'未接続'});await status(connectionError(reason));
   }).catch(()=>{});
  });
  p.postMessage({action:'hello'});
 });
 return connection;
}
function newId(){return crypto.randomUUID();}
function optionsSnapshot(value){
 const o=value&&typeof value==='object'?value:{};
 return {media:['audio','thumbnail'].includes(o.media)?o.media:'video',embedThumbnail:!!o.embedThumbnail,embedMetadata:!!o.embedMetadata,clipEnabled:o.clipEnabled===true,clipStart:String(o.clipStart??'').slice(0,24),clipEnd:String(o.clipEnd??'').slice(0,24),normalizeEnabled:o.normalizeEnabled===true,targetLUFS:String(o.targetLUFS??'-15').slice(0,16)};
}
async function snapshot(m,s){
 const u=new URL(m.url);if(!['https:','http:'].includes(u.protocol)||u.username||u.password||m.url.length>16000)throw Error('動画ページのURLを確認してください');
 const settings=await chrome.storage.local.get(['destination','authSites']);
 const nico=u.hostname==='www.nicovideo.jp',x=namaDLSites.isXHost(u.hostname);
 let enabled=s.tab?(settings.authSites?.[nico?'nicovideo.jp':namaDLSites.authKey(u.href)]??nico):m.auth?.enabled===true;
 let storeId=s.tab?undefined:m.auth?.storeId;
 if(enabled&&s.tab){const stores=await chrome.cookies.getAllCookieStores();storeId=stores.find(x=>x.tabIds.includes(s.tab.id))?.id;if(!storeId)throw Error('ログイン情報のプロファイルを確認できません。ページを開き直してください。');}
 return {id:newId(),url:m.url,title:String(m.title||s.tab?.title||m.url).slice(0,300),playlist:!!m.playlist,options:optionsSnapshot(m.options),destination:settings.destination||'',auth:{enabled:!!enabled,...(typeof storeId==='string'?{storeId}:{}),...(nico?{domain:'nicovideo.jp'}:x?{domain:'x.com'}:{url:u.href})},state:'waiting',text:'順番待ち',createdAt:Date.now()};
}
async function cookiesFor(job){
 if(!job.auth.enabled)return [];
 if(job.auth.storeId){const stores=await chrome.cookies.getAllCookieStores();if(!stores.some(s=>s.id===job.auth.storeId))throw Error('追加時のブラウザープロファイルが見つかりません。同じプロファイルで追加し直してください。');}
 const {enabled,...query}=job.auth,cookies=await chrome.cookies.getAll(query);
 if(job.auth.domain==='nicovideo.jp'&&!cookies.some(c=>c.name==='user_session'&&c.value)&&job.options.media!=='thumbnail')throw Error('ニコニコへログインし直してください。ログインCookieが見つかりません。');
 return cookies;
}
async function start(job,action='download'){
 let p;try{p=await connect();}catch(e){e.pauseQueue=true;throw e;}
 const cookies=await cookiesFor(job);activeDestination=job.destination;
 p.postMessage({action,jobId:job.id,url:job.url,options:job.options,playlist:job.playlist,destination:job.destination,cookies});
}
async function pump(){
 if(active||inspect||queue.paused)return;
 while(!active&&!queue.paused){
  const job=queue.jobs.find(j=>j.state==='waiting');if(!job)return;
  active=job;job.state='active';job.text='動画を解析中…';job.startedAt=Date.now();await save();await status(job.text);
  try{await start(job);return;}
  catch(e){job.state='error';job.text=e.message;job.endedAt=Date.now();active=null;await save();await status(e.message);
   // A missing/outdated native host affects every item: leave the remaining jobs waiting.
   if(e.pauseQueue){queue.paused=true;await save();return;}}
 }
}
async function enqueue(m,s){
 if(queue.jobs.filter(j=>['waiting','active'].includes(j.state)).length>=100)throw Error('キューは実行中を含め100件までです。完了後に追加してください。');
 const job=await snapshot(m,s);
 const same=j=>j.url===job.url&&j.playlist===job.playlist&&j.destination===job.destination&&JSON.stringify(j.options)===JSON.stringify(job.options)&&JSON.stringify(j.auth)===JSON.stringify(job.auth);
 const duplicate=queue.jobs.find(j=>['waiting','active'].includes(j.state)&&same(j));
 if(duplicate)return {ok:true,duplicate:true,id:duplicate.id};
 queue.jobs.push(job);await save();await pump();return {ok:true,id:job.id};
}
async function queueAction(m){
 if(m.action==='queuePause')queue.paused=true;
 else if(m.action==='queueResume')queue.paused=false;
 else if(m.action==='queueClear')queue.jobs=queue.jobs.filter(j=>!finished.has(j.state));
 else {
  const job=queue.jobs.find(j=>j.id===m.id);if(!job)throw Error('キューの項目が見つかりません');
  if(m.action==='queueRemove'){if(job.state!=='waiting'&&!finished.has(job.state))throw Error('実行中の項目は「処理を中止」で停止してください');queue.jobs=queue.jobs.filter(j=>j!==job);}
  if(m.action==='queueRetry'){
   if(!['error','cancelled','interrupted'].includes(job.state))throw Error('この項目は再試行できません');
   if(queue.jobs.filter(j=>['waiting','active'].includes(j.state)).length>=100)throw Error('キューがいっぱいです');
   if(queue.jobs.some(j=>j!==job&&['waiting','active'].includes(j.state)&&j.url===job.url&&j.playlist===job.playlist&&j.destination===job.destination&&JSON.stringify(j.options)===JSON.stringify(job.options)&&JSON.stringify(j.auth)===JSON.stringify(job.auth)))throw Error('同じ設定の項目がすでにキューにあります');
   job.state='waiting';job.text='再試行の順番待ち';delete job.endedAt;queue.jobs=queue.jobs.filter(j=>j!==job);queue.jobs.push(job);
  }
 }
 await save();await pump();return {ok:true};
}
chrome.runtime.onMessage.addListener((m,s,reply)=>{
 if(s.id!==chrome.runtime.id)return;
 if(s.tab){
  let page;try{page=new URL(s.tab.url||s.url);}catch{reply({error:'動画ページを確認できません'});return;}
  if(page.protocol!=='https:'||(!['www.nicovideo.jp','www.youtube.com'].includes(page.hostname)&&!namaDLSites.isXHost(page.hostname))){reply({error:'このページから操作できません'});return;}
  if(['download','inspect'].includes(m.action)){
   let target;try{target=new URL(m.url);}catch{reply({error:'URLが不正です'});return;}
   const sameOrigin=target.origin===page.origin;
   const playlist=sameOrigin&&(target.hostname==='www.nicovideo.jp'?(/^\/(?:user\/\d+\/|my\/)?mylist\/\d+\/?$/.test(target.pathname)||(/^\/(?:my\/)?mylist\/?$/.test(target.pathname)&&/^#\/\d+(?:[/?]|$)/.test(target.hash))):target.pathname==='/playlist'&&/^[\w-]+$/.test(target.searchParams.get('list')||''));
   const cardVideo=sameOrigin&&m.source==='card'&&!target.username&&!target.password&&(target.hostname==='www.nicovideo.jp'?/^\/watch\/(?:sm|nm|so)?\d+\/?$/.test(target.pathname):target.pathname==='/watch'&&/^[\w-]{11}$/.test(target.searchParams.get('v')||''));
   const post=namaDLSites.isXHost(page.hostname)&&namaDLSites.xPostURL(target.href);
   if(namaDLSites.isXHost(page.hostname)&&!post){reply({error:'動画付き投稿のダウンロードボタンを押してください'});return;}
   if(m.url!==page.href&&!playlist&&!cardVideo&&!(post&&(m.source==='post'||post===namaDLSites.xPostURL(page.href)))){reply({error:'動画が切り替わりました。メニューを開き直してください'});return;}
   if(post)m={...m,url:post,playlist:false};
   if(cardVideo)m={...m,url:target.origin+(target.hostname==='www.nicovideo.jp'?target.pathname.replace(/\/$/,''):'/watch?v='+encodeURIComponent(target.searchParams.get('v'))),playlist:false};

  }
 }

 transaction(async()=>{
  try{
   if(m.action==='download'){reply(await enqueue(m,s));return;}
   if(m.action==='inspect'){
    if(active||inspect)throw Error('現在の処理が終わるまでお待ちください');
    const job=await snapshot({...m,playlist:false},s);inspect=job;
    try{await status('画質を確認中…');await start(job,'inspect');}catch(e){inspect=null;await status(e.message);throw e;}
   }else if(['queuePause','queueResume','queueRemove','queueRetry','queueClear'].includes(m.action)){reply(await queueAction(m));return;}
   else if(['folder','chooseFolder'].includes(m.action)){
    const settings=await chrome.storage.local.get('destination');
    (await connect()).postMessage({action:m.action,destination:m.action==='folder'&&(active||inspect)?activeDestination:(settings.destination||'')});
   }else if(m.action==='cancel'){
    if(active||inspect)(await connect()).postMessage({action:'cancel',jobId:(active||inspect).id});
   }else if(m.action==='hello'){await connect();await pump();}
   else throw Error('未対応の操作です');
   reply({ok:true});
  }catch(e){reply({error:e.message});}
 }).catch(e=>reply({error:e.message}));return true;
});
transaction(pump).catch(()=>{});
