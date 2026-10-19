import json, math, os, re, struct, subprocess, sys, threading, tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
OUT=Path(os.environ.get('USERPROFILE',str(Path.home())))/'Videos'/'VideoButton'
lock=threading.Lock()
job_lock=threading.Lock()
proc=None
cancel=threading.Event()
worker=None
picker=None
message_context=threading.local()
job_ready=threading.Event()
job_ready.set()

def send(kind,text,**extra):
    if getattr(message_context,'capture',False) and kind in ('done','error','cancelled'):
        message_context.terminal=(kind,text,extra);return
    job_id=getattr(message_context,'job_id',None)
    if job_id:extra={'jobId':job_id,**extra}
    data=json.dumps({'type':kind,'text':text,**extra},ensure_ascii=False).encode('utf-8')
    with lock:
        sys.stdout.buffer.write(struct.pack('<I',len(data))+data);sys.stdout.buffer.flush()

def read_exact(n):
    data=b''
    while len(data)<n:
        chunk=sys.stdin.buffer.read(n-len(data))
        if not chunk: raise EOFError
        data+=chunk
    return data

def validate_url(url):
    if not isinstance(url,str) or len(url)>16000: raise ValueError('URLが不正です')
    u=urlsplit(url)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password: raise ValueError('HTTP/HTTPSの動画URLが必要です')
    return u

def cookie_text(cookies,hostname):
    lines=['# Netscape HTTP Cookie File']
    for c in cookies:
        domain=str(c.get('domain',''));base=domain.lstrip('.')
        if not base or not (hostname==base or hostname.endswith('.'+base)):continue
        fields=[domain,'TRUE' if domain.startswith('.') else 'FALSE',str(c.get('path','/')),'TRUE' if c.get('secure') else 'FALSE',str(int(c.get('expirationDate',0))),str(c.get('name','')),str(c.get('value',''))]
        if any(any(x in f for x in '\r\n\t') for f in fields):continue
        lines.append('\t'.join(fields))
    return '\n'.join(lines)+'\n'

def destination_path(value=''):
    if not isinstance(value,str):raise ValueError('保存先が不正です')
    value=value.strip()
    path=Path(value) if value else OUT
    if not path.is_absolute():raise ValueError('保存先は絶対パスで指定してください')
    path.mkdir(parents=True,exist_ok=True)
    # Check permission before starting any network download.
    with tempfile.TemporaryFile(dir=path):pass
    return path

def options_for(value=None):
    value=value if isinstance(value,dict) else {}
    media=value.get('media') if value.get('media') in ('audio','thumbnail') else 'video'
    clip=media!='thumbnail' and value.get('clipEnabled') is True
    normalize=media!='thumbnail' and value.get('normalizeEnabled') is True
    start=parse_time(value.get('clipStart',0)) if clip else 0.0
    end=parse_time(value.get('clipEnd'),optional=True) if clip else None
    if clip and end is not None and end<=start:raise ValueError('終了時刻は開始時刻より後にしてください')
    target=-15.0
    if normalize:
        try:target=float(value.get('targetLUFS',-15))
        except (ValueError,TypeError):raise ValueError('目標LUFSは-40〜-5の数値で指定してください')
        if not math.isfinite(target) or not -40<=target<=-5:raise ValueError('目標LUFSは-40〜-5の数値で指定してください')
    return {'media':media,'embedThumbnail':media=='video' and bool(value.get('embedThumbnail')),'embedMetadata':media!='thumbnail' and bool(value.get('embedMetadata')),'clipEnabled':clip,'clipStart':start,'clipEnd':end,'normalizeEnabled':normalize,'targetLUFS':target}

def parse_time(value,optional=False):
    if value is None or value=='':
        if optional:return None
        return 0.0
    if isinstance(value,bool):raise ValueError('時刻は秒数、分:秒、時:分:秒で指定してください')
    text=str(value).strip()
    if len(text)>24 or not re.fullmatch(r'\d+(?::\d+){0,2}(?:\.\d{1,3})?',text):raise ValueError('時刻は秒数、分:秒、時:分:秒（小数3桁まで）で指定してください')
    parts=[float(part) for part in text.split(':')]
    if any(part>=60 for part in parts[1:]):raise ValueError('時刻の分・秒は0〜59で指定してください')
    result=0.0
    for part in parts:result=result*60+part
    if not math.isfinite(result) or result>3599999:raise ValueError('指定時刻が大きすぎます')
    return result

def processing_window(data,options):
    if not options['clipEnabled']:return None
    if data.get('_source_window'):return dict(data['_source_window'])
    duration=float(data.get('format',{}).get('duration') or 0)
    if not math.isfinite(duration) or duration<=0:raise ValueError('動画・音声の長さを確認できないため切り出せません')
    start=options['clipStart'];end=min(options['clipEnd'] if options['clipEnd'] is not None else duration,duration)
    if start>=end:raise ValueError('開始時刻が動画・音声の末尾以降です。時刻を確認してください')
    return {'start':start,'end':end,'duration':end-start}

def media_input(path,window=None):
    # Transcoding with accurate_seek discards frames/samples before the requested time.
    return (['-seek_timestamp','1'] if window and window.get('absolute') else [])+(['-ss',f"{window['start']:.3f}"] if window and (window['start'] or window.get('absolute')) else [])+['-i',str(path)]

def window_output(window):
    return ['-t',f"{window['duration']:.3f}"] if window else []

