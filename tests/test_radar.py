"""Synthetic public-API responses plus real local CLI; no test network traffic."""
import copy,http.client,json,tempfile,unittest,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from horizon.radar import Radar,RadarError,projection,fetch,NoRedirect
ROOT=Path(__file__).resolve().parents[1]
def item(rid=1,stars=10,name='example/project'):
    return {'id':rid,'full_name':name,'stargazers_count':stars,'created_at':'2026-01-01T00:00:00Z','description':'Synthetic repository','language':'Python','fork':False,'archived':False}
def payload(items=None,total=None,incomplete=False):
    items=[item()] if items is None else items
    return json.dumps({'items':items,'total_count':len(items) if total is None else total,'incomplete_results':incomplete}).encode()
class Projection(unittest.TestCase):
    def test_projection(self):
        r=projection(payload(),20);self.assertEqual(r['items'][0]['stars'],10);self.assertEqual(r['items'][0]['url'],'https://github.com/example/project')
    def test_bad_types(self):
        for k,v in [('id',True),('stargazers_count',1.0),('archived',1),('fork','false'),('created_at','2026-01-01'),('description',{}),('description','\ud800'),('full_name','evil/x?token=secret')]:
            x=item();x[k]=v
            with self.subTest(k=k),self.assertRaises(RadarError):projection(payload([x]),20)
    def test_bad_coverage(self):
        for raw in [payload(total=0),payload(incomplete=1),payload([item(),item()]),b'{}',b'[]',b'['*10000+b']'*10000,b'x'*(2*1024*1024+1)]:
            with self.assertRaises(RadarError):projection(raw,20)
    def test_too_many(self):
        with self.assertRaises(RadarError):projection(payload([item(),item(2)]),1)
    def test_empty(self):self.assertEqual(projection(payload([]),20)['returned'],0)
    def test_no_redirect(self):self.assertIsNone(NoRedirect().redirect_request(None,None,302,None,None,'https://example.invalid'))
    def test_transport_fixed_endpoint(self):
        class Reply:
            status=200
            def __init__(self):self.raw=payload()
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):chunk,self.raw=self.raw[:n],self.raw[n:];return chunk
        with patch('horizon.radar.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value=Reply();self.assertEqual(fetch('topic:test',2),payload());request=factory.return_value.open.call_args[0][0]
            self.assertTrue(request.full_url.startswith('https://api.github.com/search/repositories?'));self.assertIn('page=1',request.full_url);self.assertNotIn('Authorization',request.headers)
class RadarTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name);self.r=Radar(self.p/'workspace.sqlite3');self.q=self.r.add('Synthetic','created:>=2026-01-01',20)
    def collect(self,items=None,at='2026-01-02T00:00:00+00:00',**kw):
        with patch('horizon.radar.now',return_value=at):return self.r.collect(self.q,lambda q,n:payload(items,**kw))
    def test_initial(self):self.assertEqual(self.r.review(self.q)['status'],'never_collected')
    def test_first_no_growth(self):
        r=self.collect();c=r['candidates'][0];self.assertEqual(c['discovery'],'first_seen_in_this_query');self.assertIsNone(c['star_delta']);self.assertIsNone(c['stars_per_day_observed'])
    def test_growth_exact_interval(self):
        self.collect();c=self.collect([item(stars=22)],at='2026-01-02T02:00:00+00:00')['candidates'][0];self.assertEqual(c['star_delta'],12);self.assertEqual(c['interval_seconds'],7200);self.assertEqual(c['stars_per_day_observed'],144)
    def test_short_interval_not_extrapolated(self):
        self.collect();c=self.collect([item(stars=22)],at='2026-01-02T00:01:00+00:00')['candidates'][0];self.assertEqual(c['star_delta'],12);self.assertIsNone(c['stars_per_day_observed'])
    def test_negative_delta(self):
        self.collect();c=self.collect([item(stars=2)],at='2026-01-03T00:00:00+00:00')['candidates'][0];self.assertEqual(c['star_delta'],-8)
    def test_clock_regression(self):
        self.collect();c=self.collect([item(stars=2)],at='2026-01-01T00:00:00+00:00')['candidates'][0];self.assertEqual(c['comparison_status'],'non_increasing_clock');self.assertIsNone(c['stars_per_day_observed'])
    def test_not_returned_not_deleted(self):
        self.collect();r=self.collect([item(2,name='other/repo')],at='2026-01-03T00:00:00+00:00');self.assertEqual(r['not_returned_since_previous'],[1]);self.assertEqual(r['candidates'][0]['discovery'],'first_seen_in_this_query')
    def test_reappear_uses_last_seen(self):
        self.collect();self.collect([],at='2026-01-03T00:00:00+00:00');c=self.collect([item(stars=14)],at='2026-01-04T00:00:00+00:00')['candidates'][0];self.assertEqual(c['discovery'],'reappeared_in_this_query');self.assertEqual(c['interval_seconds'],172800);self.assertEqual(c['star_delta'],4)
    def test_rename_same_id(self):
        self.collect();c=self.collect([item(name='new/name')],at='2026-01-03T00:00:00+00:00')['candidates'][0];self.assertEqual(c['previous_full_name'],'example/project');self.assertEqual(c['discovery'],'returned_again')
    def test_failed_attempt_not_stale_green(self):
        self.collect()
        def fail(q,n):raise RadarError('Synthetic failure')
        r=self.r.collect(self.q,fail);self.assertEqual(r['status'],'failed');self.assertEqual(r['candidates'],[]);self.assertIsNotNone(r['last_successful_observation'])
        with self.assertRaises(RadarError):self.r.import_candidate(self.q,1)
    def test_protocol_read_failure_is_recorded(self):
        self.collect()
        class BrokenReply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):raise http.client.IncompleteRead(b'SECRET_SENTINEL',100)
        with patch('horizon.radar.urllib.request.build_opener') as factory:
            factory.return_value.open.return_value=BrokenReply()
            result=self.r.collect(self.q)
        self.assertEqual(result['status'],'failed');self.assertEqual(len(result['runs']),2);self.assertEqual(result['candidates'],[])
        self.assertNotIn('SECRET_SENTINEL',json.dumps(result));self.assertEqual(self.r.review(self.q)['status'],'failed')
        with self.assertRaises(RadarError):self.r.import_candidate(self.q,1)
    def test_protocol_connection_failure_is_redacted(self):
        with patch('horizon.radar.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect=http.client.BadStatusLine('SECRET_SENTINEL')
            with self.assertRaises(RadarError) as caught:fetch('public query',3)
        self.assertNotIn('SECRET_SENTINEL',str(caught.exception))
    def test_recovery_after_error(self):
        self.collect();self.r.collect(self.q,lambda q,n:b'{}');r=self.collect([item(stars=11)],at='2026-01-04T00:00:00+00:00');self.assertEqual(r['candidates'][0]['star_delta'],1);self.assertEqual(len(r['runs']),3)
    def test_coverage_not_hidden(self):
        r=self.collect(total=400,incomplete=True);self.assertTrue(r['coverage']['truncated_to_page']);self.assertTrue(r['coverage']['incomplete_results']);self.assertEqual(r['coverage']['returned'],1)
    def test_separate_queries(self):
        self.collect();q2=self.r.add('Other','topic:other',5);r=self.r.collect(q2,lambda q,n:payload());self.assertIsNone(r['candidates'][0]['star_delta'])
    def test_import_summary(self):
        self.collect();state=self.r.import_candidate(self.q,1);s=state['sources'][0];self.assertEqual(s['kind'],'summary');self.assertEqual(s['latest']['availability'],'summary');self.assertIn('not a repository quality review',s['latest']['text']);self.assertEqual(len(state['claims']),0)
    def test_import_idempotence(self):
        self.collect();self.r.import_candidate(self.q,1);state=self.r.import_candidate(self.q,1);self.assertEqual(len(state['sources']),1);self.assertEqual(len(state['sources'][0]['snapshots']),1)
    def test_portable_excludes_query_registry(self):
        self.collect();self.assertNotIn('radar_queries',self.r.store.portable()['tables'])
    def test_registration_validation(self):
        for q,n in [('',20),('secret\nquery',20),('x',True),('x',51)]:
            with self.assertRaises(RadarError):self.r.add('Bad',q,n)
    def test_cli_no_network_without_flag(self):
        c=subprocess.run([sys.executable,'-m','horizon.radar','--data-dir',str(self.p),'collect',self.q],cwd=ROOT,capture_output=True,text=True,timeout=5);self.assertEqual(c.returncode,2);self.assertEqual(self.r.review(self.q)['status'],'never_collected')
    def test_cli_export(self):
        self.collect();out=self.p/'review.json';cmd=[sys.executable,'-m','horizon.radar','--data-dir',str(self.p),'review',self.q,'--out',str(out)]
        self.assertEqual(subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=5).returncode,0);self.assertEqual(subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=5).returncode,2);self.assertIn('coverage',json.loads(out.read_text()))
if __name__=='__main__':unittest.main()
