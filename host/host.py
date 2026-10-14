import json, os, struct, subprocess, sys, threading, tempfile
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

def send(kind,text,**extra):
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
    return {'media':media,'embedThumbnail':media=='video' and bool(value.get('embedThumbnail')),'embedMetadata':media!='thumbnail' and bool(value.get('embedMetadata'))}

def command(url,cookie=None,playlist=False,destination=None,options=None):
    o=options_for(options)
    # Short internal filenames avoid Windows/FFmpeg path limits. Final names use the title.
    template=('%(playlist_id|Playlist).40B/' if playlist else '')+'%(id)s/media_%(format_id).40B.%(ext)s'
    args=[str(ROOT/'bin'/'yt-dlp.exe'),'--ignore-config','--no-plugin-dirs','--newline','--encoding','utf-8','--no-color','--windows-filenames','--no-overwrites','--socket-timeout','30','--retries','10','--fragment-retries','10','--concurrent-fragments','4','--fixup','never','--ffmpeg-location',str(ROOT/'bin'),'--js-runtimes','deno:'+str(ROOT/'bin'/'deno.exe'),'-P',str(destination if destination is not None else OUT),'-o',template,'--no-simulate','--no-write-playlist-metafiles']
    fields='id,title,width,height,format_id,uploader,artist,channel,upload_date,description,webpage_url'
    args+=['--print','before_dl:VBMETA:%(.{'+fields+'})j']
    if o['media']=='thumbnail':args+=['--skip-download','--write-thumbnail','--ignore-no-formats-error']
    elif o['media']=='audio':args+=['-f','ba/b']
    else:args+=['-f','bv*,ba/b','--format-sort-force','-S','res,fps,br','--print','before_dl:画質: %(resolution)s / %(format_id)s']
    if o['media']!='thumbnail':args+=['--print','after_move:VBRESULT:%(.{filepath,'+fields+'})j']
    if o['embedThumbnail']:args+=['--write-thumbnail']
    if playlist:args+=['--yes-playlist','--no-abort-on-error']
    # X may return several videos in one post. Keep them all, without treating a profile as a playlist.
    elif urlsplit(url).hostname in ('x.com','www.x.com','twitter.com','www.twitter.com'):args+=['--no-playlist','--no-abort-on-error']
    else:args+=['--no-playlist','--playlist-items','1']
    if cookie:args+=['--cookies',str(cookie)]
    return args+['--',url]


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
    vf='pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p'
    if video.get('color_transfer') in ('smpte2084','arib-std-b67'):
        vf='zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,'+vf
        progress('HDR → SDR に色変換: '+source.name)
    progress('高速保存の可否を確認中: '+source.name)
    copy_video=can_copy_video(source,video)
    if audio_source:
        audio_info=audio_info if audio_info is not None else probe(audio_source)
    audio=next((x for x in (audio_info if audio_source else data).get('streams',[]) if x.get('codec_type')=='audio'),None)
    copy_audio=can_copy_audio(audio)
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
            args=[str(ROOT/'bin'/'ffmpeg.exe'),'-hide_banner','-nostdin','-n','-i',str(source)]
            if audio_source:args+=['-i',str(audio_source)]
            if o['embedThumbnail']:args+=['-i',str(thumb)]
            args+=['-map','0:'+str(video['index']),'-map',('1:a:0' if audio_source else '0:a:0?')]
            if o['embedThumbnail']:args+=['-map',('2:v:0' if audio_source else '1:v:0')]
            args+=['-map_metadata','-1','-sn','-dn']
            if copy_video:args+=['-c:v:0','copy']
            else:args+=['-filter:v:0',vf,'-c:v:0','libx264','-preset:v:0','fast','-crf:v:0','16','-pix_fmt:v:0','yuv420p','-fps_mode:v:0','cfr']
            if copy_audio:args+=['-c:a','copy']
            else:args+=['-c:a','aac','-b:a','320k','-ar','48000']
            if o['embedThumbnail']:args+=['-c:v:1','copy','-disposition:v:1','attached_pic']
            for key,value in metadata.items():args+=['-metadata',key+'='+value]
            args+=['-movflags','+faststart','-progress','pipe:1','-nostats',str(temp)]
            progress(('映像は再圧縮なしでMP4へ保存' if copy_video else '映像をH.264へ高品質変換')+(' / 音声は再圧縮なし' if copy_audio else '')+'\n'+source.name)
            errors.clear()
            try:
                code=run_process(args,line)
                if code or not temp.exists() or temp.stat().st_size==0:raise RuntimeError('MP4変換失敗: '+source.name+'\n'+'\n'.join(errors))
                checked=probe(temp)
                result_video=next((x for x in checked.get('streams',[]) if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),None)
                if not result_video or result_video.get('codec_name')!='h264':raise RuntimeError('MP4の映像確認に失敗しました。MKVは残します。')
                if (result_video.get('width'),result_video.get('height'))!=((video['width']+1)//2*2,(video['height']+1)//2*2):raise RuntimeError('MP4の解像度が取得した映像と一致しません。元動画は残します。')
                if (audio_source or audio) and not any(x.get('codec_type')=='audio' and x.get('codec_name')=='aac' for x in checked['streams']):raise RuntimeError('MP4の音声確認に失敗しました。MKVは残します。')
                if o['embedThumbnail'] and not any(x.get('disposition',{}).get('attached_pic') for x in checked['streams']):raise RuntimeError('サムネイル埋め込みの確認に失敗しました。元MKVは残します。')
                if metadata.get('title') and checked.get('format',{}).get('tags',{}).get('title')!=metadata['title']:raise RuntimeError('メタデータ埋め込みの確認に失敗しました。元MKVは残します。')
                before=float(data.get('format',{}).get('duration') or 0)
                after=float(checked.get('format',{}).get('duration') or 0)
                if after<=0 or (before>0 and abs(before-after)>max(1.0,before*0.01)):raise RuntimeError('MP4の長さが元動画と一致しません。MKVは残します。')
                break
            except InterruptedError:raise
            except Exception:
                if attempt==len(modes)-1:raise
                temp.unlink(missing_ok=True)
                progress('高速保存を完了できなかったため、高品質変換で再試行します。')
        if output.exists():raise RuntimeError('同名MP4が作成されたため上書きを中止しました')
        if cancel.is_set():raise InterruptedError('中止しました')
        temp.rename(output)
        if verified is not None:verified.update(checked,save_mode='映像・音声は再圧縮なし' if copy_video and copy_audio else '映像は再圧縮なし' if copy_video else 'H.264へ高品質変換')
        if source.suffix.lower()=='.mkv':
            if cancel.is_set():raise InterruptedError('中止しました。MKVは残します。')
            current=source.stat()
            if (current.st_size,current.st_mtime_ns)!=(original_stat.st_size,original_stat.st_mtime_ns):raise RuntimeError('変換中に元MKVが変更されたため削除しませんでした。MP4は保存済みです。')
            delete_mkv(source,original_stat)
            progress('MP4確認完了・元MKVを削除: '+source.name)
        return output
    finally:temp.unlink(missing_ok=True)

def convert_audio(source,target,record,options):
    import uuid
    output=unique_path(target/(title_name(record.get('title') or source.stem,target)+'.wav'))
    temp=target/(uuid.uuid4().hex+'.working.wav')
    args=[str(ROOT/'bin'/'ffmpeg.exe'),'-v','error','-nostdin','-n','-i',str(source),'-map','0:a:0','-vn','-c:a','pcm_s24le','-rf64','auto','-map_metadata','-1']
    if options['embedMetadata']:
        for k,v in tag_values(record).items():args+=['-metadata',k+'='+v]
    args+=[str(temp)];logs=[]
    try:
        code=run_process(args,logs.append)
        if code:raise RuntimeError('WAV変換失敗: '+'\n'.join(logs[-10:]))
        checked=probe(temp)
        if not any(x.get('codec_name')=='pcm_s24le' for x in checked['streams']):raise RuntimeError('WAVの確認に失敗しました')
        if cancel.is_set():raise InterruptedError('中止しました')
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

def download(m):
    result=('error','処理が完了しませんでした')
    stage=None
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
            code=run_process(command(m['url'],cookie,playlist,stage,o),line)
        if o['media']=='thumbnail':
            files=[str(p) for p in sorted(stage.rglob('*')) if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
            if len(files)<len(item_meta):download_errors.append(f'サムネイルを取得できない項目があります（対象 {len(item_meta)} / 画像取得 {len(files)}）')
        groups={}
        for file in files:groups.setdefault(str(Path(file).parent),[]).append(file)
        converted=0;failed=[];deleted=0;quality_results=[]
        for i,(directory,group) in enumerate(groups.items(),1):
            if cancel.is_set():raise InterruptedError('中止しました')
            source=Path(group[0]).resolve()
            if not source.is_relative_to(stage.resolve()):raise RuntimeError('取得ファイルの保存場所が一致しません')
            target=destination/source.parent.parent.name if playlist else destination
            target.mkdir(parents=True,exist_ok=True)
            prefix=f'保存処理 {i}/{len(groups)}\n'
            info=item_meta.get(source.parent.name) or records.get(group[0]) or {'title':source.stem,'id':source.parent.name}
            try:
                if o['media']=='thumbnail':
                    png=png_image(source);output=unique_path(target/(title_name(info.get('title') or source.stem,target)+'.png'))
                    checked=probe(png)
                    if not any(x.get('codec_name')=='png' for x in checked['streams']):raise RuntimeError('PNG画像の確認に失敗しました')
                    png.rename(output)
                else:
                    inputs=[(Path(file).resolve(),probe(Path(file))) for file in group]
                    if o['media']=='audio':
                        source=next((path for path,data in inputs if any(x.get('codec_type')=='audio' for x in data['streams'])),None)
                        if source is None:raise RuntimeError('音声トラックを取得できませんでした')
                        output=convert_audio(source,target,info,o)
                    else:
                        videos=[(path,data) for path,data in inputs if any(x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic') for x in data['streams'])]
                        if not videos:raise RuntimeError('映像トラックを取得できませんでした')
                        source,data=videos[0]
                        audio_pair=next(((path,d) for path,d in inputs if path!=source and any(x.get('codec_type')=='audio' for x in d['streams']) and not any(x.get('codec_type')=='video' for x in d['streams'])),None)
                        audio=audio_pair[0] if audio_pair else None
                        v=next(x for x in data['streams'] if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic'))
                        info={**info,'width':v.get('width'),'height':v.get('height'),'format_id':'+'.join(str(records.get(file,{}).get('format_id') or Path(file).stem) for file in group)}
                        send('progress',prefix+quality_summary(info))
                        checked={}
                        output=convert_file(source,lambda t:send('progress',prefix+t),target,o,info,audio,source_info=data,audio_info=audio_pair[1] if audio_pair else None,verified=checked)
                        video=next((x for x in checked['streams'] if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),{})
                        quality_results.append(str(info.get('id'))+': 取得 '+str(info.get('width'))+'×'+str(info.get('height'))+' → MP4 '+str(video.get('width'))+'×'+str(video.get('height'))+' / '+checked['save_mode'])
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
        if failed or download_errors or code not in (0,101):
            result=('error','一部または全部の処理に失敗しました。\n'+text+'\n'+'\n'.join((download_errors+failed+tail)[-12:])+'\n途中ファイル: '+str(stage))
        elif not files:result=('error','取得ファイルがありません。URLを確認してください。\n'+'\n'.join(tail))
        else:result=('done','完了\n'+text)
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

def main():
    global worker,picker
    if os.name=='nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(),os.O_BINARY);msvcrt.setmode(sys.stdout.fileno(),os.O_BINARY)
    try:
        while True:
            size=struct.unpack('<I',read_exact(4))[0]
            if size>2*1024*1024:break
            m=json.loads(read_exact(size))
            if m.get('action')=='hello':send('hello','',version='1.11.0')
            elif m.get('action')=='chooseFolder':
                if picker and picker.is_alive():send('folderNotice','フォルダー選択画面はすでに開いています。')
                else:
                    picker=threading.Thread(target=choose_folder,args=(m.get('destination',''),),daemon=True);picker.start()
            elif m.get('action') in ('download','inspect'):
                if worker and worker.is_alive():send('progress','ダウンロード中です');continue
                cancel.clear();worker=threading.Thread(target=inspect_quality if m.get('action')=='inspect' else download,args=(m,));worker.start()
            elif m.get('action')=='cancel':stop()
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