def measure_loudness(source,window=None,sample_rate=None):
    # loudnorm is used ONLY as a meter. The rendered audio uses volume=fixed gain.
    filters=(f'aresample={sample_rate},' if sample_rate else '')+'loudnorm=I=-15:TP=-1:LRA=50:print_format=json'
    args=[str(ROOT/'bin'/'ffmpeg.exe'),'-hide_banner','-nostdin']+media_input(source,window)+window_output(window)+['-map','0:a:0','-vn','-sn','-dn','-af',filters,'-f','null','-']
    logs=[]
    def line(text):
        logs.append(text)
        if len(logs)>45:logs.pop(0)
    code=run_process(args,line)
    text='\n'.join(logs)
    if code:raise RuntimeError('LUFSの測定に失敗しました。元ファイルは残します。\n'+text[-2000:])
    match=re.search(r'\{\s*"input_i".*?\}',text,re.S)
    if not match:raise RuntimeError('LUFSの測定結果を取得できませんでした。元ファイルは残します。')
    result=json.loads(match.group())
    return {'i':float(result['input_i']),'tp':float(result['input_tp'])}

def normalization_plan(source,window,options,progress,sample_rate=None):
    if not options['normalizeEnabled']:return None
    progress('音量を解析中…（曲中の強弱を変えず、全体に同じゲインを適用します）')
    measured=measure_loudness(source,window,sample_rate)
    valid=math.isfinite(measured['i']) and math.isfinite(measured['tp'])
    requested=options['targetLUFS']-measured['i'] if valid else 0.0
    gain=min(requested,-1.0-measured['tp']) if valid else 0.0
    return {'input':measured,'target':options['targetLUFS'],'gain':gain,'valid':valid,'limited':valid and gain<requested-.01}

def gain_filter(plan):
    return f"volume={plan['gain']:.6f}dB:precision=double"

def render_with_gain(args,temp,on_line,plan=None):
    if not plan or not plan['valid']:return run_process(args,on_line)
    # Verify the encoded output as AAC encoding can introduce new true peaks.
    # A retry re-renders from the ORIGINAL input with less fixed gain, never a limiter.
    for attempt in range(3):
        command=list(args);command[command.index('-af')+1]=gain_filter(plan)
        code=run_process(command,on_line)
        if code:return code
        measured=measure_loudness(temp);plan['output']=measured
        if not math.isfinite(measured['i']) or not math.isfinite(measured['tp']):raise RuntimeError('保存後の音量を確認できませんでした。元ファイルは残します。')
        peak_excess=measured['tp']+1.0
        loudness_excess=measured['i']-plan['target']
        if peak_excess<=.01 and loudness_excess<=.15:return 0
        if attempt==2:raise RuntimeError('固定ゲインでの音量確認に失敗しました。元ファイルは残します。')
        correction=max(peak_excess+.05 if peak_excess>.01 else 0,loudness_excess if loudness_excess>.15 else 0)
        plan['gain']-=correction;plan['limited']=True
        temp.unlink(missing_ok=True)
    raise RuntimeError('音量の確認に失敗しました')

def processing_summary(window,plan):
    parts=[]
    if window:parts.append(f"切り出し: {window['start']:.3f}〜{window['end']:.3f}秒（{window['duration']:.3f}秒）")
    if plan:
        if not plan['valid']:parts.append('LUFS: 無音・短い音声等で測定できないため音量変更なし')
        else:
            after=plan['output'];parts.append(f"LUFS: {plan['input']['i']:.2f} → {after['i']:.2f} / 目標 {plan['target']:.2f} / 固定ゲイン {plan['gain']:+.2f} dB / True Peak {after['tp']:.2f} dBTP")
            if plan['limited'] and after['i']<plan['target']-.15:parts.append('ピーク上限を優先したため目標LUFS未達（強弱は維持・リミッターなし）')
    return '\n'.join(parts)

def command(url,cookie=None,playlist=False,destination=None,options=None,partial=False):
    o=options_for(options)
    # Short internal filenames avoid Windows/FFmpeg path limits. Final names use the title.
    template=('%(playlist_id|Playlist).40B/' if playlist else '')+'%(id)s/media_%(format_id).40B.%(ext)s'
    if partial:template=template.replace('.%(ext)s','.nut')
    args=[str(ROOT/'bin'/'yt-dlp.exe'),'--ignore-config','--no-plugin-dirs','--newline','--encoding','utf-8','--no-color','--windows-filenames','--no-overwrites','--socket-timeout','30','--retries','10','--fragment-retries','10','--concurrent-fragments','4','--fixup','never','--ffmpeg-location',str(ROOT/'bin'),'--js-runtimes','deno:'+str(ROOT/'bin'/'deno.exe'),'-P',str(destination if destination is not None else OUT),'-o',template,'--no-simulate','--no-write-playlist-metafiles']
    fields='id,title,width,height,format_id,uploader,artist,channel,upload_date,description,webpage_url'
    if partial:fields+=',duration,section_start,section_end'
    args+=['--print','before_dl:VBMETA:%(.{'+fields+'})j']
    if o['media']=='thumbnail':args+=['--skip-download','--write-thumbnail','--ignore-no-formats-error']
    elif o['media']=='audio':args+=['-f','ba/b']
    else:args+=['-f','bv*+ba/b' if partial else 'bv*,ba/b','--format-sort-force','-S','res,fps,br','--print','before_dl:画質: %(resolution)s / %(format_id)s']
    if o['media']!='thumbnail':args+=['--print','after_move:VBRESULT:%(.{filepath,'+fields+'})j']
    if o['embedThumbnail']:args+=['--write-thumbnail']
    if partial:
        args[args.index('--retries')+1]='2';args[args.index('--fragment-retries')+1]='2'
        start=max(0,o['clipStart']-3)
        end=f"{o['clipEnd']+3:.3f}" if o['clipEnd'] is not None else 'inf'
        args+=['--download-sections',f'*{start:.3f}-{end}','--no-force-keyframes-at-cuts','--downloader-args','ffmpeg_o:-copyts -start_at_zero -avoid_negative_ts disabled -f nut']
        args+=['--downloader-args','ffmpeg_i:-rw_timeout 15000000']
    if playlist:args+=['--yes-playlist','--no-abort-on-error']
    # X may return several videos in one post. Keep them all, without treating a profile as a playlist.
    elif urlsplit(url).hostname in ('x.com','www.x.com','twitter.com','www.twitter.com'):args+=['--no-playlist','--no-abort-on-error']
    else:args+=['--no-playlist','--playlist-items','1']
    if cookie:args+=['--cookies',str(cookie)]
    return args+['--',url]

