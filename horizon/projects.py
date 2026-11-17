"""Explicit public README observations and human-reviewed project dossiers. MIT walker512."""
import argparse,base64,binascii,hashlib,http.client,json,re,sqlite3,sys,time,urllib.error,urllib.request
from pathlib import Path
from .model import Store,key,now,digest
from .radar import Radar,NoRedirect,integer,bounded_text
from .fields import capture
from .actions import bounded,ActionError
from .server import bounded_json
from .watch import read_source,invalidate

class ProjectError(ValueError):pass
LIMIT=2*1024*1024
NAME=r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}'
COLUMNS={
'project_registry':['id','repo_id','full_name','query_id','selected_run','created_at'],
'project_runs':['id','project_id','observed_at','status','detail'],
'project_profiles':['id','project_id','run_id','spec','basis','recorded_at','withdrawn','withdrawal_note']}
def name(x):
    if type(x) is not str or not re.fullmatch(NAME,x) or x.split('/')[-1] in ('.','..'):raise ProjectError('Invalid public repository name.')
    return x
def fetch(full_name,readme=False):
    url='https://api.github.com/repos/'+name(full_name)+('/readme' if readme else '')
    req=urllib.request.Request(url,headers={'User-Agent':'Horizon-project-review/1','Accept':'application/vnd.github+json','Accept-Encoding':'identity','X-GitHub-Api-Version':'2022-11-28'})
    try:
        start=time.monotonic()
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as r:
            if r.status!=200 or r.geturl()!=url:raise ProjectError('Unexpected HTTP response.')
            if r.headers.get_content_type()!='application/json' or r.headers.get('Content-Encoding','identity').lower() not in ('','identity'):raise ProjectError('Unsupported response encoding/type.')
            charset=r.headers.get_content_charset()
            if charset and charset.lower() not in ('utf-8','utf8'):raise ProjectError('Only UTF-8 JSON is supported.')
            ls=r.headers.get_all('Content-Length',[]);ts=r.headers.get_all('Transfer-Encoding',[])
            if len(ls)>1 or len(ts)>1 or (ls and ts):raise ProjectError('Ambiguous HTTP framing.')
            if ts and ts[0].strip().lower()!='chunked':raise ProjectError('Unsupported transfer framing.')
            expected=None
            if ls:
                v=ls[0].strip()
                if not re.fullmatch(r'[0-9]{1,10}',v):raise ProjectError('Invalid response length.')
                expected=int(v)
                if expected>LIMIT:raise ProjectError('Response too large.')
            raw=bytearray()
            while True:
                if time.monotonic()-start>30:raise ProjectError('Read deadline exceeded.')
                c=r.read(min(65536,LIMIT+1-len(raw)))
                if not c:break
                raw.extend(c)
                if len(raw)>LIMIT:raise ProjectError('Response too large.')
            if expected is not None and len(raw)!=expected:raise ProjectError('Truncated response.')
            return bytes(raw)
    except urllib.error.HTTPError as e:
        e.close();raise ProjectError('GitHub unavailable; no redirect/retry.') from None
    except (urllib.error.URLError,OSError,http.client.HTTPException):raise ProjectError('GitHub connection failed; no fallback.') from None

def obj(raw):
    if type(raw) is not bytes or len(raw)>LIMIT:raise ProjectError('Response exceeds bounds.')
    d=bounded_json(raw)
    if type(d) is not dict:raise ProjectError('Expected JSON object.')
    return d

def metadata(raw,rid):
    d=obj(raw);integer(d.get('id'),1,2**63-1)
    if d['id']!=rid or d.get('private') is not False:raise ProjectError('Repository identity/public status mismatch.')
    n=name(d.get('full_name'));branch=bounded_text(d.get('default_branch'),200)
    if type(d.get('archived')) is not bool:raise ProjectError('Invalid archived flag.')
    lic=d.get('license');label=None
    if lic is not None:
        if type(lic) is not dict:raise ProjectError('Invalid API license metadata.')
        label=lic.get('spdx_id')
        if label is not None:bounded_text(label,200)
    return {'repo_id':rid,'full_name':n,'default_branch':branch,'archived':d['archived'],'api_spdx_label':label,'release_version':None,'license_full_text_collected':False}

