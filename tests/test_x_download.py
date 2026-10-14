import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('native_host', Path(__file__).parents[1] / 'host/host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class XDownloadTests(unittest.TestCase):
    def test_x_does_not_truncate_multiple_videos(self):
        for media in ('video', 'audio', 'thumbnail'):
            args = host.command('https://x.com/author/status/123', options={'media': media})
            self.assertNotIn('--playlist-items', args)
            self.assertIn('--no-playlist', args)
        args = host.command('https://www.youtube.com/watch?v=abcdefghijk')
        self.assertEqual(args[args.index('--playlist-items') + 1], '1')

    def test_two_videos_save_separately_and_clean_their_own_intermediates(self):
        messages = []
        streams = [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080}]
        def acquire(args, on_line):
            stage = Path(args[args.index('-P') + 1])
            for index in (1, 2):
                directory = stage / str(index)
                directory.mkdir()
                source = directory / 'media_http.mp4'
                source.write_bytes(b'fixture')
                meta = {'id': str(index), 'title': f'Post #{index}', 'format_id': 'http'}
                on_line('VBMETA:' + json.dumps(meta))
                on_line('VBRESULT:' + json.dumps({**meta, 'filepath': str(source)}))
            return 0
        def convert(source, on_progress, target, options, info, audio, **kwargs):
            output = target / (info['title'] + '.mp4')
            output.write_bytes(source.read_bytes())
            kwargs['verified'].update(streams=streams, save_mode='再圧縮なし')
            return output
        with tempfile.TemporaryDirectory() as tmp, patch.object(host, 'run_process', acquire), patch.object(host, 'probe', return_value={'streams': streams}), patch.object(host, 'convert_file', convert), patch.object(host, 'send', side_effect=lambda *args, **kwargs: messages.append(args)):
            host.cancel.clear()
            host.download({'url': 'https://x.com/author/status/123', 'destination': tmp, 'options': {'media': 'video'}})
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['Post #1.mp4', 'Post #2.mp4'])
            self.assertEqual(messages[-1][0], 'done')
            self.assertIn('MP4保存: 2 件', messages[-1][1])


if __name__ == '__main__':
    unittest.main()
