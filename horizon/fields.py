"""Human-reviewed structured AI product observations; no automatic semantic extraction."""
import argparse,json,re,sqlite3,sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from .model import Store,key,now,digest
from .actions import basis,bounded,ActionError
from .server import bounded_json
from .watch import read_source

class FieldError(ValueError):pass
UNITS={'price_input':('USD/million_tokens','EUR/million_tokens'), 'price_output':('USD/million_tokens','EUR/million_tokens'), 'context_window':('tokens',), 'max_output':('tokens',), 'license':('identifier',), 'request_limit':('requests/minute','requests/day'), 'token_limit':('tokens/minute','tokens/day')}
SCOPE=('provider','model','channel','region','tier','conditions')
def validate(d):
    if type(d) is not dict or set(d)!={'scope','field','unit','value','qualifier','effective_date','raw_value','note'}:raise FieldError('Exact observation fields required.')
    if type(d['scope']) is not dict or set(d['scope'])!=set(SCOPE):raise FieldError('Explicit scope fields required.')
    for k,v in d['scope'].items():
        if v is not None:bounded(v,k,1000 if k=='conditions' else 200)
    f=d['field'];u=d['unit'];v=d['value'];q=d['qualifier']
    if type(f) is not str or f not in UNITS or type(u) is not str or u not in UNITS[f]:raise FieldError('Invalid field/unit combination.')
    if q not in ('exact','from','up_to','unknown'):raise FieldError('Explicit value qualifier required.')
    bounded(d['raw_value'],'Raw quoted value',300,True);bounded(d['note'],'Mapping/review note',2000)
    e=d['effective_date']
    if type(e) is not str or (e and (not re.fullmatch(r'\d{4}-\d\d-\d\d',e) or date.fromisoformat(e).isoformat()!=e)):raise FieldError('Effective date must be YYYY-MM-DD or empty (unknown).')
    if q=='unknown':
        if v is not None or d['raw_value']:raise FieldError('Unknown value must be null without invented raw value.')
    else:
        if not d['raw_value']:raise FieldError('Supply the exact value wording present in the selected quote.')
        if f=='license':
            if q!='exact':raise FieldError('License labels only support exact or unknown.')
            bounded(v,'License label',200)
        elif f.startswith('price_'):
            if type(v) is not str or not re.fullmatch(r'(?:0|[1-9]\d{0,8})(?:\.\d{1,6})?',v):raise FieldError('Price must be a bounded nonnegative decimal string, not a float.')
        elif type(v) is not int or not 0<=v<=10**12:raise FieldError('Capacity/limit must be a bounded nonnegative integer, not boolean.')
    return d

def capture(db,c):
    b=basis(c)
    for e in b['evidence']:
        s=db.execute('SELECT created_at FROM snapshots WHERE id=?',(e['snapshot_id'],)).fetchone()
        e['source_observed_at']=s['created_at'] if s else None
    if len(json.dumps(b,ensure_ascii=True).encode())>256*1024:raise FieldError('Captured evidence exceeds 256 KiB.')
    return b

