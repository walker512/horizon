"""Original synthetic public-repository examples; no third-party README or network."""
import base64,copy,hashlib,http.client,io,json,os,subprocess,sys,tempfile,unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from horizon.projects import Projects,ProjectError,metadata,readme,fetch,validate,markdown,name,LIMIT
from horizon.radar import Radar
from horizon.backup import backup,restore,check
ROOT=Path(__file__).resolve().parents[1]
def repo(n='synthetic/tool',rid=7):return {'id':rid,'full_name':n,'private':False,'default_branch':'main','archived':False,'license':{'spdx_id':'MIT'}}
def readmedoc(text='Synthetic tool solves sorting. Alternatives include Sample. Requires Python 3.'):
    b=text.encode();return {'type':'file','encoding':'base64','size':len(b),'content':base64.b64encode(b).decode()+'\n','sha':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'path':'README.md'}
def raw(x):return json.dumps(x).encode()
def transport(n,r):return raw(readmedoc() if r else repo(n))
def spec(cid=None,eid=None):
    return {'project_version':None,'entries':[{'category':cat,'criterion':cat,'definition':'Human-defined '+cat,'unit':'text','platform':'Linux','version_scope':'README-observed default branch; release unverified','state':'known' if cid else 'unknown','value':'sorting' if cid else None,'raw_value':'sorting' if cid else '', 'claim_id':cid,'evidence_id':eid,'note':'Synthetic mapping, not semantic verification.'} for cat in ('purpose','alternatives','barrier')]}
