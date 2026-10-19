// Shared popup/page queue view. No polling, thumbnails, or media decoding.
globalThis.namaDLQueueUI={
 mount(scope,send){
  const container=scope.getElementById('queue');
  container.innerHTML=`<style>
   .dl-queue{margin-top:14px;border-top:1px solid #383838;padding-top:12px;color:#ccc;font:12px/1.5 system-ui}.dl-queue summary{cursor:pointer}.dl-queue .queue-tools{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0}.dl-queue button{font-size:11px;padding:5px 8px}.dl-queue ol{list-style:none;padding:0;margin:0;max-height:210px;overflow:auto;overscroll-behavior:contain}.dl-queue li{border-top:1px solid #353535;padding:9px 0}.dl-queue .queue-title{display:block;color:#eee;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}.dl-queue .queue-meta,.dl-queue .queue-hint{color:#aaa;font-size:11px;overflow-wrap:anywhere}.dl-queue .queue-actions{display:flex;gap:6px;margin-top:6px}.dl-queue .queue-result{margin-top:5px;font-size:11px}.dl-queue pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:105px;overflow:auto;margin:5px 0;color:#bbb;font:11px/1.5 system-ui}.dl-queue [hidden]{display:none!important}.dl-queue .queue-message{color:#f6c16c;margin:5px 0}.dl-queue p{margin:0}
  </style><details class="dl-queue"><summary>ダウンロードキュー <span data-count></span></summary><div class="queue-tools"><button type="button" data-toggle>一時停止</button><button type="button" data-clear>履歴を消す</button></div><p class="queue-hint" data-hint></p><p class="queue-message" role="status" data-message></p><ol aria-label="ダウンロードキュー"></ol></details>`;
  const details=container.querySelector('details'),list=container.querySelector('ol'),toggle=container.querySelector('[data-toggle]'),clear=container.querySelector('[data-clear]'),message=container.querySelector('[data-message]');
  const rows=new Map();let lastQueue=null;
  const act=async(action,id)=>{try{message.textContent='';const r=await send({action,id});if(r?.error)throw Error(r.error);}catch(e){message.textContent=e.message;}};
  toggle.onclick=()=>act(lastQueue?.paused?'queueResume':'queuePause');clear.onclick=()=>act('queueClear');
  const states={waiting:'待機中',active:'実行中',done:'完了',error:'失敗',cancelled:'中止',interrupted:'接続中断'};
  const element=(tag,cls,parent)=>{const node=container.ownerDocument.createElement(tag);if(cls)node.className=cls;parent.append(node);return node;};
  return {
   render(q,status){
    q=q||{jobs:[],paused:false};lastQueue=q;const jobs=q.jobs||[],waiting=jobs.filter(j=>j.state==='waiting').length,active=jobs.some(j=>j.state==='active');
    container.querySelector('[data-count]').textContent=`実行 ${active?1:0} / 待機 ${waiting}`;
    toggle.textContent=q.paused?'再開':'一時停止';clear.disabled=!jobs.some(j=>['done','error','cancelled','interrupted'].includes(j.state));
    container.querySelector('[data-hint]').textContent=q.paused?(active?'一時停止予約中。現在の処理が終わったら停止します。':'一時停止中。「再開」で順番に処理します。'):(jobs.length?'1件ずつ順番に処理します。メニューを閉じても続きます。':'ダウンロードしたい動画をキューに追加してください。');
    const ids=new Set(jobs.map(j=>j.id));for(const [id,row] of rows)if(!ids.has(id)){row.li.remove();rows.delete(id);}
    let previous=null;
    // Active/waiting first; preserve row nodes and focus during progress updates.
    const ordered=[...jobs.filter(j=>j.state==='active'),...jobs.filter(j=>j.state==='waiting'),...jobs.filter(j=>!['active','waiting'].includes(j.state)).reverse()];
    for(const job of ordered){
     let row=rows.get(job.id);
     if(!row){
      const li=element('li','',list),title=element('span','queue-title',li),meta=element('p','queue-meta',li),result=element('details','queue-result',li),summary=element('summary','',result),text=element('pre','',result),actions=element('div','queue-actions',li);
      summary.textContent='進行状況・結果';
      const retry=element('button','',actions),remove=element('button','',actions);retry.type=remove.type='button';retry.textContent='再試行';remove.textContent='削除';
      retry.onclick=()=>act('queueRetry',job.id);remove.onclick=()=>act('queueRemove',job.id);
      row={li,title,meta,result,text,retry,remove};rows.set(job.id,row);
     }
     const next=previous?previous.nextSibling:list.firstChild;if(next!==row.li)list.insertBefore(row.li,next);previous=row.li;
     row.title.textContent=job.title||job.url;row.title.title=job.url;
     const o=job.options||{},media={video:'MP4',audio:'WAV',thumbnail:'PNG'}[o.media]||'MP4';
     row.meta.textContent=`${states[job.state]||job.state} · ${media}${job.playlist?' · リスト全体':''}${o.clipEnabled?' · '+(o.clipStart||'0')+'〜'+(o.clipEnd||'末尾'):''}${o.normalizeEnabled?' · '+o.targetLUFS+' LUFS':''}`;
     row.meta.title='保存先: '+(job.destination||'ビデオ / VideoButton');
     row.text.textContent='URL: '+job.url+'\n保存先: '+(job.destination||'ビデオ / VideoButton')+'\n'+(status?.jobId===job.id&&job.state==='active'?status.text:(job.text||''));
     row.retry.hidden=!['error','cancelled','interrupted'].includes(job.state);row.remove.hidden=job.state==='active';
    }
   },
   added(duplicate=false){details.open=true;message.textContent=duplicate?'同じ設定の項目がすでにキューにあります。':'キューに追加しました。';}
  };
 }
};
