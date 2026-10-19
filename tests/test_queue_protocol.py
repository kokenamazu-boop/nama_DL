"""Exercise framed native messages, cleanup ordering, IDs and cancellation in a real process."""
import json
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import unittest

HOST=Path(__file__).parents[1]/'host/host.py'
SCRIPT=r'''
import importlib.util,sys,time
spec=importlib.util.spec_from_file_location('host',sys.argv[1]);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def fixture(m):
    if m['url']=='exception':raise RuntimeError('fixture failure')
    h.send('progress','working')
    if m['url']=='slow':
        for _ in range(200):
            if h.cancel.is_set():h.send('cancelled','stopped');return
            time.sleep(.005)
    h.send('done','saved')
    # A terminal event must not escape while this cleanup is still running.
    time.sleep(.02)
h.download=h.inspect_quality=fixture
h.main()
'''
class NativeQueueTests(unittest.TestCase):
    def setUp(self):
        self.process=subprocess.Popen([sys.executable,'-u','-c',SCRIPT,str(HOST)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.messages=queue.Queue()
        def read():
            while True:
                size=self.process.stdout.read(4)
                if len(size)!=4:return
                self.messages.put(json.loads(self.process.stdout.read(struct.unpack('<I',size)[0])))
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
    def tearDown(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait();raise
        self.reader.join(timeout=2)
        error=self.process.stderr.read().decode();self.process.stdout.close();self.process.stderr.close()
        self.assertEqual(error,'')
    def send(self,m):
        data=json.dumps(m).encode();self.process.stdin.write(struct.pack('<I',len(data))+data);self.process.stdin.flush()
    def read(self):return self.messages.get(timeout=5)
    def test_30_immediate_next_jobs_have_no_loss_or_overlapping_cleanup(self):
        self.send({'action':'hello'});self.assertEqual(self.read()['version'],'1.13.0')
        for i in range(30):
            job=str(i);self.send({'action':'download','url':'normal','jobId':job})
            progress=self.read();self.assertEqual((progress['type'],progress['jobId']),('progress',job))
            end=self.read();self.assertEqual((end['type'],end['jobId']),('done',job))
    def test_cancel_matches_active_job_and_busy_rejection_uses_incoming_id(self):
        self.send({'action':'download','url':'slow','jobId':'first'});self.assertEqual(self.read()['type'],'progress')
        self.send({'action':'download','url':'normal','jobId':'second'})
        rejected=self.read();self.assertEqual((rejected['type'],rejected['jobId']),('error','second'))
        self.send({'action':'cancel','jobId':'stale'})
        self.send({'action':'hello'});self.assertEqual(self.read()['type'],'hello')
        self.send({'action':'cancel','jobId':'first'})
        cancelled=self.read();self.assertEqual((cancelled['type'],cancelled['jobId']),('cancelled','first'))
        self.send({'action':'inspect','url':'normal','jobId':'inspect'})
        self.assertEqual(self.read()['jobId'],'inspect');self.assertEqual(self.read()['type'],'done')
    def test_unexpected_exception_is_terminal_and_next_job_can_run(self):
        self.send({'action':'download','url':'exception','jobId':'bad'})
        result=self.read();self.assertEqual((result['type'],result['jobId']),('error','bad'))
        self.assertIn('fixture failure',result['text'])
        self.send({'action':'download','url':'normal','jobId':'good'})
        self.assertEqual(self.read()['type'],'progress');self.assertEqual(self.read()['jobId'],'good')

if __name__=='__main__':unittest.main()