class Fields:
    def __init__(self,path):
        self.store=Store(path)
        with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS product_observations(id TEXT PRIMARY KEY,claim_id TEXT NOT NULL REFERENCES claims(id),evidence_id TEXT NOT NULL REFERENCES evidence(id),spec TEXT NOT NULL,basis TEXT NOT NULL,recorded_at TEXT NOT NULL,withdrawn INTEGER NOT NULL,withdrawal_note TEXT NOT NULL)')
    def add(self,claim_id,evidence_id,spec):
        validate(spec)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM product_observations').fetchone()[0]>=500:raise FieldError('At most 500 observations per workspace.')
            c=next((c for c in self.store.state(db)['claims'] if c['id']==claim_id),None)
            if c is None:raise FieldError('Claim not found.')
            b=capture(db,c);e=next((e for e in b['evidence'] if e['id']==evidence_id),None)
            if e is None or e['relation']!='supports':raise FieldError('Select an active supporting evidence link from this approved claim.')
            if spec['qualifier']!='unknown' and spec['raw_value'] not in e['quote']:raise FieldError('Raw value wording not found in selected evidence quote.')
            encoded=json.dumps(b,ensure_ascii=True)
            if db.execute('SELECT COALESCE(sum(length(basis)+length(spec)),0) FROM product_observations').fetchone()[0]+len(encoded)+len(json.dumps(spec,ensure_ascii=True))>32*1024*1024:raise FieldError('Observation storage limit reached.')
            oid=key();db.execute('INSERT INTO product_observations VALUES(?,?,?,?,?,?,0,?)',(oid,claim_id,evidence_id,json.dumps(spec,ensure_ascii=True),encoded,now(),''));self.store.log(db,'product-observation-added',{'id':oid,'claim_id':claim_id});return oid
    def _view(self,db,row,claims):
        r=dict(row);r['spec']=json.loads(r['spec']);r['basis']=json.loads(r['basis']);r['withdrawn']=bool(r['withdrawn']);c=claims.get(r['claim_id']);current=False
        if c is not None:
            try:current=digest(capture(db,c))==digest(r['basis'])
            except (ActionError,FieldError):pass
        r['basis_status']='current_editorial_basis' if current else 'needs_review';r['semantic_mapping_verified']=False
        r['selected_evidence']=next(e for e in r['basis']['evidence'] if e['id']==r['evidence_id'])
        return r
    def listing(self):
        with self.store.connect() as db:
            claims={c['id']:c for c in self.store.state(db)['claims']};out=[]
            for row in db.execute('SELECT * FROM product_observations ORDER BY rowid'):
                r=self._view(db,row,claims);r.pop('basis');out.append(r)
            return out
    def show(self,oid):
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM product_observations WHERE id=?',(oid,)).fetchone()
            if row is None:raise FieldError('Observation not found.')
            return self._view(db,row,{c['id']:c for c in self.store.state(db)['claims']})
    def withdraw(self,oid,note):
        bounded(note,'Withdrawal reason',2000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT withdrawn FROM product_observations WHERE id=?',(oid,)).fetchone()
            if row is None or row['withdrawn']:raise FieldError('Missing or already withdrawn observation.')
            db.execute('UPDATE product_observations SET withdrawn=1,withdrawal_note=? WHERE id=?',(note,oid));self.store.log(db,'product-observation-withdrawn',{'id':oid,'note':note})
    def compare(self,left,right):
        with self.store.connect() as db:
            db.execute('BEGIN')
            claims={c['id']:c for c in self.store.state(db)['claims']};rows=[]
            for oid in (left,right):
                row=db.execute('SELECT * FROM product_observations WHERE id=?',(oid,)).fetchone()
                if row is None:raise FieldError('Observation not found.')
                rows.append(self._view(db,row,claims))
            a,b=rows
        x=a['spec'];y=b['spec'];mismatch=[k for k in ('field','unit','scope') if x[k]!=y[k]]
        r={'left':a,'right':b,'arithmetic_only':True,'mapping_requires_human_review':True,'delta':None,'mismatched_dimensions':mismatch,'chronology_inferred':False,'impact_inferred':False}
        if a['withdrawn'] or b['withdrawn']:r['comparison']='withdrawn'
        elif mismatch:r['comparison']='incomparable_scope_or_unit'
        elif any(v is None for v in x['scope'].values()):r['comparison']='unknown_scope'
        elif x['qualifier']!='exact' or y['qualifier']!='exact':r['comparison']='non_exact_or_unknown'
        elif x['field']=='license':r['comparison']='same_label' if x['value']==y['value'] else 'label_changed_no_legal_inference'
        else:
            r['delta']=format(Decimal(str(y['value']))-Decimal(str(x['value'])),'f');r['comparison']='exact_declared_arithmetic'
        r['review_required']=a['basis_status']!='current_editorial_basis' or b['basis_status']!='current_editorial_basis' or a['withdrawn'] or b['withdrawn']
        return r

def main():
    p=argparse.ArgumentParser(description='Record reviewed product fields and compare only declared matching scopes.')
    p.add_argument('--data-dir',required=True);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('add');a.add_argument('--claim-id',required=True);a.add_argument('--evidence-id',required=True);a.add_argument('--spec',required=True)
    s.add_parser('list');a=s.add_parser('show');a.add_argument('id');a=s.add_parser('withdraw');a.add_argument('id');a.add_argument('--note',required=True)
    a=s.add_parser('compare');a.add_argument('left');a.add_argument('right');a.add_argument('--out',required=True)
    a=p.parse_args()
    try:
        f=Fields(Path(a.data_dir)/'workspace.sqlite3')
        if a.command=='add':r={'id':f.add(a.claim_id,a.evidence_id,bounded_json(read_source(a.spec).encode('utf8')))}
        elif a.command=='list':r={'observations':f.listing()}
        elif a.command=='show':r=f.show(a.id)
        elif a.command=='withdraw':f.withdraw(a.id,a.note);r={'withdrawn':a.id}
        else:
            raw=(json.dumps(f.compare(a.left,a.right),ensure_ascii=True,indent=2)+'\n').encode('ascii')
            if len(raw)>4*1024*1024:raise FieldError('Comparison exceeds output limit.')
            with open(a.out,'xb') as o:o.write(raw)
            r={'exported':True}
        print(json.dumps(r,ensure_ascii=True));return 0
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error):
        print('Product observation failed. Check explicit schema, approved evidence, limits and output destination. No private input is echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
