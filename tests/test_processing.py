import array
import importlib.util
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

spec = importlib.util.spec_from_file_location('processing_host', Path(__file__).parents[1] / 'host/host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class OptionTests(unittest.TestCase):
    def test_encoded_peak_retry_reduces_only_the_fixed_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'output.mp4';calls=[]
            def encode(args,on_line):calls.append(list(args));output.write_bytes(b'fixture');return 0
            plan={'valid':True,'gain':3,'target':-15,'limited':False}
            args=['ffmpeg','-i','original.mp4','-af','volume=3dB:precision=double',str(output)]
            with patch.object(host,'run_process',encode),patch.object(host,'measure_loudness',side_effect=[{'i':-15,'tp':-.2},{'i':-15.85,'tp':-1.05}]):
                self.assertEqual(host.render_with_gain(args,output,lambda text:None,plan),0)
            self.assertEqual(len(calls),2)
            self.assertEqual([c[c.index('-i')+1] for c in calls],['original.mp4','original.mp4'])
            self.assertTrue(all(c[c.index('-af')+1].startswith('volume=') for c in calls))
            self.assertAlmostEqual(plan['gain'],2.15)

    def test_off_and_thumbnail_ignore_inactive_invalid_values(self):
        for media in ('video', 'audio', 'thumbnail'):
            value = {'media': media, 'clipStart': 'bad', 'clipEnd': 'bad', 'targetLUFS': 'bad'}
            if media == 'thumbnail':value.update(clipEnabled=True, normalizeEnabled=True)
            options = host.options_for(value)
            self.assertFalse(options['clipEnabled'])
            self.assertFalse(options['normalizeEnabled'])
        self.assertEqual(host.command('https://x.com/a/status/123'), host.command('https://x.com/a/status/123', options={'clipEnabled': False, 'normalizeEnabled': False, 'clipStart': 'bad', 'targetLUFS': 'bad'}))

    def test_time_validation_and_end_of_file(self):
        self.assertEqual(host.parse_time('01:02:03.125'), 3723.125)
        self.assertEqual(host.parse_time('01:20'), 80)
        for value in ('-1', 'nan', '00:60', '1:60:00', '1.2345', '1;exit', True):
            with self.assertRaises(ValueError):host.parse_time(value)
        for value in ('nan', float('inf'), -41, -4):
            with self.assertRaises(ValueError):host.options_for({'normalizeEnabled': True, 'targetLUFS': value})
        with self.assertRaises(ValueError):host.options_for({'clipEnabled': True, 'clipStart': '5', 'clipEnd': '4'})
        options = host.options_for({'clipEnabled': True, 'clipStart': '2', 'clipEnd': '20'})
        self.assertEqual(host.processing_window({'format': {'duration': '6'}}, options), {'start': 2, 'end': 6, 'duration': 4})
        with self.assertRaises(ValueError):host.processing_window({'format': {'duration': '1'}}, options)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and FFprobe required')
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='nama-DL-processing-test-')
        cls.root = Path(cls.tmp.name)
        (cls.root / 'bin').mkdir()
        for tool in ('ffmpeg', 'ffprobe'):(cls.root / 'bin' / (tool + '.exe')).symlink_to(shutil.which(tool))
        cls.old_root = host.ROOT
        host.ROOT = cls.root
        cls.source = cls.root / 'levels.wav'
        cls.spiky = cls.root / 'spiky.wav'
        cls.silent = cls.root / 'silent.wav'
        for path, spiky, silent in ((cls.source, False, False), (cls.spiky, True, False), (cls.silent, False, True)):
            pcm = bytearray()
            for n in range(48000 * 6):
                amplitude = (.025, .1, .04)[min(n // 96000, 2)]
                sample = amplitude * math.sin(2 * math.pi * 440 * n / 48000)
                if spiky:sample = .97 if n == 60001 else sample * .2
                if silent:sample = 0
                pcm += int(sample * 8388607).to_bytes(3, 'little', signed=True)
            with wave.open(str(path), 'wb') as f:
                f.setnchannels(1);f.setsampwidth(3);f.setframerate(48000);f.writeframes(pcm)
        cls.video = cls.root / 'video.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30:duration=6', '-i', str(cls.source), '-c:v', 'libx264', '-g', '120', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        host.ROOT = cls.old_root
        cls.tmp.cleanup()

    def setUp(self):
        host.cancel.clear()
        self.output = Path(tempfile.mkdtemp(dir=self.root))
        self.progress = []

    def convert_wav(self, source=None, **options):
        checked = {}
        with patch.object(host, 'send'):
            output = host.convert_audio(source or self.source, self.output, {'title': 'fixture'}, host.options_for({'media': 'audio', **options}), verified=checked)
        return output, checked

    def samples(self, path):
        data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-f', 'f64le', '-c:a', 'pcm_f64le', '-'])
        samples = array.array('d');samples.frombytes(data)
        return samples

    def test_wav_fixed_gain_preserves_waveform_and_reaches_target(self):
        original = self.samples(self.source)
        output, checked = self.convert_wav(normalizeEnabled=True, targetLUFS=-20)
        result = self.samples(output)
        before, after = host.measure_loudness(self.source), host.measure_loudness(output)
        self.assertAlmostEqual(after['i'], -20, delta=.15)
        gain = 10 ** ((after['i'] - before['i']) / 20)
        ratios = []
        for start in (10000, 110000, 210000):
            a = original[start:start+1000];b = result[start:start+1000]
            ratios.append(math.sqrt(sum(x*x for x in b) / sum(x*x for x in a)))
        self.assertLess(max(ratios) - min(ratios), .00001)
        self.assertAlmostEqual(ratios[0], gain, delta=.002)
        self.assertIn('固定ゲイン', checked['processing'])

    def test_peak_protection_uses_less_gain_without_limiter(self):
        output, checked = self.convert_wav(self.spiky, normalizeEnabled=True, targetLUFS=-8)
        measured = host.measure_loudness(output)
        self.assertLessEqual(measured['tp'], -.99)
        self.assertLess(measured['i'], -8 - 1)
        self.assertIn('目標LUFS未達', checked['processing'])
        a, b = self.samples(self.spiky), self.samples(output)
        factor = b[60001] / a[60001]
        self.assertLess(max(abs(b[i] - a[i]*factor) for i in range(1000, 10000)), .000001)

    def test_exact_wav_clip_and_clip_only_measurement(self):
        output, checked = self.convert_wav(clipEnabled=True, clipStart='2.350', clipEnd='5.150', normalizeEnabled=True, targetLUFS=-20)
        self.assertAlmostEqual(float(checked['format']['duration']), 2.8, delta=1/48000)
        original = self.samples(self.source)[112800:247200]
        actual = self.samples(output)
        self.assertEqual(len(original), len(actual))
        factor = actual[123] / original[123]
        self.assertLess(max(abs(actual[i] - original[i]*factor) for i in range(1000, 12000)), .000002)
        self.assertAlmostEqual(host.measure_loudness(output)['i'], -20, delta=.15)

    def test_precise_video_cut_between_keyframes_and_normalization(self):
        original = self.output / 'source.mkv';shutil.copy(self.video, original)
        checked = {}
        result = host.convert_file(original, self.progress.append, self.output, {'clipEnabled': True, 'clipStart': '2.350', 'clipEnd': '5.150', 'normalizeEnabled': True, 'targetLUFS': -20}, {'title': 'cut'}, verified=checked)
        self.assertAlmostEqual(float(checked['format']['duration']), 2.8, delta=.08)
        self.assertEqual([(s.get('width'), s.get('height')) for s in checked['streams'] if s['codec_type']=='video'], [(160, 90)])
        self.assertFalse(original.exists())
        first = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(result), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
        errors = []
        for n in (70, 71):
            reference = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(self.video), '-vf', f'select=eq(n\\,{n})', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
            errors.append(sum(abs(a-b) for a,b in zip(first, reference)) / len(first))
        self.assertLess(min(errors), 5)
        self.assertAlmostEqual(host.measure_loudness(result)['i'], -20, delta=.15)

    def test_off_skips_analysis_and_keeps_normal_wav_samples(self):
        with patch.object(host, 'measure_loudness', side_effect=AssertionError('OFF must not analyze')):
            result, checked = self.convert_wav(clipEnabled=False, clipStart='bad', normalizeEnabled=False, targetLUFS='bad')
        self.assertEqual(self.samples(result), self.samples(self.source))
        self.assertEqual(checked['processing'], '')

    def test_video_clip_only_skips_loudness_work(self):
        source=self.output/'clip-only.mkv';shutil.copy(self.video,source);checked={}
        with patch.object(host,'measure_loudness',side_effect=AssertionError('LUFS OFF must not analyze')):
            host.convert_file(source,self.progress.append,self.output,{'clipEnabled':True,'clipStart':'1.123','clipEnd':'3.456'},verified=checked)
        self.assertAlmostEqual(float(checked['format']['duration']),2.333,delta=.08)
        self.assertIn('切り出し',checked['processing'])
        self.assertNotIn('LUFS',checked['processing'])

    def test_loudness_only_copies_compatible_video(self):
        source=self.output/'normalization-only.mkv';shutil.copy(self.video,source);checked={}
        output=host.convert_file(source,self.progress.append,self.output,{'normalizeEnabled':True,'targetLUFS':-20},verified=checked)
        self.assertEqual(checked['save_mode'],'映像は再圧縮なし')
        def frame_hashes(path):
            data=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-f','framemd5','-']).decode()
            return [line.rsplit(',',1)[-1].strip() for line in data.splitlines() if not line.startswith('#')]
        self.assertEqual(frame_hashes(output),frame_hashes(self.video))
        self.assertLessEqual(host.measure_loudness(output)['tp'],-.99)

    def test_separate_audio_with_clip_cover_and_metadata(self):
        video=self.output/'separate.mp4'
        subprocess.run(['ffmpeg','-v','error','-i',str(self.video),'-map','0:v:0','-c','copy',str(video)],check=True)
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=32x32:color=blue','-frames:v','1','-threads','1',str(video.with_suffix('.png'))],check=True)
        checked={}
        host.convert_file(video,self.progress.append,self.output,{'clipEnabled':True,'clipStart':'2.350','clipEnd':'4.650','normalizeEnabled':True,'targetLUFS':-20,'embedThumbnail':True,'embedMetadata':True},{'title':'切り出しテスト','uploader':'Author'},audio_source=self.source,verified=checked)
        self.assertAlmostEqual(float(checked['format']['duration']),2.3,delta=.08)
        self.assertTrue(any(s.get('disposition',{}).get('attached_pic') for s in checked['streams']))
        self.assertEqual(checked['format']['tags']['title'],'切り出しテスト')

    def test_silence_and_failed_analysis_preserve_source(self):
        result, checked = self.convert_wav(self.silent, normalizeEnabled=True)
        self.assertEqual(self.samples(result), self.samples(self.silent))
        self.assertIn('音量変更なし', checked['processing'])
        original = self.output / 'keep.mkv';shutil.copy(self.video, original)
        for error in (RuntimeError('meter failed'), InterruptedError('cancelled')):
            with patch.object(host, 'measure_loudness', side_effect=error):
                with self.assertRaises(type(error)):host.convert_file(original, self.progress.append, self.output, {'normalizeEnabled': True})
            self.assertTrue(original.exists())
        self.assertFalse(list(self.output.glob('*.working.*')))


if __name__ == '__main__':unittest.main()