def partial_options(source,data,record,options):
    # The FFmpeg downloader preserves the original, zero-based media timeline.
    # NUT preserves stream time bases, including sub-millisecond audio timestamps.
    try:
        duration=float(record['duration']);section_start=float(record['section_start']);section_end=float(record['section_end'])
        origin=float(data['format']['start_time'])
    except (KeyError,TypeError,ValueError):raise ValueError('部分取得したデータの元動画上の時刻を確認できません')
    if not all(math.isfinite(n) for n in (duration,section_start,section_end,origin)) or duration<=0:raise ValueError('部分取得の時刻情報が不正です')
    start=options['clipStart'];end=min(options['clipEnd'] if options['clipEnd'] is not None else duration,duration)
    requested_start=max(0,start-3);requested_end=min(options['clipEnd']+3 if options['clipEnd'] is not None else duration,duration)
    if start>=end:raise ValueError('開始時刻が動画・音声の末尾以降です')
    if abs(section_start-requested_start)>.01 or abs(section_end-requested_end)>.1:raise ValueError('部分取得の範囲が指定内容と一致しません')
    if data['format'].get('format_name')!='nut':raise ValueError('部分取得の時刻保持形式を確認できません')
    streams={int(s['index']):s for s in data['streams'] if s.get('codec_type') in ('audio','video') and not s.get('disposition',{}).get('attached_pic')}
    bounds={}
    def line(text):
        fields=dict(part.split('=',1) for part in text.split('|') if '=' in part)
        try:index=int(fields['stream_index']);pts=float(fields['pts_time'])
        except (KeyError,ValueError):return
        try:span=float(fields.get('duration_time',0))
        except ValueError:span=0.0
        if index not in streams or not math.isfinite(pts) or not math.isfinite(span):return
        low,high=bounds.get(index,(pts,pts));bounds[index]=(min(low,pts),max(high,pts+span))
    code=run_process([str(ROOT/'bin'/'ffprobe.exe'),'-v','error','-show_entries','packet=stream_index,pts_time,duration_time','-of','compact=p=0:nk=0',str(source)],line)
    if code or not streams or set(bounds)!=set(streams):raise ValueError('部分取得した映像・音声の時刻を確認できません')
    for index,stream in streams.items():
        low,high=bounds[index]
        tolerance=.05
        if stream['codec_type']=='video':
            from fractions import Fraction
            try:rate=float(Fraction(stream.get('r_frame_rate') or '0'));tolerance=max(.05,1/rate+.01) if rate>0 else .1
            except (ValueError,ZeroDivisionError):tolerance=.1
        if low>start+tolerance or high<end-tolerance:raise ValueError('部分取得したデータに必要な区間が含まれていません')
    if origin>start+.05:raise ValueError('部分取得したデータの開始時刻を確認できません')
    window={'start':start,'end':end,'duration':end-start}
    data['_source_window']={**window,'absolute':True}
    return options,window


def unique_path(path):
    candidate=path;index=2
    while candidate.exists():
        candidate=path.with_name(path.stem+f' ({index})'+path.suffix);index+=1
    return candidate


def stop():
    cancel.set()
    with job_lock:
        p=proc
        if p and p.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000)
            else:p.kill()


def run_process(args, on_line):
    global proc
    with job_lock:
        if cancel.is_set():raise InterruptedError('中止しました')
        proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,encoding='utf-8',errors='replace',creationflags=0x08000000 if os.name=='nt' else 0)
        current=proc
    try:
        for line in current.stdout:
            if line.strip():on_line(line.strip())
        code=current.wait()
        if cancel.is_set():raise InterruptedError('中止しました')
        return code
    finally:
        current.stdout.close()
        with job_lock:proc=None

def probe(path):
    data=[]
    code=run_process([str(ROOT/'bin'/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(path)],data.append)
    if code:raise RuntimeError('動画情報を読み取れません: '+path.name)
    return json.loads('\n'.join(data))

def delete_mkv(source,original_stat):
    for attempt in range(6):
        if cancel.is_set():raise InterruptedError('中止しました。MKVは残します。')
        current=source.stat()
        if (current.st_size,current.st_mtime_ns)!=(original_stat.st_size,original_stat.st_mtime_ns):raise RuntimeError('元MKVが変更されたため削除しませんでした。MP4は保存済みです。')
        try:source.unlink();return
        except PermissionError as e:
            if attempt==5:raise RuntimeError('MP4は保存済みですがMKVを削除できません。動画プレイヤーやエクスプローラーのプレビューを閉じてください。対象: '+str(source)+' / '+str(e))
            cancel.wait(0.4)

def title_name(title, directory):
    import re
    text=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(title)).rstrip(' .') or 'video'
    if text.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:text='_'+text
    limit=max(20, min(180,230-len(str(directory.resolve()))))
    text=text.encode('utf-8')[:limit].decode('utf-8',errors='ignore').rstrip(' .')
    return text or 'video'

