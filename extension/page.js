(() => {
 if (globalThis.__namaDLPage) return;
 globalThis.__namaDLPage = true;
 const icon='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg>';
 const isNico=location.hostname==='www.nicovideo.jp';
 const isX=namaDLSites.isXHost(location.hostname);
 const authKey=isNico?'nicovideo.jp':namaDLSites.authKey(location.href);
 const posts=new Map();
 const cards=new Map();let activeContext=null;
 let buttonHost=null,buttonRoot=null,layer=null,root=null,lastUrl=location.href,returnFocus=null,scheduled=false;
 const $=id=>root?.getElementById(id);
 function watchPage(){return isX?!!namaDLSites.xPostURL(location.href):isNico?/^\/watch\//.test(location.pathname):(location.pathname==='/watch'&&new URLSearchParams(location.search).has('v'));}

 function playlistTarget(value){
  if(isX)return null;
  try{
   const u=new URL(value,location.href);
   if(u.origin!==location.origin)return null;
   if(isNico){
    const direct=u.pathname.match(/^\/(?:user\/\d+\/|my\/)?mylist\/(\d+)\/?$/);
    const legacy=/^\/(?:my\/)?mylist\/?$/.test(u.pathname)&&u.hash.match(/^#\/(\d+)(?:[/?]|$)/);
    const id=direct?.[1]||legacy?.[1];
    if(id)return u.origin+'/mylist/'+id;
   }
   const id=u.searchParams.get('list');
   if(!isNico&&['/playlist','/watch'].includes(u.pathname)&&id&&/^[\w-]+$/.test(id))return 'https://www.youtube.com/playlist?list='+encodeURIComponent(id);
  }catch{}
  return null;
 }
 function playlistPage(){return isNico?!!playlistTarget(location.href):location.pathname==='/playlist'&&!!playlistTarget(location.href);}
 function videoTarget(value){
  try{
   const u=new URL(value,location.href);if(u.origin!==location.origin)return null;
   if(isNico&&/^\/watch\/(?:sm|nm|so)?\d+\/?$/.test(u.pathname))return u.origin+u.pathname.replace(/\/$/,'');
   const id=u.pathname==='/watch'?u.searchParams.get('v'):u.pathname.match(/^\/(?:shorts|live)\/([\w-]{11})\/?$/)?.[1];
   if(!isNico&&/^[\w-]{11}$/.test(id||''))return u.origin+'/watch?v='+encodeURIComponent(id);
  }catch{}
  return null;
 }
 function pageContext(){return {url:isX?namaDLSites.xPostURL(location.href):playlistPage()?playlistTarget(location.href):location.href,playlist:playlistPage(),label:(isNico&&playlistPage()?document.querySelector('.MylistHeader-name')?.textContent:null)||document.title.replace(/\s*[-–]\s*(YouTube|ニコニコ動画).*$/,'')};}
 function postContext(article){
  if(!article.isConnected)return null;
  // Prefer the timestamp permalink; a quoted post or a link in the text is not the action row's target.
  const own=node=>node.closest('article[data-testid="tweet"]')===article&&!node.closest('[data-testid="quoteTweet"],[data-testid="card.wrapper"],div[role="link"]');
  const links=[...article.querySelectorAll('a[href]')].filter(own);
  const permalink=links.find(a=>a.querySelector('time')&&namaDLSites.xPostURL(a.href))||links.find(a=>a.closest('[data-testid="User-Name"]')&&namaDLSites.xPostURL(a.href));
  const url=permalink&&namaDLSites.xPostURL(permalink.href);
  if(!url)return null;
  const text=[...article.querySelectorAll('[data-testid="tweetText"]')].find(own)?.textContent;
  return {url,playlist:false,source:'post',label:text?.trim()||'Xの動画付き投稿'};
 }
 function postSlot(article){
  const media=[...article.querySelectorAll('video,[data-testid="videoPlayer"],[data-testid="videoComponent"]')].some(v=>v.closest('article[data-testid="tweet"]')===article);
  if(!media)return null;
  for(const group of article.querySelectorAll('[role="group"]')){
   if(group.closest('article[data-testid="tweet"]')!==article)continue;
   const share=[...group.querySelectorAll('button,[role="button"]')].find(b=>!b.closest('[data-nama-dl]')&&b.closest('[role="group"]')===group&&(/share|共有|シェア/i.test((b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||''))||b.getAttribute('data-testid')==='share'));
   if(!share)continue;
   let anchor=share;
   while(anchor.parentElement&&anchor.parentElement!==group)anchor=anchor.parentElement;
   return {controls:group,before:anchor.nextSibling,share};
  }
  return null;
 }
 function syncPosts(){
  const seen=new Set();
  for(const article of document.querySelectorAll('article[data-testid="tweet"]')){
   const context=postContext(article),target=context&&postSlot(article);if(!target)continue;
   seen.add(article);let item=posts.get(article);
   if(!item){item=createButton(()=>postSlot(article)&&postContext(article));posts.set(article,item);}
   if(item.host.parentElement!==target.controls||target.before!==item.host)target.controls.insertBefore(item.host,target.before);
   const color=getComputedStyle(target.share).color;
   const css='color:'+color+';--nama-hover:rgba(29,155,240,.15);width:36px;height:36px;flex:0 0 36px;';
   if(item.host.getAttribute('style')!==css)item.host.setAttribute('style',css);
   const button=item.shadow.querySelector('button'),label='この投稿の動画をダウンロード: '+context.label;
   if(button.title!==label){button.title=label;button.setAttribute('aria-label',label);}
  }
  for(const [article,item] of posts)if(!seen.has(article)){item.host.remove();posts.delete(article);}
 }
 function menuButton(container,anchor=null){
  return [...container.querySelectorAll('button,[role="button"]')].find(b=>{const r=b.getBoundingClientRect(),a=anchor?.getBoundingClientRect();return !b.closest('[data-nama-dl]')&&r.width>0&&r.height>0&&(!a||(r.top>a.top-40&&r.top<a.bottom+60))&&/その他|メニュー|more|menu/i.test((b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||''));});
 }
 function listSlot(){
  if(isNico){
   const header=[...document.querySelectorAll('.MylistHeader')].find(x=>x.getBoundingClientRect().width>0);
   const controls=header?.querySelector('.MylistHeaderAction,.MylistHeader-action');
   if(controls){
    let before=controls.querySelector('.MylistHeaderMenu')||controls.lastElementChild;
    while(before&&before.parentElement!==controls)before=before.parentElement;
    return {controls,before,list:true};
   }
  }
  if(!isNico){
   const header=[...document.querySelectorAll('ytd-playlist-header-renderer,yt-page-header-renderer,ytd-playlist-byline-renderer')].find(x=>x.getBoundingClientRect().width>0);
   if(header){const menu=menuButton(header)||header.querySelector('ytd-menu-renderer button');if(menu)return {controls:menu.parentElement,before:menu,list:true};return {controls:header,list:true};}
  }
  const heading=[...document.querySelectorAll('.MylistHeader-name,h1,h2,[role="heading"]')].find(x=>x.getBoundingClientRect().width>0&&!x.closest('.CommonHeader,.UserDetailsHeader,.MylistSideContainer,nav,aside'));
  if(!heading)return null;
  for(let parent=heading.parentElement,n=0;parent&&n<5;parent=parent.parentElement,n++){
   const menu=menuButton(parent,heading);if(menu)return {controls:menu.parentElement,before:menu,list:true};
  }
  return {controls:heading.parentElement,list:true};
 }
 function listStyle(host,controls,overlay=false){
  let dark=false;
  if(!isNico||overlay){
   dark=document.documentElement.hasAttribute('dark')||document.querySelector('ytd-app')?.hasAttribute('dark')||getComputedStyle(document.documentElement).colorScheme==='dark';
   if(!dark){
    for(let node=controls;node;node=node.parentElement){
     const color=getComputedStyle(node).backgroundColor.match(/^rgba?\(([^)]+)\)/);
     if(!color)continue;
     const rgb=color[1].split(',').map(Number);
     if(rgb.length===4&&rgb[3]<.5)continue;
     dark=.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]<128;break;
    }
   }
  }
  const color=isNico&&!overlay?getComputedStyle(controls).color:(dark?'#fff':'#000');
  const css='color:'+color+';--nama-hover:'+(dark?'rgba(255,255,255,.17)':'rgba(0,0,0,.08)')+';width:36px;height:36px;flex:0 0 36px;'+(overlay?'position:absolute;right:8px;top:8px;z-index:10;border-radius:50%;background:'+(dark?'rgba(0,0,0,.85)':'rgba(255,255,255,.9)')+';':'');
  if(host.getAttribute('style')!==css)host.setAttribute('style',css);
 }
 const ytCardSelector='ytd-video-renderer,ytd-grid-video-renderer,ytd-compact-video-renderer,ytd-playlist-renderer,ytd-grid-playlist-renderer,ytd-rich-grid-media,ytd-rich-item-renderer,yt-lockup-view-model,.yt-lockup-view-model,ytd-playlist-panel-video-renderer';
 const nicoCardSelector='.CheckboxVideoMediaObject,.NC-VideoMediaObjectWrapper,.NC-VideoMediaObject,.NC-MylistMediaObject,.VideoMediaObject,.VideoItem';
 function cardContainer(a){
  if(isNico)return a.closest('.CheckboxVideoMediaObject,.NC-VideoMediaObjectWrapper')||a.closest(nicoCardSelector);
  return a.closest(ytCardSelector);
 }
 function cardContext(container){
  if(!container.isConnected)return null;
  const title=container.querySelector('#video-title,#playlist-title,.yt-lockup-metadata-view-model__title,.NC-VideoMediaObject-title,.NC-MediaObjectTitle,h3,a[title]');
  const links=[...(container.matches('a[href]')?[container]:[]),...container.querySelectorAll('a[href]')].filter(a=>cardContainer(a)===container);
  const titleLink=title?.matches('a[href]')?title:title?.querySelector('a[href]');
  const fullListLink=links.find(a=>a!==titleLink&&/^(?:再生リスト(?:の)?全体(?:を見る)?|view full playlist)$/i.test(a.textContent.trim()));
  const candidates=[fullListLink,titleLink,...links].filter(Boolean);
  const listRenderer=container.matches('ytd-playlist-renderer,ytd-grid-playlist-renderer,.NC-MylistMediaObject');
  for(const a of candidates){
   // A watch URL with list=RD... is still a video card in recommendations.
   // Explicit list links and playlist renderers retain whole-list behavior.
   let list=null;
   try{if(listRenderer||a===fullListLink||new URL(a.href).pathname==='/playlist'||isNico)list=playlistTarget(a.href);}catch{}
   const url=list||videoTarget(a.href);if(!url)continue;
   return {url,playlist:!!list,source:'card',label:(title?.textContent||a.getAttribute('title')||a.textContent||(list?'再生リスト':'動画')).trim()};
  }
  return null;
 }
 function visible(node){
  const r=node?.getBoundingClientRect();if(!r||!r.width||!r.height)return false;
  for(let current=node;current;current=current.parentElement){const style=getComputedStyle(current);if(style.visibility==='hidden'||style.visibility==='collapse'||style.opacity==='0')return false;}
  return true;
 }
 function cardSlot(container){
  const labeled=menuButton(container);
  const menu=(labeled&&visible(labeled)?labeled:null)||[...container.querySelectorAll('ytd-menu-renderer button,button[aria-haspopup="true"],.NC-ThreePointMenu-button,.VideoMenu button')].find(visible);
  if(menu){
   const anchor=isNico?(menu.closest('.NC-ThreePointMenu,.VideoMenu')||menu):menu;
   const controls=anchor.parentElement;
   if(controls&&visible(controls))return {controls,before:anchor,overlay:false};
  }
  return {controls:container,before:null,overlay:true};
 }
 function restoreCardLayout(item){
  if(!item.layout)return;
  const {controls,changes,hadStyle}=item.layout;
  for(const [key,value] of changes){
   if(controls.style.getPropertyValue(key)!==value.applied)continue;
   if(value.before)controls.style.setProperty(key,value.before,value.priority);else controls.style.removeProperty(key);
  }
  if(!hadStyle&&!controls.getAttribute('style'))controls.removeAttribute('style');
  item.layout=null;
 }
 function setCardLayout(item,target){
  const controls=target.controls;
  if(item.layout?.controls===controls&&item.overlay===target.overlay&&item.host.parentElement===controls)return;
  restoreCardLayout(item);
  const layout={controls,hadStyle:controls.hasAttribute('style'),changes:new Map()};
  const styles=target.overlay?(getComputedStyle(controls).position==='static'?{position:'relative'}:{}):{display:'inline-flex','align-items':'center',width:'max-content',gap:'2px'};
  for(const [key,value] of Object.entries(styles)){
   const before=controls.style.getPropertyValue(key),priority=controls.style.getPropertyPriority(key);
   controls.style.setProperty(key,value);layout.changes.set(key,{before,priority,applied:controls.style.getPropertyValue(key)});
  }
  item.layout=layout;item.overlay=target.overlay;controls.insertBefore(item.host,target.before);
 }
 function syncCards(){
  const found=new Set(),seen=new Set();
  for(const a of document.querySelectorAll(isNico?'a[href*="/watch/"],a[href*="mylist"]':'a[href*="/watch?"],a[href*="/playlist?"],a[href*="/shorts/"],a[href*="/live/"]')){
   const container=cardContainer(a);
   if(container&&!container.closest('ytd-playlist-header-renderer,.MylistHeader'))found.add(container);
  }
  for(const container of found){
   const context=cardContext(container);if(!context)continue;
   seen.add(container);let item=cards.get(container);
   if(!item){item=createButton(()=>cardContext(container));cards.set(container,item);}
   const target=cardSlot(container);setCardLayout(item,target);listStyle(item.host,target.controls,target.overlay);
   const label=(context.playlist?'リスト全体':'この動画')+'をダウンロード: '+context.label;
   const button=item.shadow.querySelector('button');if(button.title!==label){button.title=label;button.setAttribute('aria-label',label);}
  }
  for(const [container,item] of cards){
   if(!seen.has(container)){item.host.remove();restoreCardLayout(item);cards.delete(container);}
  }
 }
 function videos(){return [...document.querySelectorAll('video')].filter(v=>v.getBoundingClientRect().width>100).sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width);}
 function slot(){
  if(!isNico){const controls=document.querySelector('#movie_player .ytp-right-controls');if(controls)return {controls};}
  const video=videos()[0];if(!video)return null;
  const vr=video.getBoundingClientRect();
  for(let parent=video.parentElement,depth=0;parent&&depth<8;parent=parent.parentElement,depth++){
   const pr=parent.getBoundingClientRect();
   if(pr.width>vr.width*1.4||pr.height>vr.height+220)break;
   const settings=[...parent.querySelectorAll('button,[role="button"]')].find(b=>{
    if(b.closest('[data-nama-dl]'))return false;
    const label=(b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||'');
    const br=b.getBoundingClientRect();
    return /設定|全画面|fullscreen|settings/i.test(label)&&br.width>0&&br.height>0&&br.top>vr.bottom-95&&br.top<vr.bottom+90;
   });
   if(settings){
    let controls=settings.parentElement,before=settings;
    while(controls&&controls!==parent&&controls.getBoundingClientRect().width<settings.getBoundingClientRect().width*1.6){before=controls;controls=controls.parentElement;}
    if(controls)return {controls,before};
   }
  }
  return {fallback:video};
 }
 function closeMenu(){
  if(!layer)return;
  layer.remove();layer=null;root=null;
  returnFocus?.focus();returnFocus=null;
 }
 function createButton(getContext=pageContext){
  const host=document.createElement('span');host.dataset.namaDl='button';
  const shadow=host.attachShadow({mode:'closed'});
  shadow.innerHTML='<style>:host{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;width:40px;height:40px;flex:0 0 40px;color:white}button{display:flex;align-items:center;justify-content:center;width:36px;height:36px;padding:0;border:0;border-radius:50%;background:transparent;color:inherit;cursor:pointer;opacity:.95}button:hover{background:var(--nama-hover,rgba(255,255,255,.17))}button:focus-visible{outline:2px solid currentColor;outline-offset:2px}</style><button type="button" title="nama_DL ダウンロード" aria-label="nama_DL ダウンロード">'+icon+'</button>';
  shadow.querySelector('button').addEventListener('click',e=>{e.preventDefault();e.stopPropagation();if(e.isTrusted){const context=getContext();if(context)openMenu(context,shadow.querySelector('button'));}});
  return {host,shadow};
 }
 function ensureButton(){
  scheduled=false;
  if(lastUrl!==location.href){lastUrl=location.href;closeMenu();}
  if(isX){syncPosts();buttonHost?.remove();return;}
  syncCards();
  if(!watchPage()&&!playlistPage()){buttonHost?.remove();return;}
  const target=playlistPage()?listSlot():slot();if(!target){buttonHost?.remove();return;}
  if(!buttonHost){const created=createButton();buttonHost=created.host;buttonRoot=created.shadow;}
  if(target.controls){
   if(target.list)listStyle(buttonHost,target.controls);else buttonHost.style.cssText='';
   if(buttonHost.parentElement!==target.controls)target.controls.insertBefore(buttonHost,target.before||target.controls.firstChild);
  }else{
   const rect=target.fallback.getBoundingClientRect(),parent=document.fullscreenElement||document.body;
   if(buttonHost.parentElement!==parent)parent.append(buttonHost);
   const css=`position:fixed;z-index:2147483000;left:${Math.max(rect.left+10,rect.right-210)}px;top:${rect.bottom-51}px;`;
   if(buttonHost.style.cssText!==css)buttonHost.style.cssText=css;
  }
 }
 function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(ensureButton);}}
 async function settingsChanged(){
  if(!root)return;
  try{
   const data=await chrome.storage.local.get(['destination','folderMessage','status']);
   if(!root)return;
   $('destination').textContent=data.destination||'ビデオ / VideoButton';
   $('folderMessage').textContent=data.folderMessage||'';
   $('status').textContent=data.status?.text||'待機中';
   $('start').disabled=!!data.status?.busy;
   $('inspect').disabled=!!data.status?.busy;
   $('cancel').hidden=!data.status?.busy;
  }catch{if(root)$('status').textContent='拡張機能を更新した場合は、この動画ページを再読み込みしてください。';}
 }
 function selectedOptions(validate=false){return {media:root.querySelector('input[name="media"]:checked').value,embedThumbnail:$('embedThumbnail').checked,embedMetadata:$('embedMetadata').checked,...namaDLEdits.read(root,activeContext.url,validate)};}
 function modeUI(){
  const o=selectedOptions();
  namaDLEdits.update(root,o.media);
  $('embedThumbnail').disabled=o.media!=='video';$('embedMetadata').disabled=o.media==='thumbnail';
  for(const card of root.querySelectorAll('.choice'))card.classList.toggle('selected',card.querySelector('input').checked);
 }
 async function saveOptions(){modeUI();await chrome.storage.local.set({options:selectedOptions()});}
 async function request(action,event){
  if(event&&!event.isTrusted)return;
  try{
   $('status').textContent=action==='chooseFolder'?'フォルダー選択画面を開いています…':'処理を準備中…';
   const response=await chrome.runtime.sendMessage({action,url:activeContext.url,source:activeContext.source,playlist:action==='inspect'?false:(activeContext.playlist||$('playlist').checked),options:selectedOptions(action==='download')});
   if(response?.error)throw Error(response.error);
  }catch(e){if(root)$('status').textContent=e.message;}
 }
 async function openMenu(context=pageContext(),focus=buttonRoot?.querySelector('button')){
  if(layer){$('start').focus();return;}
  activeContext=context;
  returnFocus=focus;
  layer=document.createElement('div');layer.dataset.namaDl='menu';root=layer.attachShadow({mode:'closed'});
  root.innerHTML=`<style>
   :host{position:fixed;inset:0;z-index:2147483647;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#eee;font-size:14px;line-height:1.5;--blue:#0085ff}
   *{box-sizing:border-box}.backdrop{position:absolute;inset:0;background:#0008;backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;padding:20px}
   .dialog{width:520px;max-width:100%;max-height:90vh;overflow:auto;background:#1b1b1b;border:1px solid #383838;border-radius:14px;box-shadow:0 12px 50px #0007}
   header{display:flex;align-items:center;gap:10px;padding:19px 22px;border-bottom:1px solid #383838;font-size:18px;font-weight:700}header .close{margin-left:auto;border:0;background:none;color:#aaa;font-size:24px;width:30px;padding:0}
   main{padding:18px 20px}button{font:inherit;cursor:pointer;color:#eee;border:1px solid #494949;border-radius:8px;background:#303030;padding:8px 12px}button:hover:not(:disabled){background:#414141}button:disabled{opacity:.4;cursor:default}
   .choices{display:grid;gap:9px}.choice{display:flex;align-items:center;gap:12px;background:#2c2c2c;border:1px solid #414141;border-radius:10px;padding:13px 14px;cursor:pointer}.choice.selected{border-color:var(--blue);background:#203242}.choice strong{font-size:15px}.choice small{display:block;color:#aaa;font-size:12px;margin-top:2px}input{accent-color:var(--blue)}input[type=radio]{width:17px;height:17px;margin:0}
   details{margin-top:17px;color:#ccc;font-size:13px}summary{cursor:pointer}.checks{display:grid;gap:9px;margin:13px 0}label:has(input:disabled){opacity:.45}
   .folder{margin-top:17px;border-top:1px solid #383838;padding-top:15px;display:flex;gap:10px;align-items:center}.path{min-width:0;flex:1}.path small{display:block;color:#999;font-size:11px}.path span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}.folder button{white-space:nowrap;font-size:12px}
   #folderMessage{font-size:11px;color:#aaa;margin:5px 0 0}#status{font:12px/1.5 system-ui;white-space:pre-wrap;overflow-wrap:anywhere;color:#bbb;max-height:135px;overflow:auto;margin:14px 0 0}
   footer{display:flex;gap:10px;padding:15px 20px;border-top:1px solid #383838;align-items:center}.primary{margin-left:auto;background:var(--blue);border-color:var(--blue);color:white;font-weight:600;padding:10px 19px}.primary:hover:not(:disabled){background:#2195ff}footer .minor{font-size:12px;padding:7px 9px}button:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid #55b3ff;outline-offset:3px}
  </style><div class="backdrop"><section class="dialog" role="dialog" aria-modal="true" aria-label="nama_DL ダウンロード"><header>${icon}<span>nama_DL ダウンロード</span><button class="close" id="close" aria-label="閉じる">×</button></header><main>
  <p id="context" style="font-size:12px;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0 0 12px"></p><div class="choices" role="radiogroup" aria-label="保存内容">
   <label class="choice"><input name="media" value="video" type="radio" checked><span><strong>動画を保存</strong><small>MP4 · 最高画質 · After Effects用</small></span></label>
   <label class="choice"><input name="media" value="audio" type="radio"><span><strong>音声のみを保存</strong><small>WAV · 24bit PCM</small></span></label>
   <label class="choice"><input name="media" value="thumbnail" type="radio"><span><strong>サムネイルのみを保存</strong><small>PNG画像</small></span></label>
  </div><div id="editOptions"></div><details><summary>詳細設定</summary><div class="checks">
   <label><input type="checkbox" id="embedThumbnail"> サムネイルを埋め込む（動画のみ）</label>
   <label><input type="checkbox" id="embedMetadata"> メタデータを埋め込む</label>
   <label><input type="checkbox" id="auth"> このサイトのログイン情報を使う</label>
   <label><input type="checkbox" id="playlist"> 再生リスト・マイリスト全体を保存</label>
  </div><button id="inspect" type="button">画質を確認</button> <button id="folder" type="button">保存先を開く</button></details>
  <div class="folder"><div class="path"><small>保存先</small><span id="destination"></span></div><button id="chooseFolder">変更</button></div><p id="folderMessage"></p><pre id="status">待機中</pre>
  </main><footer><button id="cancel" class="minor" hidden>処理を中止</button><button id="start" class="primary">ダウンロード</button></footer></section></div>`;
  (document.fullscreenElement||document.body).append(layer);
  $('context').textContent=(activeContext.playlist?'リスト全体: ':activeContext.source==='post'?'投稿: ':activeContext.source==='card'?'動画: ':'')+(activeContext.label||'現在の動画');
  $('context').title=$('context').textContent;
  $('playlist').checked=!!activeContext.playlist;$('playlist').disabled=!!activeContext.playlist||activeContext.source==='card';
  if(isX){$('playlist').checked=false;$('playlist').disabled=true;$('playlist').closest('label').hidden=true;}
  $('close').onclick=closeMenu;
  root.querySelector('.backdrop').addEventListener('click',e=>{if(e.target.classList.contains('backdrop'))closeMenu();});
  layer.addEventListener('keydown',e=>{
   e.stopPropagation();
   if(e.key==='Escape'){e.preventDefault();closeMenu();return;}
   if(e.key==='Tab'){
    const focus=[...root.querySelectorAll('button,input,summary')].filter(x=>!x.disabled&&!x.hidden&&x.getClientRects().length);
    const first=focus[0],last=focus.at(-1),active=root.activeElement;
    if(e.shiftKey&&active===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&active===last){e.preventDefault();first.focus();}
   }
  });
  for(const action of ['download','inspect','chooseFolder','folder','cancel']){
   const id=action==='download'?'start':action;$(id).onclick=e=>request(action,e);
  }
  for(const input of root.querySelectorAll('input[name="media"],#embedThumbnail,#embedMetadata'))input.onchange=saveOptions;
  $('auth').onchange=async()=>{const data=await chrome.storage.local.get('authSites');await chrome.storage.local.set({authSites:{...(data.authSites||{}),[authKey]:$('auth').checked}});};
  try{
   const data=await chrome.storage.local.get(['options','authSites']);if(!root)return;
   const o=data.options||{},media=['audio','thumbnail'].includes(o.media)?o.media:'video';
   root.querySelector('input[value="'+media+'"]').checked=true;
   namaDLEdits.mount(root,o,activeContext.url,saveOptions,()=>playbackTime(activeContext.url));
   $('embedThumbnail').checked=!!o.embedThumbnail;$('embedMetadata').checked=!!o.embedMetadata;$('auth').checked=data.authSites?.[authKey]??isNico;
   modeUI();await settingsChanged();$('start')?.focus();
  }catch(e){if(root)$('status').textContent=e.message;}
 }
 chrome.storage.onChanged.addListener(settingsChanged);
 function playbackTime(url){
  if(isX){const article=[...document.querySelectorAll('article[data-testid="tweet"]')].find(a=>postContext(a)?.url===namaDLSites.xPostURL(url));const media=article?[...article.querySelectorAll('video')].filter(v=>v.closest('article[data-testid="tweet"]')===article):[];return media.length===1?media[0].currentTime:null;}
  if(!watchPage()||videoTarget(url)!==videoTarget(location.href))return null;
  return videos()[0]?.currentTime??null;
 }
 chrome.runtime.onMessage.addListener((m,s,reply)=>{
  if(m.action==='getNamaPlayback'){reply({seconds:playbackTime(m.url)});return;}
  if(m.action==='openNamaMenu'){if(!watchPage()&&!playlistPage()){reply({error:'動画またはリストの個別ページを開いてください'});return;}openMenu().then(()=>reply({ok:true}));return true;}
 });
 document.addEventListener('fullscreenchange',()=>{if(layer)(document.fullscreenElement||document.body).append(layer);schedule();});
 document.addEventListener('yt-navigate-finish',schedule);
 window.addEventListener('hashchange',schedule);
 window.addEventListener('resize',schedule);window.addEventListener('scroll',schedule,true);
 new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['href','aria-label','title','data-testid']});
 new MutationObserver(schedule).observe(document.documentElement,{attributes:true,attributeFilter:['dark','class','style','data-theme']});
 setInterval(schedule,1500);schedule();
})();
