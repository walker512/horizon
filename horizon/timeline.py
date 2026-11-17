"""Human-declared event windows with retained editorial evidence; not factual chronology."""
import argparse,json,sqlite3,sys,re
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from pathlib import Path
from .model import Store,key,now,digest
from .actions import basis,bounded,ActionError

class TimelineError(ValueError):pass
KINDS=('release','policy','security','community','other')
STAGES=('released','planned','reported','rumor','unknown')
def window(precision,start='',end='',zone=''):
    for x in (precision,start,end,zone):
        if type(x) is not str:raise TimelineError('Event time fields must be text.')
    if precision=='unknown':
        if start or end or zone:raise TimelineError('Unknown time must not carry invented boundaries or a zone.')
        return {'precision':precision,'start':'','end':'','zone':'','lower_utc':None,'upper_utc':None}
    if precision=='day':
        if not zone or len(zone)>100:raise TimelineError('Day precision requires an explicit IANA time zone.')
        try:
            tz=ZoneInfo(zone)
            if not re.fullmatch(r'\d{4}-\d\d-\d\d',start) or (end and not re.fullmatch(r'\d{4}-\d\d-\d\d',end)):raise ValueError()
            a=date.fromisoformat(start);b=date.fromisoformat(end or start)
            if not 1900<=a.year<=2100 or not 1900<=b.year<=2100 or not 0<=(b-a).days<=3660:raise ValueError()
            # Roundtrip midnight and next midnight: reject skipped/ambiguous boundaries.
            def boundary(d):
                naive=datetime.combine(d,time());valid=[]
                for fold in (0,1):
                    x=naive.replace(tzinfo=tz,fold=fold);utc=x.astimezone(timezone.utc)
                    if utc.astimezone(tz).replace(tzinfo=None)==naive and utc not in valid:valid.append(utc)
                if len(valid)!=1:raise TimelineError('Day boundary is nonexistent or ambiguous in that zone; supply an explicit offset interval instead.')
                return valid[0]
            lo=boundary(a);hi=boundary(b+timedelta(days=1))-timedelta(microseconds=1)
            if hi<lo:raise TimelineError('Calendar window has no instants.')
        except (ValueError,ZoneInfoNotFoundError,OverflowError):raise TimelineError('Invalid day range/zone; use explicit valid calendar boundaries.') from None
    elif precision=='instant':
        if zone:raise TimelineError('Offset-bearing instants must not also supply a zone.')
        def instant(s):
            if not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)',s):raise TimelineError('Instant requires ISO date/time with seconds and an explicit UTC offset.')
            if s.endswith('-00:00'):raise TimelineError('Unknown -00:00 offset is not treated as UTC; supply a known offset or unknown time.')
            if not s.endswith('Z') and (int(s[-5:-3])>23 or int(s[-2:])>59):raise TimelineError('Invalid UTC offset.')
            try:x=datetime.fromisoformat(s.replace('Z','+00:00'))
            except ValueError:raise TimelineError('Invalid offset-bearing timestamp.') from None
            if not 1900<=x.year<=2100:raise TimelineError('Supported event years: 1900..2100.')
            return x.astimezone(timezone.utc)
        lo=instant(start);hi=instant(end or start)
        if not timedelta(0)<=hi-lo<=timedelta(days=3661):raise TimelineError('Reversed or excessively wide event interval.')
    else:raise TimelineError('Precision must be day, instant or unknown.')
    return {'precision':precision,'start':start,'end':end or start,'zone':zone,'lower_utc':lo.isoformat(timespec='microseconds'),'upper_utc':hi.isoformat(timespec='microseconds')}

