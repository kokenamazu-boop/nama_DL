let tab;
const $=id=>document.getElementById(id);
function isNico(url){try{const h=new URL(url).hostname;return h==='nicovideo.jp'||h.endsWith('.nicovideo.jp');}catch{return false;}}
function listPage(url){try{const u=new URL(url);return isNico(url)?(/^\/(?:user\/\d+\/|my\/)?mylist\/\d+\/?$/.test(u.pathname)||(/^\/(?:my\/)?mylist\/?$/.test(u.pathname)&&/^#\/\d+(?:[/?]|$)/.test(u.hash))):u.hostname.endsWith('youtube.com')&&u.pathname==='/playlist'&&u.searchParams.has('list');}catch{return false;}}
function isX(url){try{return namaDLSites.isXHost(new URL(url).hostname);}catch{return false;}}
function authKey(url){return isNico(url)?'nicovideo.jp':namaDLSites.authKey(url);}
function readOptions(){return {media:document.querySelector('input[name=media]:checked').value,embedThumbnail:$('embedThumbnail').checked,embedMetadata:$('embedMetadata').checked};}
function modeUI(){const o=readOptions();$('embedThumbnail').disabled=o.media!=='video';$('embedMetadata').disabled=o.media==='thumbnail';for(const card of document.querySelectorAll('.choice'))card.classList.toggle('selected',card.querySelector('input').checked);$('modeNote').textContent=o.media==='audio'?'WAV（24bit PCM）。サムネイル埋め込みは動画のみ対応。':o.media==='thumbnail'?'動画・音声を取得せず、PNG画像だけを保存します。':'';}
async function refresh(){const s=await chrome.storage.local.get(['status','destination','folderMessage','hostVersion']);$('status').textContent=s.status?.text||'待機中';const busy=!!s.status?.busy;$('start').disabled=busy||!/^https?:/.test(tab?.url||'');$('inspect').disabled=busy||!/^https?:/.test(tab?.url||'');$('cancel').hidden=!busy;$('destination').textContent=s.destination||'ビデオ / VideoButton';$('destination').title=$('destination').textContent;$('settingMessage').textContent=s.folderMessage||'';$('version').textContent='拡張機能 1.11.0 / PC側 '+(s.hostVersion||'未確認');}
async function submit(action){try{
 const x=isX(tab.url),url=x?namaDLSites.xPostURL(tab.url):tab.url;
 if(x&&!url)throw Error('動画付き投稿のダウンロードボタンを押すか、投稿の個別ページを開いてください。');
 let cookies=[];
 if($('auth').checked){
  const nico=isNico(tab.url),origin=nico?'https://*.nicovideo.jp/*':x?'https://*.x.com/*':new URL(tab.url).origin+'/*';
  if(!await chrome.permissions.request({origins:[origin]}))throw Error('ログイン情報へのアクセスが許可されませんでした');
  const stores=await chrome.cookies.getAllCookieStores(),store=stores.find(s=>s.tabIds.includes(tab.id));
  cookies=await chrome.cookies.getAll({...(nico?{domain:'nicovideo.jp'}:x?{domain:'x.com'}:{url:tab.url}),...(store?{storeId:store.id}:{})});
  if(nico&&!cookies.some(c=>c.name==='user_session'&&c.value)&&readOptions().media!=='thumbnail')throw Error('ニコニコへログインし直してください。ログインCookieが見つかりません。');
 }
 const r=await chrome.runtime.sendMessage({action,url,cookies,playlist:x||action==='inspect'?false:(listPage(tab.url)||$('playlist').checked),options:readOptions()});if(r?.error)throw Error(r.error);
}catch(e){$('status').textContent=e.message;}}
$('id').textContent=chrome.runtime.id;
$('close').onclick=()=>window.close();$('start').onclick=()=>submit('download');$('inspect').onclick=()=>submit('inspect');$('cancel').onclick=()=>chrome.runtime.sendMessage({action:'cancel'});$('folder').onclick=()=>chrome.runtime.sendMessage({action:'folder'});
$('chooseFolder').onclick=async()=>{const r=await chrome.runtime.sendMessage({action:'chooseFolder'});if(r?.error)$('status').textContent=r.error;};
$('resetFolder').onclick=()=>chrome.storage.local.set({destination:'',folderMessage:'標準の保存先に戻しました。'});
$('copyId').onclick=async()=>{try{await navigator.clipboard.writeText(chrome.runtime.id);$('copyMessage').textContent='コピーしました。';}catch{$('copyMessage').textContent='上のIDを選択してコピーしてください。';}};
$('auth').onchange=async()=>{const s=await chrome.storage.local.get('authSites');await chrome.storage.local.set({authSites:{...(s.authSites||{}),[authKey(tab.url)]:$('auth').checked}});};
for(const input of document.querySelectorAll('input[name=media],#embedThumbnail,#embedMetadata'))input.onchange=()=>{modeUI();chrome.storage.local.set({options:readOptions()});};
$('pageMenu').onclick=async()=>{try{const r=await chrome.tabs.sendMessage(tab.id,{action:'openNamaMenu'});if(r?.ok)window.close();else if(r?.error)$('status').textContent=r.error;}catch{$('status').textContent='動画・リストのページを再読み込みしてください。';}};
chrome.storage.onChanged.addListener(refresh);
(async()=>{
 [tab]=await chrome.tabs.query({active:true,currentWindow:true});const s=await chrome.storage.local.get(['options','authSites']);
 $('title').textContent=tab?.title||'動画のページを開いてください';$('title').title=$('title').textContent;$('url').textContent=tab?.url||'';
 const media=['audio','thumbnail'].includes(s.options?.media)?s.options.media:'video';document.querySelector('input[value="'+media+'"]').checked=true;
 for(const id of ['embedThumbnail','embedMetadata'])$(id).checked=!!s.options?.[id];
 if(tab?.url?.match(/^https?:/))$('auth').checked=s.authSites?.[authKey(tab.url)]??isNico(tab.url);
 const list=listPage(tab?.url);$('playlist').checked=list;$('playlist').disabled=list;$('scopeNote').hidden=!list;$('scopeNote').textContent=list?'このリスト全体を保存します。':'';
 if(isX(tab?.url)){$('playlist').disabled=true;$('playlist').closest('label').hidden=true;$('scopeNote').hidden=false;$('scopeNote').textContent=namaDLSites.xPostURL(tab.url)?'この投稿に含まれる動画を保存します。':'タイムラインでは、動画付き投稿の共有ボタン横から保存してください。';}
 try{$('pageMenu').hidden=!['www.nicovideo.jp','www.youtube.com'].includes(new URL(tab.url).hostname)&&!namaDLSites.xPostURL(tab.url);}catch{}
 modeUI();await refresh();const r=await chrome.runtime.sendMessage({action:'hello'});if(r?.error)$('status').textContent=r.error;
})().catch(e=>{$('status').textContent=e.message;});
