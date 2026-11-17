"""Explicit local source-file tracking. No URL fetching or background scheduler."""
import argparse,difflib,json,os,sqlite3,stat,sys
from pathlib import Path
from .model import Store,now,safe_url,text

class WatchError(ValueError):pass

def read_source(path):
    try:
        if not stat.S_ISREG(Path(path).lstat().st_mode):raise WatchError('Expected a regular non-symlink source file.')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_BINARY',0))
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size>2*1024*1024:raise WatchError('Invalid source file type or size.')
            with os.fdopen(fd,'rb') as f:fd=None;raw=f.read(2*1024*1024+1)
        finally:
            if fd is not None:os.close(fd)
        if len(raw)>2*1024*1024:raise WatchError('Source exceeds byte limit.')
        value=raw.decode('utf8')
        if not value.strip() or len(value)>500000 or '\x00' in value:raise WatchError('Source must contain 1..500000 text characters without NUL.')
        return value
    except (OSError,UnicodeError):raise WatchError('Source is unavailable or not valid UTF-8.') from None

def invalidate(store,db,before):
    for c in store.state(db)['claims']:
        old=before.get(c['id'])
        if old and old['review_signature'] and old['review_signature']!='invalidated' and old['signature']!=c['signature']:
            db.execute("UPDATE claims SET review_signature='invalidated' WHERE id=?",(c['id'],))
            store.log(db,'review-invalidated',{'claim_id':c['id'],'operation':'local-watch','previous_signature':old['review_signature']})

class Watch:
    def __init__(self,dbpath):
        self.store=Store(dbpath)
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS local_watches(source_id TEXT PRIMARY KEY REFERENCES sources(id),local_path TEXT NOT NULL,availability TEXT NOT NULL,last_checked TEXT NOT NULL,last_result TEXT NOT NULL)')
    def register(self,path,url,title,kind='report',availability='summary'):
        if availability not in ('full','summary'):raise WatchError('Explicit file availability must be full or summary.')
        content=read_source(path);url=safe_url(url);text(title,'Title',300)
        absolute=os.path.abspath(path)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM local_watches').fetchone()[0]>=50:raise WatchError('At most 50 registered local files.')
            if db.execute('SELECT 1 FROM local_watches w JOIN sources s ON s.id=w.source_id WHERE s.url=?',(url,)).fetchone():raise WatchError('This source is already tracked; untrack before changing its local file.')
            before={c['id']:c for c in self.store.state(db)['claims']}
            sid=self.store.source(db,{'title':title,'url':url,'kind':kind,'text':content,'availability':availability})
            db.execute('INSERT INTO local_watches VALUES(?,?,?,?,?)',(sid,absolute,availability,now(),'registered'))
            self.store.log(db,'local-watch-registered',{'source_id':sid})
            invalidate(self.store,db,before)
            return sid
    def untrack(self,sid):
        with self.store.connect() as db:
            if not db.execute('DELETE FROM local_watches WHERE source_id=?',(sid,)).rowcount:raise WatchError('Tracked source not found.')
            self.store.log(db,'local-watch-removed',{'source_id':sid})
    def listing(self):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('SELECT w.source_id,s.title,s.url,w.availability,w.last_checked,w.last_result FROM local_watches w JOIN sources s ON s.id=w.source_id ORDER BY w.rowid')]
    def scan(self):
        # All successfully read contents and unavailable markers commit together.
        # Database quota/validation failures roll back the whole scan, not a subset.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');before={c['id']:c for c in self.store.state(db)['claims']};results=[]
            for row in db.execute('SELECT * FROM local_watches ORDER BY rowid').fetchall():
                old=db.execute('SELECT * FROM snapshots WHERE source_id=? ORDER BY rowid DESC LIMIT 1',(row['source_id'],)).fetchone()
                try:content=read_source(row['local_path']);availability=row['availability'];error=''
                except WatchError:content='';availability='failed';error='Registered local file is unavailable, invalid, or exceeds the text limits. No deletion or policy-change inference is made.'
                new=self.store.snapshot(db,{'source_id':row['source_id'],'text':content,'availability':availability,'error':error})
                status='unavailable' if availability=='failed' else ('unchanged' if old and old['id']==new else ('recovered' if old and old['availability']=='failed' else 'changed'))
                db.execute('UPDATE local_watches SET last_checked=?,last_result=? WHERE source_id=?',(now(),status,row['source_id']))
                results.append({'source_id':row['source_id'],'previous_snapshot':old['id'] if old else None,'snapshot_id':new,'result':status,'new_version':not old or new!=old['id']})
            invalidate(self.store,db,before)
            if results:self.store.log(db,'local-watch-scan',{'results':results})
            return results
    def changes(self,sid):
        state=self.store.state();source=next((s for s in state['sources'] if s['id']==sid),None)
        if source is None:raise WatchError('Source not found.')
        snapshots=source['snapshots'];latest=snapshots[0];base=next((s for s in snapshots[1:] if s['availability']!='failed'),None)
        report={'source_id':sid,'title':source['title'],'url':source['url'],'kind':source['kind'],'observed_at':latest['created_at'],'latest_snapshot':latest['id'],'latest_availability':latest['availability'],'latest_hash':latest['hash'],'comparison_base':base['id'] if base else None,'comparison_base_observed_at':base['created_at'] if base else None,'comparison_base_hash':base['hash'] if base else None,'timeline':[{'snapshot_id':s['id'],'observed_at':s['created_at'],'availability':s['availability'],'hash':s['hash']} for s in reversed(snapshots)],'diff':[],'affected_claims':[{'id':c['id'],'text':c['text'],'status':c['status'],'decision':c['decision'],'linked_versions':sorted(set(e['snapshot_id'] for e in c['evidence'] if e['source_id']==sid))} for c in state['claims'] if any(e['source_id']==sid for e in c['evidence'])]}
        if latest['availability']=='failed':report['diff_status']='unavailable_not_deletion'
        elif base is None:report['diff_status']='first_available_version'
        elif latest['text']==base['text']:report['diff_status']='same_text_as_comparison_base'
        elif len(latest['text'])>100000 or len(base['text'])>100000 or len(latest['text'].splitlines())>1000 or len(base['text'].splitlines())>1000:report['diff_status']='changed_diff_omitted_size_limit'
        else:
            report['diff_status']='text_changed';report['diff']=list(difflib.unified_diff(base['text'].splitlines(keepends=True),latest['text'].splitlines(keepends=True),fromfile='previous_available',tofile='latest',n=3))
        return report