class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.ps=Projects(self.p/'db'/'workspace.sqlite3');self.r=Radar(self.ps.store.path);self.q=self.r.add('Synthetic','synthetic',2);self.search();self.pid=self.ps.select(self.q,7)
    def search(self,n='synthetic/tool',rid=7):
        item={**repo(n,rid),'stargazers_count':1,'created_at':'2026-01-01T00:00:00Z','description':'Synthetic','language':'Python','fork':False}
        self.r.collect(self.q,lambda q,p:raw({'total_count':1,'incomplete_results':False,'items':[item]}))
    def collect(self):return self.ps.collect(self.pid,True,transport)
    def approved(self):
        run=self.collect();sid=run['detail']['parts']['readme']['snapshot_id'];st=self.ps.store.apply('claim',{'text':'Synthetic sorting claim'});cid=st['claims'][0]['id'];self.ps.store.apply('evidence',{'claim_id':cid,'snapshot_id':sid,'quote':'solves sorting','relation':'supports'});st=self.ps.store.apply('review',{'claim_id':cid,'decision':'approve'});eid=next(c for c in st['claims'] if c['id']==cid)['evidence'][0]['id'];return cid,eid
    def profile(self):
        c,e=self.approved();return self.ps.add(self.pid,spec(c,e))
    def test_select_duplicate_and_missing(self):
        self.assertEqual(self.ps.select(self.q,7),self.pid)
        with self.assertRaises(ValueError):self.ps.select(self.q,8)
    def test_permission_strict(self):
        for x in (False,1,'true',None):
            with self.assertRaises(ProjectError):self.ps.collect(self.pid,x,lambda *a:self.fail('network'))
    def test_two_requests_source_urls(self):
        calls=[]
        def t(n,r):calls.append((n,r));return transport(n,r)
        r=self.ps.collect(self.pid,True,t);self.assertEqual(calls,[('synthetic/tool',False),('synthetic/tool',True)]);self.assertEqual(r['status'],'observed');self.assertEqual(r['detail']['parts']['readme']['url'],'https://api.github.com/repos/synthetic/tool/readme');self.assertFalse(r['detail']['atomic_version'])
    def test_stable_collection_no_snapshot_noise(self):
        a=self.collect();b=self.collect();self.assertNotEqual(a['id'],b['id']);self.assertEqual(a['detail'],b['detail']);self.assertEqual(len(self.ps.store.state()['sources'][0]['snapshots']),1)
    def test_public_identity_mismatch(self):
        for change in ({'id':8},{'id':True},{'private':True},{'private':0}):
            d=repo();d.update(change)
            with self.assertRaises(ValueError):metadata(raw(d),7)
    def test_path_boundary(self):
        for n in ('x/.','x/..','x/y/z','x/%2e%2e','https://x/y'):
            with self.assertRaises(ValueError):name(n)
    def test_metadata_failure_no_readme(self):
        calls=[]
        def t(n,r):calls.append(r);return raw(repo(rid=8))
        r=self.ps.collect(self.pid,True,t);self.assertEqual(calls,[False]);self.assertEqual(r['status'],'failed');self.assertTrue(all(s['latest']['text']=='' for s in self.ps.store.state()['sources']))
    def test_partial_and_recovery_invalidates(self):
        oid=self.profile()
        def t(n,r):
            if r:raise ProjectError('synthetic failure')
            return transport(n,r)
        result=self.ps.collect(self.pid,True,t);self.assertEqual(result['status'],'partial');self.assertEqual(self.ps.show(oid)['basis_status'],'needs_review');self.collect();self.assertEqual(self.ps.show(oid)['basis_status'],'needs_review')
    def test_readme_strict_content(self):
        for change in ({'type':'dir'},{'encoding':'none'},{'size':True},{'size':1},{'content':'YQ== '},{'sha':'0'*40},{'path':None}):
            d=readmedoc();d.update(change)
            with self.assertRaises(ValueError):readme(raw(d))
    def test_readme_unicode_and_limits(self):
        text,info=readme(raw(readmedoc('Synthetic 😀 sorting')));self.assertIn('😀',text)
        for t in ('\x00',' ','x'*524289):
            with self.assertRaises(ValueError):readme(raw(readmedoc(t)))
    def test_json_duplicate_nonfinite(self):
        for b in (b'{"id":7,"id":7}',b'{"x":NaN}',b'x'*(LIMIT+1)):
            with self.assertRaises(ValueError):metadata(b,7)
    def test_profile_capture(self):
        oid=self.profile();p=self.ps.show(oid);self.assertEqual(p['basis_status'],'current_editorial_basis');self.assertFalse(p['semantic_mapping_verified']);self.assertTrue(p['review_complete']);self.assertEqual(len(p['basis']),1)
    def test_unknown_not_complete(self):
        self.collect();oid=self.ps.add(self.pid,spec());p=self.ps.show(oid);self.assertFalse(p['review_complete']);self.assertEqual(p['basis_status'],'needs_review')
    def test_wrong_project_evidence(self):
        c,e=self.approved();self.search('synthetic/other',8);pid=self.ps.select(self.q,8);self.ps.collect(pid,True,lambda n,r:raw(readmedoc() if r else repo(n,8)))
        with self.assertRaises(ValueError):self.ps.add(pid,spec(c,e))
    def test_unapproved_wrong_quote(self):
        c,e=self.approved();d=spec(c,e);d['entries'][0]['raw_value']='absent'
        with self.assertRaises(ValueError):self.ps.add(self.pid,d)
        self.ps.store.apply('review',{'claim_id':c,'decision':'withhold'})
        with self.assertRaises(ValueError):self.ps.add(self.pid,spec(c,e))
    def test_claim_edit_stales(self):
        oid=self.profile();cid=next(iter(self.ps.show(oid)['basis']));self.ps.store.apply('claim',{'id':cid,'text':'Correction'});self.assertEqual(self.ps.show(oid)['basis_status'],'needs_review')
    def test_rename_reselect(self):
        oid=self.profile();self.search('synthetic/renamed');self.assertEqual(self.ps.select(self.q,7),self.pid);self.assertEqual(self.ps.show(oid)['basis_status'],'needs_review');self.collect();self.assertEqual(self.ps.listing()[0]['full_name'],'synthetic/renamed');self.assertEqual(self.ps.show(oid)['basis_status'],'needs_review')
    def test_compare_scope_and_versions(self):
        c,e=self.approved();d=spec(c,e);d['project_version']='v1';a=self.ps.add(self.pid,d);d['project_version']='v9';b=self.ps.add(self.pid,d);r=self.ps.compare([a,b]);self.assertTrue(all(x['scope_status']=='declared_comparable' for x in r['rows']));self.assertIsNone(r['ranking']);d['entries'][0]['platform']='Windows';z=self.ps.add(self.pid,d);self.assertEqual(self.ps.compare([a,z])['rows'][2]['scope_status'],'unknown_or_different_scope')
    def test_withdraw_historical(self):
        a=self.profile();b=self.profile();self.ps.withdraw(a,'Wrong mapping');r=self.ps.compare([a,b]);self.assertTrue(all(x['review_required'] for x in r['rows']));self.assertTrue(r['profiles'][0]['withdrawn']);self.assertFalse(r['profiles'][0]['review_complete'])
    def test_schema_unknown_duplicates(self):
        for change in ({'state':'maybe'},{'raw_value':'invented'},{'value':'invented'},{'note':''}):
            d=spec();d['entries'][0].update(change)
            with self.assertRaises(ValueError):validate(d)
        d=spec();d['entries'][1]['criterion']='purpose'
        with self.assertRaises(ValueError):validate(d)
    def test_markdown_inert(self):
        a=self.profile();b=self.profile();r=self.ps.compare([a,b]);r['rows'][0]['criterion']='[x](https://x) ! * <script> \\';s=markdown(r);self.assertNotIn('<script>',s);self.assertNotIn('https://',s);self.assertNotIn('[x]',s);self.assertIn('&#',s)
    def test_backup_restore(self):
        a=self.profile();out=self.p/'backup.sqlite3';backup(self.ps.store.path,out);self.assertIn('project_profiles',check(out)['counts']);restore(out,self.p/'restored',True);p=Projects(self.p/'restored'/'workspace.sqlite3');self.assertEqual(p.show(a)['basis_status'],'needs_review')
    def test_real_cli_and_output_refusal(self):
        a=self.profile();b=self.profile();base=[sys.executable,'-m','horizon.projects','--data-dir',str(self.p/'db')]
        for args in (['list'],['show',a],['compare',a,b,'--out',str(self.p/'out.json')]):self.assertEqual(subprocess.run(base+args,cwd=ROOT,capture_output=True).returncode,0)
        self.assertEqual(subprocess.run(base+['compare',a,b,'--out',str(self.p/'out.json')],cwd=ROOT,capture_output=True).returncode,2)
        self.assertEqual(subprocess.run(base+['collect',self.pid],cwd=ROOT,capture_output=True).returncode,2)
    def test_rollback(self):
        before=len(self.ps.listing()[0]['latest'] or {});
        with patch.object(self.ps.store,'log',side_effect=ValueError('synthetic quota')):
            with self.assertRaises(ValueError):self.collect()
        self.assertIsNone(self.ps.listing()[0]['latest']);self.assertEqual(self.ps.store.state()['sources'],[])

