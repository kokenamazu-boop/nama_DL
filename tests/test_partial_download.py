import array
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('partial_host',Path(__file__).parents[1]/'host/host.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)


class PartialCommandTests(unittest.TestCase):
    def test_partial_is_stream_copy_with_original_timestamps_and_padding(self):
        args=host.command('https://x.com/a/status/123',options={'clipEnabled':True,'clipStart':'10.350','clipEnd':'12.750'},partial=True)
        self.assertEqual(args[args.index('--download-sections')+1],'*7.350-15.750')
        self.assertEqual(args[args.index('-f')+1],'bv*+ba/b')
        self.assertIn('--no-force-keyframes-at-cuts',args)
        self.assertEqual(args[args.index('--downloader-args')+1],'ffmpeg_o:-copyts -start_at_zero -avoid_negative_ts disabled -f nut')
        self.assertTrue(args[args.index('-o')+1].endswith('.nut'))
        default=host.command('https://x.com/a/status/123')
        self.assertNotIn('--download-sections',default)
        self.assertNotIn('--downloader-args',default)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class PartialMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='nama-partial-test-');cls.root=Path(cls.tmp.name)
        (cls.root/'bin').mkdir();cls.old_root=host.ROOT;host.ROOT=cls.root
        for tool in ('ffmpeg','ffprobe'):
            for name in (tool,tool+'.exe'):(cls.root/'bin'/name).symlink_to(shutil.which(tool))
        cls.source=cls.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=20','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=20','-c:v','libx264','-preset','fast','-crf','18','-g','120','-c:a','aac','-movflags','+faststart',str(cls.source)],check=True)

    @classmethod
    def tearDownClass(cls):host.ROOT=cls.old_root;cls.tmp.cleanup()

    def setUp(self):
        host.cancel.clear();self.out=Path(tempfile.mkdtemp(dir=self.root));self.messages=[];self.attempts=[];self.real=host.run_process

    def fake_download(self,behavior='ok',media='video',count=1):
        def run(args,on_line):
            if '-P' not in args:return self.real(args,on_line)
            partial='--download-sections' in args;self.attempts.append(partial)
            stage=Path(args[args.index('-P')+1])
            if partial and behavior in ('unsupported','cancel'):
                (stage/'unfinished.part').write_bytes(b'partial')
                if behavior=='cancel':raise InterruptedError('cancelled')
                on_line('ERROR: partial download unsupported');return 1
            if not partial and behavior=='both_fail':
                (stage/'unfinished.part').write_bytes(b'full');on_line('ERROR: full download failed');return 1
            for index in range(count):
                directory=stage/str(index+1);directory.mkdir()
                file=directory/('media.nut' if partial else 'media.mp4')
                if partial:
                    cmd=['ffmpeg','-v','error','-ss','6.350','-t','8.800','-i',str(self.source),'-c','copy','-copyts','-start_at_zero','-avoid_negative_ts','disabled']
                    if media=='audio':cmd+=['-vn']
                    subprocess.run(cmd+['-f','nut',str(file)],check=True)
                else:shutil.copy(self.source,file)
                info={'id':str(index+1),'title':f'fixture {index+1}','duration':20,'format_id':'http'}
                if partial:info.update(section_start=6.350,section_end=15.150)
                if partial and behavior in ('wrong_time','both_fail'):info['section_start']=0
                on_line('VBMETA:'+json.dumps(info));on_line('VBRESULT:'+json.dumps({**info,'filepath':str(file)}))
            return 0
        return run

    def job(self,behavior='ok',media='video',count=1,normalize=False):
        with patch.object(host,'run_process',self.fake_download(behavior,media,count)),patch.object(host,'send',side_effect=lambda *args,**kwargs:self.messages.append(args)):
            host.download({'url':'https://x.com/a/status/123','destination':str(self.out),'options':{'media':media,'clipEnabled':True,'clipStart':'9.350','clipEnd':'12.150','normalizeEnabled':normalize,'targetLUFS':-20}})

    def test_partial_video_matches_full_acquisition_at_same_position(self):
        self.job(normalize=True)
        self.assertEqual(self.attempts,[True]);self.assertEqual(self.messages[-1][0],'done',self.messages[-1])
        output=next(self.out.glob('*.mp4'));data=host.probe(output)
        self.assertAlmostEqual(float(data['format']['duration']),2.8,delta=.08)
        self.assertAlmostEqual(host.measure_loudness(output)['i'],-20,delta=.15)
        self.assertIn('9.350〜12.150',self.messages[-1][1]);self.assertIn('部分取得',self.messages[-1][1])
        reference_dir=self.root/'reference';reference_dir.mkdir(exist_ok=True)
        full=host.convert_file(self.source,lambda t:None,reference_dir,{'clipEnabled':True,'clipStart':'9.350','clipEnd':'12.150','normalizeEnabled':True,'targetLUFS':-20})
        def pixels(file):return subprocess.check_output(['ffmpeg','-v','error','-i',str(file),'-map','0:v:0','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        self.assertEqual(pixels(output),pixels(full))
        self.assertFalse((self.out/'.VideoButton-work').exists())

    def test_partial_wav_keeps_sample_count_and_position(self):
        self.job(media='audio');self.assertEqual(self.attempts,[True]);self.assertEqual(self.messages[-1][0],'done',self.messages[-1])
        output=next(self.out.glob('*.wav'));self.assertAlmostEqual(float(host.probe(output)['format']['duration']),2.8,delta=1/48000)
        reference_dir=self.root/'audio-reference';reference_dir.mkdir(exist_ok=True)
        with patch.object(host,'send'):full=host.convert_audio(self.source,reference_dir,{'title':'reference'},{'media':'audio','clipEnabled':True,'clipStart':'9.350','clipEnd':'12.150'})
        def samples(path):
            a=array.array('d');a.frombytes(subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-f','f64le','-c:a','pcm_f64le','-']));return a
        a,b=samples(output),samples(full);self.assertEqual(len(a),len(b));self.assertLess(math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a)),.0001)

    def test_non_h264_partial_source_is_saved_as_h264_aac(self):
        alternate=self.out/'vp9.webm'
        subprocess.run(['ffmpeg','-v','error','-i',str(self.source),'-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-g','120','-c:a','libopus',str(alternate)],check=True)
        self.source=alternate;self.job()
        self.assertEqual(self.attempts,[True]);self.assertEqual(self.messages[-1][0],'done',self.messages[-1])
        output=next(self.out.glob('*.mp4'));streams=host.probe(output)['streams']
        self.assertTrue(any(s.get('codec_name')=='h264' for s in streams))
        self.assertTrue(any(s.get('codec_name')=='aac' for s in streams))

    def test_unsupported_and_unverifiable_timestamps_fall_back_without_duplicates(self):
        for behavior in ('unsupported','wrong_time'):
            self.attempts=[];self.messages=[]
            self.out=Path(tempfile.mkdtemp(dir=self.root));self.job(behavior)
            self.assertEqual(self.attempts,[True,False]);self.assertEqual(self.messages[-1][0],'done',self.messages[-1])
            self.assertEqual(len(list(self.out.glob('*.mp4'))),1)
            self.assertIn('全体取得',self.messages[-1][1]);self.assertFalse((self.out/'.VideoButton-work').exists())

    def test_failed_second_conversion_does_not_publish_first_before_retry(self):
        real_convert=host.convert_file
        def convert(source,*args,**kwargs):
            if Path(source).suffix=='.nut' and Path(source).parent.name=='2':raise RuntimeError('partial decode failure')
            return real_convert(source,*args,**kwargs)
        with patch.object(host,'convert_file',convert):self.job(count=2)
        self.assertEqual(self.attempts,[True,False]);self.assertEqual(self.messages[-1][0],'done',self.messages[-1])
        self.assertEqual(sorted(p.name for p in self.out.glob('*.mp4')),['fixture 1.mp4','fixture 2.mp4'])

    def test_cancel_never_retries_and_both_failures_keep_work(self):
        self.job('cancel');self.assertEqual(self.attempts,[True]);self.assertEqual(self.messages[-1][0],'cancelled')
        self.attempts=[];self.messages=[];self.out=Path(tempfile.mkdtemp(dir=self.root));self.job('both_fail')
        self.assertEqual(self.attempts,[True,False]);self.assertEqual(self.messages[-1][0],'error')
        self.assertEqual(len(list((self.out/'.VideoButton-work').iterdir())),2)
        self.assertFalse(list(self.out.glob('*.mp4')))


if __name__=='__main__':unittest.main()
