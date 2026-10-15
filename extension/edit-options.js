// Shared controls: no polling or audio processing runs in the browser.
globalThis.namaDLEdits={
 parseTime(value,optional=false){
  const text=String(value??'').trim();if(!text)return optional?null:0;
  if(text.length>24||!/^\d+(?::\d+){0,2}(?:\.\d{1,3})?$/.test(text))throw Error('時刻は秒数、分:秒、時:分:秒（小数3桁まで）で入力してください。');
  const parts=text.split(':').map(Number);
  if(parts.slice(1).some(n=>n>=60))throw Error('時刻の分・秒は0〜59で入力してください。');
  const seconds=parts.reduce((n,p)=>n*60+p,0);
  if(!Number.isFinite(seconds)||seconds>3599999)throw Error('指定時刻が大きすぎます。');
  return seconds;
 },
 read(scope,url,validate=false){
  const $=id=>scope.getElementById(id),enabled=scope.querySelector('input[name="media"]:checked')?.value!=='thumbnail';
  const value={clipEnabled:enabled&&$('clipEnabled').checked,clipStart:$('clipStart').value,clipEnd:$('clipEnd').value,clipURL:url,normalizeEnabled:enabled&&$('normalizeEnabled').checked,targetLUFS:$('targetLUFS').value};
  if(validate&&value.clipEnabled){const start=this.parseTime(value.clipStart),end=this.parseTime(value.clipEnd,true);if(end!==null&&end<=start)throw Error('終了時刻は開始時刻より後にしてください。');}
  if(validate&&value.normalizeEnabled&&(!value.targetLUFS.trim()||!Number.isFinite(Number(value.targetLUFS))||Number(value.targetLUFS)<-40||Number(value.targetLUFS)>-5))throw Error('目標LUFSは-40〜-5の数値で入力してください。');
  return value;
 },
 update(scope,media){
  const $=id=>scope.getElementById(id);if(!$('clipEnabled'))return;
  const enabled=media!=='thumbnail';
  $('clipEnabled').disabled=!enabled;$('normalizeEnabled').disabled=!enabled;
  $('clipFields').hidden=!enabled||!$('clipEnabled').checked;
  $('normalizeFields').hidden=!enabled||!$('normalizeEnabled').checked;
  for(const id of ['clipStart','clipEnd','currentStart','currentEnd'])$(id).disabled=!enabled||!$('clipEnabled').checked;
  $('targetLUFS').disabled=!enabled||!$('normalizeEnabled').checked;
  $('editUnavailable').hidden=enabled;
 },
 mount(scope,stored,url,onChange,playback){
  const $=id=>scope.getElementById(id);
  $('editOptions').innerHTML=`<style>
   .edit-controls{margin-top:14px;color:#ccc;font-size:12px}.edit-controls summary{cursor:pointer}.edit-controls .edit-group{margin-top:12px}.edit-fields{margin:8px 0 0 22px}.edit-controls .edit-row{display:flex;align-items:center;gap:7px;margin-top:7px}.edit-controls .edit-row label{flex:0 0 30px}.edit-controls input[type=text]{width:120px}.edit-controls input[type=number]{width:82px}.edit-controls input[type=text],.edit-controls input[type=number]{font:inherit;background:#242424;color:#eee;border:1px solid #555;border-radius:5px;padding:6px;min-width:0}.edit-controls button{font-size:11px;padding:5px 7px}.edit-controls small{display:block;color:#aaa;font-size:11px;line-height:1.5;margin-top:6px}.edit-controls [hidden]{display:none!important}#editMessage{color:#f6c16c}
  </style><details class="edit-controls"><summary>切り出し・音量調整</summary>
  <div class="edit-group"><label><input type="checkbox" id="clipEnabled"> 指定した区間だけ保存</label>
   <div id="clipFields" class="edit-fields" hidden>
    <div class="edit-row"><label for="clipStart">開始</label><input id="clipStart" type="text" maxlength="24" placeholder="00:00:00" aria-label="開始時刻"><button id="currentStart" type="button">現在位置</button></div>
    <div class="edit-row"><label for="clipEnd">終了</label><input id="clipEnd" type="text" maxlength="24" placeholder="空欄なら末尾" aria-label="終了時刻"><button id="currentEnd" type="button">現在位置</button></div>
    <small>秒数・分:秒・時:分:秒で指定。小数3桁まで。MP4は指定位置に合わせて再圧縮。WAVは非圧縮で保存。リスト・複数動画は各動画に同じ区間を適用します。</small>
   </div>
  </div><div class="edit-group"><label><input type="checkbox" id="normalizeEnabled"> LUFSで音量をそろえる</label>
   <div id="normalizeFields" class="edit-fields" hidden><div class="edit-row"><label for="targetLUFS">目標</label><input id="targetLUFS" type="number" min="-40" max="-5" step="0.1" value="-15"><span>LUFS</span></div>
    <small>保存する区間の音量を測り、全体に同じゲインを適用。リミッターは使いません。ピーク上限 −1 dBTPを優先し、目標に届かない場合は結果に表示します。</small>
   </div>
  </div><small id="editUnavailable" hidden>サムネイルのみの保存では、切り出し・音量調整は適用しません。</small><small id="editMessage" aria-live="polite"></small></details>`;
  $('clipEnabled').checked=stored?.clipEnabled===true&&stored.clipURL===url;
  $('clipStart').value=stored?.clipURL===url?String(stored.clipStart??''):'';
  $('clipEnd').value=stored?.clipURL===url?String(stored.clipEnd??''):'';
  $('normalizeEnabled').checked=stored?.normalizeEnabled===true;
  const target=Number(stored?.targetLUFS??-15);$('targetLUFS').value=Number.isFinite(target)&&target>=-40&&target<=-5?String(target):'-15';
  const change=()=>{this.update(scope,scope.querySelector('input[name="media"]:checked')?.value);$('editMessage').textContent='';Promise.resolve(onChange()).catch(e=>{$('editMessage').textContent=e.message;});};
  for(const id of ['clipEnabled','clipStart','clipEnd','normalizeEnabled','targetLUFS'])$(id).onchange=change;
  for(const [id,targetId] of [['currentStart','clipStart'],['currentEnd','clipEnd']])$(id).onclick=async()=>{
   try{const seconds=await playback();if(typeof seconds!=='number'||!Number.isFinite(seconds)||seconds<0)throw Error('この動画の再生位置を取得できません。時刻を直接入力してください。');
    $(targetId).value=seconds.toFixed(3);change();
   }catch(e){$('editMessage').textContent=e.message;}
  };
  this.update(scope,scope.querySelector('input[name="media"]:checked')?.value);
 }
};
