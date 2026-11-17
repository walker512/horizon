"""Original synthetic HN/GitHub API payloads; no network in tests."""
import io,json,http.client,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from horizon.community import Community,CommunityError,fetch,project,repo_link
from horizon.radar import Radar
from horizon.backup import backup,restore
ROOT=Path(__file__).resolve().parents[1]
def raw(x):return json.dumps(x).encode()
def story(i=1,score=2,url='https://github.com/example/project'):
    return {'id':i,'type':'story','title':'Show HN: synthetic project','time':1770000000,'score':score,'descendants':3,'url':url}
class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.c=Community(self.p/'db'/'workspace.sqlite3')
    def transport(self,items=None,ids=None):
        items=items if items is not None else {1:story()};ids=ids if ids is not None else list(items)
        def t(path):return raw(ids if '/' not in path else items[int(path.split('/')[1].split('.')[0])])
        return t
    def collect(self,**kw):return self.c.collect(allow_network=True,transport=self.transport(),**kw)
    def test_no_network_without_exact_consent(self):
        for v in (False,None,1,'true'):
            t=unittest.mock.Mock()
            with self.assertRaises(CommunityError):self.c.collect(allow_network=v,transport=t)
            t.assert_not_called()
    def test_sample_and_local_filter(self):
        t=unittest.mock.Mock(side_effect=self.transport({1:story(),2:story(2)},[1,2]));r=self.c.collect(n=1,keyword='synthetic',allow_network=True,transport=t);self.assertEqual(t.call_count,2);self.assertEqual(r['coverage']['feed_returned'],2);self.assertEqual(r['coverage']['selected_ids'],[1]);self.assertEqual(len(r['candidates']),1)
    def test_nonmatches_disclosed(self):
        r=self.collect(keyword='nomatch');self.assertEqual(r['candidates'],[]);self.assertEqual(r['coverage']['title_nonmatches'],[1])
    def test_optional_counts_unknown(self):
        x=story();del x['score'];del x['descendants'];p=project(raw(x),1);self.assertIsNone(p['score']);self.assertIsNone(p['comments_reported'])
    def test_null_deleted_nonstory(self):
        r=self.c.collect(allow_network=True,transport=self.transport({1:None,2:{'id':2,'deleted':True},3:{'id':3,'type':'job'}}));self.assertEqual(r['candidates'],[]);self.assertEqual(len(r['coverage']['excluded_items']),3)
    def test_strict_projection(self):
        for k,v in [('id',True),('id',2),('score',False),('time',-1),('deleted',1),('title',''),('url',False),('url','https://user:secret@example.invalid'),('type',None)]:
            x=story();x[k]=v
            with self.assertRaises(ValueError):project(raw(x),1)
    def test_bad_lists(self):
        for ids in ([1,1],[True],[0],list(range(1,1002)),{}):
            r=self.c.collect(allow_network=True,transport=self.transport(ids=ids));self.assertEqual(r['status'],'failed');self.assertEqual(r['candidates'],[])
    def test_score_change_and_absence_not_deletion(self):
        self.collect();r=self.c.collect(allow_network=True,transport=self.transport({1:story(score=4),2:story(2)}));self.assertEqual(r['candidates'][0]['score_delta'],2);r=self.c.collect(allow_network=True,transport=self.transport({2:story(2)}));self.assertEqual(r['not_returned_since_previous'],[1])
    def test_streams_separate(self):self.collect(n=1);self.assertEqual(self.c.review(n=2)['status'],'never_collected');self.assertEqual(self.c.review(feed='show',n=1)['status'],'never_collected')
    def test_failed_latest_hides_and_blocks_import(self):
        self.collect()
        def fail(p):raise CommunityError('SECRET')
        r=self.c.collect(allow_network=True,transport=fail);self.assertEqual(r['status'],'failed');self.assertEqual(r['candidates'],[]);self.assertNotIn('SECRET',json.dumps(r))
        with self.assertRaises(CommunityError):self.c.import_item(1)
    def test_one_bad_item_no_partial_success(self):
        r=self.c.collect(allow_network=True,transport=self.transport({1:story(),2:{'id':999}}));self.assertEqual(r['status'],'failed');self.assertEqual(r['candidates'],[])
    def test_import_actual_source_and_claim(self):
        self.collect();state=self.c.import_item(1);s=state['sources'][0];self.assertEqual(s['kind'],'relay');self.assertEqual(s['origin_group'],'');self.assertEqual(s['latest']['availability'],'summary');self.assertEqual(s['url'],'https://news.ycombinator.com/item?id=1')
        state=self.c.store.apply('claim',{'text':'A synthetic HN item links to the project, not a quality endorsement.'});cid=state['claims'][0]['id'];self.c.store.apply('evidence',{'claim_id':cid,'snapshot_id':s['latest']['id'],'quote':'Show HN: synthetic project','relation':'supports'});self.assertEqual(len(self.c.store.state()['claims'][0]['evidence']),1)
    def test_strict_repository_links(self):
        self.assertEqual(repo_link('https://github.com/EXAMPLE/Project/'),'example/project')
        for u in ('http://github.com/a/b','https://github.com/a/b/issues/1','https://github.com/a/b?token=x','https://github.com/a/b#readme','https://github.com.evil.invalid/a/b','https://github.com:443/a/b','https://github.com:/a/b','https://github.com/a/b//','https://github.com/a/b///','https://u:p@github.com/a/b'):
            self.assertIsNone(repo_link(u))
    def github(self):
        r=Radar(self.p/'db'/'workspace.sqlite3');qid=r.add('Synthetic','test');payload={'total_count':1,'incomplete_results':False,'items':[{'id':123,'full_name':'example/project','stargazers_count':50,'created_at':'2026-01-01T00:00:00Z','fork':False,'archived':False,'description':'Synthetic','language':None}]};r.collect(qid,transport=lambda *a:raw(payload));return r,qid
    def test_association_same_repo_not_independence(self):
        _,q=self.github();self.collect();r=self.c.associate(q);self.assertEqual(len(r['matches']),1);self.assertEqual(r['matches'][0]['repository_id'],123);self.assertIn('not evidence of independent',r['relation'])
    def test_failed_github_no_match(self):
        r,q=self.github();self.collect()
        from horizon.radar import RadarError
        def fail(*a):raise RadarError('Unavailable')
        r.collect(q,transport=fail);self.assertEqual(self.c.associate(q)['matches'],[])
    def test_backup_restores_community_observations(self):
        self.collect();backup(self.p/'db'/'workspace.sqlite3',self.p/'copy');restore(self.p/'copy',self.p/'restored',True);other=Community(self.p/'restored'/'workspace.sqlite3');self.assertEqual(other.review()['candidates'],self.c.review()['candidates'])
    def response(self,body,headers):
        class Socket:
            def makefile(self,*args):return io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'+headers+b'\r\n'+body)
        r=http.client.HTTPResponse(Socket());r.begin();r.url='https://hacker-news.firebaseio.com/v0/newstories.json';return r
    def test_real_http_response_truncation(self):
        with patch('horizon.community.urllib.request.build_opener') as b:
            b.return_value.open.return_value=self.response(b'[1]',b'Content-Length: 999\r\n')
            with self.assertRaises(CommunityError):fetch('newstories.json')
    def test_real_http_response_success(self):
        with patch('horizon.community.urllib.request.build_opener') as b:
            b.return_value.open.return_value=self.response(b'[1]',b'Content-Length: 3\r\n');self.assertEqual(fetch('newstories.json'),b'[1]')
    def test_path_no_escape(self):
        with patch('horizon.community.urllib.request.build_opener') as b:
            for path in ('https://localhost/','../users.json','user/test.json','item/01.json','item/1.json?x=1'):
                with self.assertRaises(CommunityError):fetch(path)
            b.assert_not_called()
    def test_cli_offline(self):
        self.collect()
        def cli(*args):return subprocess.run([sys.executable,'-m','horizon.community','--data-dir',str(self.p/'db'),*args],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(cli('review').returncode,0);self.assertEqual(cli('import','1').returncode,0);self.assertEqual(cli('collect').returncode,2)
if __name__=='__main__':unittest.main()
