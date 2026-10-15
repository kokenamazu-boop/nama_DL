const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const extension=path.join(__dirname,'../extension');
const sitesSource=fs.readFileSync(path.join(extension,'sites.js'),'utf8');
const version=JSON.parse(fs.readFileSync(path.join(extension,'manifest.json'),'utf8')).version;

function worker(settings={}) {
 const sent=[],cookieRequests=[],data={...settings};let handler,nativeHandler;
 const port={onMessage:{addListener(fn){nativeHandler=fn;}},onDisconnect:{addListener(){}},postMessage(m){sent.push(m);if(m.action==='hello')queueMicrotask(()=>nativeHandler({type:'hello',version}));}};
 const sandbox={URL,setTimeout,clearTimeout,chrome:{
  runtime:{id:'test-id',onMessage:{addListener(fn){handler=fn;}},onStartup:{addListener(){}},connectNative(){return port;}},
  storage:{local:{async get(){return data;},async set(values){Object.assign(data,values);}}},
  cookies:{async getAllCookieStores(){return [{id:'profile-2',tabIds:[7]}];},async getAll(query){cookieRequests.push(query);return [{domain:'.x.com',name:'auth_token',value:'test'}];}}
 }};
 const context=vm.createContext(sandbox);
 sandbox.importScripts=()=>vm.runInContext(sitesSource,context);
 vm.runInContext(fs.readFileSync(path.join(extension,'worker.js'),'utf8'),context);
 return {sent,cookieRequests,sites:context.namaDLSites,send(m,url){return new Promise(resolve=>handler(m,{id:'test-id',tab:{id:7,url}},resolve));}};
}

test('X post URLs normalize only supported HTTPS post links',()=>{
 const {sites}=worker();
 for(const url of ['https://x.com/author/status/123?s=20','https://twitter.com/author/status/123/video/2','https://www.twitter.com/author/status/123/photo/1'])assert.equal(sites.xPostURL(url),'https://x.com/author/status/123');
 assert.equal(sites.xPostURL('https://x.com/i/web/status/123'),'https://x.com/i/web/status/123');
 for(const url of ['https://x.com/home','https://x.com/author','https://x.com.evil.test/author/status/123','https://evil.test/author/status/123','http://x.com/author/status/123','https://user:secret@x.com/author/status/123','https://x.com:9000/author/status/123','https://x.com/author/status/not-an-id'])assert.equal(sites.xPostURL(url),null);
 assert.equal(sites.authKey('https://twitter.com/home'),'https://x.com');
});

test('timeline button sends the selected post, with X cookies from the same profile',async()=>{
 const w=worker({authSites:{'https://x.com':true},destination:'D:\\Videos'});
 const reply=await w.send({action:'download',source:'post',url:'https://twitter.com/author/status/123?s=20',playlist:true,options:{media:'video'}},'https://x.com/home');
 assert.equal(reply.ok,true);
 const request=w.sent.find(m=>m.action==='download');
 assert.equal(request.url,'https://x.com/author/status/123');assert.equal(request.playlist,false);assert.equal(request.destination,'D:\\Videos');
 assert.equal(w.cookieRequests[0].domain,'x.com');assert.equal(w.cookieRequests[0].storeId,'profile-2');
});

test('X default sends no cookies and normalized individual-page requests work',async()=>{
 const w=worker();
 assert.equal((await w.send({action:'inspect',url:'https://x.com/author/status/123'},'https://twitter.com/author/status/123?s=20')).ok,true);
 assert.equal(w.cookieRequests.length,0);assert.equal(w.sent.at(-1).cookies.length,0);
});

test('X rejects profile downloads, other hosts and missing timeline context',async()=>{
 for(const [target,source] of [['https://x.com/author','post'],['https://evil.test/author/status/123','post'],['https://www.youtube.com/watch?v=abcdefghijk','post'],['https://x.com/author/status/123',undefined]]){
  const w=worker();assert.ok((await w.send({action:'download',url:target,source},'https://x.com/home')).error);assert.equal(w.sent.length,0);
 }
});

test('YouTube and Nico card requests retain individual-video behavior',async()=>{
 for(const [page,target] of [['https://www.youtube.com/','https://www.youtube.com/watch?v=abcdefghijk&list=RDabcdefghijk'],['https://www.nicovideo.jp/','https://www.nicovideo.jp/watch/sm123/']]){
  const w=worker({authSites:{'nicovideo.jp':false}});
  assert.equal((await w.send({action:'download',source:'card',url:target,playlist:true},page)).ok,true);
  assert.equal(w.sent.at(-1).playlist,false);
 }
});
