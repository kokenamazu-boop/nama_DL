from pathlib import Path
import importlib.util,json,subprocess,threading,http.server,re,time,sys
# Run after installing yt-dlp, optionally with --hls. All traffic stays on localhost.
repo=Path(__file__).resolve().parents[1]
yt_spec=importlib.util.find_spec('yt_dlp')
if not yt_spec:raise SystemExit('Install yt-dlp in the test Python environment first.')
yt_root=str(Path(yt_spec.origin).parents[1])
hls='--hls' in sys.argv
spec=importlib.util.spec_from_file_location('partial_tests',repo/'tests/test_partial_download.py');tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests);tests.PartialMediaTests.setUpClass();host=tests.host;root=host.ROOT
requests=[];sent=[0]
class Handler(http.server.SimpleHTTPRequestHandler):
 def __init__(self,*a,**k):super().__init__(*a,directory=str(root),**k)
 def log_message(self,*args):pass
 def send_head(self):
  path=Path(self.translate_path(self.path))
  if not path.is_file():self.send_error(404);return None
  f=path.open('rb');size=path.stat().st_size;start=0;end=size-1
  match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers.get('Range',''))
  if match:start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
  if start> end:f.close();self.send_error(416);return None
  self.send_response(206 if match else 200);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
  if match:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers();f.seek(start);self.remaining=end-start+1;requests.append((path.name,start,end));return f
 def copyfile(self,f,out):
  while self.remaining:
   chunk=f.read(min(16384,self.remaining))
   if not chunk:break
   try:out.write(chunk)
   except (BrokenPipeError,ConnectionResetError):break
   sent[0]+=len(chunk);self.remaining-=len(chunk);time.sleep(.0005)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 long=root/'long.mp4';subprocess.run(['ffmpeg','-v','error','-stream_loop','4','-i',str(tests.PartialMediaTests.source),'-c','copy','-movflags','+faststart',str(long)],check=True)
 if hls:subprocess.run(['ffmpeg','-v','error','-i',str(long),'-c','copy','-hls_time','4','-hls_list_size','0','-hls_segment_filename',str(root/'segment%03d.ts'),str(root/'index.m3u8')],check=True)
 url=f'http://127.0.0.1:{server.server_port}/'+('index.m3u8' if hls else 'long.mp4');duration=float(host.probe(long)['format']['duration'])
 info={'id':'range-fixture','title':'range fixture','duration':duration,'webpage_url':url,'extractor':'generic','extractor_key':'Generic','formats':[{'format_id':'http','url':url,'ext':'mp4','protocol':'m3u8_native' if hls else 'http','vcodec':'avc1.64000b','acodec':'mp4a.40.2','width':320,'height':180}]}
 info_path=root/'info.json';info_path.write_text(json.dumps(info))
 shim=root/'bin/yt-dlp.exe';shim.write_text("#!/usr/bin/env python3\nimport sys\nsys.path.insert(0,"+repr(yt_root)+")\nfrom yt_dlp import main\nmain(['--load-info-json',"+repr(str(info_path))+"]+sys.argv[1:-2])\n");shim.chmod(0o755)
 messages=[]
 def send(kind,text,**extra):
  messages.append((kind,text))
  if kind in ('done','error') or '全体取得で再試行' in text:print(kind,text,flush=True)
 host.send=send
 original=host.partial_options
 def partial(source,data,record,options):
  print('Partial metadata:',{k:record.get(k) for k in ('duration','section_start','section_end')},'file',data['format'].get('start_time'),data['format'].get('duration'),flush=True)
  return original(source,data,record,options)
 host.partial_options=partial
 out=root/'output';out.mkdir();host.download({'url':url,'destination':str(out),'options':{'clipEnabled':True,'clipStart':'45.350','clipEnd':'47.750','normalizeEnabled':True,'targetLUFS':-20}})
 assert messages[-1][0]=='done',messages[-1]
 assert '部分取得 → 指定位置' in messages[-1][1],messages[-1]
 output=next(out.glob('*.mp4'));print('HTTP ranges:',requests,'transferred',sent[0],'full file',long.stat().st_size,'output duration',host.probe(output)['format']['duration'],flush=True)
 if hls:
  assert any(name.endswith('.ts') for name,_,_ in requests)
  assert len({name for name,_,_ in requests if name.endswith('.ts')})<len(list(root.glob('*.ts')))
 else:assert any(start>0 for _,start,end in requests)
 assert sent[0]<long.stat().st_size*.8
finally:
 server.shutdown();server.server_close();tests.PartialMediaTests.tearDownClass()