def readme(raw):
    d=obj(raw)
    if d.get('type')!='file' or d.get('encoding')!='base64':raise ProjectError('README must be one base64 file.')
    size=d.get('size');integer(size,1,512*1024)
    content=d.get('content');sha=d.get('sha');path=d.get('path')
    if type(content) is not str or not re.fullmatch(r'[A-Za-z0-9+/=\r\n]*',content):raise ProjectError('Invalid base64 characters.')
    try:b=base64.b64decode(content.replace('\r','').replace('\n',''),validate=True);text=b.decode('utf8')
    except (ValueError,UnicodeError):raise ProjectError('Invalid UTF-8/base64 README.') from None
    if len(b)!=size or len(text)>500000 or not text.strip() or '\x00' in text:raise ProjectError('README length/text mismatch.')
    if type(sha) is not str or not re.fullmatch('[0-9a-f]{40}',sha) or hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()!=sha:raise ProjectError('Git blob SHA mismatch.')
    bounded_text(path,500)
    return text,{'blob_sha':sha,'path':path,'decoded_bytes':size}

class Projects:
    def __init__(self,path):
        self.store=Store(path)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS project_registry(id TEXT PRIMARY KEY,repo_id INTEGER NOT NULL UNIQUE,full_name TEXT NOT NULL,query_id TEXT NOT NULL,selected_run TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_runs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES project_registry(id),observed_at TEXT NOT NULL,status TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_profiles(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES project_registry(id),run_id TEXT NOT NULL REFERENCES project_runs(id),spec TEXT NOT NULL,basis TEXT NOT NULL,recorded_at TEXT NOT NULL,withdrawn INTEGER NOT NULL,withdrawal_note TEXT NOT NULL);''')
    def select(self,qid,rid):
        integer(rid,1,2**63-1);r=Radar(self.store.path).review(qid)
        if r['status']!='observed':raise ProjectError('Select from a current successful radar page.')
        c=next((x for x in r['candidates'] if x['id']==rid),None)
        if c is None:raise ProjectError('Candidate not returned.')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT id FROM project_registry WHERE repo_id=?',(rid,)).fetchone()
            if old:
                db.execute('UPDATE project_registry SET full_name=?,query_id=?,selected_run=? WHERE id=?',(c['full_name'],qid,r['latest_attempt']['id'],old['id']))
                self.store.log(db,'project-reselected',{'id':old['id'],'full_name':c['full_name']})
                return old['id']
            if db.execute('SELECT count(*) FROM project_registry').fetchone()[0]>=100:raise ProjectError('Project limit reached.')
            pid=key();db.execute('INSERT INTO project_registry VALUES(?,?,?,?,?,?)',(pid,rid,c['full_name'],qid,r['latest_attempt']['id'],now()));self.store.log(db,'project-selected',{'id':pid,'repo_id':rid});return pid
    def _project(self,db,pid):
        r=db.execute('SELECT * FROM project_registry WHERE id=?',(pid,)).fetchone()
        if r is None:raise ProjectError('Project not found.')
        return dict(r)
    def _latest(self,db,pid):
        r=db.execute('SELECT * FROM project_runs WHERE project_id=? ORDER BY rowid DESC LIMIT 1',(pid,)).fetchone()
        if r is None:return None
        d=dict(r);d['detail']=json.loads(d['detail']);return d
    def collect(self,pid,allow_network=False,transport=fetch):
        if allow_network is not True:raise ProjectError('Explicit network permission required.')
        with self.store.connect() as db:
            p=self._project(db,pid)
            if db.execute('SELECT count(*) FROM project_runs').fetchone()[0]>=500:raise ProjectError('Run limit reached.')
        n=p['full_name'];parts={};meta=None
        try:
            raw=transport(n,False);meta=metadata(raw,p['repo_id']);n=meta['full_name'];parts['metadata']={'text':json.dumps(meta,ensure_ascii=True,sort_keys=True,indent=2),'sha256':hashlib.sha256(raw).hexdigest(),'availability':'summary'}
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):parts['metadata']={'text':'','availability':'failed'}
        if meta:
            try:
                raw=transport(n,True);txt,info=readme(raw);parts['readme']={'text':txt,'sha256':hashlib.sha256(raw).hexdigest(),'availability':'summary',**info}
            except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):parts['readme']={'text':'','availability':'failed'}
        else:parts['readme']={'text':'','availability':'failed'}
        parts['metadata']['request_url']='https://api.github.com/repos/'+p['full_name']
        parts['metadata']['request_attempted']=True
        parts['readme']['request_url']='https://api.github.com/repos/'+n+'/readme'
        parts['readme']['request_attempted']=meta is not None
        status='observed' if all(x['availability']=='summary' for x in parts.values()) else ('partial' if meta else 'failed')
        try:return self._commit(pid,p,n,meta,parts,status)
        except (ValueError,sqlite3.Error):
            # A successful fetch with failed persistence must not leave an old run looking current.
            # Record a failed attempt independently when the run table remains writable.
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT count(*) FROM project_runs').fetchone()[0]>=500:raise ProjectError('Run quota prevents recording persistence failure.')
                run=key();detail={'full_name':n,'repo_id':p['repo_id'],'parts':{},'metadata':None,'persistence_failed':True,'atomic_version':False}
                db.execute('INSERT INTO project_runs VALUES(?,?,?,?,?)',(run,pid,now(),'failed',json.dumps(detail)))
                self.store.log(db,'project-persistence-failed',{'project_id':pid,'run_id':run})
                return {'id':run,'status':'failed','detail':detail}
    def _commit(self,pid,p,n,meta,parts,status):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            selected=self._project(db,pid)
            if any(selected[k]!=p[k] for k in ('full_name','query_id','selected_run')):raise ProjectError('Selection changed during collection; response not imported.')
            if db.execute('SELECT count(*) FROM project_runs').fetchone()[0]>=500:raise ProjectError('Run limit reached.')
            before={c['id']:c for c in self.store.state(db)['claims']};out={}
            for kind,x in parts.items():
                # Preserve the endpoint actually requested, not the returned canonical name.
                # A skipped README retains its intended source URL with request_attempted=False.
                url=x['request_url']
                sid=self.store.source(db,{'title':n+' '+kind,'url':url,'kind':'primary','origin_group':'github-repository-'+str(p['repo_id']),'text':x['text'],'availability':x['availability'],'error':'' if x['availability']=='summary' else 'GitHub observation unavailable or unsupported; no deletion inference.'})
                snap=db.execute('SELECT id FROM snapshots WHERE source_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()['id']
                out[kind]={k:v for k,v in x.items() if k!='text'};out[kind].update(source_id=sid,snapshot_id=snap,url=url)
            detail={'full_name':n,'repo_id':p['repo_id'],'parts':out,'metadata':meta,'atomic_version':False,'releases_collected':False,'license_interpretation':False}
            run=key();db.execute('INSERT INTO project_runs VALUES(?,?,?,?,?)',(run,pid,now(),status,json.dumps(detail,ensure_ascii=True)))
            if meta:db.execute('UPDATE project_registry SET full_name=? WHERE id=?',(n,pid))
            invalidate(self.store,db,before);self.store.log(db,'project-observed',{'project_id':pid,'run_id':run,'status':status});return {'id':run,'status':status,'detail':detail}
    def listing(self):
        with self.store.connect() as db:return [{**dict(p),'latest':self._latest(db,p['id'])} for p in db.execute('SELECT * FROM project_registry ORDER BY rowid')]
    def add(self,pid,spec):
        validate(spec)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._project(db,pid);run=self._latest(db,pid)
            if not run or run['status']!='observed' or run['detail']['full_name']!=self._project(db,pid)['full_name']:raise ProjectError('A fully available observation is required for a new dossier.')
            claims={c['id']:c for c in self.store.state(db)['claims']};bases={};allowed={x['source_id']:x['snapshot_id'] for x in run['detail']['parts'].values()}
            for item in spec['entries']:
                if item['state']=='unknown':continue
                c=claims.get(item['claim_id'])
                if c is None:raise ProjectError('Claim missing.')
                b=capture(db,c);e=next((e for e in b['evidence'] if e['id']==item['evidence_id']),None)
                if e is None or e['relation']!='supports' or allowed.get(e['source_id'])!=e['snapshot_id']:raise ProjectError('Supporting evidence must belong to this observed project and current snapshot.')
                if item['raw_value'] not in e['quote']:raise ProjectError('Value wording must occur literally in evidence.')
                bases[c['id']]=b
            encoded=json.dumps(bases,ensure_ascii=True);sp=json.dumps(spec,ensure_ascii=True)
            if len(encoded)>256*1024:raise ProjectError('Basis exceeds limit.')
            count,total=db.execute('SELECT count(*),COALESCE(sum(length(basis)+length(spec)),0) FROM project_profiles').fetchone()
            if count>=500 or total+len(encoded)+len(sp)>32*1024*1024:raise ProjectError('Dossier storage limit.')
            oid=key();db.execute('INSERT INTO project_profiles VALUES(?,?,?,?,?,?,0,?)',(oid,pid,run['id'],sp,encoded,now(),''));self.store.log(db,'project-profile-added',{'id':oid,'project_id':pid});return oid
    def _view(self,db,oid,claims):
        row=db.execute('SELECT * FROM project_profiles WHERE id=?',(oid,)).fetchone()
        if row is None:raise ProjectError('Dossier missing.')
        r=dict(row);r['spec']=json.loads(r['spec']);r['basis']=json.loads(r['basis']);r['withdrawn']=bool(r['withdrawn']);latest=self._latest(db,r['project_id']);original=db.execute('SELECT detail FROM project_runs WHERE id=?',(r['run_id'],)).fetchone();r['observation']=json.loads(original['detail']);r['latest_observation']=latest
        current=bool(r['basis'] and self._project(db,r['project_id'])['full_name']==r['observation']['full_name'] and latest and latest['status']=='observed' and latest['detail']['full_name']==r['observation']['full_name'] and all(latest['detail']['parts'][k]['snapshot_id']==v['snapshot_id'] for k,v in r['observation']['parts'].items()))
        for cid,b in r['basis'].items():
            try:current=current and digest(capture(db,claims[cid]))==digest(b)
            except (KeyError,ValueError):current=False
        # Any intervening failed/renamed/changed observation invalidates an older dossier permanently.
        past=False
        for x in db.execute('SELECT id,status,detail FROM project_runs WHERE project_id=? ORDER BY rowid',(r['project_id'],)):
            if x['id']==r['run_id']:past=True;continue
            if past:
                d=json.loads(x['detail'])
                if x['status']!='observed' or d['full_name']!=r['observation']['full_name'] or any(d['parts'][k]['snapshot_id']!=v['snapshot_id'] for k,v in r['observation']['parts'].items()):current=False
        r['basis_status']='current_editorial_basis' if current else 'needs_review';r['review_complete']=current and not r['withdrawn'] and all(x['state']=='known' for x in r['spec']['entries']);r['semantic_mapping_verified']=False;return r
    def show(self,oid):
        with self.store.connect() as db:
            db.execute('BEGIN');return self._view(db,oid,{c['id']:c for c in self.store.state(db)['claims']})
    def withdraw(self,oid,note):
        bounded(note,'Withdrawal note',2000)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('UPDATE project_profiles SET withdrawn=1,withdrawal_note=? WHERE id=? AND withdrawn=0',(note,oid)).rowcount:raise ProjectError('Missing or withdrawn dossier.')
            self.store.log(db,'project-profile-withdrawn',{'id':oid,'note':note})
    def compare(self,ids):
        if not 2<=len(ids)<=10 or len(set(ids))!=len(ids):raise ProjectError('Select 2..10 distinct dossier IDs.')
        with self.store.connect() as db:
            db.execute('BEGIN');claims={c['id']:c for c in self.store.state(db)['claims']};profiles=[self._view(db,i,claims) for i in ids]
        criteria=sorted(set(e['criterion'] for p in profiles for e in p['spec']['entries']));rows=[]
        for criterion in criteria:
            cells=[next((e for e in p['spec']['entries'] if e['criterion']==criterion),None) for p in profiles];comparable=all(c and c['state']=='known' for c in cells)
            if comparable:comparable=all(all(c[k]==cells[0][k] and c[k] is not None for k in ('category','definition','unit','platform','version_scope')) for c in cells)
            rows.append({'criterion':criterion,'cells':cells,'scope_status':'declared_comparable' if comparable else 'unknown_or_different_scope','review_required':any(p['withdrawn'] or p['basis_status']!='current_editorial_basis' for p in profiles)})
        return {'profiles':profiles,'rows':rows,'ranking':None,'mapping_requires_human_review':True,'version_scope_semantics':'Shared comparison condition, not equality of project versions; project_version is human-declared separately.'}

def validate(s):
    if type(s) is not dict or set(s)!={'project_version','entries'}:raise ProjectError('Exact dossier schema required.')
    if s['project_version'] is not None:bounded(s['project_version'],'Project version',200)
    es=s['entries']
    if type(es) is not list or not 3<=len(es)<=20:raise ProjectError('Supply 3..20 entries, including purpose/alternatives/barrier.')
    seen=set();cats=set()
    for e in es:
        if type(e) is not dict or set(e)!={'category','criterion','definition','unit','platform','version_scope','state','value','raw_value','claim_id','evidence_id','note'}:raise ProjectError('Exact entry schema required.')
        if e['category'] not in ('purpose','alternatives','barrier'):raise ProjectError('Invalid category.')
        cats.add(e['category']);bounded(e['criterion'],'Criterion',100);bounded(e['definition'],'Definition',1000);bounded(e['note'],'Human mapping or unknown reason',2000)
        if e['criterion'] in seen:raise ProjectError('Duplicate criterion.')
        seen.add(e['criterion'])
        for k in ('unit','platform','version_scope'):
            if e[k] is not None:bounded(e[k],k,300)
        if e['state']=='unknown':
            if any(e[k] is not None for k in ('value','claim_id','evidence_id')) or e['raw_value']!='':raise ProjectError('Unknown entries cannot invent values/evidence.')
        elif e['state']=='known':
            for k in ('value','raw_value','claim_id','evidence_id'):bounded(e[k],k,2000 if k=='value' else 1000)
        else:raise ProjectError('Explicit known/unknown required.')
    if cats!={'purpose','alternatives','barrier'}:raise ProjectError('Each required category must be represented, even if unknown.')

def escape(x):
    # Encode explicit Markdown/HTML syntax. Renderer auto-linking/previews are outside this contract.
    return ''.join(c if c.isalnum() or c==' ' else '&#'+str(ord(c))+';' for c in str(x))
def markdown(r):
    out=['# Human-reviewed project comparison','','No ranking, runtime test, license interpretation or semantic verification. Source excerpts/URLs may be sensitive; inspect before sharing.','']
    for p in r['profiles']:
        out+=['## '+escape(p['observation']['full_name']), 'Declared version: '+escape(p['spec']['project_version']), 'Basis: '+escape(p['basis_status'])+'; withdrawn: '+str(p['withdrawn'])]
    out+=['','| Criterion | Scope | Values (profile order) |','| --- | --- | --- |']
    for row in r['rows']:out+=['| '+escape(row['criterion'])+' | '+escape(row['scope_status'])+'; review required '+str(row['review_required'])+' | '+' / '.join(escape(c['value'] if c and c['state']=='known' else 'UNKNOWN') for c in row['cells'])+' |']
    for p in r['profiles']:
        out+=['','## Evidence '+escape(p['id']), 'Full human criteria and mapping: '+escape(json.dumps(p['spec'],ensure_ascii=False,sort_keys=True))]
        for c in p['basis'].values():
            out+=['Claim: '+escape(c['text'])]
            for e in c['evidence']:out+=['Quote: '+escape(e['quote']),'Source: '+escape(e['source_url'])]
    return '\n\n'.join(out)+'\n'

def main():
    p=argparse.ArgumentParser(description='Explicit public project observation and human-reviewed dossiers; no ranking.')
    p.add_argument('--data-dir',required=True);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('select');a.add_argument('query_id');a.add_argument('repo_id',type=int)
    a=s.add_parser('collect');a.add_argument('project_id');a.add_argument('--allow-network',action='store_true')
    s.add_parser('list');a=s.add_parser('add');a.add_argument('project_id');a.add_argument('--spec',required=True)
    a=s.add_parser('show');a.add_argument('id');a=s.add_parser('withdraw');a.add_argument('id');a.add_argument('--note',required=True)
    a=s.add_parser('compare');a.add_argument('ids',nargs='+');a.add_argument('--out',required=True);a.add_argument('--format',choices=['json','markdown'],default='json')
    a=p.parse_args()
    try:
        ps=Projects(Path(a.data_dir)/'workspace.sqlite3')
        if a.command=='select':r={'id':ps.select(a.query_id,a.repo_id)}
        elif a.command=='collect':
            r=ps.collect(a.project_id,a.allow_network);print(json.dumps(r,ensure_ascii=True));return 0 if r['status']=='observed' else 3
        elif a.command=='list':r={'projects':ps.listing()}
        elif a.command=='add':r={'id':ps.add(a.project_id,bounded_json(read_source(a.spec).encode()))}
        elif a.command=='show':r=ps.show(a.id)
        elif a.command=='withdraw':ps.withdraw(a.id,a.note);r={'withdrawn':a.id}
        else:
            result=ps.compare(a.ids);raw=(markdown(result) if a.format=='markdown' else json.dumps(result,ensure_ascii=True,indent=2)+'\n').encode('utf8')
            if len(raw)>4*1024*1024:raise ProjectError('Export exceeds limit.')
            with open(a.out,'xb') as f:f.write(raw)
            r={'exported':True}
        print(json.dumps(r,ensure_ascii=True));return 0
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error,RecursionError):
        print('Project operation failed. Check consent, selected repository, current approved evidence, schema and storage/output bounds. No source text echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
