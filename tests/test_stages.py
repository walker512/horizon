"""Original synthetic editorial stage assessments, not true release/rumor classifications."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from horizon.timeline import Timeline,TimelineError,markdown
from horizon.backup import backup,restore
ROOT=Path(__file__).resolve().parents[1]
class Stages(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.t=Timeline(self.p/'db'/'workspace.sqlite3');s=self.t.store.apply('demo',{});self.cid=next(c['id'] for c in s['claims'] if c['evidence']);self.t.store.apply('review',{'claim_id':self.cid,'decision':'approve'});self.e=self.t.create(self.cid,'Synthetic release','release','unknown','','','','Declared timing unknown')
    def assessment(self):return self.t.show(self.e)['assessment']
    def test_default_unknown(self):self.assertEqual(self.assessment()['status'],'not_assessed');self.assertEqual(self.assessment()['effective_stage'],'unknown')
    def test_all_stages(self):
        for stage in ('released','planned','reported','rumor','unknown'):
            self.t.assess(self.e,stage,'Human classification only');a=self.assessment();self.assertEqual(a['effective_stage'],stage);self.assertFalse(a['automatic_verification']);self.assertEqual(a['status'],'current_editorial_assessment')
    def test_history_and_correction(self):
        self.t.assess(self.e,'released','Initial reading');self.t.assess(self.e,'planned','Correction: only announced');h=[x for x in self.t.show(self.e)['history'] if x['operation']=='stage-assessed'];self.assertEqual([x['detail']['stage'] for x in h],['released','planned']);self.assertEqual(h[-1]['detail']['previous']['declared_stage'],'released')
    def test_withhold_makes_effective_unknown(self):
        self.t.assess(self.e,'released','Human reading');self.t.store.apply('review',{'claim_id':self.cid,'decision':'withhold'});a=self.assessment();self.assertEqual(a['declared_stage'],'released');self.assertEqual(a['effective_stage'],'unknown');self.assertEqual(a['status'],'needs_review')
        with self.assertRaises(TimelineError):self.t.assess(self.e,'released','Not current')
    def test_new_approval_does_not_revive(self):
        self.t.assess(self.e,'released','Reading');self.t.store.apply('review',{'claim_id':self.cid,'decision':'approve','note':'Reviewed again'});self.assertEqual(self.assessment()['status'],'needs_review')
    def test_revise_requires_new_assessment(self):
        self.t.assess(self.e,'planned','Plan');self.t.revise(self.e,'New title','release','unknown','','','','Correct title');self.assertEqual(self.assessment()['effective_stage'],'unknown');self.t.assess(self.e,'reported','New human assessment');self.assertEqual(self.assessment()['effective_stage'],'reported')
    def test_unchanged_revise_also_invalidates(self):
        self.t.assess(self.e,'planned','Plan');self.t.revise(self.e,'Synthetic release','release','unknown','','','','Declared timing unknown');self.assertEqual(self.assessment()['status'],'needs_review')
    def test_withdraw_reopen(self):
        self.t.assess(self.e,'released','Reading');self.t.withdraw(self.e,'Incorrect event');self.assertEqual(self.assessment()['effective_stage'],'unknown')
        with self.assertRaises(TimelineError):self.t.assess(self.e,'rumor','Closed')
        self.t.revise(self.e,'Synthetic release','release','unknown','','','','Reopen');self.assertEqual(self.assessment()['effective_stage'],'unknown')
    def test_no_time_promotion(self):
        self.t.assess(self.e,'planned','Old plan');self.t.revise(self.e,'Old plan','release','instant','2020-01-01T00:00:00Z','','','Historical date');self.t.assess(self.e,'planned','Still only a plan');self.assertEqual(self.assessment()['effective_stage'],'planned')
    def test_source_revision_invalidates(self):
        self.t.assess(self.e,'released','Reading');s=self.t.show(self.e)['basis']['evidence'][0]['source_id'];self.t.store.apply('snapshot',{'source_id':s,'text':'Synthetic correction: report withdrawn','availability':'full'});self.assertEqual(self.assessment()['status'],'needs_review')
    def test_bad_inputs(self):
        for stage,note in [('confirmed','Note'),('released',''),(True,'Note')]:
            with self.assertRaises(ValueError):self.t.assess(self.e,stage,note)
        self.assertEqual(self.assessment()['status'],'not_assessed')
    def test_atomic_history_failure(self):
        self.t.assess(self.e,'planned','Plan');before=self.t.show(self.e)
        with patch.object(self.t,'_log',side_effect=ValueError('quota')):
            with self.assertRaises(ValueError):self.t.assess(self.e,'released','Later claim')
        self.assertEqual(before,self.t.show(self.e))
    def test_topic_captured_not_current(self):
        first=self.t.show(self.e)['basis']['topic'];c=next(x for x in self.t.store.state()['claims'] if x['id']==self.cid);self.t.store.apply('claim',{'id':self.cid,'text':c['text'],'topic':'Another topic'});self.t.store.apply('review',{'claim_id':self.cid,'decision':'approve'});new=self.t.create(self.cid,'Another event','other','unknown','','','','Other topic')
        if first:self.assertEqual([r['id'] for r in self.t.listing(first)['events']],[self.e])
        self.assertEqual([r['id'] for r in self.t.listing('Another topic')['events']],[new]);self.assertEqual(self.t.listing('missing')['events'],[])
    def test_filter_overlap_scope(self):
        r=self.t.listing('missing');self.assertEqual(r['captured_topic_filter'],'missing');self.assertEqual(r['overlap_scope'],'returned events only')
    def test_markdown_warning_and_escape(self):
        self.t.assess(self.e,'released','<script>bad</script> [link](https://example.invalid)');self.t.withdraw(self.e,'Withdraw');m=markdown(self.t.listing());self.assertIn('effective stage is unknown',m);self.assertNotIn('<script>',m);self.assertIn('Last declared stage',m)
    def test_backup_restore_assessment_stale(self):
        self.t.assess(self.e,'released','Reading');backup(self.p/'db'/'workspace.sqlite3',self.p/'copy');restore(self.p/'copy',self.p/'new',True);t=Timeline(self.p/'new'/'workspace.sqlite3');a=t.show(self.e)['assessment'];self.assertEqual(a['declared_stage'],'released');self.assertEqual(a['effective_stage'],'unknown')
    def test_cli(self):
        def cli(*args):return subprocess.run([sys.executable,'-m','horizon.timeline','--data-dir',str(self.p/'db'),*args],cwd=ROOT,capture_output=True,text=True,timeout=5)
        r=cli('assess',self.e,'--stage','reported','--note','Human report classification');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(cli('show',self.e).stdout)['assessment']['effective_stage'],'reported');self.assertEqual(json.loads(cli('list','--topic','missing').stdout)['events'],[])
        out=self.p/'topic.md';self.assertEqual(cli('export','--topic','missing','--format','markdown','--out',str(out)).returncode,0)
if __name__=='__main__':unittest.main()
