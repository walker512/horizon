"""Consistent local workspace copies. Trusted backups only; not a database sanitizer."""
import argparse,hashlib,json,os,sqlite3,stat,sys,tempfile,time
from datetime import datetime,timezone
from contextlib import closing
from pathlib import Path

class BackupError(ValueError):pass
MAX_BYTES=512*1024*1024
COLUMNS={
'project_registry':['id','repo_id','full_name','query_id','selected_run','created_at'],
'project_runs':['id','project_id','observed_at','status','detail'],
'project_profiles':['id','project_id','run_id','spec','basis','recorded_at','withdrawn','withdrawal_note'],
'community_runs':['id','feed','sample_size','keyword','observed_at','status','error','observation'],
'product_observations':['id','claim_id','evidence_id','spec','basis','recorded_at','withdrawn','withdrawal_note'],
'sources':['id','title','url','kind','origin_group'],
'snapshots':['id','source_id','text','availability','error','created_at','hash'],
'claims':['id','text','topic','decision','review_signature','review_note','reviewed_at'],
'evidence':['id','claim_id','snapshot_id','start','end','relation','note','removed'],
'audit':['id','time','action','detail'],
'local_watches':['source_id','local_path','availability','last_checked','last_result'],
'radar_queries':['id','label','query','per_page','created_at'],
'radar_runs':['id','query_id','observed_at','status','error','observation'],
'news_actions':['id','claim_id','title','why','owner','due_date','status','checklist','basis','created_at','updated_at'],
'news_action_events':['id','action_id','time','operation','detail'],
'intel_events':['id','claim_id','title','kind','time_window','basis','status','note','recorded_at','updated_at'],
'intel_event_history':['id','event_id','time','operation','detail'],
}
REQUIRED={'sources','snapshots','claims','evidence','audit'}

def regular(path):
    try:
        p=Path(path)
        if not stat.S_ISREG(p.lstat().st_mode):raise BackupError('Expected a regular non-symlink SQLite file.')
        fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_BINARY',0))
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or not 16<=s.st_size<=MAX_BYTES or os.read(fd,16)!=b'SQLite format 3\x00':raise BackupError('Invalid or oversized SQLite file.')
        finally:os.close(fd)
        return p.absolute()
    except OSError:raise BackupError('Cannot read SQLite file safely.') from None

def readonly(path):
    p=regular(path);db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=1)
    db.execute('PRAGMA trusted_schema=OFF');db.enable_load_extension(False)
    return db

def inspect_connection(db):
    deadline=time.monotonic()+10
    db.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,10000)
    try:
        if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise BackupError('SQLite structural integrity check failed.')
        objects=db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall();tables=set()
        for typ,name,sql in objects:
            if typ!='table' or name not in COLUMNS or not sql or 'VIRTUAL TABLE' in sql.upper():raise BackupError('Unknown tables, views, triggers or explicit indexes are not supported.')
            columns=[r[1] for r in db.execute('PRAGMA table_info("'+name+'")')]
            if columns!=COLUMNS[name]:raise BackupError('Workspace schema is not supported.')
            tables.add(name)
        if not REQUIRED<=tables:raise BackupError('Required editorial workspace tables are missing.')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:raise BackupError('Workspace has broken foreign-key relationships.')
        return {name:db.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0] for name in sorted(tables)}
    finally:db.set_progress_handler(None,0)

def check(path):
    with closing(readonly(path)) as db:counts=inspect_connection(db)
    return {'format':'horizon-sqlite-workspace','structural_check':'passed','counts':counts,'semantic_validation':False,'authenticity_verified':False}

