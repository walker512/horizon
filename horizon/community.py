"""Bounded official Hacker News observations linked by explicit repository URL only."""
import argparse,hashlib,http.client,json,re,sqlite3,sys,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
from .model import Store,key,now,safe_url
from .radar import NoRedirect,integer,bounded_text,Radar
from .server import bounded_json

class CommunityError(ValueError):pass
FEEDS=('new','top','show');LIMIT=1024*1024

def fetch(path):
    if type(path) is not str or not re.fullmatch(r'(?:newstories|topstories|showstories|item/[1-9]\d{0,14})\.json',path):raise CommunityError('Unknown official API path.')
    url='https://hacker-news.firebaseio.com/v0/'+path
    request=urllib.request.Request(url,headers={'User-Agent':'Horizon-community-observer/1','Accept':'application/json','Accept-Encoding':'identity'})
    try:
        start=time.monotonic()
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=10) as r:
            if r.status!=200 or r.geturl()!=url or r.headers.get_content_type()!='application/json' or r.headers.get('Content-Encoding','identity').lower() not in ('','identity'):raise CommunityError('Unsupported API response.')
            lengths=r.headers.get_all('Content-Length',[]);transfers=r.headers.get_all('Transfer-Encoding',[])
            if len(lengths)>1 or len(transfers)>1 or (lengths and transfers) or (transfers and transfers[0].strip().lower()!='chunked'):raise CommunityError('Ambiguous API response framing.')
            expected=None
            if lengths:
                s=lengths[0].strip()
                if not s or len(s)>10 or any(c not in '0123456789' for c in s):raise CommunityError('Invalid API response length.')
                expected=int(s)
                if expected>LIMIT:raise CommunityError('API response exceeds bound.')
            raw=bytearray()
            while True:
                if time.monotonic()-start>20:raise CommunityError('API read deadline exceeded.')
                b=r.read(min(65536,LIMIT+1-len(raw)))
                if not b:break
                raw.extend(b)
                if len(raw)>LIMIT:raise CommunityError('API response exceeds bound.')
            if expected is not None and expected!=len(raw):raise CommunityError('Truncated API response.')
            return bytes(raw)
    except urllib.error.HTTPError as e:e.close();raise CommunityError('HN API unavailable; no redirect or retry.') from None
    except (urllib.error.URLError,OSError,TimeoutError,http.client.HTTPException):raise CommunityError('HN API connection failed; no retry.') from None

def decode(raw):
    if type(raw) is not bytes or len(raw)>LIMIT:raise CommunityError('Invalid bounded API bytes.')
    try:return bounded_json(raw)
    except (ValueError,UnicodeError,RecursionError):raise CommunityError('Invalid API JSON.') from None

def repo_link(url):
    if not url:return None
    try:p=urllib.parse.urlsplit(url)
    except ValueError:return None
    if p.scheme!='https' or p.netloc.casefold()!='github.com' or p.username or p.password or p.query or p.fragment:return None
    if p.path.endswith('//'):return None
    parts=p.path.removesuffix('/').split('/')
    if len(parts)!=3 or parts[0] or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',parts[1]) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',parts[2]):return None
    return (parts[1]+'/'+parts[2]).casefold()

def project(raw,item_id):
    x=decode(raw)
    if x is None:return {'id':item_id,'status':'null_item'}
    if type(x) is not dict or type(x.get('id')) is not int or x['id']!=item_id:raise CommunityError('Item identity mismatch.')
    for flag in ('deleted','dead'):
        if flag in x and type(x[flag]) is not bool:raise CommunityError('Invalid item flag.')
    if x.get('deleted') or x.get('dead'):return {'id':item_id,'status':'deleted_or_dead'}
    if type(x.get('type')) is not str or x['type'] not in ('story','job','comment','poll','pollopt'):raise CommunityError('Invalid item type.')
    if x.get('type')!='story':return {'id':item_id,'status':'not_story'}
    title=bounded_text(x.get('title'),1000);integer(x.get('time'),0,10**11)
    for name in ('score','descendants'):
        if x.get(name) is not None:integer(x[name],0,10**9)
    url=x.get('url')
    if url=='':url=None
    if url is not None:
        if type(url) is not str:raise CommunityError('Invalid item link.')
        try:url=safe_url(url)
        except ValueError:raise CommunityError('Unsafe item link.') from None
    return {'id':item_id,'status':'story','title':title,'created_unix':x['time'],'score':x.get('score'),'comments_reported':x.get('descendants'),'linked_url':url,'github_repository':repo_link(url),'discussion_url':'https://news.ycombinator.com/item?id='+str(item_id),'raw_response_sha256':hashlib.sha256(raw).hexdigest()}

