let port=null,busy=false,activeDestination='',connection=null;
function connectionError(reason){return /not found|specified native messaging host/i.test(reason||'')?'初回セットアップが必要です。「初回セットアップ・接続確認」からIDをコピーしてSetup.cmdを実行してください。':'PC側へ接続できません。CheckSetup.cmdを実行し、必要ならApplyUpdate.cmdで更新してください。'+(reason?'\n'+reason:'');}
function status(text){return chrome.storage.local.set({status:{text,busy}});}
function connect(){
 if(connection)return connection;
 connection=new Promise((resolve,reject)=>{
  port=chrome.runtime.connectNative('com.videobutton.ytdlp');
  let settled=false;
  const fail=()=>{const text='PC側の更新を確認できません。ApplyUpdate.cmdを実行し、拡張機能を再読み込みしてください。';chrome.storage.local.set({hostVersion:'更新が必要'});reject(Error(text));};
  const timer=setTimeout(()=>{if(!settled){settled=true;fail();}},4000);
  port.onMessage.addListener(m=>{
   if(m.type==='hello'){
    chrome.storage.local.set({hostVersion:m.version});
    if(!settled){settled=true;clearTimeout(timer);if(m.version==='1.10.0')resolve(port);else fail();}
    return;
   }
   if(m.type==='folderSelected'){
    chrome.storage.local.set({destination:m.path,folderMessage:'保存先を設定しました。次のダウンロードから適用します。'});return;
   }
   if(m.type==='folderNotice'){chrome.storage.local.set({folderMessage:m.text});return;}
   if(['done','error','cancelled'].includes(m.type))busy=false;
   status(m.text||'');
  });
  port.onDisconnect.addListener(()=>{
   const reason=chrome.runtime.lastError?.message;
   clearTimeout(timer);if(!settled){settled=true;reject(Error(connectionError(reason)));}
   port=null;connection=null;busy=false;
   chrome.storage.local.set({hostVersion:'未接続'});
   status(connectionError(reason));
  });
  port.postMessage({action:'hello'});
 });
 return connection;
}
chrome.runtime.onMessage.addListener((m,s,reply)=>{
 if(s.id!==chrome.runtime.id)return;
 if(s.tab){
  let page;try{page=new URL(s.tab.url||s.url);}catch{reply({error:'動画ページを確認できません'});return;}
  if(!['www.nicovideo.jp','www.youtube.com'].includes(page.hostname)){reply({error:'このページから操作できません'});return;}
  if(['download','inspect'].includes(m.action)){
   let target;try{target=new URL(m.url);}catch{reply({error:'URLが不正です'});return;}
   const sameOrigin=target.origin===page.origin;
   const playlist=sameOrigin&&(target.hostname==='www.nicovideo.jp'?(/^\/(?:user\/\d+\/|my\/)?mylist\/\d+\/?$/.test(target.pathname)||(/^\/(?:my\/)?mylist\/?$/.test(target.pathname)&&/^#\/\d+(?:[/?]|$)/.test(target.hash))):target.pathname==='/playlist'&&/^[\w-]+$/.test(target.searchParams.get('list')||''));
   const cardVideo=sameOrigin&&m.source==='card'&&!target.username&&!target.password&&(target.hostname==='www.nicovideo.jp'?/^\/watch\/(?:sm|nm|so)?\d+\/?$/.test(target.pathname):target.pathname==='/watch'&&/^[\w-]{11}$/.test(target.searchParams.get('v')||''));
   if(m.url!==page.href&&!playlist&&!cardVideo){reply({error:'動画が切り替わりました。メニューを開き直してください'});return;}
   if(cardVideo)m={...m,url:target.origin+(target.hostname==='www.nicovideo.jp'?target.pathname.replace(/\/$/,''):'/watch?v='+encodeURIComponent(target.searchParams.get('v'))),playlist:false};

  }
 }

 (async()=>{
  try{
   if(['download','inspect'].includes(m.action)){
    if(busy)throw Error('現在の処理が終わるまでお待ちください');
    if(!/^https?:\/\//.test(m.url))throw Error('動画ページを開いてください');
    busy=true;
    try{
     const settings=await chrome.storage.local.get(['destination','authSites']);activeDestination=settings.destination||'';
     if(s.tab){
      const page=new URL(m.url),nico=page.hostname==='www.nicovideo.jp';
      const authKey=nico?'nicovideo.jp':page.origin;
      const useAuth=settings.authSites?.[authKey]??nico;
      let cookies=[];
      if(useAuth){
       const stores=await chrome.cookies.getAllCookieStores();const store=stores.find(x=>x.tabIds.includes(s.tab.id));
       cookies=await chrome.cookies.getAll({domain:nico?'nicovideo.jp':'youtube.com',...(store?{storeId:store.id}:{})});
       if(nico&&!cookies.some(c=>c.name==='user_session'&&c.value)&&m.options?.media!=='thumbnail')throw Error('ニコニコへログインし直してください。ログインCookieが見つかりません。');
      }
      m={action:m.action,url:m.url,cookies,options:m.options,playlist:!!m.playlist};
     }
     const p=await connect();await status('動画を解析中…');p.postMessage({...m,destination:activeDestination});
    }catch(e){busy=false;throw e;}
   }else if(['folder','chooseFolder'].includes(m.action)){
    const settings=await chrome.storage.local.get('destination');
    const p=await connect();p.postMessage({action:m.action,destination:m.action==='folder'&&busy?activeDestination:(settings.destination||'')});
   }else if(m.action==='cancel'){(await connect()).postMessage(m);}
   else if(m.action==='hello'){await connect();}
   reply({ok:true});
  }catch(e){status(e.message);reply({error:e.message});}
 })();return true;
});
chrome.runtime.onStartup.addListener(()=>{busy=false;status('待機中');});
status('待機中');
