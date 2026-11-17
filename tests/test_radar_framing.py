"""Actual HTTPResponse framing regressions, no outbound requests."""
import http.client,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from horizon import radar
BODY=json.dumps({'total_count':0,'incomplete_results':False,'items':[]}).encode()
def reply(headers,body=BODY):
 class Sock:
  def makefile(self,*args):return io.BytesIO(b'HTTP/1.1 200 OK\r\n'+headers+b'\r\n'+body)
 response=http.client.HTTPResponse(Sock());response.begin();return response
class Framing(unittest.TestCase):
 def fetch(self,response):
  with patch.object(radar.urllib.request,'build_opener') as factory:
   factory.return_value.open.return_value=response
   return radar.fetch('synthetic',1)
 def test_actual_early_eof_records_failure_after_success(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=radar.Radar(Path(tmp)/'workspace.sqlite3');qid=r.add('Synthetic','synthetic',1)
   self.assertEqual(r.collect(qid,lambda q,n:BODY)['status'],'observed')
   response=reply(b'Content-Length: '+str(len(BODY)+100).encode()+b'\r\n')
   with patch.object(radar.urllib.request,'build_opener') as factory:
    factory.return_value.open.return_value=response;result=r.collect(qid)
   self.assertEqual(result['status'],'failed');self.assertEqual(len(result['runs']),2);self.assertEqual(result['candidates'],[])
   with self.assertRaises(radar.RadarError):r.import_candidate(qid,1)
 def test_complete_content_length_chunked_and_close_delimited(self):
  self.assertEqual(self.fetch(reply(b'Content-Length: '+str(len(BODY)).encode()+b'\r\n')),BODY)
  encoded=(hex(len(BODY))[2:]+'\r\n').encode()+BODY+b'\r\n0\r\n\r\n'
  self.assertEqual(self.fetch(reply(b'Transfer-Encoding: chunked\r\n',encoded)),BODY)
  self.assertEqual(self.fetch(reply(b'')),BODY)
 def test_ambiguous_invalid_and_oversized_headers(self):
  for h in [b'Content-Length: 1\r\nContent-Length: 1\r\n',b'Content-Length: 1\r\nTransfer-Encoding: chunked\r\n',b'Content-Length: SECRET_SENTINEL\r\n',b'Content-Length: -1\r\n',b'Content-Length: 2097153\r\n',b'Transfer-Encoding: gzip\r\n',b'Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n']:
   with self.subTest(header=h):
    with self.assertRaises(radar.RadarError) as c:self.fetch(reply(h))
    self.assertNotIn('SECRET_SENTINEL',str(c.exception))
 def test_actual_truncated_chunk_does_not_echo_data(self):
  with self.assertRaises(radar.RadarError) as c:self.fetch(reply(b'Transfer-Encoding: chunked\r\n',b'100\r\nSECRET_SENTINEL'))
  self.assertNotIn('SECRET_SENTINEL',str(c.exception))
if __name__=='__main__':unittest.main()