class Fake:
    def __init__(self,body,headers):self.body=io.BytesIO(body);self.status=200;self.headers=Message();[self.headers.add_header(k,v) for k,v in headers];self.headers.add_header('Content-Type','application/json')
    def geturl(self):return 'https://api.github.com/repos/synthetic/tool'
    def read(self,n):return self.body.read(n)
    def __enter__(self):return self
    def __exit__(self,*a):pass
class Socket:
    def __init__(self,b):self.b=b
    def makefile(self,*a,**kw):return io.BytesIO(self.b)
class TransportTests(unittest.TestCase):
    def test_framing_rejections(self):
        for hs in ([('Content-Length','4')],[('Content-Length','1'),('Content-Length','1')],[('Content-Length','1'),('Transfer-Encoding','chunked')],[('Content-Length','-1')],[('Content-Length',str(LIMIT+1))],[('Transfer-Encoding','gzip')]):
            with patch('urllib.request.build_opener') as p:
                p.return_value.open.return_value=Fake(b'{}',hs)
                with self.assertRaises(ProjectError):fetch('synthetic/tool')
    def test_valid_close_and_length(self):
        for hs in ([],[('Content-Length','2')]):
            with patch('urllib.request.build_opener') as p:
                p.return_value.open.return_value=Fake(b'{}',hs);self.assertEqual(fetch('synthetic/tool'),b'{}')
    def test_actual_httpresponse_early_eof(self):
        r=http.client.HTTPResponse(Socket(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 20\r\n\r\n{}'));r.begin();r.geturl=lambda:'https://api.github.com/repos/synthetic/tool'
        with patch('urllib.request.build_opener') as p:
            p.return_value.open.return_value=r
            with self.assertRaises(ProjectError):fetch('synthetic/tool')
    def test_http_exception(self):
        with patch('urllib.request.build_opener') as p:
            p.return_value.open.side_effect=http.client.IncompleteRead(b'partial')
            with self.assertRaises(ProjectError):fetch('synthetic/tool')
if __name__=='__main__':unittest.main()

class PersistenceTests(unittest.TestCase):
    setUp=ProjectTests.setUp
    search=ProjectTests.search
    collect=ProjectTests.collect
    approved=ProjectTests.approved
    profile=ProjectTests.profile
    def test_snapshot_quota_failed_attempt(self):
        a=self.profile()
        with patch.object(self.ps.store,'snapshot',side_effect=ValueError('quota')):r=self.collect()
        self.assertEqual(r['status'],'failed');self.assertTrue(r['detail']['persistence_failed']);self.assertEqual(self.ps.show(a)['basis_status'],'needs_review')
    def test_run_quota_no_network(self):
        with self.ps.store.connect() as db:
            for i in range(500):db.execute('INSERT INTO project_runs VALUES(?,?,?,?,?)',(str(i),self.pid,'synthetic','failed','{}'))
        with self.assertRaises(ValueError):self.ps.collect(self.pid,True,lambda *a:self.fail('network must not run'))
    def test_cli_spec_special_files(self):
        self.collect();base=[sys.executable,'-m','horizon.projects','--data-dir',str(self.p/'db'),'add',self.pid,'--spec']
        f=self.p/'spec.json';f.write_text(json.dumps(spec()));link=self.p/'link';link.symlink_to(f);fifo=self.p/'fifo';os.mkfifo(fifo)
        for path in (link,fifo):self.assertEqual(subprocess.run(base+[str(path)],cwd=ROOT,capture_output=True,timeout=5).returncode,2)
        f.write_bytes(b'x'*(2*1024*1024+1));self.assertEqual(subprocess.run(base+[str(f)],cwd=ROOT,capture_output=True).returncode,2)
    def test_output_preflight_and_export_unicode(self):
        a=self.profile();b=self.profile();base=[sys.executable,'-m','horizon.projects','--data-dir',str(self.p/'db')];target=self.p/'report.md'
        self.assertEqual(subprocess.run(base+['compare',a,b,'--format','markdown','--out',str(target)],cwd=ROOT,capture_output=True).returncode,0)
        self.assertIn('Full human criteria',target.read_text());self.assertNotIn('https://',target.read_text())
    def test_no_add_before_renamed_observation(self):
        c,e=self.approved();self.search('synthetic/new');self.ps.select(self.q,7)
        with self.assertRaises(ProjectError):self.ps.add(self.pid,spec(c,e))

    def test_reselection_during_collection_not_overwritten(self):
        calls=[]
        def t(n,r):
            calls.append(r)
            if r:
                self.search('synthetic/renamed');self.ps.select(self.q,7)
            return transport(n,r)
        r=self.ps.collect(self.pid,True,t)
        self.assertEqual(r['status'],'failed');self.assertTrue(r['detail']['persistence_failed'])
        self.assertEqual(self.ps.listing()[0]['full_name'],'synthetic/renamed');self.assertEqual(self.ps.store.state()['sources'],[])

class ExtraBoundaryTests(unittest.TestCase):
    def test_actual_chunked_success_and_truncation(self):
        for chunks,okay in ((b'2\r\n{}\r\n0\r\n\r\n',True),(b'10\r\n{}',False)):
            r=http.client.HTTPResponse(Socket(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n'+chunks));r.begin();r.geturl=lambda:'https://api.github.com/repos/synthetic/tool'
            with patch('urllib.request.build_opener') as p:
                p.return_value.open.return_value=r
                if okay:self.assertEqual(fetch('synthetic/tool'),b'{}')
                else:
                    with self.assertRaises(ProjectError):fetch('synthetic/tool')
    def test_http_error_closed_no_retry(self):
        import urllib.error
        body=io.BytesIO(b'not retained');err=urllib.error.HTTPError('https://api.github.com/repos/synthetic/tool',301,'Moved',Message(),body)
        with patch('urllib.request.build_opener') as p:
            p.return_value.open.side_effect=err
            with self.assertRaises(ProjectError):fetch('synthetic/tool')
            self.assertEqual(p.return_value.open.call_count,1);self.assertTrue(body.closed)
    def test_format_and_type_rejected(self):
        for header,value in (('Content-Type','text/html'),('Content-Encoding','gzip')):
            r=Fake(b'{}',[]);del r.headers[header];r.headers[header]=value
            with patch('urllib.request.build_opener') as p:
                p.return_value.open.return_value=r
                with self.assertRaises(ProjectError):fetch('synthetic/tool')
    def test_cli_output_limit_before_creation(self):
        from horizon.projects import main
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'large.json'
            with patch.object(Projects,'compare',return_value={'huge':'x'*(4*1024*1024)}),patch.object(sys,'argv',['projects','--data-dir',str(Path(tmp)/'db'),'compare','a','b','--out',str(out)]),patch('sys.stderr',new=io.StringIO()):self.assertEqual(main(),2)
            self.assertFalse(out.exists())


class RequestIdentityTests(unittest.TestCase):
    setUp=ProjectTests.setUp
    search=ProjectTests.search
    def test_canonical_name_does_not_rewrite_metadata_request(self):
        for canonical in ('Synthetic/Tool','synthetic/renamed'):
            with self.subTest(canonical=canonical):
                calls=[]
                # Reset the selected name explicitly to make both paths independently testable.
                self.search('synthetic/tool');self.ps.select(self.q,7)
                def t(n,r):
                    calls.append((n,r))
                    return raw(readmedoc() if r else repo(canonical))
                result=self.ps.collect(self.pid,True,t);parts=result['detail']['parts']
                self.assertEqual(calls,[('synthetic/tool',False),(canonical,True)])
                self.assertEqual(parts['metadata']['url'],'https://api.github.com/repos/synthetic/tool')
                self.assertEqual(parts['readme']['url'],'https://api.github.com/repos/'+canonical+'/readme')
                for part in parts.values():
                    self.assertEqual(part['url'],part['request_url']);self.assertTrue(part['request_attempted'])
                sources={x['id']:x for x in self.ps.store.state()['sources']}
                self.assertEqual(sources[parts['metadata']['source_id']]['url'],parts['metadata']['request_url'])
    def test_readme_failure_keeps_actual_canonical_endpoint(self):
        def t(n,r):
            if r:raise ProjectError('synthetic unavailable')
            return raw(repo('synthetic/renamed'))
        result=self.ps.collect(self.pid,True,t);parts=result['detail']['parts']
        self.assertEqual(result['status'],'partial')
        self.assertEqual(parts['metadata']['request_url'],'https://api.github.com/repos/synthetic/tool')
        self.assertEqual(parts['readme']['url'],'https://api.github.com/repos/synthetic/renamed/readme')
        self.assertTrue(parts['readme']['request_attempted'])
    def test_identity_failure_marks_readme_not_attempted(self):
        calls=[]
        def t(n,r):calls.append((n,r));return raw(repo('synthetic/wrong',99))
        result=self.ps.collect(self.pid,True,t);parts=result['detail']['parts']
        self.assertEqual(calls,[('synthetic/tool',False)])
        self.assertEqual(parts['metadata']['url'],'https://api.github.com/repos/synthetic/tool')
        self.assertEqual(parts['readme']['url'],'https://api.github.com/repos/synthetic/tool/readme')
        self.assertFalse(parts['readme']['request_attempted'])
