"""Bounded local HTTP integration of existing CLI workflows; no new frontend."""
from .actions import Actions
from .timeline import Timeline
from .radar import Radar,fetch
from .watch import Watch

class Workflow:
    def __init__(self,path):
        self.actions=Actions(path);self.timeline=Timeline(path);self.radar=Radar(path);self.watch=Watch(path)
    def read(self,resource='overview',offset=0,limit=25):
        if type(offset) is not int or not 0<=offset<=10000 or type(limit) is not int or not 1<=limit<=50:raise ValueError('Pagination requires offset 0..10000 and limit 1..50.')
        if resource=='overview':
            with self.actions.store.connect() as db:
                return {'counts':{name:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for name,table in [('claims','claims'),('actions','news_actions'),('events','intel_events'),('queries','radar_queries'),('watches','local_watches')]},'notice':'Human review/planning only. Explicit network consent and registered-file read consent are separate POST actions.'}
        if resource=='claims':items=[{k:c[k] for k in ('id','text','topic','status')} for c in self.actions.store.state()['claims']]
        elif resource=='actions':items=self.actions.listing()
        elif resource=='events':
            items=self.timeline.listing()['events']
            for row in items:row.pop('basis')
        elif resource=='queries':items=self.radar.listing()
        elif resource=='watches':items=self.watch.listing()
        else:raise ValueError('Unknown workflow resource.')
        return {'resource':resource,'offset':offset,'limit':limit,'total':len(items),'items':items[offset:offset+limit],'pagination_notice':'Separate requests are not a frozen snapshot; concurrent edits may change page membership.'}
    def apply(self,op,d):
        shapes={
            'action-create':{'claim_id','title','why','steps','owner','due'},
            'action-check':{'action_id','index','done','note'},
            'action-status':{'action_id','status','note'},
            'action-review':{'action_id','note'},
            'action-show':{'action_id'},
            'action-edit':{'action_id','title','why','owner','due','note'},
            'event-create':{'claim_id','title','kind','precision','start','end','zone','note'},
            'event-withdraw':{'event_id','note'},
            'event-revise':{'event_id','title','kind','precision','start','end','zone','note'},
            'event-show':{'event_id'},
            'radar-add':{'label','query','per_page'},
            'radar-collect':{'query_id','allow_network'},
            'radar-review':{'query_id'},
            'radar-import':{'query_id','repo_id'},
            'watch-scan':{'allow_local_reads'},
            'watch-changes':{'source_id'},
        }
        if op not in shapes or type(d) is not dict or set(d)!=shapes[op]:raise ValueError('Unknown operation or unexpected/missing fields.')
        if op=='action-create':return {'action_id':self.actions.create(d['claim_id'],d['title'],d['why'],d['steps'],d['owner'],d['due'])}
        if op=='action-check':self.actions.check(d['action_id'],d['index'],d['done'],d['note'])
        elif op=='action-status':self.actions.transition(d['action_id'],d['status'],d['note'])
        elif op=='action-review':self.actions.rebase(d['action_id'],d['note'])
        elif op=='action-edit':self.actions.edit(d['action_id'],d['title'],d['why'],d['owner'],d['due'],d['note'])
        elif op=='action-show':return {'action':self.actions.show(d['action_id'])}
        elif op=='event-create':return {'event_id':self.timeline.create(d['claim_id'],d['title'],d['kind'],d['precision'],d['start'],d['end'],d['zone'],d['note'])}
        elif op=='event-revise':self.timeline.revise(d['event_id'],d['title'],d['kind'],d['precision'],d['start'],d['end'],d['zone'],d['note'])
        elif op=='event-withdraw':self.timeline.withdraw(d['event_id'],d['note'])
        elif op=='event-show':return {'event':self.timeline.show(d['event_id'])}
        elif op=='radar-add':return {'query_id':self.radar.add(d['label'],d['query'],d['per_page'])}
        elif op=='radar-collect':
            if d['allow_network'] is not True:raise ValueError('Explicit boolean allow_network=true is required to send the saved query to GitHub.')
            return {'review':self.radar.collect(d['query_id'],transport=fetch)}
        elif op=='radar-review':return {'review':self.radar.review(d['query_id'])}
        elif op=='radar-import':self.radar.import_candidate(d['query_id'],d['repo_id'])
        elif op=='watch-scan':
            if d['allow_local_reads'] is not True:raise ValueError('Explicit boolean allow_local_reads=true is required to scan registered local files.')
            return {'results':self.watch.scan()}
        elif op=='watch-changes':return {'changes':self.watch.changes(d['source_id'])}
        return {'recorded':True}
