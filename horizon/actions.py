"""Human action planning tied to explicit editorial evidence. Never executes a task."""
import argparse,html,json,sqlite3,sys
from datetime import date
from pathlib import Path
from .model import Store,key,now,digest,text

class ActionError(ValueError):pass
STATES=('planned','active','blocked','done','cancelled')
def bounded(value,name,limit,empty=False):
    text(value,name,limit,empty)
    try:value.encode('utf8')
    except UnicodeError:raise ActionError('Invalid Unicode text.') from None
    if '\x00' in value:raise ActionError('NUL characters are not accepted.')
    return value

def basis(claim):
    if claim['status']!='editor-approved':raise ActionError('Action basis requires current editor-approved wording. This is not factual verification.')
    if len(claim['evidence'])>100:raise ActionError('Action basis supports at most 100 evidence links.')
    result={k:claim[k] for k in ('id','text','topic','signature','review_signature','reviewed_at','review_note')}
    result['evidence']=[{k:e[k] for k in ('id','source_id','snapshot_id','quote','relation','note','source_title','source_url','kind','availability','origin_group')} for e in claim['evidence']]
    if len(json.dumps(result,ensure_ascii=True).encode())>256*1024:raise ActionError('Action basis exceeds 256 KiB.')
    return result

class Actions:
    def __init__(self,path):
        self.store=Store(path)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS news_actions(id TEXT PRIMARY KEY,claim_id TEXT NOT NULL REFERENCES claims(id),title TEXT NOT NULL,why TEXT NOT NULL,owner TEXT NOT NULL,due_date TEXT NOT NULL,status TEXT NOT NULL,checklist TEXT NOT NULL,basis TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS news_action_events(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id TEXT NOT NULL REFERENCES news_actions(id),time TEXT NOT NULL,operation TEXT NOT NULL,detail TEXT NOT NULL);''')
    def _claims(self,db):return {c['id']:c for c in self.store.state(db)['claims']}
    def _event(self,db,aid,operation,detail):
        if db.execute('SELECT count(*) FROM news_action_events').fetchone()[0]>=10000:raise ActionError('Action history limit reached; archive this workspace.')
        encoded=json.dumps(detail,ensure_ascii=True)
        if len(encoded)>1024*1024 or db.execute('SELECT COALESCE(sum(length(detail)),0) FROM news_action_events').fetchone()[0]+len(encoded)>16*1024*1024:raise ActionError('Bounded action history storage limit reached.')
        db.execute('INSERT INTO news_action_events(action_id,time,operation,detail) VALUES(?,?,?,?)',(aid,now(),operation,encoded))
    def _row(self,db,aid):
        row=db.execute('SELECT * FROM news_actions WHERE id=?',(aid,)).fetchone()
        if row is None:raise ActionError('Action not found.')
        x=dict(row);x['checklist']=json.loads(x['checklist']);x['basis']=json.loads(x['basis']);return x
    def _view(self,db,row,claims):
        c=claims.get(row['claim_id']);current=False
        if c is not None and c['status']=='editor-approved':
            try:current=digest(basis(c))==digest(row['basis'])
            except ActionError:current=False
        return {**row,'basis_status':'current_editorial_basis' if current else 'needs_review','current_claim_status':c['status'] if c else 'missing','current_claim_text':c['text'] if c else None,'completed_steps':sum(x['done'] for x in row['checklist']),'step_count':len(row['checklist'])}
    def create(self,claim_id,title,why,steps,owner='',due=''):
        bounded(title,'Title',300);bounded(why,'Why',3000);bounded(owner,'Owner',200,True)
        if type(due) is not str or (due and (len(due)!=10 or date.fromisoformat(due).isoformat()!=due)):raise ActionError('Due date must be YYYY-MM-DD or empty.')
        if type(steps) is not list or not 1<=len(steps)<=20:raise ActionError('Supply 1..20 explicit next steps.')
        for x in steps:bounded(x,'Step',1000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM news_actions').fetchone()[0]>=500:raise ActionError('At most 500 actions per workspace.')
            claim=self._claims(db).get(claim_id)
            if claim is None:raise ActionError('Claim not found.')
            captured=basis(claim);aid=key();time=now();checks=[{'text':s,'done':False} for s in steps]
            db.execute('INSERT INTO news_actions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(aid,claim_id,title,why,owner,due,'planned',json.dumps(checks,ensure_ascii=True),json.dumps(captured,ensure_ascii=True),time,time))
            self._event(db,aid,'created',{'title':title,'why':why,'owner':owner,'due_date':due,'checklist':checks,'basis':captured})
            return aid
    def listing(self):
        with self.store.connect() as db:
            claims=self._claims(db);out=[]
            for r in db.execute('SELECT id FROM news_actions ORDER BY rowid'):
                view=self._view(db,self._row(db,r['id']),claims);view.pop('basis');out.append(view)
            return out
    def show(self,aid):
        with self.store.connect() as db:
            row=self._view(db,self._row(db,aid),self._claims(db));row['history']=[{**dict(r),'detail':json.loads(r['detail'])} for r in db.execute('SELECT time,operation,detail FROM news_action_events WHERE action_id=? ORDER BY id',(aid,))];return row
    def check(self,aid,index,done,note):
        if type(index) is not int or type(done) is not bool:raise ActionError('Step index and boolean required.')
        bounded(note,'Progress note',2000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=self._row(db,aid)
            if r['status'] in ('done','cancelled'):raise ActionError('Reopen the action before editing its checklist.')
            if not 0<=index<len(r['checklist']):raise ActionError('Step index out of range.')
            old=r['checklist'][index]['done'];r['checklist'][index]['done']=done
            db.execute('UPDATE news_actions SET checklist=?,updated_at=? WHERE id=?',(json.dumps(r['checklist'],ensure_ascii=True),now(),aid))
            self._event(db,aid,'step-updated',{'index':index,'previous_done':old,'done':done,'note':note})
    def transition(self,aid,status,note):
        if status not in STATES:raise ActionError('Unknown action status.')
        bounded(note,'Status note',2000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=self._row(db,aid);v=self._view(db,r,self._claims(db))
            if r['status'] in ('done','cancelled') and status not in (r['status'],'planned'):raise ActionError('Reopen a closed action to planned before changing it.')
            if status=='done':
                if v['basis_status']!='current_editorial_basis':raise ActionError('Review the changed basis before recording completion.')
                if not all(x['done'] for x in r['checklist']):raise ActionError('Complete every checklist step before recording done.')
            db.execute('UPDATE news_actions SET status=?,updated_at=? WHERE id=?',(status,now(),aid))
            self._event(db,aid,'status-updated',{'previous_status':r['status'],'status':status,'note':note,'basis_hash':digest(r['basis'])})
    def rebase(self,aid,note):
        bounded(note,'Basis review note',2000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=self._row(db,aid);claim=self._claims(db).get(r['claim_id'])
            if claim is None:raise ActionError('Claim not found.')
            captured=basis(claim)
            # Never rewrite the historical basis of an already completed/cancelled task.
            if r['status'] in ('done','cancelled'):raise ActionError('Reopen the closed action before applying a new basis.')
            changed=digest(captured)!=digest(r['basis']);checks=[{**x,'done':False} for x in r['checklist']] if changed else r['checklist']
            db.execute('UPDATE news_actions SET basis=?,checklist=?,updated_at=? WHERE id=?',(json.dumps(captured,ensure_ascii=True),json.dumps(checks,ensure_ascii=True),now(),aid))
            self._event(db,aid,'basis-reviewed',{'previous_basis':r['basis'],'new_basis':captured,'previous_checklist':r['checklist'],'checklist_reset':changed,'note':note})
    def edit(self,aid,title,why,owner,due,note):
        bounded(title,'Title',300);bounded(why,'Why',3000);bounded(owner,'Owner',200,True);bounded(note,'Edit note',2000)
        if type(due) is not str or (due and (len(due)!=10 or date.fromisoformat(due).isoformat()!=due)):raise ActionError('Due date must be YYYY-MM-DD or empty.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=self._row(db,aid)
            if r['status'] in ('done','cancelled'):raise ActionError('Reopen the closed action before editing it.')
            db.execute('UPDATE news_actions SET title=?,why=?,owner=?,due_date=?,updated_at=? WHERE id=?',(title,why,owner,due,now(),aid))
            self._event(db,aid,'plan-edited',{'previous':{k:r[k] for k in ('title','why','owner','due_date')},'current':{'title':title,'why':why,'owner':owner,'due_date':due},'note':note})

def markdown(item):
    def esc(x):
        import re
        return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])',r'\\\1',html.escape(str(x),quote=False))
    lines=['# '+esc(item['title']),'','Human-entered plan and progress, not an executed task or factual verification.',f"Status: {item['status']} | Basis: {item['basis_status']}",'']
    if item['basis_status']=='needs_review':lines+=['WARNING: The current claim/evidence differs or is no longer editor-approved. Historical completion is not revalidated.','']
    lines += ['Why: '+esc(item['why']),'Owner label: '+esc(item['owner']),'Due date: '+esc(item['due_date']),'','## Checklist']
    for i,s in enumerate(item['checklist']):lines.append(f"- [{'x' if s['done'] else ' '}] {i}: "+esc(s['text']))
    lines+=['','## Captured editorial basis',esc(item['basis']['text']),'','Current claim status: '+esc(item['current_claim_status']),'Current wording: '+esc(item['current_claim_text']),'']
    for e in item['basis']['evidence']:
        lines+=['- '+esc(e['relation'])+': '+esc(e['source_title']), '  Snapshot: '+esc(e['snapshot_id']), '  URL: '+esc(e['source_url']), '  Quote: '+esc(e['quote'])]
    lines+=['','## Recorded history']
    for h in item['history']:lines.append('- '+esc(h['time'])+' '+esc(h['operation'])+' '+esc(json.dumps(h['detail'],ensure_ascii=False)))
    return '\n'.join(lines)+'\n'

def main():
    p=argparse.ArgumentParser(description='Human action planning from reviewed Horizon claims. No external action execution.')
    p.add_argument('--data-dir',required=True);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('create');c.add_argument('--claim',required=True);c.add_argument('--title',required=True);c.add_argument('--why',required=True);c.add_argument('--step',action='append',required=True);c.add_argument('--owner',default='');c.add_argument('--due',default='')
    sub.add_parser('list');sub.add_parser('claims')
    s=sub.add_parser('show');s.add_argument('action_id')
    c=sub.add_parser('check');c.add_argument('action_id');c.add_argument('index',type=int);c.add_argument('--done',choices=['yes','no'],required=True);c.add_argument('--note',required=True)
    s=sub.add_parser('status');s.add_argument('action_id');s.add_argument('state',choices=STATES);s.add_argument('--note',required=True)
    r=sub.add_parser('review-basis');r.add_argument('action_id');r.add_argument('--note',required=True)
    e=sub.add_parser('edit');e.add_argument('action_id');e.add_argument('--title',required=True);e.add_argument('--why',required=True);e.add_argument('--owner',default='');e.add_argument('--due',default='');e.add_argument('--note',required=True)
    e=sub.add_parser('export');e.add_argument('action_id');e.add_argument('--format',choices=['json','markdown'],default='json');e.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        actions=Actions(Path(a.data_dir)/'workspace.sqlite3')
        if a.command=='create':result={'action_id':actions.create(a.claim,a.title,a.why,a.step,a.owner,a.due)}
        elif a.command=='list':result={'actions':actions.listing()}
        elif a.command=='claims':result={'claims':[{k:c[k] for k in ('id','text','topic','status')} for c in actions.store.state()['claims']]}
        elif a.command=='show':result=actions.show(a.action_id)
        elif a.command=='check':actions.check(a.action_id,a.index,a.done=='yes',a.note);result={'recorded':True}
        elif a.command=='status':actions.transition(a.action_id,a.state,a.note);result={'recorded':True}
        elif a.command=='review-basis':actions.rebase(a.action_id,a.note);result={'basis_review_recorded':True}
        elif a.command=='edit':actions.edit(a.action_id,a.title,a.why,a.owner,a.due,a.note);result={'recorded':True}
        else:
            item=actions.show(a.action_id);raw=((json.dumps(item,ensure_ascii=True,indent=2)+'\n') if a.format=='json' else markdown(item)).encode('utf8')
            if len(raw)>16*1024*1024:raise ActionError('Action export exceeds 16 MiB.')
            with open(a.out,'xb') as f:f.write(raw)
            result={'exported':True}
        print(json.dumps(result,ensure_ascii=True));return 0
    except (ValueError,OSError,sqlite3.Error,TypeError,KeyError,UnicodeError):
        print('Action operation rejected. Check reviewed basis, checklist, status, input limits and output availability. No supplied text or path echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
