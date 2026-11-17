"""Original fictional action planning; no external execution or messages."""
import copy,json,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from horizon.actions import Actions,ActionError,markdown
ROOT=Path(__file__).resolve().parents[1]
class ActionsTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name);self.a=Actions(self.p/'workspace.sqlite3');s=self.a.store.apply('demo',{});self.cid=next(c['id'] for c in s['claims'] if c['evidence']);self.a.store.apply('review',{'claim_id':self.cid,'decision':'approve','note':'Synthetic editorial judgment'})
    def create(self):return self.a.create(self.cid,'Evaluate Atlas offline option','Decide whether it fits our synthetic workflow',['Read release notes','Try a local synthetic case'],'Editor','2026-12-01')
    def test_create(self):
        x=self.a.show(self.create());self.assertEqual(x['status'],'planned');self.assertEqual(x['basis_status'],'current_editorial_basis');self.assertEqual(x['completed_steps'],0);self.assertEqual(len(x['basis']['evidence']),2)
    def test_unreviewed_rejected(self):
        self.a.store.apply('review',{'claim_id':self.cid,'decision':'unreviewed'})
        with self.assertRaises(ActionError):self.create()
        self.assertEqual(self.a.listing(),[])
    def test_withheld_rejected(self):
        self.a.store.apply('review',{'claim_id':self.cid,'decision':'withhold'})
        with self.assertRaises(ActionError):self.create()
    def test_incomplete_checklist_blocks_done(self):
        aid=self.create()
        with self.assertRaises(ActionError):self.a.transition(aid,'done','Tried')
        self.assertEqual(self.a.show(aid)['status'],'planned')
    def test_complete(self):
        aid=self.create();self.a.transition(aid,'active','Starting locally')
        for i in range(2):self.a.check(aid,i,True,'Observed by user')
        self.a.transition(aid,'done','Human reports complete');self.assertEqual(self.a.show(aid)['status'],'done')
    def test_old_done_retained_with_warning(self):
        aid=self.create()
        for i in range(2):self.a.check(aid,i,True,'done')
        self.a.transition(aid,'done','done');self.a.store.apply('demo-update',{});x=self.a.show(aid);self.assertEqual(x['status'],'done');self.assertEqual(x['basis_status'],'needs_review');self.assertIn('Historical completion is not revalidated',markdown(x))
    def test_stale_blocks_done(self):
        aid=self.create()
        for i in range(2):self.a.check(aid,i,True,'done')
        self.a.store.apply('demo-update',{})
        with self.assertRaises(ActionError):self.a.transition(aid,'done','attempt')
    def test_edit_restore_not_current(self):
        aid=self.create();c=next(c for c in self.a.store.state()['claims'] if c['id']==self.cid)
        self.a.store.apply('claim',{'id':self.cid,'text':'Changed','topic':c['topic']});self.a.store.apply('claim',{'id':self.cid,'text':c['text'],'topic':c['topic']});self.assertEqual(self.a.show(aid)['basis_status'],'needs_review')
    def test_reapprove_requires_action_review_and_resets_steps(self):
        aid=self.create();self.a.check(aid,0,True,'Old progress');self.a.store.apply('review',{'claim_id':self.cid,'decision':'approve','note':'Rechecked basis'})
        self.assertEqual(self.a.show(aid)['basis_status'],'needs_review');self.a.rebase(aid,'Reviewed new editorial basis');x=self.a.show(aid);self.assertEqual(x['basis_status'],'current_editorial_basis');self.assertEqual(x['completed_steps'],0);self.assertTrue(x['history'][-1]['detail']['checklist_reset'])
    def test_same_basis_review_preserves_steps(self):
        aid=self.create();self.a.check(aid,0,True,'Progress');self.a.rebase(aid,'No material basis change');self.assertEqual(self.a.show(aid)['completed_steps'],1)
    def test_stale_cannot_rebase(self):
        aid=self.create();self.a.store.apply('demo-update',{})
        with self.assertRaises(ActionError):self.a.rebase(aid,'Tried review without current evidence')
    def test_cancel_allowed_when_stale(self):
        aid=self.create();self.a.store.apply('demo-update',{});self.a.transition(aid,'cancelled','No longer appropriate');self.assertEqual(self.a.show(aid)['status'],'cancelled')
    def test_closed_protects_history(self):
        aid=self.create();self.a.transition(aid,'cancelled','Stop')
        with self.assertRaises(ActionError):self.a.check(aid,0,True,'Progress')
        with self.assertRaises(ActionError):self.a.rebase(aid,'Review')
        with self.assertRaises(ActionError):self.a.edit(aid,'New','why','','','note')
        with self.assertRaises(ActionError):self.a.transition(aid,'active','Resume')
        self.a.transition(aid,'planned','Explicitly reopened');self.assertEqual(self.a.show(aid)['status'],'planned')
    def test_edit_keeps_history(self):
        aid=self.create();self.a.edit(aid,'New title','New reason','Other','2026-12-02','Scope clarified');x=self.a.show(aid);self.assertEqual(x['title'],'New title');self.assertEqual(x['history'][-1]['detail']['previous']['title'],'Evaluate Atlas offline option')
    def test_free_text_does_not_complete_task(self):
        aid=self.a.create(self.cid,'Send a message','Consider discussing news',['email team@example.invalid']);self.a.transition(aid,'active','Planning only');self.assertEqual(self.a.show(aid)['completed_steps'],0);self.assertFalse((self.p/'outbox').exists())
    def test_bad_inputs(self):
        for steps,due in [([],''),(['x']*21,''),(['x'],'2026-02-30'),(['x'],'2026-1-01'),(['\x00'],'')]:
            with self.subTest(due=due),self.assertRaises(ValueError):self.a.create(self.cid,'title','why',steps,due=due)
        self.assertEqual(self.a.listing(),[])
    def test_step_types(self):
        aid=self.create()
        for index,done in [(True,True),(0,1),(-1,True),(5,False)]:
            with self.assertRaises(ActionError):self.a.check(aid,index,done,'note')
    def test_uncheck(self):
        aid=self.create();self.a.check(aid,0,True,'done');self.a.check(aid,0,False,'Needs another try');self.assertEqual(self.a.show(aid)['completed_steps'],0)
    def test_restart(self):
        aid=self.create();self.a.check(aid,0,True,'done');b=Actions(self.p/'workspace.sqlite3');self.assertEqual(b.show(aid)['completed_steps'],1)
    def test_transaction_rollback(self):
        aid=self.create();old=self.a.show(aid)
        def fail(*args):raise ActionError('quota')
        self.a._event=fail
        with self.assertRaises(ActionError):self.a.check(aid,0,True,'done')
        self.assertEqual(old,self.a.show(aid))
    def test_portable_does_not_pretend_actions_included(self):
        self.create();project=self.a.store.portable();self.assertNotIn('news_actions',project['tables']);b=Actions(self.p/'import.sqlite3');b.store.apply('import',project);self.assertEqual(b.listing(),[])
    def test_escape_markdown(self):
        aid=self.a.create(self.cid,'<script>bad</script> [click](javascript:x)','<img src=x>', ['**task**']);out=markdown(self.a.show(aid));self.assertNotIn('<script>',out);self.assertNotIn('<img',out);self.assertIn('\\[click\\]',out)
    def test_cli(self):
        aid=self.create()
        def cli(*x):return subprocess.run([sys.executable,'-m','horizon.actions','--data-dir',str(self.p),*map(str,x)],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(cli('list').returncode,0);self.assertIn(self.cid,cli('claims').stdout);self.assertEqual(cli('status',aid,'done','--note','not finished').returncode,2)
        self.assertEqual(cli('check',aid,0,'--done','yes','--note','done').returncode,0)
        out=self.p/'action.md';self.assertEqual(cli('export',aid,'--format','markdown','--out',out).returncode,0);self.assertEqual(cli('export',aid,'--out',out).returncode,2);self.assertNotIn(b'\r',out.read_bytes())
if __name__=='__main__':unittest.main()
