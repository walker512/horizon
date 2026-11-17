"""Transparent deterministic role prompts; no model calls or task execution."""
import argparse,json,sqlite3,sys
from pathlib import Path
from .actions import Actions,ActionError,basis,bounded
from .server import bounded_json
from .watch import read_source

class PlanError(ValueError):pass
ROLES={
 'developer':{'official_docs':'Check the official documentation and exact supported API/model version.','pricing':'Check billing units, input/output/cache conditions, region and account tier; do not infer a task bill.','code_example':'Review the relevant code example, license, dependencies and failure handling in an authorized local environment.','compatibility':'Check affected interfaces and migration/rollback requirements; do not deploy based on a quoted announcement alone.'},
 'researcher':{'dataset':'Check dataset provenance, access rights, split definitions and leakage risks.','code':'Check code availability, license, environment and exact revision.','experiment_design':'Write a testable hypothesis, baseline, metrics, controls and a reproducible experiment plan.','limitations':'Record reported limitations and unresolved threats to validity; distinguish paper claims from reproduced findings.'},
}

def validate_spec(spec):
    if type(spec) is not dict or set(spec)!={'role','claim_id','slots','interpretations'}:raise PlanError('Exact role-plan spec fields required.')
    role=spec['role'];bounded(spec['claim_id'],'Claim ID',100)
    if type(role) is not str or role not in ROLES:raise PlanError('Unknown planning role.')
    slots=spec['slots']
    if type(slots) is not dict or set(slots)!=set(ROLES[role]):raise PlanError('All role slots must be explicit, using empty lists for gaps.')
    for ids in slots.values():
        if type(ids) is not list or len(ids)>5:raise PlanError('Each slot accepts at most five evidence IDs.')
        for eid in ids:bounded(eid,'Evidence ID',100)
        if len(set(ids))!=len(ids):raise PlanError('Duplicate evidence link in one slot.')
    v=spec['interpretations']
    if type(v) is not list or len(v)>5:raise PlanError('At most five explicitly unverified interpretations.')
    for x in v:bounded(x,'Unverified interpretation',300)
    return spec

class Plans:
    def __init__(self,path):self.actions=Actions(path)
    def evidence(self,claim_id):
        bounded(claim_id,'Claim ID',100)
        with self.actions.store.connect() as db:
            db.execute('BEGIN');c=next((x for x in self.actions.store.state(db)['claims'] if x['id']==claim_id),None)
            if c is None:raise PlanError('Claim not found.')
            return basis(c)
    def draft(self,spec):
        validate_spec(spec);b=self.evidence(spec['claim_id'])
        evidence={e['id']:e for e in b['evidence']};slots=[];steps=[]
        for name,prompt in ROLES[spec['role']].items():
            ids=spec['slots'][name]
            if any(e not in evidence for e in ids):raise PlanError('Slot references must belong to this current approved claim.')
            slots.append({'name':name,'status':'referenced_not_semantically_verified' if ids else 'missing_reference','references':[evidence[e] for e in ids],'classification_by':'human'})
            steps.append(('Review the selected references. ' if ids else 'Find and link an authorized relevant source; currently missing. ')+prompt)
        steps.append('Record unresolved questions, separate quoted claims from your inferences, and explicitly decide whether to proceed, defer or stop. No external action is authorized by this checklist.')
        why='Deterministic '+spec['role']+' review prompts; references are human-classified, not automatic factual/semantic verification. Unverified interpretations are not approved facts. '+json.dumps({'slot_evidence_ids':spec['slots'],'unverified_interpretations':spec['interpretations']},ensure_ascii=True,separators=(',',':'))
        bounded(why,'Adoptable rationale',3000)
        result={'format':'horizon-role-plan-v1','template_version':1,'input':spec,'captured_basis':b,'role_slots':slots,'unverified_interpretations':[{'text':x,'status':'unverified_human_interpretation'} for x in spec['interpretations']],'proposal':{'title':spec['role'].capitalize()+' review: '+b['text'][:220],'why':why,'steps':steps},'generation':'deterministic_role_prompts_no_model','notice':'Evidence quotations and editorial approval are not proof of truth or slot correctness. Suggested steps are not executed. Review and explicitly adopt into Actions.'}
        if len(json.dumps(result,ensure_ascii=True,indent=2))+1>500000:raise PlanError('Draft exceeds the supported 500000-character input/output bound.')
        return result
    def adopt(self,draft,owner='',due=''):
        if type(draft) is not dict or 'input' not in draft:raise PlanError('Expected a role-plan draft.')
        expected=self.draft(draft['input'])
        if json.dumps(draft,sort_keys=True,ensure_ascii=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,ensure_ascii=True,allow_nan=False):raise PlanError('Draft content, evidence or template differs; regenerate and review it.')
        p=expected['proposal']
        # Actions validates the same basis again inside its write transaction.
        return self.actions.create(draft['input']['claim_id'],p['title'],p['why'],p['steps'],owner,due,expected_basis=expected['captured_basis'])

def main():
    p=argparse.ArgumentParser(description='Prepare explicit developer/researcher review plans without AI calls or execution.')
    p.add_argument('--data-dir',required=True);s=p.add_subparsers(dest='command',required=True)
    e=s.add_parser('evidence');e.add_argument('claim_id')
    a=s.add_parser('draft');a.add_argument('--spec',required=True);a.add_argument('--out',required=True)
    a=s.add_parser('adopt');a.add_argument('--draft',required=True);a.add_argument('--owner',default='');a.add_argument('--due',default='')
    a=p.parse_args()
    try:
        plans=Plans(Path(a.data_dir)/'workspace.sqlite3')
        if a.command=='evidence':result=plans.evidence(a.claim_id)
        elif a.command=='draft':
            result=plans.draft(bounded_json(read_source(a.spec).encode('utf8')));raw=(json.dumps(result,ensure_ascii=True,indent=2)+'\n').encode('ascii')
            if len(raw)>500000:raise PlanError('Draft exceeds 500000 bytes.')
            with open(a.out,'xb') as f:f.write(raw)
            result={'drafted':True,'adopted':False,'executed':False}
        else:result={'action_id':plans.adopt(bounded_json(read_source(a.draft).encode('utf8')),a.owner,a.due),'executed':False}
        print(json.dumps(result,ensure_ascii=True));return 0
    except (ValueError,TypeError,KeyError,OSError,sqlite3.Error):print('Role-plan operation failed. Check reviewed evidence, explicit schema, limits and output destination. No private content echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
