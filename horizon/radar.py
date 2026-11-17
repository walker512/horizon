"""Explicit GitHub public-search observations, not forecasts or global trending."""
import argparse,http.client,hashlib,json,os,re,sqlite3,sys,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from .model import Store,key,now
from .server import bounded_json

class RadarError(ValueError):pass

def integer(x,lo,hi):
    if type(x) is not int or not lo<=x<=hi:raise RadarError('Invalid integer field.')
def bounded_text(x,n,empty=False):
    if type(x) is not str or len(x)>n or (not empty and not x) or any(ord(c)<32 for c in x):raise RadarError('Invalid bounded text field.')
    try:x.encode('utf8')
    except UnicodeError:raise RadarError('Invalid Unicode text field.') from None
    return x

def stamp(x):
    if type(x) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)',x):raise RadarError('UTC observation timestamp required.')
    try:return datetime.fromisoformat(x.replace('Z','+00:00'))
    except ValueError:raise RadarError('Invalid UTC timestamp.') from None

def projection(raw,per_page):
    integer(per_page,1,50)
    if len(raw)>2*1024*1024:raise RadarError('API response too large.')
    try:d=bounded_json(raw)
    except (ValueError,UnicodeError,RecursionError):raise RadarError('Invalid API JSON.') from None
    if type(d) is not dict:raise RadarError('Expected API object.')
    integer(d.get('total_count'),0,10**9)
    if type(d.get('incomplete_results')) is not bool or type(d.get('items')) is not list or len(d['items'])>per_page:raise RadarError('Invalid API search coverage.')
    result=[];ids=set()
    for x in d['items']:
        if type(x) is not dict:raise RadarError('Invalid repository record.')
        rid=x.get('id');integer(rid,1,2**63-1)
        if rid in ids:raise RadarError('Duplicate repository ID in one response.')
        ids.add(rid);name=bounded_text(x.get('full_name'),202)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}',name):raise RadarError('Invalid repository full name.')
        stars=x.get('stargazers_count');integer(stars,0,10**9)
        for field in ('fork','archived'):
            if type(x.get(field)) is not bool:raise RadarError('Expected repository boolean flag.')
        created=x.get('created_at');stamp(created)
        desc=x.get('description');lang=x.get('language')
        if desc is not None:
            if type(desc) is not str or len(desc)>4000:raise RadarError('Invalid description.')
            try:desc.encode('utf8')
            except UnicodeError:raise RadarError('Invalid Unicode description.') from None
        if lang is not None:bounded_text(lang,100)
        result.append({'id':rid,'full_name':name,'url':'https://github.com/'+name,'stars':stars,'created_at':created,'description':desc,'language':lang,'fork':x['fork'],'archived':x['archived']})
    if d['total_count']<len(result):raise RadarError('Search total smaller than returned rows.')
    return {'total_count':d['total_count'],'incomplete_results':d['incomplete_results'],'returned':len(result),'items':result,'raw_response_sha256':hashlib.sha256(raw).hexdigest()}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch(query,per_page):
    bounded_text(query,256);integer(per_page,1,50)
    url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':query,'sort':'stars','order':'desc','per_page':per_page,'page':1})
    request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'Horizon-public-radar/1','X-GitHub-Api-Version':'2022-11-28'})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        start=time.monotonic()
        with opener.open(request,timeout=15) as response:
            if response.status!=200:raise RadarError('GitHub did not return a successful search response.')
            lengths=response.headers.get_all('Content-Length',[])
            transfers=response.headers.get_all('Transfer-Encoding',[])
            if len(lengths)>1 or len(transfers)>1 or (lengths and transfers):raise RadarError('Ambiguous GitHub response framing.')
            if transfers and transfers[0].strip().lower()!='chunked':raise RadarError('Unsupported GitHub transfer encoding.')
            expected=None
            if lengths:
                value=lengths[0].strip()
                if not value or len(value)>10 or any(c not in '0123456789' for c in value):raise RadarError('Invalid declared GitHub response length.')
                expected=int(value)
                if expected>2*1024*1024:raise RadarError('Declared GitHub response exceeds byte limit.')
            raw=bytearray()
            while True:
                if time.monotonic()-start>30:raise RadarError('GitHub response exceeded the read deadline.')
                chunk=response.read(min(65536,2*1024*1024+1-len(raw)))
                if not chunk:break
                raw.extend(chunk)
                if len(raw)>2*1024*1024:raise RadarError('GitHub response exceeded the byte limit.')
            if expected is not None and len(raw)!=expected:raise RadarError('Truncated GitHub response.')
        return bytes(raw)
    except urllib.error.HTTPError as e:
        code=e.code;e.close();raise RadarError('GitHub HTTP status '+str(code)+'. No retry or redirect was followed.') from None
    except (urllib.error.URLError,OSError,TimeoutError,http.client.HTTPException):raise RadarError('GitHub connection unavailable. No fallback or retry was attempted.') from None