class Timeline:
    def __init__(self,path):
        self.store=Store(path)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS intel_events(id TEXT PRIMARY KEY,claim_id TEXT NOT NULL REFERENCES claims(id),title TEXT NOT NULL,kind TEXT NOT NULL,time_window TEXT NOT NULL,basis TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL,recorded_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intel_event_history(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL REFERENCES intel_events(id),time TEXT NOT NULL,operation TEXT NOT NULL,detail TEXT NOT NULL);''')
    def _claim(self,db,cid):
        c=next((x for x in self.store.state(db)['claims'] if x['id']==cid),None)
        if c is None:raise TimelineError('Claim not found.')
        return c
    def _basis(self,db,claim):
        b=basis(claim)
        for e in b['evidence']:
            snap=db.execute('SELECT created_at FROM snapshots WHERE id=?',(e['snapshot_id'],)).fetchone()
            if snap is None:raise TimelineError('Captured source version not found.')
            e['source_observed_at']=snap['created_at']
        if len(json.dumps(b,ensure_ascii=True).encode('ascii'))>256*1024:raise TimelineError('Event basis including observation timestamps exceeds 256 KiB.')
        return b
    def _row(self,db,eid):
        x=db.execute('SELECT * FROM intel_events WHERE id=?',(eid,)).fetchone()
        if x is None:raise TimelineError('Event not found.')
        r=dict(x);r['time_window']=json.loads(r['time_window']);r['basis']=json.loads(r['basis']);return r
    def _log(self,db,eid,op,detail):
        raw=json.dumps(detail,ensure_ascii=True)
        if len(raw)>1024*1024 or db.execute('SELECT count(*) FROM intel_event_history').fetchone()[0]>=10000 or db.execute('SELECT COALESCE(sum(length(detail)),0) FROM intel_event_history').fetchone()[0]+len(raw)>16*1024*1024:raise TimelineError('Bounded event history limit reached.')
        db.execute('INSERT INTO intel_event_history(event_id,time,operation,detail) VALUES(?,?,?,?)',(eid,now(),op,raw))
    def create(self,cid,title,kind,precision,start,end,zone,note):
        bounded(title,'Event title',300);bounded(note,'Time/source interpretation note',3000)
        if kind not in KINDS:raise TimelineError('Unknown event category.')
        w=window(precision,start,end,zone)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM intel_events').fetchone()[0]>=500:raise TimelineError('At most 500 timeline events.')
            b=self._basis(db,self._claim(db,cid));eid=key();t=now()
            db.execute('INSERT INTO intel_events VALUES(?,?,?,?,?,?,?,?,?,?)',(eid,cid,title,kind,json.dumps(w,ensure_ascii=True),json.dumps(b,ensure_ascii=True),'active',note,t,t))
            self._log(db,eid,'created',{'title':title,'kind':kind,'time_window':w,'basis':b,'note':note});return eid
    def revise(self,eid,title,kind,precision,start,end,zone,note):
        bounded(title,'Event title',300);bounded(note,'Revision note',3000)
        if kind not in KINDS:raise TimelineError('Unknown event category.')
        w=window(precision,start,end,zone)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self._row(db,eid);b=self._basis(db,self._claim(db,old['claim_id']))
            db.execute('UPDATE intel_events SET title=?,kind=?,time_window=?,basis=?,status=?,note=?,updated_at=? WHERE id=?',(title,kind,json.dumps(w,ensure_ascii=True),json.dumps(b,ensure_ascii=True),'active',note,now(),eid))
            self._log(db,eid,'revised',{'previous':old,'current':{'title':title,'kind':kind,'time_window':w,'basis':b,'status':'active','note':note}})
    def withdraw(self,eid,note):
        bounded(note,'Withdrawal note',3000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self._row(db,eid)
            db.execute("UPDATE intel_events SET status='withdrawn',updated_at=? WHERE id=?",(now(),eid));self._log(db,eid,'withdrawn',{'previous_status':old['status'],'note':note})
    def _fingerprint(self,r):
        return digest({k:r[k] for k in ('id','claim_id','title','kind','time_window','basis','status','note','recorded_at','updated_at')})
    def _assessment(self,db,r,current):
        row=db.execute("SELECT time,detail FROM intel_event_history WHERE event_id=? AND operation='stage-assessed' ORDER BY id DESC LIMIT 1",(r['id'],)).fetchone()
        if row is None:return {'declared_stage':'unknown','effective_stage':'unknown','status':'not_assessed','note':'','assessed_at':None,'automatic_verification':False}
        d=json.loads(row['detail']);valid=current and r['status']=='active' and d['event_fingerprint']==self._fingerprint(r)
        return {'declared_stage':d['stage'],'effective_stage':d['stage'] if valid else 'unknown','status':'current_editorial_assessment' if valid else 'needs_review','note':d['note'],'assessed_at':row['time'],'automatic_verification':False}
    def assess(self,eid,stage,note):
        if stage not in STAGES:raise TimelineError('Unknown declared stage.')
        bounded(note,'Stage assessment reason',3000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=self._row(db,eid);claims={c['id']:c for c in self.store.state(db)['claims']};view=self._view(db,r,claims)
            if r['status']!='active' or view['basis_status']!='current_editorial_basis':raise TimelineError('Stage assessment requires an active event with current reviewed evidence.')
            self._log(db,eid,'stage-assessed',{'stage':stage,'note':note,'event_fingerprint':self._fingerprint(r),'previous':view['assessment']})
    def _view(self,db,r,claims):
        c=claims.get(r['claim_id']);current=False
        if c and c['status']=='editor-approved':
            try:current=digest(self._basis(db,c))==digest(r['basis'])
            except (ActionError,TimelineError):current=False
        return {**r,'assessment':self._assessment(db,r,current),'basis_status':'current_editorial_basis' if current else 'needs_review','current_claim_status':c['status'] if c else 'missing','current_claim_text':c['text'] if c else None}
    def show(self,eid):
        with self.store.connect() as db:
            db.execute('BEGIN')
            claims={c['id']:c for c in self.store.state(db)['claims']};r=self._view(db,self._row(db,eid),claims);r['history']=[{**dict(x),'detail':json.loads(x['detail'])} for x in db.execute('SELECT time,operation,detail FROM intel_event_history WHERE event_id=? ORDER BY id',(eid,))];return r
    def listing(self,topic=None):
        if topic is not None:bounded(topic,'Captured topic filter',200)
        with self.store.connect() as db:
            db.execute('BEGIN')
            claims={c['id']:c for c in self.store.state(db)['claims']};rows=[self._view(db,self._row(db,r['id']),claims) for r in db.execute('SELECT id FROM intel_events ORDER BY rowid')]
        if topic is not None:rows=[r for r in rows if r['basis']['topic']==topic]
        rows.sort(key=lambda r:(r['time_window']['lower_utc'] is None,r['time_window']['lower_utc'] or '',r['recorded_at'],r['id']))
        for r in rows:
            a=r['time_window'];r['possible_overlap_ids']=[]
            if r['status']=='active' and a['lower_utc'] is not None:
                r['possible_overlap_ids']=[s['id'] for s in rows if s['id']!=r['id'] and s['status']=='active' and s['time_window']['lower_utc'] is not None and a['lower_utc']<=s['time_window']['upper_utc'] and s['time_window']['lower_utc']<=a['upper_utc']]
            r['ordering_status']='unknown_time' if a['lower_utc'] is None else ('withdrawn_historical_window' if r['status']=='withdrawn' else ('overlapping_declared_windows' if r['possible_overlap_ids'] else 'disjoint_among_known_active_windows'))
        return {'format':'horizon-event-timeline-v1','captured_topic_filter':topic,'overlap_scope':'returned events only','generated_at':now(),'ordering_notice':'Sorted by earliest declared UTC bound; overlapping or unknown windows do not establish a definite event order. All times are human assertions, not verified facts.','unknown_time_active_ids':[r['id'] for r in rows if r['status']=='active' and r['time_window']['lower_utc'] is None],'events':rows}

def markdown(timeline):
    import html
    def esc(x):return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])',r'\\\1',html.escape(str(x),quote=False))
    lines=['# Horizon event timeline','',timeline['ordering_notice'],'','Recorded/observed time is separate from declared event time. No authenticity or actual event occurrence is certified.','']
    lines+=['Captured topic filter: '+esc(timeline.get('captured_topic_filter') or 'all topics')+'; overlaps are checked only within returned events.','']
    for r in timeline['events']:
        w=r['time_window'];lines+=['## '+esc(r['title']),f"State: {r['status']} | Basis: {r['basis_status']} | Order: {r['ordering_status']}", 'Declared: '+esc(w['start'] or 'unknown')+' through '+esc(w['end'] or 'unknown')+'; precision '+w['precision']+'; zone '+esc(w['zone'] or 'explicit offset / unknown'), 'UTC window: '+esc(w['lower_utc'])+' through '+esc(w['upper_utc']),'Recorded locally: '+esc(r['recorded_at']),'Interpretation note: '+esc(r['note']),'Captured claim: '+esc(r['basis']['text']),'Current claim state: '+esc(r['current_claim_status']),'Possible overlap IDs: '+esc(', '.join(r['possible_overlap_ids'])),'']
        assessment=r.get('assessment',{'effective_stage':'unknown','declared_stage':'unknown','status':'not_assessed','note':'','assessed_at':None})
        lines+=['Human-declared stage: '+esc(assessment['effective_stage'])+' | Assessment: '+esc(assessment['status']),'Last declared stage (historical if stale): '+esc(assessment['declared_stage']),'Stage reason: '+esc(assessment['note']),'Assessed locally: '+esc(assessment['assessed_at']),'No automatic verification of release or rumor status.','']
        if assessment['status']=='needs_review':lines+=['WARNING: Stage assessment needs review; effective stage is unknown.','']
        if r['basis_status']=='needs_review':lines+=['WARNING: Event basis needs human re-review. Historical wording/time is not automatically revalidated.','']
        if r['status']=='withdrawn':lines+=['WITHDRAWN: retained as history, excluded from active overlap checks.','']
        for e in r['basis']['evidence']:lines+=['- '+esc(e['relation'])+' / '+esc(e['source_title'])+' / '+esc(e['snapshot_id']),'  Source observed/imported: '+esc(e['source_observed_at']),'  '+esc(e['quote']),'  '+esc(e['source_url'])]
        lines.append('')
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description='Human-declared intelligence event windows, distinct from observation timestamps.')
    p.add_argument('--data-dir',required=True);sub=p.add_subparsers(dest='command',required=True)
    for name in ('create','revise'):
        a=sub.add_parser(name)
        if name=='create':a.add_argument('--claim',required=True)
        else:a.add_argument('event_id')
        a.add_argument('--title',required=True);a.add_argument('--kind',choices=KINDS,default='other');a.add_argument('--precision',choices=['instant','day','unknown'],required=True);a.add_argument('--start',default='');a.add_argument('--end',default='');a.add_argument('--zone',default='');a.add_argument('--note',required=True)
    l=sub.add_parser('list');l.add_argument('--topic');s=sub.add_parser('show');s.add_argument('event_id');w=sub.add_parser('withdraw');w.add_argument('event_id');w.add_argument('--note',required=True)
    stage=sub.add_parser('assess');stage.add_argument('event_id');stage.add_argument('--stage',choices=STAGES,required=True);stage.add_argument('--note',required=True)
    e=sub.add_parser('export');e.add_argument('--topic');e.add_argument('--format',choices=['json','markdown'],default='json');e.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        t=Timeline(Path(a.data_dir)/'workspace.sqlite3')
        if a.command=='create':result={'event_id':t.create(a.claim,a.title,a.kind,a.precision,a.start,a.end,a.zone,a.note)}
        elif a.command=='revise':t.revise(a.event_id,a.title,a.kind,a.precision,a.start,a.end,a.zone,a.note);result={'revised':True,'status':'active'}
        elif a.command=='withdraw':t.withdraw(a.event_id,a.note);result={'withdrawn':True,'history_retained':True}
        elif a.command=='show':result=t.show(a.event_id)
        elif a.command=='list':result=t.listing(a.topic)
        elif a.command=='assess':t.assess(a.event_id,a.stage,a.note);result={'assessed':True,'automatic_verification':False}
        else:
            result=t.listing(a.topic);raw=((json.dumps(result,ensure_ascii=True,indent=2)+'\n') if a.format=='json' else markdown(result)).encode('utf8')
            if len(raw)>32*1024*1024:raise TimelineError('Timeline export exceeds 32 MiB.')
            with open(a.out,'xb') as f:f.write(raw)
            result={'exported':True}
        print(json.dumps(result,ensure_ascii=True));return 0
    except (ValueError,OSError,sqlite3.Error,TypeError,KeyError,UnicodeError,OverflowError):print('Timeline operation rejected. Check reviewed basis, explicit time boundaries, limits and output availability. No source text or paths echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