def _copy(source,destination):
    # SQLite's online backup API includes committed journal/WAL contents.
    with closing(readonly(source)) as src:
        inspect_connection(src)
        with closing(sqlite3.connect(destination,timeout=1)) as dst:
            deadline=time.monotonic()+15
            page_size=src.execute('PRAGMA page_size').fetchone()[0]
            def progress(status,remaining,total):
                if total*page_size>MAX_BYTES:raise BackupError('Snapshot exceeds size bound.')
                if time.monotonic()>deadline:raise BackupError('Snapshot exceeded copy deadline; no output published.')
            src.backup(dst,pages=128,progress=progress,sleep=.05)
            inspect_connection(dst)
    if Path(destination).stat().st_size>MAX_BYTES:raise BackupError('Snapshot exceeds file size bound.')

def _hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def _publish(temp,out):
    # Same-directory hard link publishes the complete file without replacing any existing path.
    with open(temp,'rb') as f:os.fsync(f.fileno())
    os.link(temp,out)

def backup(source,out):
    out=Path(out)
    if os.path.lexists(out):raise BackupError('Backup destination already exists.')
    regular(source)
    fd,temp=tempfile.mkstemp(prefix='.horizon-backup-',suffix='.sqlite3',dir=out.parent);os.close(fd)
    try:
        _copy(source,temp);result=check(temp);result['sha256']=_hash(temp);_publish(temp,out);return result
    finally:
        for p in (temp,temp+'-journal',temp+'-wal',temp+'-shm'):
            try:os.unlink(p)
            except FileNotFoundError:pass

def restore(source,data_dir,acknowledge_reset=False):
    if acknowledge_reset is not True:raise BackupError('Explicit --acknowledge-reset is required for restoring into a new directory.')
    target=Path(data_dir)
    if os.path.lexists(target):raise BackupError('Restore requires a nonexistent data directory.')
    regular(source)
    fd,temp=tempfile.mkstemp(prefix='.horizon-restore-',suffix='.sqlite3',dir=target.parent);os.close(fd);made=False
    try:
        _copy(source,temp)
        with closing(sqlite3.connect(temp,timeout=1)) as db:
            counts=inspect_connection(db)
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE claims SET decision='unreviewed',review_signature=NULL,reviewed_at=NULL")
            removed=counts.get('local_watches',0)
            if 'local_watches' in counts:db.execute('DELETE FROM local_watches')
            detail={'claims_reset_for_review':counts['claims'],'local_file_registrations_removed':removed,'note':'Trusted backup copy restored; history is supplied, not authenticated. No source files were read and no network request was made.'}
            db.execute('INSERT INTO audit(time,action,detail) VALUES(?,?,?)',(datetime.now(timezone.utc).isoformat(),'workspace-restored',json.dumps(detail,ensure_ascii=True)))
            db.commit()
        result=check(temp);result['safety_reset']=detail;result['sha256']=_hash(temp)
        target.mkdir(mode=0o700);made=True;_publish(temp,target/'workspace.sqlite3');return result
    except BaseException:
        if made:
            try:target.rmdir() # never recursively remove unknown files
            except OSError:pass
        raise
    finally:
        for p in (temp,temp+'-journal',temp+'-wal',temp+'-shm'):
            try:os.unlink(p)
            except FileNotFoundError:pass

def main():
    p=argparse.ArgumentParser(description='Local full-workspace SQLite backup and safe-new-directory restore. Use trusted backups only.')
    sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('create');b.add_argument('--data-dir',required=True);b.add_argument('--out',required=True)
    c=sub.add_parser('check');c.add_argument('file')
    r=sub.add_parser('restore');r.add_argument('file');r.add_argument('--data-dir',required=True);r.add_argument('--acknowledge-reset',action='store_true')
    a=p.parse_args()
    try:
        result=backup(Path(a.data_dir)/'workspace.sqlite3',a.out) if a.command=='create' else check(a.file) if a.command=='check' else restore(a.file,a.data_dir,a.acknowledge_reset)
        print(json.dumps(result,sort_keys=True));return 0
    except (BackupError,sqlite3.Error,OSError,ValueError,OverflowError):print('Backup operation rejected. Check trusted input/schema, file limits, new destination and available storage. No paths or source contents echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
