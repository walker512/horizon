"""Explicit fixed-catalogue official-page observations, not legal interpretation."""
import argparse,hashlib,http.client,json,sqlite3,sys,time,urllib.error,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from .model import Store
from .watch import Watch,invalidate
from .radar import NoRedirect

CATALOGUE={
 'openai-usage':{'url':'https://openai.com/policies/usage-policies/','title':'OpenAI usage policies','heading':'usage policies'},
 'anthropic-usage':{'url':'https://www.anthropic.com/legal/aup','title':'Anthropic usage policy','heading':'usage policy'},
}
LIMIT=2*1024*1024
class PolicyError(ValueError):pass

class PageText(HTMLParser):
    """Conservative static main element extraction; never a browser visibility claim."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.stack=[];self.parts=[];self.headings=[];self.main_count=0;self.closed=0
    def handle_starttag(self,tag,attrs):
        if len(self.stack)>=128:raise PolicyError('HTML nesting exceeds extraction limit.')
        if tag=='main':self.main_count+=1
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.stack.append(tag)
        if tag in {'p','div','li','h1','h2','h3','h4','br','section','article','tr'}:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag=='main':self.closed+=1
        if tag in self.stack:
            self.stack=self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]
        if tag in {'p','div','li','h1','h2','h3','h4','section','article','tr'}:self.parts.append('\n')
    def handle_data(self,data):
        if 'main' in self.stack and not any(t in self.stack for t in ('script','style','noscript','template','nav','footer')):
            self.parts.append(' '+data+' ')
            if 'h1' in self.stack:self.headings.append(data)

def extract(raw,heading):
    if type(raw) is not bytes or len(raw)>LIMIT:raise PolicyError('Page exceeds input limit.')
    try:
        value=raw.decode('utf-8',errors='strict')
        if '\x00' in value:raise PolicyError('Invalid page text.')
        p=PageText();p.feed(value);p.close()
    except (UnicodeError,RecursionError):raise PolicyError('Invalid UTF-8 page.') from None
    if p.main_count!=1 or p.closed!=1 or 'main' in p.stack:raise PolicyError('Expected one complete static main element.')
    if ' '.join(''.join(p.headings).split()).casefold()!=heading:raise PolicyError('Expected official-page heading is missing or changed.')
    result='\n'.join(line for line in (' '.join(x.split()) for x in ''.join(p.parts).splitlines()) if line)
    if not 100<=len(result)<=500000:raise PolicyError('Insufficient or excessive extracted text.')
    return result

def fetch(entry):
    # Only catalogue-selected URLs reach this function. No caller-controlled destination.
    if type(entry) is not str or entry not in CATALOGUE:raise PolicyError('Unknown catalogue entry.')
    url=CATALOGUE[entry]['url'];start=time.monotonic()
    request=urllib.request.Request(url,headers={'User-Agent':'Horizon-policy-observer/1','Accept':'text/html','Accept-Encoding':'identity'})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=15) as response:
            if response.status!=200 or response.geturl()!=url:raise PolicyError('Page did not return an exact successful response.')
            if response.headers.get_content_type()!='text/html' or response.headers.get('Content-Encoding','identity').lower() not in ('identity',''):raise PolicyError('Unsupported page encoding or content type.')
            charset=response.headers.get_content_charset()
            if charset and charset.lower() not in ('utf-8','utf8'):raise PolicyError('Only UTF-8 pages are supported.')
            lengths=response.headers.get_all('Content-Length',[])
            transfers=response.headers.get_all('Transfer-Encoding',[])
            if len(lengths)>1 or len(transfers)>1 or (lengths and transfers):raise PolicyError('Ambiguous HTTP message framing.')
            if transfers and transfers[0].strip().lower()!='chunked':raise PolicyError('Unsupported transfer encoding.')
            expected=None
            if lengths:
                value=lengths[0].strip()
                if not value or len(value)>10 or any(c not in '0123456789' for c in value):raise PolicyError('Invalid declared response length.')
                expected=int(value)
                if expected>LIMIT:raise PolicyError('Declared response exceeds byte limit.')
            raw=bytearray()
            while True:
                if time.monotonic()-start>30:raise PolicyError('Page read deadline exceeded.')
                chunk=response.read(min(65536,LIMIT+1-len(raw)))
                if not chunk:break
                raw.extend(chunk)
                if len(raw)>LIMIT:raise PolicyError('Page exceeds input limit.')
            if expected is not None and len(raw)!=expected:raise PolicyError('Truncated HTTP response.')
            return bytes(raw)
    except urllib.error.HTTPError as e:
        e.close();raise PolicyError('Official page unavailable; no redirect or retry followed.') from None
    except (urllib.error.URLError,OSError,TimeoutError,http.client.HTTPException):raise PolicyError('Official page connection failed; no retry attempted.') from None

class Policies:
    def __init__(self,path):self.store=Store(path)
    def collect(self,entry,allow_network=False):
        if allow_network is not True:raise PolicyError('Explicit network permission required.')
        if type(entry) is not str or entry not in CATALOGUE:raise PolicyError('Unknown catalogue entry.')
        meta=CATALOGUE[entry];raw_hash=None
        try:
            raw=fetch(entry);content=extract(raw,meta['heading']);raw_hash=hashlib.sha256(raw).hexdigest();error='';availability='summary'
        except PolicyError:
            content='';availability='failed';error='Official page unavailable or static extraction unsupported. No deletion or policy-change inference is made.'
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');before={c['id']:c for c in self.store.state(db)['claims']}
            existing=db.execute('SELECT id FROM sources WHERE url=?',(meta['url'],)).fetchone()
            old=db.execute('SELECT * FROM snapshots WHERE source_id=? ORDER BY rowid DESC LIMIT 1',(existing['id'],)).fetchone() if existing else None
            sid=self.store.source(db,{'url':meta['url'],'title':meta['title'],'kind':'primary','text':content,'availability':availability,'error':error})
            latest=db.execute('SELECT * FROM snapshots WHERE source_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
            status='unavailable' if availability=='failed' else ('unchanged' if old and old['id']==latest['id'] else ('recovered' if old and old['availability']=='failed' else ('changed' if old else 'first_observation')))
            result={'entry':entry,'source_id':sid,'snapshot_id':latest['id'],'result':status,'new_version':not old or old['id']!=latest['id'],'raw_response_sha256':raw_hash,'availability':availability,'extractor':'static-main-v1','legal_interpretation':False}
            self.store.log(db,'official-policy-observed',result);invalidate(self.store,db,before)
            return result

def main():
    p=argparse.ArgumentParser(description='Observe two fixed official policy pages explicitly, without a browser or scheduler.')
    sub=p.add_subparsers(dest='command',required=True);sub.add_parser('catalogue')
    c=sub.add_parser('collect');c.add_argument('entry',choices=CATALOGUE);c.add_argument('--data-dir',required=True);c.add_argument('--allow-network',action='store_true')
    a=p.parse_args()
    try:
        result=CATALOGUE if a.command=='catalogue' else Policies(Path(a.data_dir)/'workspace.sqlite3').collect(a.entry,a.allow_network)
        print(json.dumps(result,ensure_ascii=True));return 3 if result.get('result')=='unavailable' else 0
    except (ValueError,OSError,sqlite3.Error,TypeError):
        print('Policy operation failed. Check explicit permission, catalogue entry and workspace limits. No response or path is echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
