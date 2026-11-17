"""Synthetic declared-event windows, not real-world event verification."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError
from horizon.timeline import Timeline,TimelineError,window,markdown
from horizon.actions import ActionError
ROOT=Path(__file__).resolve().parents[1]
class Windows(unittest.TestCase):
    def test_instant_offset(self):
        w=window('instant','2026-05-01T09:00:00-05:00');self.assertEqual(w['lower_utc'],'2026-05-01T14:00:00.000000+00:00');self.assertEqual(w['lower_utc'],w['upper_utc'])
    def test_interval(self):
        w=window('instant','2026-01-01T00:00:00Z','2026-01-01T01:00:00Z');self.assertNotEqual(w['lower_utc'],w['upper_utc'])
    def test_day_requires_zone(self):
        with self.assertRaises(TimelineError):window('day','2026-01-01')
    def test_utc_day(self):
        w=window('day','2026-01-01',zone='UTC');self.assertEqual(w['lower_utc'],'2026-01-01T00:00:00.000000+00:00');self.assertEqual(w['upper_utc'],'2026-01-01T23:59:59.999999+00:00')
    def test_dst_day_lengths(self):
        for d,hours in [('2026-03-08',23),('2026-11-01',25)]:
            w=window('day',d,zone='America/New_York');delta=datetime.fromisoformat(w['upper_utc'])-datetime.fromisoformat(w['lower_utc'])+timedelta(microseconds=1);self.assertEqual(delta,timedelta(hours=hours))
    def test_skipped_date_rejected(self):
        with self.assertRaises(TimelineError):window('day','2011-12-30',zone='Pacific/Apia')
    def test_missing_timezone_database_controlled(self):
        with patch('horizon.timeline.ZoneInfo',side_effect=ZoneInfoNotFoundError('missing database')):
            with self.assertRaises(TimelineError):window('day','2026-01-01',zone='America/New_York')
            self.assertEqual(window('instant','2026-01-01T00:00:00Z')['lower_utc'],'2026-01-01T00:00:00.000000+00:00')
    def test_unknown(self):
        self.assertIsNone(window('unknown')['lower_utc'])
        with self.assertRaises(TimelineError):window('unknown','2026-01-01')
    def test_invalid_dates(self):
        for args in [('instant','2026-01-01T01:00:00'),('instant','2026-01-01T01:00:00-00:00'),('instant','2026-01-01T01:00:00+00:99'),('instant','2026-01-01T24:00:00Z'),('day','2026-02-30','','UTC'),('day','2026-01-02','2026-01-01','UTC'),('day','2026-01-01','','bad/zone'),('instant','1800-01-01T00:00:00Z'),('instant','2026-01-02T00:00:00Z','2026-01-01T00:00:00Z')]:
            with self.subTest(args=args),self.assertRaises(TimelineError):window(*args)
class Events(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name);self.x=Timeline(self.p/'workspace.sqlite3');s=self.x.store.apply('demo',{});self.cid=next(c['id'] for c in s['claims'] if c['evidence']);self.x.store.apply('review',{'claim_id':self.cid,'decision':'approve','note':'Synthetic human review'})
    def add(self,start='2026-05-01T10:00:00Z',end='',precision='instant',zone=''):
        return self.x.create(self.cid,'Synthetic launch','release',precision,start,end,zone,'Human-provided event time, not verified')
    def test_final_basis_size_after_observation_fields(self):
        # Isolate the final bound: upstream basis is just below 256 KiB, then
        # actual immutable snapshot observation timestamps push it over.
        from horizon.actions import basis
        claim=next(c for c in self.x.store.state()['claims'] if c['id']==self.cid)
        b=basis(claim);b['review_note']=''
        current=len(json.dumps(b,ensure_ascii=True).encode('ascii'))
        b['review_note']='x'*(256*1024-current-1)
        self.assertLess(len(json.dumps(b,ensure_ascii=True).encode('ascii')),256*1024)
        with patch('horizon.timeline.basis',return_value=b):
            with self.assertRaises(TimelineError):self.add()
        self.assertEqual(self.x.listing()['events'],[])
    def test_capture(self):
        r=self.x.show(self.add());self.assertEqual(r['basis_status'],'current_editorial_basis');self.assertIn('source_observed_at',r['basis']['evidence'][0]);self.assertNotEqual(r['recorded_at'],r['time_window']['start'])
    def test_order(self):
        late=self.add('2026-05-02T10:00:00Z');early=self.add();self.assertEqual([r['id'] for r in self.x.listing()['events']],[early,late])
    def test_overlap(self):
        a=self.add(end='2026-05-01T12:00:00Z');b=self.add('2026-05-01T11:00:00Z');r=self.x.listing()['events'];self.assertEqual(r[0]['possible_overlap_ids'],[b]);self.assertEqual(r[1]['possible_overlap_ids'],[a])
    def test_touching_inclusive(self):
        a=self.add(end='2026-05-01T12:00:00Z');b=self.add('2026-05-01T12:00:00Z');self.assertIn(b,self.x.listing()['events'][0]['possible_overlap_ids'])
    def test_adjacent_days_disjoint(self):
        self.add('2026-05-01',precision='day',zone='UTC');self.add('2026-05-02',precision='day',zone='UTC');self.assertTrue(all(not r['possible_overlap_ids'] for r in self.x.listing()['events']))
    def test_unknown_last_and_explicit(self):
        u=self.add('',precision='unknown');k=self.add();r=self.x.listing();self.assertEqual(r['events'][-1]['id'],u);self.assertEqual(r['unknown_time_active_ids'],[u]);self.assertEqual(r['events'][0]['ordering_status'],'disjoint_among_known_active_windows')
    def test_stale_retains_time(self):
        eid=self.add();old=self.x.show(eid);self.x.store.apply('demo-update',{});new=self.x.show(eid);self.assertEqual(new['basis_status'],'needs_review');self.assertEqual(old['time_window'],new['time_window']);self.assertIn('needs human re-review',markdown(self.x.listing()))
    def test_withdraw_retains_history(self):
        a=self.add();b=self.add();self.x.withdraw(a,'Incorrect claimed event');r=self.x.show(a);self.assertEqual(r['status'],'withdrawn');self.assertEqual(r['history'][-1]['operation'],'withdrawn');self.assertTrue(all(not r['possible_overlap_ids'] for r in self.x.listing()['events']));self.assertIn('WITHDRAWN',markdown(self.x.listing()))
    def test_revive_explicit_revision(self):
        eid=self.add();self.x.withdraw(eid,'Withdrawn');self.x.revise(eid,'Corrected launch','release','instant','2026-05-03T00:00:00Z','','','Human corrected the time');r=self.x.show(eid);self.assertEqual(r['status'],'active');self.assertEqual(r['history'][-1]['detail']['previous']['status'],'withdrawn');self.assertEqual(len(r['history']),3)
    def test_stale_revision_blocked(self):
        eid=self.add();self.x.store.apply('demo-update',{})
        with self.assertRaises(ActionError):self.x.revise(eid,'Correct','other','unknown','','','','No current support')
    def test_unreviewed_creation_blocked(self):
        self.x.store.apply('review',{'claim_id':self.cid,'decision':'withhold'})
        with self.assertRaises(ActionError):self.add()
        self.assertEqual(self.x.listing()['events'],[])
    def test_restart(self):
        eid=self.add();self.assertEqual(Timeline(self.p/'workspace.sqlite3').show(eid)['id'],eid)
    def test_atomic_revision(self):
        eid=self.add();old=self.x.show(eid)
        def fail(*args):raise TimelineError('history quota')
        self.x._log=fail
        with self.assertRaises(TimelineError):self.x.revise(eid,'New','other','unknown','','','','Attempt')
        self.assertEqual(old,self.x.show(eid))
    def test_portable_boundary(self):
        self.add();portable=self.x.store.portable();self.assertNotIn('intel_events',portable['tables']);other=Timeline(self.p/'other.sqlite3');other.store.apply('import',portable);self.assertEqual(other.listing()['events'],[])
    def test_export_escaping(self):
        self.x.create(self.cid,'<script>oops</script>','other','unknown','','','','<img src=x>');out=markdown(self.x.listing());self.assertNotIn('<script>',out);self.assertNotIn('<img',out)
    def test_cli(self):
        eid=self.add()
        def cli(*a):return subprocess.run([sys.executable,'-m','horizon.timeline','--data-dir',str(self.p),*map(str,a)],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(cli('list').returncode,0);self.assertIn(eid,cli('show',eid).stdout);out=self.p/'timeline.md';self.assertEqual(cli('export','--format','markdown','--out',out).returncode,0);self.assertEqual(cli('export','--out',out).returncode,2);self.assertNotIn(b'\r',out.read_bytes());self.assertEqual(cli('withdraw',eid,'--note','Synthetic withdrawal').returncode,0)
if __name__=='__main__':unittest.main()