def main():
    p=argparse.ArgumentParser(description='Track explicitly registered local policy/source text files. No network fetch.')
    p.add_argument('--data-dir',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('register');r.add_argument('--file',required=True);r.add_argument('--url',required=True);r.add_argument('--title',required=True);r.add_argument('--kind',choices=['primary','report','relay','summary'],default='report');r.add_argument('--availability',choices=['full','summary'],default='summary')
    sub.add_parser('list');sub.add_parser('scan')
    u=sub.add_parser('untrack');u.add_argument('source_id')
    c=sub.add_parser('changes');c.add_argument('source_id');c.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        w=Watch(Path(a.data_dir)/'workspace.sqlite3')
        if a.command=='register':result={'source_id':w.register(a.file,a.url,a.title,a.kind,a.availability)}
        elif a.command=='list':result={'tracked_sources':w.listing()}
        elif a.command=='scan':
            result={'results':w.scan()};print(json.dumps(result,ensure_ascii=True));return 3 if any(x['result']=='unavailable' for x in result['results']) else 0
        elif a.command=='untrack':w.untrack(a.source_id);result={'untracked':a.source_id,'source_history_retained':True}
        else:
            raw=(json.dumps(w.changes(a.source_id),ensure_ascii=True,indent=2)+'\n').encode('ascii')
            if len(raw)>4*1024*1024:raise WatchError('Change report exceeds output limit.')
            with open(a.out,'xb') as f:f.write(raw)
            result={'exported':True}
        print(json.dumps(result,ensure_ascii=True));return 0
    except (ValueError,OSError,sqlite3.Error,TypeError,KeyError):
        print('Operation failed. Check explicit source registration, input format/limits, workspace quota and output availability. No path or source text is echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
