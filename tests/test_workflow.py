"""Integrated real loopback workflows with fictional sources. No external requests."""
import json,tempfile,unittest,uuid,subprocess,sys,os
from pathlib import Path
from unittest.mock import patch
import test_http as fixture
from horizon.workflow import Workflow
from horizon.watch import Watch

class WorkflowHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep actual loopback/handler code, but spy on outbound/scan boundaries.
        # Any accidental fetch in a regression stays synthetic and local.
        real_popen=subprocess.Popen
        def launch(args,*a,**kw):
            target=args[args.index('--data-dir')+1];port=args[args.index('--port')+1]
            script="""import pathlib
import horizon.workflow as workflow
from horizon.radar import RadarError
from horizon.watch import Watch
from horizon.server import serve
root=pathlib.Path(DATA)
def fake_fetch(*args):
    with (root/'fetch-calls').open('a') as f:f.write('called\\n')
    raise RadarError('Synthetic transport: no network')
original_scan=Watch.scan
def scan(self):
    with (root/'scan-calls').open('a') as f:f.write('called\\n')
    return original_scan(self)
workflow.fetch=fake_fetch
Watch.scan=scan
serve(port=PORT,data=DATA)
""".replace('DATA',repr(target)).replace('PORT',port)
            return real_popen([sys.executable,'-u','-c',script],*a,**kw)
        with patch('test_http.subprocess.Popen',side_effect=launch):
            fixture.HttpTests.setUpClass.__func__(cls)
    stop=classmethod(fixture.HttpTests.stop.__func__)
    request=fixture.HttpTests.request
    def post(self,path,data):
        code,headers,raw=self.request('POST','/api/'+path,json.dumps(data),{'Content-Type':'application/json'});return code,json.loads(raw)
    def get(self,resource='overview',extra=''):
        code,headers,raw=self.request('GET','/api/workflow?resource='+resource+extra);return code,json.loads(raw)
    def seed(self):
        code,s=self.post('source',{'title':'Synthetic workflow source','url':'https://example.invalid/'+str(uuid.uuid4()),'kind':'report','text':'Synthetic policy: local trials allowed.','availability':'full'});self.assertEqual(code,200);source=s['sources'][0]
        code,s=self.post('claim',{'text':'Local trials allowed.','topic':'Synthetic workflow'});self.assertEqual(code,200);claim=s['claims'][0]['id']
        code,s=self.post('evidence',{'claim_id':claim,'snapshot_id':source['latest']['id'],'quote':'local trials allowed.','relation':'supports'});self.assertEqual(code,200)
        self.assertEqual(self.post('review',{'claim_id':claim,'decision':'approve','note':'Synthetic human review'})[0],200)
        return claim,source['id']
    def test_end_to_end_basis_change_and_repair(self):
        claim,source=self.seed()
        code,r=self.post('workflow/action-create',{'claim_id':claim,'title':'Try local trial','why':'Evaluate fit','steps':['Run synthetic case'],'owner':'Human','due':''});self.assertEqual(code,200);aid=r['action_id']
        code,r=self.post('workflow/event-create',{'claim_id':claim,'title':'Policy date unknown','kind':'policy','precision':'unknown','start':'','end':'','zone':'','note':'Source does not state event time'});self.assertEqual(code,200);eid=r['event_id']
        self.assertEqual(self.post('workflow/action-check',{'action_id':aid,'index':0,'done':True,'note':'Human reports trial run'})[0],200)
        code,s=self.post('snapshot',{'source_id':source,'text':'Synthetic policy: approval required.','availability':'full'});self.assertEqual(code,200)
        self.assertEqual(self.post('workflow/action-status',{'action_id':aid,'status':'done','note':'Attempted completion'})[0],400)
        detail=self.post('workflow/action-show',{'action_id':aid})[1]['action'];self.assertEqual(detail['basis_status'],'needs_review')
        event=self.post('workflow/event-show',{'event_id':eid})[1]['event'];self.assertEqual(event['basis_status'],'needs_review')
        c=next(c for c in s['claims'] if c['id']==claim)
        for evidence in c['evidence']:self.assertEqual(self.post('evidence-remove',{'id':evidence['id']})[0],200)
        self.assertEqual(self.post('claim',{'id':claim,'text':'Approval required.','topic':'Synthetic workflow'})[0],200)
        source_record=next(x for x in s['sources'] if x['id']==source)
        self.assertEqual(self.post('evidence',{'claim_id':claim,'snapshot_id':source_record['latest']['id'],'quote':'approval required.','relation':'supports'})[0],200)
        self.assertEqual(self.post('review',{'claim_id':claim,'decision':'approve','note':'Human read correction'})[0],200)
        self.assertEqual(self.post('workflow/action-edit',{'action_id':aid,'title':'Trial with approval','why':'Revised requirement','owner':'Human','due':'','note':'Plan clarified'})[0],200)
        self.assertEqual(self.post('workflow/event-revise',{'event_id':eid,'title':'Revised policy date unknown','kind':'policy','precision':'unknown','start':'','end':'','zone':'','note':'Corrected basis, still no reliable event date'})[0],200)
        self.assertEqual(self.post('workflow/action-review',{'action_id':aid,'note':'Plan reconsidered after correction'})[0],200)
        detail=self.post('workflow/action-show',{'action_id':aid})[1]['action'];self.assertEqual(detail['completed_steps'],0)
        self.assertEqual(self.post('workflow/action-check',{'action_id':aid,'index':0,'done':True,'note':'Reran with required approval'})[0],200)
        self.assertEqual(self.post('workflow/action-status',{'action_id':aid,'status':'done','note':'Completed under revised basis'})[0],200)
        self.assertEqual(self.post('workflow/event-withdraw',{'event_id':eid,'note':'Old event interpretation withdrawn'})[0],200)
    def test_host_origin_json_boundaries(self):
        self.assertEqual(self.request('GET','/api/workflow',headers={'Host':'evil.invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/workflow/watch-scan','{"allow_local_reads":true}',{'Content-Type':'application/json','Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/workflow/watch-scan','{}',{'Content-Type':'text/plain'})[0],415)
    def test_query_pagination_validation_and_redaction(self):
        for extra in ('&limit=51','&offset=-1','&offset=SECRET_SENTINEL','&limit=2&limit=3','&other=x'):
            code,data=self.get(extra=extra);self.assertEqual(code,400);self.assertNotIn('SECRET_SENTINEL',json.dumps(data))
        self.assertEqual(self.get('unknown')[0],400)
    def test_paginated_claims(self):
        self.seed();self.seed();code,r=self.get('claims','&limit=1');self.assertEqual(code,200);self.assertEqual(len(r['items']),1);self.assertGreaterEqual(r['total'],2);self.assertEqual(r['limit'],1)
    def test_unknown_fields_and_operation(self):
        self.assertEqual(self.post('workflow/watch-scan',{'allow_local_reads':True,'path':'SECRET_SENTINEL'})[0],400)
        code,r=self.post('workflow/not-supported',{});self.assertEqual(code,400);self.assertNotIn('SECRET_SENTINEL',json.dumps(r))
    def test_no_network_without_exact_consent(self):
        code,r=self.post('workflow/radar-add',{'label':str(uuid.uuid4()),'query':'topic:synthetic','per_page':2});self.assertEqual(code,200);qid=r['query_id']
        for v in (False,1,'true',None):self.assertEqual(self.post('workflow/radar-collect',{'query_id':qid,'allow_network':v})[0],400)
        self.assertEqual(self.post('workflow/radar-review',{'query_id':qid})[1]['review']['status'],'never_collected')
    def test_watch_registered_file_gate_and_failure(self):
        f=Path(self.temp.name)/('synthetic-'+str(uuid.uuid4())+'.txt');f.write_text('Synthetic local document')
        w=Watch(Path(self.temp.name)/'workspace.sqlite3');sid=w.register(f,'https://example.invalid/'+str(uuid.uuid4()),'Synthetic watch')
        for v in (False,1,'true',None):self.assertEqual(self.post('workflow/watch-scan',{'allow_local_reads':v})[0],400)
        f.write_text('Revised synthetic local document');code,r=self.post('workflow/watch-scan',{'allow_local_reads':True});self.assertEqual(code,200);self.assertEqual(next(x for x in r['results'] if x['source_id']==sid)['result'],'changed')
        self.assertEqual(self.post('workflow/watch-changes',{'source_id':sid})[1]['changes']['diff_status'],'text_changed')
        f.unlink();code,r=self.post('workflow/watch-scan',{'allow_local_reads':True});self.assertEqual(code,200);self.assertEqual(next(x for x in r['results'] if x['source_id']==sid)['result'],'unavailable');self.assertNotIn(str(f),json.dumps(r));w.untrack(sid)
    def test_raw_duplicate_consent_never_calls_boundaries(self):
        code,r=self.post('workflow/radar-add',{'label':str(uuid.uuid4()),'query':'topic:synthetic','per_page':2});self.assertEqual(code,200);qid=r['query_id']
        def counts():return {name:(Path(self.temp.name)/name).read_bytes() if (Path(self.temp.name)/name).exists() else b'' for name in ('fetch-calls','scan-calls')}
        before=counts()
        bodies=[('radar-collect','{"query_id":'+json.dumps(qid)+',"allow_network":false,"allow_network":true}'),('radar-collect','{"query_id":'+json.dumps(qid)+',"allow_network":true,"allow_network":false}'),('watch-scan','{"allow_local_reads":false,"allow_local_reads":true}'),('watch-scan','{"allow_local_reads":true,"allow_local_reads":false}')]
        for operation,raw in bodies:
            status,_,body=self.request('POST','/api/workflow/'+operation,raw,{'Content-Type':'application/json'})
            self.assertEqual(status,400);self.assertIn(b'Duplicate JSON',body)
        self.assertEqual(counts(),before)
        self.assertEqual(self.post('workflow/radar-review',{'query_id':qid})[1]['review']['status'],'never_collected')
    def test_nested_duplicate_json_redacted(self):
        status,_,body=self.request('POST','/api/workflow/action-create','{"nested":{"SECRET_SENTINEL":1,"SECRET_SENTINEL":2}}',{'Content-Type':'application/json'})
        self.assertEqual(status,400);self.assertNotIn(b'SECRET_SENTINEL',body)
    def test_read_resources(self):
        for resource in ('overview','claims','actions','events','queries','watches'):self.assertEqual(self.get(resource)[0],200)
        code,r=self.get('events')
        for e in r['items']:self.assertNotIn('basis',e)

class WorkflowDispatch(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.w=Workflow(Path(self.t.name)/'workspace.sqlite3')
    def test_network_dispatch_with_injected_transport(self):
        qid=self.w.apply('radar-add',{'label':'Synthetic','query':'topic:synthetic','per_page':1})['query_id']
        raw=json.dumps({'total_count':1,'incomplete_results':False,'items':[{'id':42,'full_name':'synthetic/repo','stargazers_count':3,'created_at':'2026-01-01T00:00:00Z','description':'Synthetic','language':None,'fork':False,'archived':False}]}).encode()
        with patch('horizon.workflow.fetch',return_value=raw) as call:
            for v in (False,1,'true'):
                with self.assertRaises(ValueError):self.w.apply('radar-collect',{'query_id':qid,'allow_network':v})
            call.assert_not_called();r=self.w.apply('radar-collect',{'query_id':qid,'allow_network':True});call.assert_called_once_with('topic:synthetic',1)
        self.assertEqual(r['review']['status'],'observed');self.w.apply('radar-import',{'query_id':qid,'repo_id':42});self.assertEqual(self.w.actions.store.state()['sources'][0]['kind'],'summary')
    def test_read_never_fetches_or_scans(self):
        with patch('horizon.workflow.fetch') as f,patch.object(self.w.watch,'scan') as scan:
            for r in ('overview','claims','actions','events','queries','watches'):self.w.read(r)
            f.assert_not_called();scan.assert_not_called()
    def test_strict_shapes(self):
        for op,data in [('radar-add',{}),('action-create',[]),('other',{}),('watch-scan',{'allow_local_reads':True,'unexpected':1})]:
            with self.assertRaises(ValueError):self.w.apply(op,data)
if __name__=='__main__':unittest.main()
