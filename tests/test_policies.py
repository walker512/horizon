"""Synthetic policy pages only. No tests fetch external services."""
import hashlib,http.client,io,json,subprocess,sys,tempfile,unittest,urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from horizon.policies import CATALOGUE,LIMIT,Policies,PolicyError,extract,fetch
from horizon.watch import Watch
from horizon.backup import backup,restore
ROOT=Path(__file__).resolve().parents[1]
def page(text='Exports allowed.'):
    return ('<!doctype html><html><nav>Outside</nav><main><h1>Usage policies</h1><p>'+text+' A synthetic course policy for exercises only. These are original synthetic sentences, not an actual vendor policy.</p><script>SECRET SCRIPT</script><footer>Footer</footer></main></html>').encode()
class Response:
    def __init__(self,data,status=200,ctype='text/html; charset=utf-8',url=None):
        self.data=data;self.status=status;self.headers=Message();self.headers['Content-Type']=ctype;self.url=url or CATALOGUE['openai-usage']['url']
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):r=self.data[:n];self.data=self.data[n:];return r
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.x=Policies(self.p/'db'/'workspace.sqlite3')
    def collect(self,data=None):
        with patch('horizon.policies.fetch',return_value=data if data is not None else page()):return self.x.collect('openai-usage',True)
    def approve(self):
        self.collect();s=self.x.store.state()['sources'][0]['latest'];self.x.store.apply('claim',{'text':'Exports allowed.'});cid=self.x.store.state()['claims'][0]['id'];self.x.store.apply('evidence',{'claim_id':cid,'snapshot_id':s['id'],'quote':'Exports allowed.','relation':'supports'});self.x.store.apply('review',{'claim_id':cid,'decision':'approve'});return cid
    def test_extract(self):
        s=extract(page(),'usage policies');self.assertIn('Exports allowed.',s)
        for x in ('Outside','SECRET SCRIPT','Footer'):self.assertNotIn(x,s)
    def test_static_constraints(self):
        for raw in (b'login',page().replace(b'</main>',b''),page()+b'<main></main>',page().replace(b'Usage policies',b'Challenge'),b'<main><h1>Usage policies</h1>x</main>',b'\xff',page()+b'\x00',b'x'*(LIMIT+1),b'<div>'*129+page()+b'</div>'*129):
            with self.assertRaises(PolicyError):extract(raw,'usage policies')
    def test_entity_normalization(self):self.assertIn('One & two',extract(page('One &amp; two'),'usage policies'))
    def test_explicit_permission(self):
        with patch('horizon.policies.fetch') as f:
            for val in (False,None,1,'true'):
                with self.assertRaises(PolicyError):self.x.collect('openai-usage',val)
            f.assert_not_called()
    def test_unknown_destination(self):
        with patch('horizon.policies.fetch') as f:
            for x in ('https://localhost/',{},None):
                with self.assertRaises(PolicyError):self.x.collect(x,True)
            f.assert_not_called()
    def test_first_unchanged(self):
        a=self.collect();b=self.collect();self.assertEqual(a['result'],'first_observation');self.assertEqual(b['result'],'unchanged');self.assertFalse(b['new_version']);self.assertEqual(a['raw_response_sha256'],hashlib.sha256(page()).hexdigest());self.assertEqual(a['availability'],'summary')
    def test_change_invalidation_and_no_revival(self):
        self.approve();r=self.collect(page('Exports restricted.'));self.assertEqual(r['result'],'changed');self.assertEqual(self.x.store.state()['claims'][0]['status'],'needs-review');self.collect();self.assertEqual(self.x.store.state()['claims'][0]['status'],'needs-review')
    def test_unchanged_preserves_approval(self):self.approve();self.collect();self.assertEqual(self.x.store.state()['claims'][0]['status'],'editor-approved')
    def test_failure_recovery(self):
        self.approve()
        with patch('horizon.policies.fetch',side_effect=PolicyError('SECRET')):r=self.x.collect('openai-usage',True)
        self.assertEqual(r['result'],'unavailable');w=Watch(self.p/'db'/'workspace.sqlite3');self.assertEqual(w.changes(r['source_id'])['diff_status'],'unavailable_not_deletion');self.assertNotIn('SECRET',json.dumps(self.x.store.portable()));self.assertEqual(self.collect()['result'],'recovered');self.assertEqual(self.x.store.state()['claims'][0]['status'],'needs-review')
    def test_unsupported_page_failed(self):self.assertEqual(self.collect(b'Challenge')['result'],'unavailable')
    def test_changed_report(self):
        r=self.collect();self.collect(page('Exports restricted.'));w=Watch(self.p/'db'/'workspace.sqlite3');d=w.changes(r['source_id']);self.assertEqual(d['diff_status'],'text_changed');self.assertTrue(d['diff'])
    def test_transaction_rollback(self):
        self.collect();before=self.x.store.portable()['tables']
        with patch.object(self.x.store,'log',side_effect=ValueError('quota')):
            with self.assertRaises(ValueError):self.collect(page('Changed policy.'))
        self.assertEqual(before,self.x.store.portable()['tables'])
    def test_fetch_exact(self):
        with patch('horizon.policies.urllib.request.build_opener') as build:
            build.return_value.open.return_value=Response(page());self.assertEqual(fetch('openai-usage'),page());req=build.return_value.open.call_args.args[0];self.assertEqual(req.full_url,CATALOGUE['openai-usage']['url']);self.assertNotIn('Authorization',req.headers)
    def test_fetch_protocol_and_content_errors(self):
        for response in (Response(page(),302),Response(page(),ctype='text/plain'),Response(page(),url='https://localhost/'),Response(page(),ctype='text/html; charset=latin1'),Response(b'x'*(LIMIT+1))):
            with patch('horizon.policies.urllib.request.build_opener') as build:
                build.return_value.open.return_value=response
                with self.assertRaises(PolicyError):fetch('openai-usage')
    def test_compressed_rejected(self):
        r=Response(page());r.headers['Content-Encoding']='gzip'
        with patch('horizon.policies.urllib.request.build_opener') as build:
            build.return_value.open.return_value=r
            with self.assertRaises(PolicyError):fetch('openai-usage')
    def test_real_fetch_protocol_error_recorded(self):
        self.approve();r=Response(page());r.read=lambda n:(_ for _ in ()).throw(http.client.IncompleteRead(b'SECRET'))
        with patch('horizon.policies.urllib.request.build_opener') as build:
            build.return_value.open.return_value=r;result=self.x.collect('openai-usage',True)
        self.assertEqual(result['result'],'unavailable');self.assertEqual(self.x.store.state()['claims'][0]['status'],'needs-review');self.assertNotIn('SECRET',json.dumps(self.x.store.portable()))
    def http_response(self,body,headers):
        class Socket:
            def makefile(self,*args):return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n'+headers+b'\r\n'+body)
        response=http.client.HTTPResponse(Socket());response.begin()
        response.url=CATALOGUE['openai-usage']['url']
        return response
    def test_actual_http_response_truncated_after_main(self):
        self.approve();body=page();response=self.http_response(body,b'Content-Length: 99999\r\n')
        with patch('horizon.policies.urllib.request.build_opener') as build:
            build.return_value.open.return_value=response
            r=self.x.collect('openai-usage',True)
        self.assertEqual(r['result'],'unavailable');self.assertIsNone(r['raw_response_sha256'])
        self.assertEqual(self.x.store.state()['claims'][0]['status'],'needs-review')
        w=Watch(self.p/'db'/'workspace.sqlite3');self.assertEqual(w.changes(r['source_id'])['diff_status'],'unavailable_not_deletion')
    def test_actual_http_response_correct_length(self):
        body=page();response=self.http_response(body,('Content-Length: '+str(len(body))+'\r\n').encode())
        with patch('horizon.policies.urllib.request.build_opener') as build:
            build.return_value.open.return_value=response;self.assertEqual(fetch('openai-usage'),body)
    def test_actual_http_response_chunked(self):
        body=page();framed=(hex(len(body))[2:]+'\r\n').encode()+body+b'\r\n0\r\n\r\n'
        response=self.http_response(framed,b'Transfer-Encoding: chunked\r\n')
        with patch('horizon.policies.urllib.request.build_opener') as build:
            build.return_value.open.return_value=response;self.assertEqual(fetch('openai-usage'),body)
    def test_reject_ambiguous_or_invalid_framing(self):
        for headers in (b'Content-Length: -1\r\n',b'Content-Length: 2, 2\r\n',b'Content-Length: 99999999\r\n',b'Content-Length: 2\r\nContent-Length: 2\r\n',b'Content-Length: 2\r\nTransfer-Encoding: chunked\r\n',b'Transfer-Encoding: gzip\r\n'):
            with patch('horizon.policies.urllib.request.build_opener') as build:
                build.return_value.open.return_value=self.http_response(page(),headers)
                with self.assertRaises(PolicyError):fetch('openai-usage')
    def test_backup_restore(self):
        self.approve();backup(self.p/'db'/'workspace.sqlite3',self.p/'backup.sqlite3');restore(self.p/'backup.sqlite3',self.p/'restored',True);other=Policies(self.p/'restored'/'workspace.sqlite3');self.assertEqual(other.store.state()['claims'][0]['decision'],'unreviewed');self.assertEqual(other.store.state()['sources'][0]['latest']['text'],self.x.store.state()['sources'][0]['latest']['text'])
    def test_cli_without_network(self):
        for args,code in ((['catalogue'],0),(['collect','openai-usage','--data-dir',str(self.p/'cli')],2)):
            r=subprocess.run([sys.executable,'-m','horizon.policies',*args],cwd=ROOT,capture_output=True,text=True,timeout=5);self.assertEqual(r.returncode,code,r.stderr)
if __name__=='__main__':unittest.main()
