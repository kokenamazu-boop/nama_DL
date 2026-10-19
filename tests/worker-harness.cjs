const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const extension=path.join(__dirname,'../extension');
const version=JSON.parse(fs.readFileSync(path.join(extension,'manifest.json'),'utf8')).version;
const clone=v=>JSON.parse(JSON.stringify(v));
function worker(settings={},behavior={}){
 const sent=[],cookieRequests=[],data=clone(settings),ports=[];let handler,cookieValue='fresh',disconnectHandler;
 const chrome={
  runtime:{id:'test-id',onMessage:{addListener(fn){handler=fn;}},onStartup:{addListener(){}},connectNative(){
   if(behavior.connectError)throw Error('native host not found');
   let nativeHandler;const port={onMessage:{addListener(fn){nativeHandler=fn;}},onDisconnect:{addListener(fn){disconnectHandler=fn;}},postMessage(m){sent.push(clone(m));if(m.action==='hello')queueMicrotask(()=>nativeHandler({type:'hello',version:behavior.version||version}));},emit(m){nativeHandler(m);}};ports.push(port);return port;
  }},
  storage:{local:{async get(){return clone(data);},async set(values){Object.assign(data,clone(values));}}},
  cookies:{async getAllCookieStores(){return [{id:'profile-2',tabIds:[7]}];},async getAll(query){cookieRequests.push(clone(query));return [{domain:'.x.com',name:'auth_token',value:cookieValue}];}}
 };
 const sandbox={URL,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,chrome};const context=vm.createContext(sandbox);
 sandbox.importScripts=(...files)=>files.forEach(file=>vm.runInContext(fs.readFileSync(path.join(extension,file),'utf8'),context));
 vm.runInContext(fs.readFileSync(path.join(extension,'worker.js'),'utf8'),context);
 const flush=()=>vm.runInContext('serial',context);
 return {sent,cookieRequests,data,sites:context.namaDLSites,flush,
  send(m,url='https://x.com/home'){return new Promise(resolve=>handler(m,{id:'test-id',...(url?{tab:{id:7,url}}:{})},resolve));},
  async message(m){ports.at(-1).emit(m);await flush();},
  async disconnect(){disconnectHandler();await flush();},
  setCookies(value){cookieValue=value;}
 };
}
module.exports={worker,version};
