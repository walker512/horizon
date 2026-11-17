"""Local source tracking; original synthetic policy text, no fetching or real policies."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from horizon.watch import Watch,WatchError,read_source
ROOT=Path(__file__).resolve().parents[1]
class WatchTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name);self.f=self.p/'policy.txt';self.f.write_text('Synthetic policy. Exports allowed.\n');self.w=Watch(self.p/'db'/'workspace.sqlite3');self.sid=self.w.register(self.f,'https://example.invalid/policy','Synthetic policy')
    def snapshot_count(self):return len(self.w.store.state()['sources'][0]['snapshots'])
    def approve(self):
        s=self.w.store.state()['sources'][0];state=self.w.store.apply('claim',{'text':'Exports allowed.'});c=state['claims'][0]['id'];self.w.store.apply('evidence',{'claim_id':c,'snapshot_id':s['latest']['id'],'quote':'Exports allowed.','relation':'supports'});self.w.store.apply('review',{'claim_id':c,'decision':'approve'});return c
    def test_default_summary(self):
        self.assertEqual(self.w.store.state()['sources'][0]['latest']['availability'],'summary');self.f.write_text('Changed text');self.w.scan();self.assertEqual(self.w.store.state()['sources'][0]['latest']['availability'],'summary')
    def test_full_declaration(self):
        self.w.untrack(self.sid);self.w.register(self.f,'https://example.invalid/policy','Policy',availability='full');self.f.write_text('Changed text');self.w.scan();self.assertEqual(self.w.store.state()['sources'][0]['latest']['availability'],'full')
    def test_registered(self):self.assertEqual(self.snapshot_count(),1);self.assertEqual(len(self.w.listing()),1)
    def test_unchanged(self):
        self.assertEqual(self.w.scan()[0]['result'],'unchanged');self.assertEqual(self.snapshot_count(),1)
    def test_changed_snapshot(self):
        self.f.write_text('Synthetic policy. Exports restricted.\n');self.assertEqual(self.w.scan()[0]['result'],'changed');self.assertEqual(self.snapshot_count(),2);r=self.w.changes(self.sid);self.assertEqual(r['diff_status'],'text_changed');self.assertIn('+Synthetic policy. Exports restricted.\n',r['diff'])
    def test_failed_not_deletion(self):
        self.f.unlink();self.assertEqual(self.w.scan()[0]['result'],'unavailable');self.assertEqual(self.w.changes(self.sid)['diff_status'],'unavailable_not_deletion');self.assertEqual(self.w.changes(self.sid)['diff'],[])
    def test_failed_idempotent(self):
        self.f.unlink();self.w.scan();r=self.w.scan()[0];self.assertFalse(r['new_version']);self.assertEqual(self.snapshot_count(),2)
    def test_recovery(self):
        self.f.unlink();self.w.scan();self.f.write_text('Synthetic policy. Exports allowed.\n');self.assertEqual(self.w.scan()[0]['result'],'recovered');self.assertEqual(self.w.changes(self.sid)['diff_status'],'same_text_as_comparison_base');self.assertEqual(len(self.w.changes(self.sid)['timeline']),3)
    def test_approval_invalidation(self):
        c=self.approve();self.f.write_text('Synthetic policy. Exports restricted.\n');self.w.scan();state=self.w.store.state()['claims'][0];self.assertEqual(state['review_signature'],'invalidated');self.assertEqual(state['status'],'needs-review');self.assertEqual(self.w.changes(self.sid)['affected_claims'][0]['id'],c)
        self.f.write_text('Synthetic policy. Exports allowed.\n');self.w.scan();self.assertEqual(self.w.store.state()['claims'][0]['status'],'needs-review')
    def test_unchanged_approval(self):self.approve();self.w.scan();self.assertEqual(self.w.store.state()['claims'][0]['status'],'editor-approved')
    def test_failed_invalidates(self):self.approve();self.f.unlink();self.w.scan();self.assertEqual(self.w.store.state()['claims'][0]['status'],'needs-review')
    def test_untrack_preserves(self):
        self.w.untrack(self.sid);self.assertEqual(self.w.listing(),[]);self.assertEqual(self.snapshot_count(),1);self.assertEqual(self.w.scan(),[])
    def test_duplicate_registration(self):
        with self.assertRaises(WatchError):self.w.register(self.f,'https://example.invalid/policy','Again')
        self.assertEqual(self.snapshot_count(),1)
    def test_portable_no_local_path(self):
        export=self.w.store.portable();self.assertNotIn(str(self.f),json.dumps(export));other=Watch(self.p/'other'/'db.sqlite3');other.store.apply('import',export);self.assertEqual(other.listing(),[]);self.assertEqual(len(other.store.state()['sources']),1)
    def test_report_no_local_path(self):
        self.assertNotIn(str(self.f),json.dumps(self.w.changes(self.sid)));self.assertNotIn(str(self.f),json.dumps(self.w.listing()))
    def test_first_version(self):self.assertEqual(self.w.changes(self.sid)['diff_status'],'first_available_version')
    def test_large_diff_explicit_omission(self):
        self.f.write_text('word\n'*1001);self.w.scan();r=self.w.changes(self.sid);self.assertEqual(r['diff_status'],'changed_diff_omitted_size_limit');self.assertEqual(r['diff'],[])
    def test_invalid_files(self):
        for content in [b'',b'\xff',b'\x00',b' '*10,b'x'*500001]:
            self.f.write_bytes(content)
            with self.assertRaises(WatchError):read_source(self.f)
    def test_fifo_symlink(self):
        if os.name=='nt':self.skipTest('POSIX FIFO/symlink test.')
        q=self.p/'fifo';os.mkfifo(q)
        with self.assertRaises(WatchError):read_source(q)
        q.unlink();q.symlink_to(self.f)
        with self.assertRaises(WatchError):read_source(q)
    def test_transaction_rollback(self):
        # Simulate a database quota validation failure after one source mutation.
        f=self.p/'other.txt';f.write_text('Other policy');self.w.register(f,'https://example.invalid/other','Other');self.f.write_text('Changed');f.write_text('Changed other');before=self.w.store.portable()['tables'];original=self.w.store.snapshot;count=[0]
        def fail(db,data):
            count[0]+=1
            if count[0]==2:raise ValueError('quota')
            return original(db,data)
        self.w.store.snapshot=fail
        with self.assertRaises(ValueError):self.w.scan()
        self.assertEqual(before,self.w.store.portable()['tables']);self.assertTrue(all(x['last_result']=='registered' for x in self.w.listing()))
    def test_existing_source_registration_invalidates(self):
        self.approve();self.w.untrack(self.sid);self.f.write_text('New text');self.w.register(self.f,'https://example.invalid/policy','Ignored metadata');self.assertEqual(self.w.store.state()['claims'][0]['status'],'needs-review')
    def test_cli(self):
        def cli(*a):return subprocess.run([sys.executable,'-m','horizon.watch','--data-dir',str(self.p/'db'),*map(str,a)],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(cli('list').returncode,0);self.assertEqual(cli('scan').returncode,0)
        out=self.p/'review.json';self.assertEqual(cli('changes',self.sid,'--out',out).returncode,0);self.assertEqual(cli('changes',self.sid,'--out',out).returncode,2);self.assertIn('timeline',json.loads(out.read_text()))
        self.f.unlink();self.assertEqual(cli('scan').returncode,3);self.assertEqual(cli('untrack',self.sid).returncode,0)
if __name__=='__main__':unittest.main()
