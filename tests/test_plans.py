"""Synthetic role-planning workflow, not model-generated recommendations."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from horizon.plans import Plans,PlanError,ROLES
from horizon.actions import ActionError
from horizon.backup import backup,restore
ROOT=Path(__file__).resolve().parents[1]
class PlansTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.x=Plans(self.p/'db'/'workspace.sqlite3');s=self.x.actions.store.apply('demo',{});c=next(c for c in s['claims'] if c['evidence']);self.cid=c['id'];self.eid=c['evidence'][0]['id'];self.x.actions.store.apply('review',{'claim_id':self.cid,'decision':'approve'})
    def spec(self,role='developer'):
        return {'role':role,'claim_id':self.cid,'slots':{name:[] for name in ROLES[role]},'interpretations':['This might reduce migration effort; not established by the quoted source.']}
    def test_draft_does_not_create_action(self):
        d=self.x.draft(self.spec());self.assertEqual(self.x.actions.listing(),[]);self.assertEqual(d['generation'],'deterministic_role_prompts_no_model');self.assertEqual(len(d['proposal']['steps']),5);self.assertTrue(all(s['status']=='missing_reference' for s in d['role_slots']))
    def test_both_roles(self):
        for role in ROLES:
            d=self.x.draft(self.spec(role));self.assertEqual([s['name'] for s in d['role_slots']],list(ROLES[role]))
    def test_reference_not_semantic_verification(self):
        s=self.spec();s['slots']['pricing']=[self.eid];d=self.x.draft(s);slot=next(x for x in d['role_slots'] if x['name']=='pricing');self.assertEqual(slot['status'],'referenced_not_semantically_verified');self.assertEqual(slot['references'][0]['id'],self.eid)
    def test_unverified_interpretations_separate(self):
        d=self.x.draft(self.spec());self.assertEqual(d['unverified_interpretations'][0]['status'],'unverified_human_interpretation');self.assertNotIn('reduce migration',d['captured_basis']['text'])
    def test_explicit_adoption(self):
        d=self.x.draft(self.spec());a=self.x.adopt(d,'Synthetic owner','2027-01-01');r=self.x.actions.show(a);self.assertEqual(r['owner'],'Synthetic owner');self.assertEqual(r['status'],'planned');self.assertEqual(r['completed_steps'],0);self.assertEqual(r['basis'],d['captured_basis']);self.assertIn('Unverified interpretations',r['why'])
    def test_stale_draft_rejected(self):
        d=self.x.draft(self.spec());sid=d['captured_basis']['evidence'][0]['source_id'];self.x.actions.store.apply('snapshot',{'source_id':sid,'text':'Synthetic correction','availability':'full'})
        with self.assertRaises(ValueError):self.x.adopt(d)
        self.assertEqual(self.x.actions.listing(),[])
    def test_tampered_draft_rejected(self):
        original=self.x.draft(self.spec())
        for modify in (lambda d:d['proposal']['steps'].append('Deploy now'),lambda d:d.update(template_version=999),lambda d:d.update(template_version=True),lambda d:d.update(template_version=1.0),lambda d:d['unverified_interpretations'][0].update(status='verified'),lambda d:d.update(extra='hidden')):
            d=copy.deepcopy(original);modify(d)
            with self.assertRaises(PlanError):self.x.adopt(d)
        self.assertEqual(self.x.actions.listing(),[])
    def test_race_change_before_commit_rejected(self):
        d=self.x.draft(self.spec());create=self.x.actions.create
        def race(*args,**kw):
            self.x.actions.store.apply('review',{'claim_id':self.cid,'decision':'approve','note':'New review changes basis'});return create(*args,**kw)
        with patch.object(self.x.actions,'create',side_effect=race):
            with self.assertRaises(ActionError):self.x.adopt(d)
        self.assertEqual(self.x.actions.listing(),[])
    def test_same_basis_complete_then_change_blocks(self):
        d=self.x.draft(self.spec());a=self.x.adopt(d)
        for i in range(5):self.x.actions.check(a,i,True,'Synthetic work recorded')
        self.x.actions.transition(a,'done','Explicit human completion');self.assertEqual(self.x.actions.show(a)['status'],'done')
        self.x.actions.store.apply('review',{'claim_id':self.cid,'decision':'withhold'});r=self.x.actions.show(a);self.assertEqual(r['status'],'done');self.assertEqual(r['basis_status'],'needs_review')
    def test_slots_reject_unknown_and_duplicate(self):
        for ids in (['not-a-link'],[self.eid,self.eid],[self.eid]*6):
            s=self.spec();s['slots']['pricing']=ids
            with self.assertRaises(ValueError):self.x.draft(s)
    def test_exact_schema(self):
        for mutate in (lambda s:s.update(extra=1),lambda s:s['slots'].pop('pricing'),lambda s:s.update(role='doctor'),lambda s:s.update(interpretations='not list')):
            s=self.spec();mutate(s)
            with self.assertRaises(ValueError):self.x.draft(s)
    def test_interpretation_limits(self):
        for values in (['x']*6,['x'*301],[''],[True]):
            s=self.spec();s['interpretations']=values
            with self.assertRaises(ValueError):self.x.draft(s)
    def test_large_adoptable_rationale_rejected(self):
        s=self.spec();s['interpretations']=['界'*300]*5
        with self.assertRaises(ValueError):self.x.draft(s)
    def test_serialized_size_checked_before_output(self):
        with patch('horizon.plans.basis',return_value={'evidence':[],'text':'x'*500000}):
            with self.assertRaises(PlanError):self.x.draft(self.spec())
    def test_backup_restore_cannot_adopt_old_draft(self):
        d=self.x.draft(self.spec());a=self.x.adopt(d);backup(self.p/'db'/'workspace.sqlite3',self.p/'copy');restore(self.p/'copy',self.p/'new',True);x=Plans(self.p/'new'/'workspace.sqlite3');self.assertEqual(x.actions.show(a)['status'],'planned')
        with self.assertRaises(ValueError):x.adopt(d)
    def test_cli(self):
        spec=self.p/'spec.json';spec.write_text(json.dumps(self.spec()));out=self.p/'draft.json'
        def cli(*a):return subprocess.run([sys.executable,'-m','horizon.plans','--data-dir',str(self.p/'db'),*a],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(cli('evidence',self.cid).returncode,0);r=cli('draft','--spec',str(spec),'--out',str(out));self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(self.x.actions.listing(),[]);self.assertEqual(cli('draft','--spec',str(spec),'--out',str(out)).returncode,2);r=cli('adopt','--draft',str(out),'--owner','Synthetic');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(len(self.x.actions.listing()),1)
if __name__=='__main__':unittest.main()