def thumbnail_path(source):
    candidates=[source.with_suffix(ext) for ext in ('.png','.jpg','.jpeg','.webp')]
    candidates+=[p for p in source.parent.iterdir() if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
    return next((p for p in candidates if p.is_file()),source.with_suffix('.png'))

def png_image(source):
    source=Path(source)
    if not source.is_file():raise RuntimeError('サムネイル画像が見つかりません')
    if source.suffix.lower()=='.png':return source
    output=source.with_name(source.stem+'.converted.png')
    logs=[]
    code=run_process([str(ROOT/'bin'/'ffmpeg.exe'),'-v','error','-nostdin','-y','-i',str(source),'-frames:v','1',str(output)],logs.append)
    if code:raise RuntimeError('サムネイルPNG変換失敗: '+'\n'.join(logs[-10:]))
    if not output.is_file():raise RuntimeError('PNG変換後のファイルが見つかりません')
    return output

def tag_values(meta):
    return {key:str(value)[:2000].replace(chr(0),'') for key,value in {'title':meta.get('title'),'artist':meta.get('artist') or meta.get('uploader') or meta.get('channel'),'date':meta.get('upload_date'),'description':meta.get('description'),'comment':meta.get('webpage_url')}.items() if value is not None}


def metadata_for(source,record=None):
    if isinstance(record,dict) and record.get('title'):return record
    candidates=list(source.parent.glob('*.info.json'))
    if len(candidates)==1:
        try:
            data=json.loads(candidates[0].read_text(encoding='utf-8'))
            if isinstance(data,dict):return data
        except (OSError,json.JSONDecodeError):pass
    return record if isinstance(record,dict) else {}

def can_copy_video(source,video):
    # Only pass AE-compatible SDR H.264 through. Scan timestamps without decoding:
    # equal average/r_frame_rate alone does not prove a video is constant-rate.
    if video.get('codec_name')!='h264' or video.get('pix_fmt')!='yuv420p':return False
    if not video.get('width') or not video.get('height') or video['width']%2 or video['height']%2:return False
    if video.get('color_transfer') in ('smpte2084','arib-std-b67') or video.get('field_order') not in (None,'unknown','progressive'):return False
    from fractions import Fraction
    import heapq,re
    try:
        rate=Fraction(video.get('r_frame_rate') or '0')
        timebase=Fraction(video.get('time_base') or '0')
        if not 0<rate<=240 or timebase<=0:return False
        step=float(1/rate/timebase)
        if step<1:return False
    except (ValueError,ZeroDivisionError,TypeError):return False
    pending=[];previous=None;count=0;valid=True
    def take():
        nonlocal previous,count,valid
        pts=heapq.heappop(pending)
        if previous is not None and (pts<=previous or abs(pts-previous-step)>1.01):valid=False
        previous=pts;count+=1
    def line(text):
        nonlocal valid
        match=re.search(r'(?:^|\|)pts=(-?\d+)(?:\||$)',text)
        if not match:
            if text.startswith('pts='):valid=False
            return
        heapq.heappush(pending,int(match[1]))
        # H.264 packets may arrive in decode order. A bounded reorder buffer
        # handles B-frames without retaining every timestamp of a long playlist.
        if len(pending)>64:take()
    code=run_process([str(ROOT/'bin'/'ffprobe.exe'),'-v','error','-select_streams',str(video['index']),'-show_entries','packet=pts','-of','compact=p=0:nk=0',str(source)],line)
    while pending:take()
    return code==0 and valid and count>=2

def can_copy_audio(audio):
    return bool(audio and audio.get('codec_name')=='aac' and audio.get('profile')=='LC' and audio.get('channels') in (1,2) and 32000<=int(audio.get('sample_rate') or 0)<=96000)

def convert_file(source, progress, output_dir=None, options=None, record=None, audio_source=None, source_info=None, audio_info=None, verified=None):
    source=Path(source).resolve()
    if not source.is_file():raise ValueError('ファイルが見つかりません: '+str(source))
    o=options_for(options)
    target=Path(output_dir) if output_dir is not None else source.parent
    target.mkdir(parents=True,exist_ok=True)
    output=unique_path(target/(title_name((record or {}).get('title') or source.stem,target)+'.mp4'))
    thumb=thumbnail_path(source)
    metadata={}
    if o['embedThumbnail'] and thumb.is_file():thumb=png_image(thumb)
    if o['embedThumbnail'] and not thumb.is_file():raise RuntimeError('サムネイルを取得できないため埋め込めません。元動画は残します。')
    if o['embedMetadata']:
        meta=metadata_for(source,record)
        if not meta:raise RuntimeError('メタデータ情報を取得できません。元動画は残します。')
        metadata=tag_values(meta)
    original_stat=source.stat()
    data=source_info if source_info is not None else probe(source)
    video=next((x for x in data['streams'] if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),None)
    if not video:raise ValueError('映像トラックがありません: '+source.name)
    window=processing_window(data,o)
    vf='pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'
    if video.get('color_transfer') in ('smpte2084','arib-std-b67'):
        vf='zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,'+vf
        progress('HDR → SDR に色変換: '+source.name)
    progress('高速保存の可否を確認中: '+source.name)
    copy_video=False if window else can_copy_video(source,video)
    if audio_source:
        audio_info=audio_info if audio_info is not None else probe(audio_source)
    audio=next((x for x in (audio_info if audio_source else data).get('streams',[]) if x.get('codec_type')=='audio'),None)
    normalization=normalization_plan(audio_source or source,window,o,progress,48000) if audio else None
    copy_audio=can_copy_audio(audio) and not window and not normalization
    # Unique temporary name; never replace the source or an existing completed output.
    import uuid
    temp=target/(uuid.uuid4().hex+'.working.mp4')
    errors=[]
    def line(text):
        errors.append(text)
        if len(errors)>12:errors.pop(0)
        if text.startswith('out_time='):progress(('MP4高速保存中: ' if copy_video else 'MP4変換中: ')+source.name+'\n処理済み時間: '+text.split('=',1)[1])
    try:
        modes=[(copy_video,copy_audio)]
        if copy_video or copy_audio:modes.append((False,False))
        for attempt,(copy_video,copy_audio) in enumerate(modes):
            args=[str(ROOT/'bin'/'ffmpeg.exe'),'-hide_banner','-nostdin','-n']+media_input(source,window)
            if audio_source:args+=media_input(audio_source,window)
            if o['embedThumbnail']:args+=['-i',str(thumb)]
            args+=window_output(window)
            args+=['-map','0:'+str(video['index']),'-map',('1:a:0' if audio_source else '0:a:0?')]
            if o['embedThumbnail']:args+=['-map',('2:v:0' if audio_source else '1:v:0')]
            args+=['-map_metadata','-1','-sn','-dn']
            if copy_video:args+=['-c:v:0','copy']
            else:args+=['-filter:v:0',vf,'-c:v:0','libx264','-preset:v:0','fast','-crf:v:0','16','-pix_fmt:v:0','yuv420p','-fps_mode:v:0','cfr']
            if copy_audio:args+=['-c:a','copy']
            else:args+=['-c:a','aac','-b:a','320k','-ar','48000']
            if normalization and normalization['valid']:args+=['-af',gain_filter(normalization)]
            if o['embedThumbnail']:args+=['-c:v:1','copy','-disposition:v:1','attached_pic']
            for key,value in metadata.items():args+=['-metadata',key+'='+value]
            args+=['-movflags','+faststart','-progress','pipe:1','-nostats',str(temp)]
            progress(('映像は再圧縮なしでMP4へ保存' if copy_video else '映像をH.264へ高品質変換')+(' / 音声は再圧縮なし' if copy_audio else '')+'\n'+source.name)
            errors.clear()
            try:
                code=render_with_gain(args,temp,line,normalization)
                if code or not temp.exists() or temp.stat().st_size==0:raise RuntimeError('MP4変換失敗: '+source.name+'\n'+'\n'.join(errors))
                checked=probe(temp)
                result_video=next((x for x in checked.get('streams',[]) if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),None)
                if not result_video or result_video.get('codec_name')!='h264':raise RuntimeError('MP4の映像確認に失敗しました。MKVは残します。')
                if (result_video.get('width'),result_video.get('height'))!=((video['width']+1)//2*2,(video['height']+1)//2*2):raise RuntimeError('MP4の解像度が取得した映像と一致しません。元動画は残します。')
                if (audio_source or audio) and not any(x.get('codec_type')=='audio' and x.get('codec_name')=='aac' for x in checked['streams']):raise RuntimeError('MP4の音声確認に失敗しました。MKVは残します。')
                if o['embedThumbnail'] and not any(x.get('disposition',{}).get('attached_pic') for x in checked['streams']):raise RuntimeError('サムネイル埋め込みの確認に失敗しました。元MKVは残します。')
                if metadata.get('title') and checked.get('format',{}).get('tags',{}).get('title')!=metadata['title']:raise RuntimeError('メタデータ埋め込みの確認に失敗しました。元MKVは残します。')
                before=window['duration'] if window else float(data.get('format',{}).get('duration') or 0)
                after=float(checked.get('format',{}).get('duration') or 0)
                tolerance=.15 if window else max(1.0,before*0.01)
                if after<=0 or (before>0 and abs(before-after)>tolerance):raise RuntimeError('MP4の長さが保存範囲と一致しません。元動画は残します。')
                break
            except InterruptedError:raise
            except Exception:
                if attempt==len(modes)-1:raise
                temp.unlink(missing_ok=True)
                progress('高速保存を完了できなかったため、高品質変換で再試行します。')
        if output.exists():raise RuntimeError('同名MP4が作成されたため上書きを中止しました')
        if cancel.is_set():raise InterruptedError('中止しました')
        temp.rename(output)
        details=processing_summary(window,normalization)
        if o['normalizeEnabled'] and not audio:details+=('\n' if details else '')+'音声トラックがないため音量調整なし'
        if details:progress(details)
        if verified is not None:verified.update(checked,save_mode='映像・音声は再圧縮なし' if copy_video and copy_audio else '映像は再圧縮なし' if copy_video else 'H.264へ高品質変換',processing=details)
        if source.suffix.lower()=='.mkv':
            if cancel.is_set():raise InterruptedError('中止しました。MKVは残します。')
            current=source.stat()
            if (current.st_size,current.st_mtime_ns)!=(original_stat.st_size,original_stat.st_mtime_ns):raise RuntimeError('変換中に元MKVが変更されたため削除しませんでした。MP4は保存済みです。')
            delete_mkv(source,original_stat)
            progress('MP4確認完了・元MKVを削除: '+source.name)
        return output
    finally:temp.unlink(missing_ok=True)

def convert_audio(source,target,record,options,verified=None,source_info=None):
    import uuid
    options=options_for(options)
    window=processing_window(source_info if source_info is not None else probe(source),options) if options['clipEnabled'] else None
    normalization=normalization_plan(source,window,options,lambda text:send('progress',text))
    output=unique_path(target/(title_name(record.get('title') or source.stem,target)+'.wav'))
    temp=target/(uuid.uuid4().hex+'.working.wav')
    args=[str(ROOT/'bin'/'ffmpeg.exe'),'-v','error','-nostdin','-n']+media_input(source,window)+window_output(window)+['-map','0:a:0','-vn','-c:a','pcm_s24le','-rf64','auto','-map_metadata','-1']
    if normalization and normalization['valid']:args+=['-af',gain_filter(normalization)]
    if options['embedMetadata']:
        for k,v in tag_values(record).items():args+=['-metadata',k+'='+v]
    args+=[str(temp)];logs=[]
    try:
        code=render_with_gain(args,temp,logs.append,normalization)
        if code:raise RuntimeError('WAV変換失敗: '+'\n'.join(logs[-10:]))
        checked=probe(temp)
        if not any(x.get('codec_name')=='pcm_s24le' for x in checked['streams']):raise RuntimeError('WAVの確認に失敗しました')
        if window and abs(float(checked.get('format',{}).get('duration') or 0)-window['duration'])>.005:raise RuntimeError('WAVの長さが指定区間と一致しません。元音声は残します。')
        if cancel.is_set():raise InterruptedError('中止しました')
        if output.exists():raise RuntimeError('同名WAVが作成されたため上書きを中止しました')
        if verified is not None:verified.update(checked,processing=processing_summary(window,normalization))
        temp.rename(output);return output
    finally:temp.unlink(missing_ok=True)

def inspect_command(url,cookie=None):
    args=[str(ROOT/'bin'/'yt-dlp.exe'),'--ignore-config','--no-plugin-dirs','--encoding','utf-8','--no-color','--socket-timeout','30','--retries','3','--no-playlist','--playlist-items','1','--simulate','--dump-single-json','-f','bv*+ba/b','--format-sort-force','-S','res,fps,br','--ffmpeg-location',str(ROOT/'bin'),'--js-runtimes','deno:'+str(ROOT/'bin'/'deno.exe')]
    if cookie:args+=['--cookies',str(cookie)]
    return args+['--',url]

def quality_summary(info):
    formats=info.get('formats') or []
    heights=sorted({int(f['height']) for f in formats if isinstance(f.get('height'),(int,float)) and f.get('vcodec')!='none'})
    selected=info.get('height')
    text='取得候補: '+(', '.join(str(h)+'p' for h in heights) or '解像度情報なし')+'\n選択画質: '+str(info.get('width') or '?')+'×'+str(selected or '?')+' / '+str(info.get('format_id') or '?')
    if heights and selected and selected<max(heights):text+='\n注意: 選択画質が最大候補より低くなっています。'
    if heights and max(heights)<=720:text+='\n1080p以上の候補は返されていません。ブラウザーで1080pを再生できる場合は、ログイン状態とyt-dlpの更新を確認してください。'
    return text

def inspect_quality(m):
    result=('error','画質確認に失敗しました')
    try:
        u=validate_url(m.get('url'))
        with tempfile.TemporaryDirectory(prefix='nama_DL-check-') as tmp:
            cookie=None
            if m.get('cookies'):
                cookie=Path(tmp)/'cookies.txt';cookie.write_text(cookie_text(m['cookies'],u.hostname),encoding='utf-8')
            records=[];errors=[]
            def line(text):
                if text.startswith('{'):
                    try:records.append(json.loads(text));return
                    except json.JSONDecodeError:pass
                if text.startswith('ERROR:'):errors.append(text)
            version=[];run_process([str(ROOT/'bin'/'yt-dlp.exe'),'--version'],version.append)
            send('progress','画質候補を確認中…（動画は保存しません）')
            code=run_process(inspect_command(m['url'],cookie),line)
            if code or not records:raise RuntimeError('画質情報を取得できませんでした。'+('\n'+'\n'.join(errors[-3:]) if errors else ''))
            info=records[0]
            if info.get('entries'):info=next((x for x in info['entries'] if x),{})
            has_session=any(c.get('name')=='user_session' and c.get('value') for c in m.get('cookies',[]))
            login_note='\nニコニコのログインCookie: '+('あり（有効性・会員種別は未確認）' if has_session else 'なし') if u.hostname=='nicovideo.jp' or u.hostname.endswith('.nicovideo.jp') else ''
            result=('done','画質確認結果\nyt-dlp: '+(version[0] if version else '不明')+login_note+'\n'+quality_summary(info))
    except InterruptedError:result=('cancelled','画質確認を中止しました')
    except Exception as e:result=('error',str(e))
    send(*result)

def _download_attempt(m,partial=False):
    result=('error','処理が完了しませんでした')
    stage=None;published=False
    try:
        import uuid
        u=validate_url(m.get('url'));destination=destination_path(m.get('destination',''))
        o=options_for(m.get('options'));playlist=bool(m.get('playlist'))
        stage=destination/'.VideoButton-work'/uuid.uuid4().hex
        stage.mkdir(parents=True)
        files=[];tail=[];download_errors=[];expected=set();records={};item_meta={}
        with tempfile.TemporaryDirectory(prefix='VideoButton-') as tmp:
            cookie=None
            if m.get('cookies'):
                cookie=Path(tmp)/'cookies.txt';cookie.write_text(cookie_text(m['cookies'],u.hostname),encoding='utf-8')
            def line(text):
                if text.startswith('VBMETA:'):
                    record=json.loads(text[7:]);item_meta[str(record.get('id'))]=record
                elif text.startswith('VBEXPECT:'):expected.add(json.loads(text[9:]))
                elif text.startswith('VBRESULT:'):
                    record=json.loads(text[9:]);file=record.get('filepath')
                    if isinstance(file,str):
                        records[file]=record
                        if file not in files:files.append(file)
                elif text.startswith('VBFILE:'):
                    file=json.loads(text[7:])
                    if file not in files:files.append(file)
                else:
                    tail.append(text)
                    if len(tail)>8:tail.pop(0)
                    if text.startswith('ERROR:'):download_errors.append(text)
                    send('progress','取得中（取得済み '+str(len(files))+' 件）\n'+'\n'.join(tail))
            if partial:send('progress','指定区間の前後だけを取得中…（対応できない場合は全体取得で再試行します）')
            code=run_process(command(m['url'],cookie,playlist,stage,o,partial=partial),line)
        if o['media']=='thumbnail':
            files=[str(p) for p in sorted(stage.rglob('*')) if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
            if len(files)<len(item_meta):download_errors.append(f'サムネイルを取得できない項目があります（対象 {len(item_meta)} / 画像取得 {len(files)}）')
        groups={}
        for file in files:groups.setdefault(str(Path(file).parent),[]).append(file)
        prepared={};pending=[]
        if partial:
            if code not in (0,101) or download_errors or not files:raise RuntimeError('部分取得を完了できませんでした。\n'+'\n'.join((download_errors+tail)[-5:]))
            for directory,group in groups.items():
                if len(group)!=1:raise ValueError('部分取得した映像・音声を一つの時刻軸で確認できません')
                source=Path(group[0]).resolve()
                if not source.is_relative_to(stage.resolve()):raise ValueError('部分取得ファイルの保存場所が一致しません')
                data=probe(source);info=item_meta.get(source.parent.name) or records.get(group[0]) or {}
                local_options,source_window=partial_options(source,data,info,o)
                prepared[directory]=(data,local_options,source_window)
        converted=0;failed=[];deleted=0;quality_results=[];processing_results=[]
        for i,(directory,group) in enumerate(groups.items(),1):
            if cancel.is_set():raise InterruptedError('中止しました')
            source=Path(group[0]).resolve()
            if not source.is_relative_to(stage.resolve()):raise RuntimeError('取得ファイルの保存場所が一致しません')
            final_target=destination/source.parent.parent.name if playlist else destination
            target=stage/'ready'/str(i) if partial else final_target
            target.mkdir(parents=True,exist_ok=True)
            prefix=f'保存処理 {i}/{len(groups)}\n'
            info=item_meta.get(source.parent.name) or records.get(group[0]) or {'title':source.stem,'id':source.parent.name}
            try:
                checked={}
                if o['media']=='thumbnail':
                    png=png_image(source);output=unique_path(target/(title_name(info.get('title') or source.stem,target)+'.png'))
                    checked=probe(png)
                    if not any(x.get('codec_name')=='png' for x in checked['streams']):raise RuntimeError('PNG画像の確認に失敗しました')
                    png.rename(output)
                else:
                    inputs=[(source,prepared[directory][0])] if partial else [(Path(file).resolve(),probe(Path(file))) for file in group]
                    local_options=prepared[directory][1] if partial else o
                    if o['media']=='audio':
                        source=next((path for path,data in inputs if any(x.get('codec_type')=='audio' for x in data['streams'])),None)
                        if source is None:raise RuntimeError('音声トラックを取得できませんでした')
                        output=convert_audio(source,target,info,local_options,verified=checked,source_info=inputs[0][1] if partial else None)
                    else:
                        videos=[(path,data) for path,data in inputs if any(x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic') for x in data['streams'])]
                        if not videos:raise RuntimeError('映像トラックを取得できませんでした')
                        source,data=videos[0]
                        audio_pair=next(((path,d) for path,d in inputs if path!=source and any(x.get('codec_type')=='audio' for x in d['streams']) and not any(x.get('codec_type')=='video' for x in d['streams'])),None)
                        audio=audio_pair[0] if audio_pair else None
                        v=next(x for x in data['streams'] if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic'))
                        info={**info,'width':v.get('width'),'height':v.get('height'),'format_id':'+'.join(str(records.get(file,{}).get('format_id') or Path(file).stem) for file in group)}
                        send('progress',prefix+quality_summary(info))
                        output=convert_file(source,lambda t:send('progress',prefix+t),target,local_options,info,audio,source_info=data,audio_info=audio_pair[1] if audio_pair else None,verified=checked)
                        video=next((x for x in checked['streams'] if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),{})
                        quality_results.append(str(info.get('id'))+': 取得 '+str(info.get('width'))+'×'+str(info.get('height'))+' → MP4 '+str(video.get('width'))+'×'+str(video.get('height'))+' / '+checked['save_mode'])
                if partial:
                    window=prepared[directory][2]
                    details=checked.get('processing','').split('\n')
                    if details and details[0].startswith('切り出し:'):details[0]=processing_summary(window,None)
                    checked['processing']='\n'.join(details)+'\n取得方式: 部分取得 → 指定位置で切り出し'
                    pending.append((output,final_target,info.get('title') or source.stem))
                if checked.get('processing'):processing_results.append(str(info.get('title') or info.get('id'))+'\n'+checked['processing'])
                converted+=1
                deleted+=sum(1 for file in group if Path(file).suffix.lower()=='.mkv' and not Path(file).exists())
                # Delete only intermediates in this isolated task directory after verifying the final file.
                for auxiliary in Path(directory).iterdir():
                    if auxiliary.is_file():
                        if auxiliary.suffix.lower()=='.mkv':deleted+=1
                        auxiliary.unlink()
            except InterruptedError:raise
            except Exception as e:failed.append('処理: '+o['media']+' / '+str(info.get('title') or source.name)+'\n'+str(e))
        text=f"{'PNG' if o['media']=='thumbnail' else 'WAV' if o['media']=='audio' else 'MP4'}保存: {converted} 件 / 取得ファイル: {len(files)} 件\nMKV削除: {deleted} 件\n保存先: {destination}"
        if quality_results:text+='\n画質確認:\n'+'\n'.join(quality_results[-10:])
        if processing_results:text+='\n切り出し・音量調整:\n'+'\n'.join(processing_results[-10:])
        if failed or download_errors or code not in (0,101):
            result=('error','一部または全部の処理に失敗しました。\n'+text+'\n'+'\n'.join((download_errors+failed+tail)[-12:])+'\n途中ファイル: '+str(stage))
        elif not files:result=('error','取得ファイルがありません。URLを確認してください。\n'+'\n'.join(tail))
        else:
            if partial:
                # Do not publish any partial-attempt output before ALL items verify.
                # This makes a whole-download retry safe even for playlists.
                for output,final_target,title in pending:
                    if cancel.is_set():raise InterruptedError('中止しました')
                    final_target.mkdir(parents=True,exist_ok=True)
                    final_output=unique_path(final_target/(title_name(title,final_target)+output.suffix))
                    output.rename(final_output);published=True
            result=('done','完了\n'+text)
    except InterruptedError:result=('cancelled','中止しました。完了済みファイルは残っています。途中ファイル: '+str(stage))
    except Exception as e:result=('error',str(e))
    finally:
        # Remove only empty task directories; failed downloads remain recoverable.
        if stage and stage.exists():
            for directory in sorted((p for p in stage.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                try:directory.rmdir()
                except OSError:pass
            try:stage.rmdir();stage.parent.rmdir()
            except OSError:pass
    return result,stage,published

def download(m):
    try:partial=options_for(m.get('options'))['clipEnabled']
    except Exception as e:send('error',str(e));return
    result,stage,published=_download_attempt(m,partial=partial)
    if partial and result[0]=='error' and not published and not cancel.is_set():
        send('progress','部分取得を確認できなかったため、全体取得で再試行します。\n'+result[1].split('\n')[0])
        first_stage=stage
        result,stage,_=_download_attempt(m)
        if result[0]=='done':
            if first_stage and first_stage.exists():
                import shutil
                try:shutil.rmtree(first_stage);first_stage.parent.rmdir()
                except OSError:pass
            result=(result[0],result[1]+'\n取得方式: 全体取得（部分取得に対応できなかったため）')
        elif first_stage and first_stage.exists():result=(result[0],result[1]+'\n部分取得の途中ファイル: '+str(first_stage))
    send(*result)

def choose_folder(initial):
    try:
        if os.name!='nt':raise RuntimeError('Windowsでのみ使用できます')
        env=os.environ.copy();env['VIDEOBUTTON_FOLDER']=str(initial or OUT)
        result=subprocess.run(['powershell.exe','-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',str(ROOT/'pick_folder.ps1')],capture_output=True,encoding='utf-8-sig',errors='replace',env=env,creationflags=0x08000000,timeout=600)
        if result.returncode:raise RuntimeError(result.stderr.strip() or 'フォルダー選択を開けませんでした')
        data=json.loads(result.stdout)
        if data.get('path'):send('folderSelected','保存先を設定しました',path=str(destination_path(data['path'])))
        else:send('folderNotice','フォルダー選択をキャンセルしました。保存先は変更していません。')
    except Exception as e:send('folderNotice',str(e))

def run_job(m):
    # Buffer the terminal message until processing and cleanup have returned.
    # The main reader joins this finished worker before accepting the next job.
    message_context.job_id=m.get('jobId')
    message_context.capture=True
    message_context.terminal=None
    try:
        (inspect_quality if m.get('action')=='inspect' else download)(m)
    except Exception as e:
        message_context.terminal=('error',str(e),{})
    finally:
        message_context.capture=False
        job_ready.set()
        kind,text,extra=message_context.terminal or ('error','処理結果を確認できませんでした',{})
        send(kind,text,**extra)


def main():
    global worker,picker
    worker_job=None
    if os.name=='nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(),os.O_BINARY);msvcrt.setmode(sys.stdout.fileno(),os.O_BINARY)
    try:
        while True:
            size=struct.unpack('<I',read_exact(4))[0]
            if size>2*1024*1024:break
            m=json.loads(read_exact(size))
            if m.get('action')=='hello':send('hello','',version='1.13.0')
            elif m.get('action')=='chooseFolder':
                if picker and picker.is_alive():send('folderNotice','フォルダー選択画面はすでに開いています。')
                else:
                    picker=threading.Thread(target=choose_folder,args=(m.get('destination',''),),daemon=True);picker.start()
            elif m.get('action') in ('download','inspect'):
                if worker and worker.is_alive():
                    if not job_ready.is_set():send('error','別の処理を実行中です',jobId=m.get('jobId'));continue
                    worker.join()
                cancel.clear();job_ready.clear();worker_job=m.get('jobId')
                worker=threading.Thread(target=run_job,args=(m,));worker.start()
            elif m.get('action')=='cancel':
                if not m.get('jobId') or m.get('jobId')==worker_job:stop()
            elif m.get('action')=='folder':
                try:os.startfile(destination_path(m.get('destination','')))
                except Exception as e:send('notice','保存先を開けません: '+str(e))
    except (EOFError,BrokenPipeError):pass
    finally:
        stop()
        if worker:worker.join(timeout=10)
if __name__=='__main__':
    if sys.argv[1:2]==['--convert']:
        errors=0
        for file in sys.argv[2:]:
            try:print('保存先: '+str(convert_file(file,lambda text:print(text,flush=True))),flush=True)
            except Exception as e:errors+=1;print(str(e),flush=True)
        sys.exit(1 if errors else 0)
    else:main()
