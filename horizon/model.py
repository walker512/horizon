"""Explicit editorial records, never automatic fact verification."""
import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

KINDS = {'primary', 'report', 'relay', 'summary'}
AVAILABILITY = {'full', 'summary', 'failed'}
RELATIONS = {'supports', 'refutes', 'context'}

def now():
    return datetime.now(timezone.utc).isoformat()

def key():
    return str(uuid.uuid4())

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def text(value, name, limit=10000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f'{name} must be text, {"up to" if empty else "1–"}{limit} characters.')
    return value

def safe_url(value):
    value = text(value, 'URL', 3000)
    u = urlsplit(value)
    if u.scheme not in {'http', 'https'} or not u.hostname or u.username or u.password or any(ord(c) < 32 for c in value):
        raise ValueError('Use an HTTP(S) source URL without credentials.')
    return value

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,origin_group TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id),text TEXT NOT NULL,availability TEXT NOT NULL,error TEXT NOT NULL,created_at TEXT NOT NULL,hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,text TEXT NOT NULL,topic TEXT NOT NULL,decision TEXT NOT NULL DEFAULT 'unreviewed',review_signature TEXT,review_note TEXT NOT NULL DEFAULT '',reviewed_at TEXT);
            CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,claim_id TEXT NOT NULL REFERENCES claims(id),snapshot_id TEXT NOT NULL REFERENCES snapshots(id),start INTEGER NOT NULL,end INTEGER NOT NULL,relation TEXT NOT NULL,note TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,time TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL);
            ''')
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db
    def log(self, db, action, detail):
        db.execute('INSERT INTO audit(time,action,detail) VALUES(?,?,?)', (now(), action, json.dumps(detail, ensure_ascii=False)))
    def source(self, db, data):
        title = text(data.get('title'), 'Title', 300)
        url = safe_url(data.get('url'))
        kind = data.get('kind', 'report')
        group = text(data.get('origin_group', ''), 'Origin group', 200, True).strip()
        if kind not in KINDS:
            raise ValueError('Unknown source kind.')
        existing = db.execute('SELECT * FROM sources WHERE url=?', (url,)).fetchone()
        if existing:
            source_id = existing['id']
        else:
            if db.execute('SELECT count(*) FROM sources').fetchone()[0] >= 500:
                raise ValueError('This preview supports up to 500 source documents.')
            source_id = key()
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?)', (source_id, title, url, kind, group))
            self.log(db, 'source-added', {'source_id': source_id, 'title': title})
        self.snapshot(db, {**data, 'source_id': source_id})
        return source_id
    def snapshot(self, db, data):
        source_id = data.get('source_id')
        if not db.execute('SELECT 1 FROM sources WHERE id=?', (source_id,)).fetchone():
            raise ValueError('Source not found.')
        content = text(data.get('text', ''), 'Source content', 500000, True)
        availability = data.get('availability', 'full')
        error = text(data.get('error', ''), 'Failure detail', 2000, True)
        if availability not in AVAILABILITY:
            raise ValueError('Unknown source availability.')
        if availability == 'failed' and content:
            raise ValueError('Failed retrieval records must not contain supposed article text.')
        if availability != 'failed' and not content.strip():
            raise ValueError('Full or summary snapshots need text.')
        fingerprint = digest([content, availability, error])
        latest = db.execute('SELECT * FROM snapshots WHERE source_id=? ORDER BY rowid DESC LIMIT 1', (source_id,)).fetchone()
        if latest and latest['hash'] == fingerprint:
            return latest['id']
        if db.execute('SELECT count(*) FROM snapshots').fetchone()[0]>=2500 or db.execute('SELECT COALESCE(sum(length(text)),0) FROM snapshots').fetchone()[0]+len(content)>6000000:
            raise ValueError('Workspace snapshot limit reached (2500 snapshots / 6 million text characters). Export and start a separate workspace.')
        snapshot_id = key()
        db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?,?)', (snapshot_id, source_id, content, availability, error, now(), fingerprint))
        self.log(db, 'source-version-added', {'source_id': source_id, 'snapshot_id': snapshot_id, 'availability': availability, 'previous': latest['id'] if latest else None})
        return snapshot_id
    def claim(self, db, data):
        statement = text(data.get('text'), 'Claim text', 5000)
        topic = text(data.get('topic', ''), 'Topic', 200, True)
        claim_id = data.get('id')
        if claim_id:
            if not db.execute('SELECT 1 FROM claims WHERE id=?', (claim_id,)).fetchone():
                raise ValueError('Claim not found.')
            db.execute('UPDATE claims SET text=?,topic=? WHERE id=?', (statement, topic, claim_id))
        else:
            if db.execute('SELECT count(*) FROM claims').fetchone()[0]>=2000:raise ValueError('This preview supports up to 2000 claims per workspace.')
            claim_id = key()
            db.execute('INSERT INTO claims(id,text,topic) VALUES(?,?,?)', (claim_id, statement, topic))
        self.log(db, 'claim-written', {'claim_id': claim_id, 'text': statement, 'topic': topic})
        return claim_id
    def evidence(self, db, data):
        if not db.execute('SELECT 1 FROM claims WHERE id=?', (data.get('claim_id'),)).fetchone():
            raise ValueError('Claim not found.')
        snap = db.execute('SELECT * FROM snapshots WHERE id=?', (data.get('snapshot_id'),)).fetchone()
        if not snap or snap['availability'] == 'failed':
            raise ValueError('Evidence requires an available text snapshot.')
        quote = text(data.get('quote'), 'Evidence quotation', 3000)
        content = snap['text']
        if 'prefix' in data:
            prefix = text(data['prefix'], 'Selection prefix', 500000, True)
            start = len(prefix)
            if not content.startswith(prefix) or content[start:start+len(quote)] != quote:
                raise ValueError('Selection no longer matches this immutable snapshot.')
        else:
            if content.count(quote) != 1:
                raise ValueError('Select one exact occurrence in the source text. The quotation is missing or ambiguous.')
            start = content.index(quote)
        relation = data.get('relation')
        if relation not in RELATIONS:
            raise ValueError('Choose supports, refutes, or context.')
        note = text(data.get('note', ''), 'Evidence note', 3000, True)
        duplicate = db.execute('SELECT id FROM evidence WHERE claim_id=? AND snapshot_id=? AND start=? AND end=? AND relation=? AND removed=0', (data['claim_id'], snap['id'], start, start+len(quote), relation)).fetchone()
        if duplicate:
            return duplicate['id']
        if db.execute('SELECT count(*) FROM evidence').fetchone()[0]>=10000:raise ValueError('This preview supports up to 10000 evidence links including unlinked history.')
        evidence_id = key()
        db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,0)', (evidence_id, data['claim_id'], snap['id'], start, start+len(quote), relation, note))
        self.log(db, 'evidence-linked', {'evidence_id': evidence_id, 'claim_id': data['claim_id'], 'snapshot_id': snap['id'], 'start': start, 'end': start+len(quote), 'relation': relation, 'note': note})
        return evidence_id
    def state(self, db=None):
        if db is None:
            with self.connect() as connection:
                return self.state(connection)
        sources = [dict(r) for r in db.execute('SELECT * FROM sources ORDER BY rowid DESC')]
        source_map = {}
        for s in sources:
            s['snapshots'] = [dict(r) for r in db.execute('SELECT * FROM snapshots WHERE source_id=? ORDER BY rowid DESC', (s['id'],))]
            s['latest'] = s['snapshots'][0] if s['snapshots'] else None
            source_map[s['id']] = s
        claims = [dict(r) for r in db.execute('SELECT * FROM claims ORDER BY rowid DESC')]
        for c in claims:
            rows = db.execute('''SELECT e.*,s.source_id,s.text AS source_text,s.availability FROM evidence e JOIN snapshots s ON e.snapshot_id=s.id WHERE claim_id=? AND removed=0 ORDER BY e.rowid''', (c['id'],)).fetchall()
            links = []
            for r in rows:
                e = dict(r)
                source = source_map[e['source_id']]
                e['quote'] = e.pop('source_text')[e['start']:e['end']]
                e['stale'] = e['snapshot_id'] != source['latest']['id']
                e['source_title'] = source['title']
                e['source_url'] = source['url']
                e['kind'] = source['kind']
                e['origin_group'] = source['origin_group']
                links.append(e)
            c['evidence'] = links
            c['signature'] = digest([c['text'], c['topic'], [{k:e[k] for k in ('id','snapshot_id','quote','relation','note','stale','source_title','source_url','kind','origin_group')} for e in links]])
            groups = {e['origin_group'] for e in links if e['origin_group']}
            unknown = {e['source_id'] for e in links if not e['origin_group']}
            c['known_origin_groups'] = len(groups)
            c['unknown_origin_sources'] = len(unknown)
            stale = any(e['stale'] for e in links)
            conflict = any(e['relation']=='refutes' for e in links) and any(e['relation']=='supports' for e in links)
            changed = c['review_signature'] and c['review_signature'] != c['signature']
            if stale or changed:
                c['status'] = 'needs-review'
            elif conflict:
                c['status'] = 'conflicted'
            elif c['decision'] == 'approve' and c['review_signature'] == c['signature']:
                c['status'] = 'editor-approved'
            elif c['decision'] == 'withhold':
                c['status'] = 'withheld'
            else:
                c['status'] = 'unreviewed'
        return {'sources': sources, 'claims': claims, 'audit': [dict(r) for r in db.execute('SELECT time,action,detail FROM audit ORDER BY id DESC LIMIT 200')]}
    def apply(self, operation, data):
        with self.connect() as db:
            before = {c['id']: c for c in self.state(db)['claims']} if operation not in {'review', 'import'} else {}
            if operation == 'source':
                self.source(db, data)
            elif operation == 'snapshot':
                self.snapshot(db, data)
            elif operation == 'claim':
                self.claim(db, data)
            elif operation == 'source-meta':
                source = db.execute('SELECT * FROM sources WHERE id=?', (data.get('id'),)).fetchone()
                if not source:
                    raise ValueError('Source not found.')
                title = text(data.get('title',source['title']), 'Title', 300)
                group = text(data.get('origin_group',source['origin_group']), 'Origin group', 200, True).strip()
                kind = data.get('kind',source['kind'])
                if kind not in KINDS:
                    raise ValueError('Unknown source kind.')
                db.execute('UPDATE sources SET title=?,kind=?,origin_group=? WHERE id=?', (title,kind,group,source['id']))
                self.log(db, 'source-metadata-updated', {'source_id':source['id'],'title':title,'kind':kind,'origin_group':group})
            elif operation == 'evidence':
                self.evidence(db, data)
            elif operation == 'evidence-remove':
                if not db.execute('SELECT 1 FROM evidence WHERE id=? AND removed=0', (data.get('id'),)).fetchone():
                    raise ValueError('Evidence link not found.')
                db.execute('UPDATE evidence SET removed=1 WHERE id=?', (data['id'],))
                self.log(db, 'evidence-unlinked', {'evidence_id':data['id']})
            elif operation == 'review':
                claim = next((c for c in self.state(db)['claims'] if c['id']==data.get('claim_id')), None)
                if not claim:
                    raise ValueError('Claim not found.')
                decision = data.get('decision')
                if decision not in {'approve','withhold','unreviewed'}:
                    raise ValueError('Unknown editorial decision.')
                if decision == 'approve':
                    if any(e['stale'] for e in claim['evidence']):
                        raise ValueError('Source revisions require re-linking the current evidence before approval.')
                    if not any(e['relation']=='supports' for e in claim['evidence']):
                        raise ValueError('Approval requires an explicitly selected supporting passage.')
                    if any(e['relation']=='refutes' for e in claim['evidence']):
                        raise ValueError('A refuting passage remains. Resolve the wording/evidence or withhold the claim.')
                note = text(data.get('note',''), 'Review note', 3000, True)
                db.execute('UPDATE claims SET decision=?,review_signature=?,review_note=?,reviewed_at=? WHERE id=?', (decision,claim['signature'],note,now(),claim['id']))
                self.log(db, 'editorial-review', {'claim_id':claim['id'],'decision':decision,'signature':claim['signature'],'note':note})
            elif operation == 'demo':
                self.demo(db)
            elif operation == 'demo-update':
                source = db.execute('SELECT id FROM sources WHERE url=?', ('https://example.org/horizon-demo/release',)).fetchone()
                if not source:
                    raise ValueError('Load the synthetic demo first.')
                self.snapshot(db, {'source_id':source['id'],'text':'SYNTHETIC DEMO. Correction: Atlas 2.0 will launch on 24 May, not 17 May. The previously announced launch date was incorrect.','availability':'full'})
            elif operation == 'import':
                self.restore(db,data)
            elif operation == 'feed':
                from .feeds import parse_feed
                entries = parse_feed(data.get('xml'),data.get('feed_url'))
                for entry in entries:
                    self.source(db,entry)
                self.log(db,'feed-imported',{'entries':len(entries),'feed_url':data.get('feed_url')})
            else:
                raise ValueError('Unknown operation.')
            # Persist invalidation, rather than letting a later edit back to old
            # values resurrect a historical editorial decision.
            for claim in self.state(db)['claims']:
                previous = before.get(claim['id'])
                if previous and previous['review_signature'] and previous['review_signature'] != 'invalidated' and previous['signature'] != claim['signature']:
                    db.execute("UPDATE claims SET review_signature='invalidated' WHERE id=?", (claim['id'],))
                    self.log(db, 'review-invalidated', {'claim_id': claim['id'], 'operation': operation, 'previous_signature': previous['review_signature']})
            return self.state(db)
    def demo(self,db):
        if db.execute('SELECT count(*) FROM sources').fetchone()[0] or db.execute('SELECT count(*) FROM claims').fetchone()[0]:
            raise ValueError('Demo loading requires an empty workspace. Existing work is never overwritten.')
        source_id = self.source(db,{'title':'Atlas announcement (synthetic)','url':'https://example.org/horizon-demo/release','kind':'primary','origin_group':'atlas-announcement','text':'SYNTHETIC DEMO. Atlas 2.0 will launch on 17 May. An offline mode is planned, but its release date has not been announced.','availability':'full'})
        relay_id = self.source(db,{'title':'Relay of Atlas announcement (synthetic)','url':'https://example.org/horizon-demo/relay','kind':'relay','origin_group':'atlas-announcement','text':'SYNTHETIC DEMO. Citing the Atlas announcement: Atlas 2.0 will launch on 17 May.','availability':'summary'})
        self.source(db,{'title':'Unavailable article (synthetic)','url':'https://example.org/horizon-demo/unavailable','kind':'report','origin_group':'','text':'','availability':'failed','error':'Synthetic retrieval failure; article content unknown.'})
        claim_id = self.claim(db,{'text':'Atlas announced a 17 May launch for version 2.0.','topic':'Synthetic launch'})
        for sid in (source_id,relay_id):
            snapshot_id=db.execute('SELECT id FROM snapshots WHERE source_id=?', (sid,)).fetchone()['id']
            self.evidence(db,{'claim_id':claim_id,'snapshot_id':snapshot_id,'quote':'Atlas 2.0 will launch on 17 May.','relation':'supports','note':'Manual example annotation; not a real-world factual judgment.'})
        self.claim(db,{'text':'Atlas offline mode will launch on 17 May.','topic':'Unsupported synthetic claim'})
    def portable(self):
        with self.connect() as db:
            return {'format':'horizon-v1','exported_at':now(),'author':'walker512','tables':{t:[dict(r) for r in db.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in ('sources','snapshots','claims','evidence','audit')}}
    def restore(self,db,data):
        if db.execute('SELECT count(*) FROM sources').fetchone()[0] or db.execute('SELECT count(*) FROM claims').fetchone()[0]:
            raise ValueError('Import requires an empty workspace; no existing project will be overwritten.')
        if data.get('format')!='horizon-v1' or not isinstance(data.get('tables'),dict):
            raise ValueError('Not a Horizon project.')
        tables=data['tables']
        limits={'sources':500,'snapshots':2500,'claims':2000,'evidence':10000,'audit':20000}
        columns={'sources':('id','title','url','kind','origin_group'),'snapshots':('id','source_id','text','availability','error','created_at','hash'),'claims':('id','text','topic','decision','review_signature','review_note','reviewed_at'),'evidence':('id','claim_id','snapshot_id','start','end','relation','note','removed'),'audit':('id','time','action','detail')}
        if isinstance(tables.get('snapshots'),list) and sum(len(r.get('text','')) for r in tables['snapshots'] if isinstance(r,dict) and isinstance(r.get('text'),str))>6000000:raise ValueError('Project text limit exceeded.')
        for table in columns:
            rows=tables.get(table)
            if not isinstance(rows,list) or len(rows)>limits[table]:
                raise ValueError('Invalid or oversized project table: '+table)
            for row in rows:
                if not isinstance(row,dict) or set(row)!=set(columns[table]):
                    raise ValueError('Invalid fields in '+table)
                if table!='audit':
                    text(row['id'],'Record ID',80)
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',row['id']):raise ValueError('Invalid record ID.')
                if table=='sources':
                    safe_url(row['url']);text(row['title'],'Title',300);text(row['origin_group'],'Origin group',200,True)
                    if row['kind'] not in KINDS:raise ValueError('Invalid source kind.')
                elif table=='snapshots':
                    text(row['text'],'Snapshot text',500000,True);text(row['error'],'Error',2000,True)
                    if row['availability'] not in AVAILABILITY or row['hash']!=digest([row['text'],row['availability'],row['error']]):raise ValueError('Snapshot hash/availability mismatch.')
                    if row['availability']=='failed' and row['text']:raise ValueError('Failed snapshot contains text.')
                    if row['availability']!='failed' and not row['text'].strip():raise ValueError('Full or summary snapshots need text.')
                elif table=='claims':
                    text(row['text'],'Claim',5000);text(row['topic'],'Topic',200,True);text(row['review_note'],'Review note',3000,True)
                    if row['decision'] not in {'approve','withhold','unreviewed'}:raise ValueError('Unknown decision.')
                    row={**row,'decision':'unreviewed','review_signature':None,'reviewed_at':None}
                elif table=='evidence':
                    snap=db.execute('SELECT * FROM snapshots WHERE id=?',(row['snapshot_id'],)).fetchone()
                    if not snap or snap['availability']=='failed' or type(row['start']) is not int or type(row['end']) is not int or not 0<=row['start']<row['end']<=len(snap['text']) or row['relation'] not in RELATIONS or row['removed'] not in (0,1):raise ValueError('Invalid evidence span.')
                    text(row['note'],'Evidence note',3000,True)
                elif table=='audit':
                    text(row['time'],'Audit time',100);text(row['action'],'Audit action',100);text(row['detail'],'Audit detail',20000,True)
                names=columns[table]
                db.execute('INSERT INTO '+table+'('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',tuple(row[k] for k in names))
        if db.execute('SELECT 1 FROM sources s WHERE NOT EXISTS (SELECT 1 FROM snapshots v WHERE v.source_id=s.id) LIMIT 1').fetchone():
            raise ValueError('Every imported source must contain at least one snapshot.')
        self.log(db,'project-imported',{'note':'Imported prior audit records are supplied history, not authenticated provenance. All editorial approvals reset for review.'})
