"""Real loopback HTTP tests with a temporary, synthetic-only workspace.

Binding restrictions fail explicitly; they are not counted as test passes.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1]
        # This is a normal sandboxed subprocess; do not change permissions to force a pass.
        cls.log=tempfile.TemporaryFile(mode='w+')
        cls.addClassCleanup(cls.log.close)
        cls.process=subprocess.Popen([sys.executable,'-u','-m','horizon','--port',str(cls.port),'--data-dir',cls.temp.name],cwd=ROOT,stdout=cls.log,stderr=cls.log,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        cls.addClassCleanup(cls.stop)
        ready=False
        for _ in range(100):
            if cls.process.poll() is not None:raise RuntimeError('Our test server exited before readiness.')
            cls.log.seek(0)
            # A startup line is printed only after this process successfully binds.
            if f'Horizon by walker512: http://127.0.0.1:{cls.port}' in cls.log.read():
                ready=True;break
            time.sleep(.05)
        if not ready:raise RuntimeError('Our test server did not become ready; no other instance is accepted.')
    @classmethod
    def stop(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
            try:cls.process.wait(timeout=5)
            except subprocess.TimeoutExpired:cls.process.kill();cls.process.wait(timeout=5)
    def request(self,method,path,body=None,headers=None):
        self.assertIsNone(self.process.poll())
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        try:
            conn.request(method,path,body=body,headers=headers or {})
            response=conn.getresponse();return response.status,dict(response.getheaders()),response.read()
        finally:conn.close()
    def test_root_headers(self):
        status,headers,body=self.request('GET','/')
        self.assertEqual(status,200);self.assertIn('Content-Security-Policy',headers);self.assertIn(b'Horizon',body)
    def test_bad_host(self):
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'example.org'})[0],403)
    def test_bad_origin(self):
        self.assertEqual(self.request('POST','/api/demo','{}',{'Content-Type':'application/json','Origin':'https://example.org'})[0],403)
    def test_wrong_content_type(self):
        self.assertEqual(self.request('POST','/api/demo','{}',{'Content-Type':'text/plain'})[0],415)
    def test_deep_json_controlled_error(self):
        status,_,body=self.request('POST','/api/claim','['*20000+'0'+']'*20000,{'Content-Type':'application/json'})
        self.assertEqual(status,400);self.assertIn(b'maximum depth',body);self.assertNotIn(b'Traceback',body)
        self.assertEqual(self.request('GET','/api/state')[0],200)
    def test_non_object(self):
        self.assertEqual(self.request('POST','/api/claim','[]',{'Content-Type':'application/json'})[0],400)
    def test_demo_and_exports(self):
        status,_,body=self.request('POST','/api/demo','{}',{'Content-Type':'application/json'})
        self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['sources']),3)
        for fmt in ['json','html','markdown']:
            status,headers,body=self.request('GET','/api/export?format='+fmt)
            self.assertEqual(status,200);self.assertIn('attachment',headers['Content-Disposition']);self.assertTrue(body)

if __name__=='__main__':unittest.main()
