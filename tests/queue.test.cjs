const {test}=require('node:test');
const assert=require('node:assert/strict');
const {worker}=require('./worker-harness.cjs');
const request=(id,options={})=>({action:'download',source:'post',url:`https://x.com/author/status/${id}`,title:`Video ${id}`,options:{media:'video',...options}});
const downloads=w=>w.sent.filter(m=>m.action==='download');
const q=w=>w.data.downloadQueue;

test('FIFO jobs retain options/destination, fetch fresh cookies at start, and never persist cookies',async()=>{
 const w=worker({destination:'D:\\First',authSites:{'https://x.com':true}});
 const a=await w.send(request(1,{clipEnabled:true,clipStart:'2',clipEnd:'5',normalizeEnabled:true,targetLUFS:'-18'}));
 w.data.destination='D:\\Second';
 const b=await w.send(request(2,{media:'audio'}));
 w.data.destination='D:\\Third';
 assert.equal(a.ok,true);assert.equal(b.ok,true);assert.equal(downloads(w).length,1);
 assert.equal(q(w).jobs[0].state,'active');assert.equal(q(w).jobs[1].state,'waiting');
 assert.equal(w.cookieRequests.length,1);assert.ok(!JSON.stringify(q(w)).includes('auth_token'));assert.ok(!JSON.stringify(q(w)).includes('fresh'));
 w.setCookies('new-token');await w.message({type:'done',jobId:a.id,text:'saved'});
 assert.equal(downloads(w).length,2);const next=downloads(w)[1];
 assert.equal(next.jobId,b.id);assert.equal(next.destination,'D:\\Second');assert.equal(next.options.media,'audio');assert.equal(next.cookies[0].value,'new-token');
 assert.equal(downloads(w)[0].options.clipStart,'2');assert.equal(downloads(w)[0].options.targetLUFS,'-18');
 assert.equal(q(w).jobs[0].text,'saved');assert.equal(w.data.status.busy,true);
 await w.message({type:'done',jobId:b.id,text:'finished'});assert.equal(w.data.status.busy,false);
});

test('simultaneous additions serialize and exact pending duplicates are coalesced',async()=>{
 const w=worker();const results=await Promise.all([w.send(request(1)),w.send(request(1)),w.send(request(2))]);
 assert.equal(results[1].duplicate,true);assert.equal(results[0].id,results[1].id);assert.equal(q(w).jobs.length,2);assert.equal(downloads(w).length,1);
 // Same URL, different requested output is a distinct job.
 await w.send(request(1,{media:'audio'}));assert.equal(q(w).jobs.length,3);
});

test('pause finishes current job, removal affects waiting only, resume starts next',async()=>{
 const w=worker();const a=await w.send(request(1)),b=await w.send(request(2)),c=await w.send(request(3));
 await w.send({action:'queuePause'});assert.equal(q(w).paused,true);
 assert.ok((await w.send({action:'queueRemove',id:a.id})).error);
 await w.send({action:'queueRemove',id:b.id});await w.message({type:'done',jobId:a.id,text:'OK'});
 assert.equal(downloads(w).length,1);assert.equal(q(w).jobs.length,2);
 await w.send({action:'queueResume'});assert.equal(downloads(w)[1].jobId,c.id);
});

test('error and cancellation advance queue; cancel targets active ID; retry appends to tail',async()=>{
 const w=worker();const a=await w.send(request(1)),b=await w.send(request(2)),c=await w.send(request(3));
 await w.send({action:'cancel'});assert.equal(w.sent.at(-1).jobId,a.id);
 await w.message({type:'cancelled',jobId:a.id,text:'cancelled'});assert.equal(downloads(w)[1].jobId,b.id);
 await w.send({action:'queueRetry',id:a.id});assert.equal(q(w).jobs.at(-1).id,a.id);
 await w.message({type:'error',jobId:b.id,text:'network error'});assert.equal(downloads(w)[2].jobId,c.id);
 await w.message({type:'done',jobId:c.id,text:'done'});assert.equal(downloads(w)[3].jobId,a.id);
 await w.send({action:'queueClear'});assert.equal(q(w).jobs.length,1);assert.equal(q(w).jobs[0].state,'active');
});

test('stale terminal/progress cannot finish or overwrite another job',async()=>{
 const w=worker();const a=await w.send(request(1)),b=await w.send(request(2));
 await w.message({type:'done',jobId:a.id,text:'first done'});
 await w.message({type:'done',jobId:a.id,text:'stale'});await w.message({type:'progress',jobId:a.id,text:'stale progress'});
 assert.equal(q(w).jobs[1].state,'active');assert.equal(w.data.status.text,'動画を解析中…');
 await w.message({type:'done',jobId:b.id,text:'second done'});assert.equal(q(w).jobs[0].text,'first done');
});

