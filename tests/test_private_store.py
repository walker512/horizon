import concurrent.futures
import os
from pathlib import Path
import sqlite3
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
from horizon.model import Store
from horizon.backup import backup, restore


@unittest.skipUnless(os.name == 'posix', 'POSIX storage contract')
class PrivateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def mode(self, path):
        return path.stat().st_mode & 0o777

    def test_created_private_before_sqlite_opens_and_no_umask_change(self):
        for mask in (0, 0o022):
            old = os.umask(mask)
            try:
                path = self.root / str(mask) / 'nested' / 'workspace.sqlite3'
                original = sqlite3.connect
                def connect(*a, **kw):
                    self.assertEqual(self.mode(path), 0o600)
                    self.assertEqual(self.mode(path.parent), 0o700)
                    self.assertEqual(self.mode(path.parent.parent), 0o700)
                    return original(*a, **kw)
                with patch('horizon.model.sqlite3.connect', connect):
                    Store(path)
                probe = self.root / ('probe' + str(mask))
                probe.write_text('x')
                self.assertEqual(self.mode(probe), 0o666 & ~mask)
            finally:
                os.umask(old)

    def test_live_journal_wal_shm_private(self):
        old = os.umask(0)
        try:
            p = self.root/'data'/'workspace.sqlite3'
            store = Store(p)
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute("INSERT INTO claims(id,text,topic) VALUES('a','secret','')")
                self.assertEqual(self.mode(Path(str(p)+'-journal')), 0o600)
                db.commit()
                db.execute('PRAGMA journal_mode=WAL')
                db.execute("UPDATE claims SET text='private'")
                db.commit()
                for suffix in ('-wal', '-shm'):
                    self.assertEqual(self.mode(Path(str(p)+suffix)), 0o600)
                with store.connect() as other:
                    self.assertEqual(other.execute('SELECT text FROM claims').fetchone()[0], 'private')
        finally:
            os.umask(old)

    def test_rejects_existing_permissions_without_chmod(self):
        parent = self.root/'public';parent.mkdir(mode=0o755)
        with self.assertRaises(ValueError): Store(parent/'db')
        self.assertFalse((parent/'db').exists())
        self.assertEqual(self.mode(parent),0o755)
        p=self.root/'db';p.write_bytes(b'secret');p.chmod(0o644)
        with self.assertRaises(ValueError): Store(p)
        self.assertEqual(p.read_bytes(),b'secret')
        self.assertEqual(self.mode(p),0o644)

    def test_rejects_links_and_nonregular(self):
        target=self.root/'target';target.write_text('keep');target.chmod(0o600)
        for kind in ('symlink','hardlink','fifo'):
            p=self.root/kind
            if kind=='symlink':p.symlink_to(target)
            elif kind=='hardlink':os.link(target,p)
            else:os.mkfifo(p,0o600)
            with self.assertRaises((ValueError,OSError)): Store(p)
        folder=self.root/'alias';folder.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):Store(folder/'db')
        self.assertEqual(target.read_text(),'keep')

    def test_existing_unsafe_sidecars_rejected_before_connect(self):
        for suffix in ('-journal','-wal','-shm'):
            p=self.root/(suffix+'db');store=Store(p)
            side=Path(str(p)+suffix);side.write_text('secret');side.chmod(0o644)
            with patch('horizon.model.sqlite3.connect') as connect:
                with self.assertRaises(ValueError):store.connect()
                connect.assert_not_called()
            side.unlink()
            target=self.root/(suffix+'target');target.write_text('keep');target.chmod(0o600)
            side.symlink_to(target)
            with self.assertRaises(OSError):store.connect()
            self.assertEqual(target.read_text(),'keep')

    def test_concurrent_initialization_and_writes(self):
        p=self.root/'shared'/'nested'/'db'
        def run(i):
            store=Store(p)
            with store.connect() as db:
                db.execute('INSERT INTO claims(id,text,topic) VALUES(?,?,?)',(str(i),'secret',''))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(run,range(24)))
        with Store(p).connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM claims').fetchone()[0],24)
        self.assertEqual(self.mode(p),0o600)

    def test_reconnect_checks_permissions_and_does_not_recreate(self):
        p=self.root/'db';store=Store(p);p.chmod(0o644)
        with self.assertRaises(ValueError):store.connect()
        p.unlink()
        with self.assertRaises(FileNotFoundError):store.connect()
        self.assertFalse(p.exists())

    def test_restore_creates_private_usable_workspace(self):
        p=self.root/'data'/'workspace.sqlite3';Store(p)
        backup(p,self.root/'copy')
        restore(self.root/'copy',self.root/'restored',True)
        p=self.root/'restored'/'workspace.sqlite3'
        self.assertEqual(self.mode(p.parent),0o700)
        self.assertEqual(self.mode(p),0o600)
        Store(p)

    def test_separate_process_initialization(self):
        p=self.root/'processes'/'db'
        code="from horizon.model import Store; import sys; s=Store(sys.argv[1]); s.apply('claim',{'text':sys.argv[2]})"
        processes=[subprocess.Popen([sys.executable,'-c',code,str(p),str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(6)]
        for proc in processes:
            out,err=proc.communicate(timeout=20)
            self.assertEqual(proc.returncode,0,err.decode())
        with Store(p).connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM claims').fetchone()[0],6)

    def test_sidecar_unlinked_after_open_retries_path(self):
        from horizon.private_store import prepare
        p=self.root/'db';Store(p)
        for suffix in ('-journal','-wal','-shm'):
            side=Path(str(p)+suffix);side.touch(mode=0o600)
            original=os.open
            def opening(path,*a,**kw):
                fd=original(path,*a,**kw)
                if Path(path)==side:side.unlink()
                return fd
            with patch('horizon.private_store.os.open',opening):prepare(p,create=False)
            self.assertFalse(side.exists())

    def test_unlinked_sidecar_replacement_hardlink_is_rejected(self):
        from horizon.private_store import prepare
        p=self.root/'db';Store(p)
        side=Path(str(p)+'-journal');side.touch(mode=0o600)
        target=self.root/'secret';target.write_text('private');target.chmod(0o600)
        original=os.open;first=True
        def opening(path,*a,**kw):
            nonlocal first
            fd=original(path,*a,**kw)
            if Path(path)==side and first:
                first=False;side.unlink();os.link(target,side)
            return fd
        with patch('horizon.private_store.os.open',opening):
            with self.assertRaises(ValueError):prepare(p,create=False)
        self.assertEqual(target.read_text(),'private')

    def test_sidecar_churn_bounded_and_main_unlink_still_rejected(self):
        from horizon.private_store import prepare
        p=self.root/'db';Store(p)
        side=Path(str(p)+'-journal');side.touch(mode=0o600)
        original=os.open;count=0
        def opening(path,*a,**kw):
            nonlocal count
            fd=original(path,*a,**kw)
            if Path(path)==side:
                count+=1;side.unlink();os.close(original(side,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
            return fd
        with patch('horizon.private_store.os.open',opening):
            with self.assertRaisesRegex(ValueError,'repeatedly'):prepare(p,create=False)
        self.assertEqual(count,16)
        def unlink_db(path,*a,**kw):
            fd=original(path,*a,**kw)
            if Path(path)==p:p.unlink()
            return fd
        with patch('horizon.private_store.os.open',unlink_db):
            with self.assertRaises(ValueError):prepare(p,create=False)