def parameters(feed,n,keyword):
    if type(feed) is not str or feed not in FEEDS:raise CommunityError('Unknown feed.')
    integer(n,1,20);bounded_text(keyword,100,True)

class Community:
    def __init__(self,path):
        self.store=Store(path)
        with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS community_runs(id TEXT PRIMARY KEY,feed TEXT NOT NULL,sample_size INTEGER NOT NULL,keyword TEXT NOT NULL,observed_at TEXT NOT NULL,status TEXT NOT NULL,error TEXT NOT NULL,observation TEXT)')
    def collect(self,feed='new',n=10,keyword='',allow_network=False,transport=fetch):
        parameters(feed,n,keyword)
        if allow_network is not True:raise CommunityError('Explicit network permission required.')
        with self.store.connect() as db:
            if db.execute('SELECT count(*) FROM community_runs').fetchone()[0]>=200:raise CommunityError('Community observation limit reached.')
        status='observed';error='';observation=None
        try:
            raw=transport(feed+'stories.json');ids=decode(raw)
            if type(ids) is not list or len(ids)>1000:raise CommunityError('Invalid bounded feed list.')
            for i in ids:integer(i,1,10**15-1)
            if len(set(ids))!=len(ids):raise CommunityError('Duplicate feed item IDs.')
            selected=ids[:n];items=[];start=time.monotonic()
            for i in selected:
                if time.monotonic()-start>90:raise CommunityError('Batch deadline reached.')
                items.append(project(transport('item/'+str(i)+'.json'),i))
            observation={'feed_returned':len(ids),'selected_ids':selected,'inspected':len(items),'feed_raw_sha256':hashlib.sha256(raw).hexdigest(),'items':items,'atomic_remote_snapshot':False}
        except (ValueError,TypeError,KeyError,OverflowError):status='failed';error='HN observation unavailable or invalid. No partial candidates, retry, or linked-page fetch.'
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM community_runs').fetchone()[0]>=200:raise CommunityError('Community observation limit reached.')
            db.execute('INSERT INTO community_runs VALUES(?,?,?,?,?,?,?,?)',(key(),feed,n,keyword,now(),status,error,json.dumps(observation,ensure_ascii=True) if status=='observed' else None))
        return self.review(feed,n,keyword)
    def review(self,feed='new',n=10,keyword=''):
        parameters(feed,n,keyword)
        with self.store.connect() as db:runs=[dict(r) for r in db.execute('SELECT * FROM community_runs WHERE feed=? AND sample_size=? AND keyword=? ORDER BY rowid',(feed,n,keyword))]
        r={'feed':feed,'sample_size':n,'local_title_keyword':keyword,'status':'never_collected','candidates':[],'not_returned_since_previous':[],'notice':'Bounded feed prefix, not global search. Community attention is not quality, independent corroboration or a star forecast.'}
        if not runs:return r
        last=runs[-1];r.update(status=last['status'],latest_attempt={k:last[k] for k in ('id','observed_at','status','error')},runs=[{k:x[k] for k in ('id','observed_at','status')} for x in runs])
        if last['status']!='observed':return r
        obs=json.loads(last['observation']);r['coverage']={k:v for k,v in obs.items() if k!='items'};r['coverage']['excluded_items']=[{'id':x['id'],'status':x['status']} for x in obs['items'] if x['status']!='story']
        candidates=[x for x in obs['items'] if x['status']=='story' and keyword.casefold() in x['title'].casefold()]
        r['coverage']['title_nonmatches']=[x['id'] for x in obs['items'] if x['status']=='story' and keyword.casefold() not in x['title'].casefold()]
        prior={};first={};previous_ids=set()
        for run in runs[:-1]:
            if run['status']!='observed':continue
            previous_ids=set()
            for x in json.loads(run['observation'])['items']:
                if x['status']=='story' and keyword.casefold() in x['title'].casefold():first.setdefault(x['id'],run['observed_at']);prior[x['id']]=x;previous_ids.add(x['id'])
        for x in candidates:
            old=prior.get(x['id']);r['candidates'].append({**x,'first_seen_in_this_stream':first.get(x['id'],last['observed_at']),'score_delta':x['score']-old['score'] if old and x['score'] is not None and old['score'] is not None else None,'discovery':'returned_again' if old else 'first_seen_in_this_stream'})
        r['not_returned_since_previous']=sorted(previous_ids-{x['id'] for x in candidates});return r
    def import_item(self,item_id,feed='new',n=10,keyword=''):
        integer(item_id,1,10**15-1);r=self.review(feed,n,keyword)
        if r['status']!='observed':raise CommunityError('Latest attempt must be successful before import.')
        x=next((x for x in r['candidates'] if x['id']==item_id),None)
        if x is None:raise CommunityError('Item not in latest matching candidates.')
        payload={'type':'HN metadata summary, not linked content or a factual endorsement','observed_at':r['latest_attempt']['observed_at'],'coverage':r['coverage'],'candidate':x}
        return self.store.apply('source',{'title':'HN: '+x['title'][:290],'url':x['discussion_url'],'kind':'relay','origin_group':'','text':json.dumps(payload,ensure_ascii=True,indent=2),'availability':'summary'})
    def associate(self,github_query_id,feed='new',n=10,keyword=''):
        community=self.review(feed,n,keyword);github=Radar(self.store.path).review(github_query_id)
        out={'community_status':community['status'],'github_status':github['status'],'matches':[],'relation':'Exact normalized HTTPS github.com repository URL only; not evidence of independent origin or matching quality.'}
        if community['status']=='observed' and github['status']=='observed':
            for c in community['candidates']:
                for g in github['candidates']:
                    if c['github_repository']==g['full_name'].casefold():out['matches'].append({'repository_id':g['id'],'full_name':g['full_name'],'hn_item_id':c['id'],'discussion_url':c['discussion_url'],'community_observed_at':community['latest_attempt']['observed_at'],'github_observed_at':github['latest_attempt']['observed_at']})
        return out

def main():
    p=argparse.ArgumentParser(description='Explicit official HN feed-prefix observations; never fetch linked pages/comments.')
    p.add_argument('--data-dir',required=True);p.add_argument('--feed',choices=FEEDS,default='new');p.add_argument('--sample-size',type=int,default=10);p.add_argument('--keyword',default='')
    s=p.add_subparsers(dest='command',required=True);c=s.add_parser('collect');c.add_argument('--allow-network',action='store_true');s.add_parser('review');i=s.add_parser('import');i.add_argument('item_id',type=int);a=s.add_parser('associate');a.add_argument('github_query_id')
    a=p.parse_args()
    try:
        c=Community(Path(a.data_dir)/'workspace.sqlite3');args=(a.feed,a.sample_size,a.keyword)
        if a.command=='collect':r=c.collect(*args,allow_network=a.allow_network)
        elif a.command=='review':r=c.review(*args)
        elif a.command=='import':c.import_item(a.item_id,*args);r={'imported_metadata_summary':True}
        else:r=c.associate(a.github_query_id,*args)
        print(json.dumps(r,ensure_ascii=True));return 3 if r.get('status')=='failed' else 0
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error):print('Community operation failed. Check consent, input, workspace bounds and latest observations. No private input echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
