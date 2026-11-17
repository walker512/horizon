"""Real SQLite backup/restore with synthetic workflow data, no network or real files."""
import json,os,sqlite3,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from horizon.workflow import Workflow
from horizon.backup import backup,restore,check,BackupError
ROOT=Path(__file__).resolve().parents[1]
class BackupTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.p=Path(self.t.name);self.dir=self.p/'original';self.w=Workflow(self.dir/'workspace.sqlite3');s=self.w.actions.store.apply('demo',{});self.cid=next(c['id'] for c in s['claims'] if c['evidence']);self.w.actions.store.apply('review',{'claim_id':self.cid,'decision':'approve','note':'Synthetic'});self.db=self.dir/'workspace.sqlite3';self.out=self.p/'backup.sqlite3'
    def populate(self):
        aid=self.w.actions.create(self.cid,'Plan','Why',['Step']);self.w.actions.check(aid,0,True,'Done');self.w.actions.transition(aid,'done','Human completion');eid=self.w.timeline.create(self.cid,'Event','other','unknown','','','','Unknown event time');f=self.p/'local.txt';f.write_text('Synthetic source file');self.w.watch.register(f,'https://example.invalid/backup','Local file');qid=self.w.radar.add('Synthetic','topic:synthetic',1);self.w.radar.collect(qid,lambda q,n:b'{"total_count":0,"incomplete_results":false,"items":[]}');return aid,eid,qid
    def test_full_counts(self):
        self.populate();r=backup(self.db,self.out);self.assertEqual(r['counts']['news_actions'],1);self.assertEqual(r['counts']['intel_events'],1);self.assertEqual(r['counts']['radar_runs'],1);self.assertEqual(r['counts']['local_watches'],1);self.assertEqual(check(self.out)['counts'],r['counts']);self.assertFalse(r['semantic_validation'])
    def test_restore_reset_and_retained_history(self):
        aid,eid,qid=self.populate();backup(self.db,self.out);new=self.p/'restored';r=restore(self.out,new,True);w=Workflow(new/'workspace.sqlite3');self.assertEqual(w.watch.listing(),[]);self.assertEqual(w.actions.show(aid)['status'],'done');self.assertEqual(w.actions.show(aid)['basis_status'],'needs_review');self.assertEqual(w.timeline.show(eid)['basis_status'],'needs_review');self.assertEqual(w.radar.review(qid)['status'],'observed');self.assertEqual(r['safety_reset']['local_file_registrations_removed'],1);self.assertEqual(self.w.actions.show(aid)['basis_status'],'current_editorial_basis')
    def test_original_backup_not_modified_on_restore(self):
        backup(self.db,self.out);raw=self.out.read_bytes();restore(self.out,self.p/'restored',True);self.assertEqual(raw,self.out.read_bytes())
    def test_existing_backup_not_replaced(self):
        self.out.write_bytes(b'private existing data')
        with self.assertRaises(BackupError):backup(self.db,self.out)
        self.assertEqual(self.out.read_bytes(),b'private existing data')
    def test_existing_restore_dir_refused(self):
        backup(self.db,self.out);target=self.p/'exists';target.mkdir();f=target/'sentinel';f.write_text('unchanged')
        with self.assertRaises(BackupError):restore(self.out,target,True)
        self.assertEqual(f.read_text(),'unchanged')
    def test_explicit_reset_ack(self):
        backup(self.db,self.out)
        for flag in (False,1,'true'):
            with self.assertRaises(BackupError):restore(self.out,self.p/'restore',flag)
        self.assertFalse((self.p/'restore').exists())
    def test_special_sources(self):
        if os.name=='nt':self.skipTest('POSIX FIFO/symlink capability not assumed.')
        f=self.p/'fifo';os.mkfifo(f)
        with self.assertRaises(BackupError):backup(f,self.out)
        link=self.p/'link';link.symlink_to(self.db)
        with self.assertRaises(BackupError):check(link)
    def test_unknown_schema(self):
        with closing(sqlite3.connect(self.db)) as db:db.execute('CREATE TABLE unknown(secret TEXT)');db.commit()
        with self.assertRaises(BackupError):backup(self.db,self.out)
        self.assertFalse(self.out.exists())
    def test_trigger_rejected(self):
        with closing(sqlite3.connect(self.db)) as db:db.execute('CREATE TRIGGER unwanted AFTER UPDATE ON claims BEGIN DELETE FROM audit; END;');db.commit()
        with self.assertRaises(BackupError):backup(self.db,self.out)
    def test_broken_foreign_key_rejected(self):
        with closing(sqlite3.connect(self.db)) as db:db.execute("UPDATE evidence SET snapshot_id='missing'");db.commit()
        with self.assertRaises(BackupError):backup(self.db,self.out)
    def test_corrupt_header(self):
        bad=self.p/'bad';bad.write_bytes(b'SECRET_SENTINEL'*10)
        with self.assertRaises(BackupError):check(bad)
    def test_copy_failure_no_public_partial(self):
        with patch('horizon.backup._copy',side_effect=sqlite3.OperationalError('disk failure')):
            with self.assertRaises(sqlite3.Error):backup(self.db,self.out)
        self.assertFalse(self.out.exists());self.assertFalse(list(self.p.glob('.horizon-backup-*')))
    def test_publish_failure_cleanup(self):
        with patch('horizon.backup._publish',side_effect=OSError('full')):
            with self.assertRaises(OSError):backup(self.db,self.out)
        self.assertFalse(self.out.exists());self.assertFalse(list(self.p.glob('.horizon-backup-*')))
    def test_restore_publish_failure_cleanup(self):
        backup(self.db,self.out);target=self.p/'new'
        with patch('horizon.backup._publish',side_effect=OSError('full')):
            with self.assertRaises(OSError):restore(self.out,target,True)
        self.assertFalse(target.exists());self.assertFalse(list(self.p.glob('.horizon-restore-*')))
    def test_live_wal_committed_data(self):
        # Keep writer open so the committed WAL contents have not been checkpointed away.
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
            db.execute("UPDATE claims SET topic='Committed WAL change' WHERE id=?",(self.cid,));db.commit();backup(self.db,self.out)
        with closing(sqlite3.connect(self.out)) as db:self.assertEqual(db.execute('SELECT topic FROM claims WHERE id=?',(self.cid,)).fetchone()[0],'Committed WAL change')
    def test_wal_restore_keeps_workflows_and_resets(self):
        aid,eid,qid=self.populate()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute("UPDATE claims SET review_note='WAL review note' WHERE id=?",(self.cid,));db.commit()
            backup(self.db,self.out);target=self.p/'wal-restored';restore(self.out,target,True)
        restored=Workflow(target/'workspace.sqlite3');self.assertEqual(restored.actions.show(aid)['status'],'done');self.assertEqual(restored.actions.show(aid)['basis_status'],'needs_review');self.assertEqual(restored.watch.listing(),[]);self.assertEqual(restored.radar.review(qid)['status'],'observed')
    def test_concurrent_transaction_consistency(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute("UPDATE claims SET text='pair-0',topic='pair-0' WHERE id=?",(self.cid,));db.commit()
        errors=[];ready=threading.Event();stop=threading.Event()
        def writer():
            try:
                with closing(sqlite3.connect(self.db,timeout=5)) as db:
                    i=1;ready.set()
                    while not stop.is_set() and i<100:
                        with db:db.execute('UPDATE claims SET text=?,topic=? WHERE id=?',('pair-'+str(i),'pair-'+str(i),self.cid))
                        i+=1
            except Exception as e:errors.append(type(e).__name__)
        thread=threading.Thread(target=writer);thread.start();ready.wait(3)
        try:backup(self.db,self.out)
        finally:stop.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        with closing(sqlite3.connect(self.out)) as db:
            a,b=db.execute('SELECT text,topic FROM claims WHERE id=?',(self.cid,)).fetchone();self.assertEqual(a,b)
    def test_cli(self):
        def cli(*args):return subprocess.run([sys.executable,'-m','horizon.backup',*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=10)
        r=cli('create','--data-dir',self.dir,'--out',self.out);self.assertEqual(r.returncode,0);self.assertIn('sha256',json.loads(r.stdout));self.assertNotIn(str(self.db),r.stdout)
        self.assertEqual(cli('check',self.out).returncode,0);new=self.p/'cli-restored';self.assertEqual(cli('restore',self.out,'--data-dir',new).returncode,2);self.assertEqual(cli('restore',self.out,'--data-dir',new,'--acknowledge-reset').returncode,0)
if __name__=='__main__':unittest.main()