class Radar:
    def __init__(self,path):
        self.store=Store(path)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS radar_queries(id TEXT PRIMARY KEY,label TEXT NOT NULL UNIQUE,query TEXT NOT NULL,per_page INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS radar_runs(id TEXT PRIMARY KEY,query_id TEXT NOT NULL REFERENCES radar_queries(id),observed_at TEXT NOT NULL,status TEXT NOT NULL,error TEXT NOT NULL,observation TEXT);''')
    def add(self,label,query,per_page=20):
        bounded_text(label,80);bounded_text(query,256);integer(per_page,1,50)
        with self.store.connect() as db:
            if db.execute('SELECT count(*) FROM radar_queries').fetchone()[0]>=20:raise RadarError('At most 20 queries.')
            rid=key();db.execute('INSERT INTO radar_queries VALUES(?,?,?,?,?)',(rid,label,query,per_page,now()));return rid
    def listing(self):
        with self.store.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM radar_queries ORDER BY rowid')]
    def query(self,qid):
        with self.store.connect() as db:r=db.execute('SELECT * FROM radar_queries WHERE id=?',(qid,)).fetchone()
        if r is None:raise RadarError('Query not found.')
        return dict(r)
    def collect(self,qid,transport=fetch):
        q=self.query(qid)
        with self.store.connect() as db:
            if db.execute('SELECT count(*) FROM radar_runs').fetchone()[0]>=200:raise RadarError('At most 200 observations; use a fresh workspace or database backup.')
        try:obs=projection(transport(q['query'],q['per_page']),q['per_page']);status='observed';error=''
        except RadarError as e:obs=None;status='failed';error=str(e)
        observed=now();rid=key()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM radar_runs').fetchone()[0]>=200:raise RadarError('Observation quota reached.')
            db.execute('INSERT INTO radar_runs VALUES(?,?,?,?,?,?)',(rid,qid,observed,status,error,json.dumps(obs,ensure_ascii=True) if obs is not None else None))
        return self.review(qid)
    def review(self,qid):
        q=self.query(qid)
        with self.store.connect() as db:runs=[dict(r) for r in db.execute('SELECT * FROM radar_runs WHERE query_id=? ORDER BY rowid',(qid,))]
        if not runs:return {'query':q,'status':'never_collected','runs':[],'candidates':[],'not_returned_since_previous':[]}
        latest=runs[-1];valid=[r for r in runs if r['status']=='observed']
        result={'query':q,'status':latest['status'],'latest_attempt':{k:latest[k] for k in ('id','observed_at','status','error')},'runs':[{k:r[k] for k in ('id','observed_at','status')} for r in runs],'candidates':[],'not_returned_since_previous':[],'last_successful_observation':valid[-1]['id'] if valid else None}
        if latest['status']=='failed':return result
        observation=json.loads(latest['observation']);result['coverage']={k:observation[k] for k in ('total_count','incomplete_results','returned','raw_response_sha256')};result['coverage']['page_limit']=1;result['coverage']['truncated_to_page']=observation['total_count']>observation['returned']
        prior={};first={}
        for r in valid[:-1]:
            for item in json.loads(r['observation'])['items']:
                first.setdefault(item['id'],r['observed_at']);prior[item['id']]=(item,r['observed_at'])
        previous_ids=set(x['id'] for x in json.loads(valid[-2]['observation'])['items']) if len(valid)>1 else set()
        current_ids=set(x['id'] for x in observation['items'])
        for rank,x in enumerate(observation['items'],1):
            old=prior.get(x['id']);elapsed=(stamp(latest['observed_at'])-stamp(old[1])).total_seconds() if old else None
            clock_status='first_observation' if old is None else ('comparable' if elapsed>0 else 'non_increasing_clock')
            if elapsed is not None and elapsed<=0:elapsed=None
            delta=x['stars']-old[0]['stars'] if old else None
            result['candidates'].append({**x,'rank_in_returned_page':rank,'discovery':'first_seen_in_this_query' if old is None else ('returned_again' if x['id'] in previous_ids else 'reappeared_in_this_query'),'first_observed_at':first.get(x['id'],latest['observed_at']),'previous_observed_at':old[1] if old else None,'previous_full_name':old[0]['full_name'] if old else None,'star_delta':delta,'comparison_status':clock_status,'interval_seconds':elapsed,'stars_per_day_observed':delta*86400/elapsed if elapsed is not None and elapsed>=3600 else None})
        result['not_returned_since_previous']=sorted(previous_ids-current_ids)
        return result
    def import_candidate(self,qid,repo_id):
        integer(repo_id,1,2**63-1);r=self.review(qid)
        if r['status']!='observed':raise RadarError('Latest attempt is not a successful observation; collect successfully before importing.')
        item=next((x for x in r['candidates'] if x['id']==repo_id),None)
        if item is None:raise RadarError('Repository is not in the latest returned page.')
        snapshot={'observation_type':'GitHub API metadata summary; not a repository quality review','query':r['query']['query'],'observed_at':r['latest_attempt']['observed_at'],'coverage':r['coverage'],'candidate':item}
        return self.store.apply('source',{'title':'GitHub: '+item['full_name'],'url':item['url'],'kind':'summary','origin_group':'github-repository-'+str(repo_id),'availability':'summary','text':json.dumps(snapshot,ensure_ascii=False,indent=2)})

def main():
    p=argparse.ArgumentParser(description='Explicit unauthenticated public GitHub search. Query text is sent to GitHub.')
    p.add_argument('--data-dir',required=True);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('add');a.add_argument('--label',required=True);a.add_argument('--query',required=True);a.add_argument('--per-page',type=int,default=20)
    sub.add_parser('list')
    c=sub.add_parser('collect');c.add_argument('query_id');c.add_argument('--allow-network',action='store_true')
    r=sub.add_parser('review');r.add_argument('query_id');r.add_argument('--out',required=True)
    i=sub.add_parser('import');i.add_argument('query_id');i.add_argument('repo_id',type=int)
    args=p.parse_args()
    try:
        radar=Radar(Path(args.data_dir)/'workspace.sqlite3')
        if args.command=='add':result={'query_id':radar.add(args.label,args.query,args.per_page)}
        elif args.command=='list':result={'queries':radar.listing()}
        elif args.command=='collect':
            if not args.allow_network:raise RadarError('Explicit --allow-network is required; query text goes to api.github.com.')
            result=radar.collect(args.query_id);print(json.dumps(result,ensure_ascii=True));return 3 if result['status']=='failed' else 0
        elif args.command=='review':
            raw=(json.dumps(radar.review(args.query_id),ensure_ascii=True,indent=2)+'\n').encode('ascii')
            if len(raw)>4*1024*1024:raise RadarError('Review output exceeds limit.')
            with open(args.out,'xb') as f:f.write(raw)
            result={'exported':True}
        else:
            radar.import_candidate(args.query_id,args.repo_id);result={'imported_metadata_summary':True}
        print(json.dumps(result,ensure_ascii=True));return 0
    except RadarError as e:print(str(e),file=sys.stderr);return 2
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error,UnicodeError):print('Invalid input or unavailable local workspace/output. No source content or paths echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