test('disconnect and worker restart retain waiting jobs, mark active interrupted, and pause without duplicate downloads',async()=>{
 const w=worker();const a=await w.send(request(1));await w.send(request(2));
 const atCrash=JSON.parse(JSON.stringify(w.data));
 await w.disconnect();assert.equal(q(w).paused,true);assert.equal(q(w).jobs[0].state,'interrupted');assert.equal(q(w).jobs[1].state,'waiting');
 const restarted=worker(atCrash);await restarted.flush();assert.equal(q(restarted).paused,true);assert.equal(q(restarted).jobs[0].state,'interrupted');assert.equal(downloads(restarted).length,0);
 await restarted.send({action:'queueResume'});assert.equal(downloads(restarted).length,1);assert.notEqual(downloads(restarted)[0].jobId,a.id);
});

test('login failure is per job and does not stop next non-authenticated item',async()=>{
 const w=worker({authSites:{'nicovideo.jp':true}});await w.send({action:'queuePause'});
 await w.send({action:'download',url:'https://www.nicovideo.jp/watch/sm1'},'https://www.nicovideo.jp/watch/sm1');await w.send(request(2));
 await w.send({action:'queueResume'});assert.equal(q(w).jobs[0].state,'error');assert.match(q(w).jobs[0].text,/ログイン/);assert.equal(q(w).jobs[1].state,'active');assert.equal(q(w).paused,false);
});

test('playlist stays one queued request and inspection cannot overlap downloads',async()=>{
 const w=worker();const r=await w.send({action:'download',url:'https://www.youtube.com/playlist?list=PLtest',playlist:true},'https://www.youtube.com/playlist?list=PLtest');
 assert.equal(downloads(w)[0].playlist,true);assert.equal(q(w).jobs.length,1);
 assert.ok((await w.send({action:'inspect',url:'https://www.youtube.com/watch?v=abcdefghijk'},'https://www.youtube.com/watch?v=abcdefghijk')).error);
 await w.message({type:'done',jobId:r.id,text:'done'});assert.equal(w.data.status.busy,false);
});

test('history is bounded without removing active/waiting jobs',async()=>{
 const w=worker();
 for(let i=1;i<=23;i++){const r=await w.send(request(i));await w.message({type:'done',jobId:r.id,text:'done'});}
 assert.equal(q(w).jobs.length,20);assert.ok(q(w).jobs.every(j=>j.state==='done'));
});

test('missing/outdated native host pauses remaining jobs without dropping the queue',async()=>{
 for(const behavior of [{connectError:true},{version:'0.0.0'}]){
  const w=worker({},behavior);await w.send({action:'queuePause'});await w.send(request(1));await w.send(request(2));
  await w.send({action:'queueResume'});assert.equal(q(w).jobs[0].state,'error');assert.equal(q(w).jobs[1].state,'waiting');assert.equal(q(w).paused,true);assert.equal(downloads(w).length,0);
 }
});

test('native messages lacking job IDs cannot change a queued job',async()=>{
 const w=worker();const a=await w.send(request(1));
 await w.message({type:'done',text:'old host done'});await w.message({type:'progress',text:'old host progress'});
 assert.equal(q(w).jobs[0].state,'active');assert.equal(w.data.status.busy,true);
 await w.message({type:'done',jobId:a.id,text:'right ID'});assert.equal(q(w).jobs[0].state,'done');
});

test('progress reaches the queue and a pending progress update cannot overwrite completion',async()=>{
 const w=worker();const a=await w.send(request(1));
 await w.message({type:'progress',jobId:a.id,text:'50%'});
 await new Promise(r=>setTimeout(r,550));await w.flush();assert.equal(w.data.status.text,'50%');assert.equal(w.data.status.jobId,a.id);
 await w.message({type:'progress',jobId:a.id,text:'100% progress'});await w.message({type:'done',jobId:a.id,text:'saved'});
 await new Promise(r=>setTimeout(r,550));await w.flush();assert.equal(q(w).jobs[0].text,'saved');assert.equal(w.data.status.text,'saved');
});

test('requests added during quality inspection wait until its terminal message',async()=>{
 const w=worker();await w.send({action:'inspect',url:'https://x.com/author/status/9'} ,'https://x.com/author/status/9');
 const inspection=w.sent.find(m=>m.action==='inspect');const a=await w.send(request(1));assert.equal(downloads(w).length,0);assert.equal(q(w).jobs[0].state,'waiting');
 await w.message({type:'done',jobId:inspection.jobId,text:'formats listed'});assert.equal(downloads(w)[0].jobId,a.id);
});
