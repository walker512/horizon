"""Prepare an original-synthetic draft; adoption requires an explicit option."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horizon.plans import Plans,ROLES
p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True);p.add_argument('--role',choices=ROLES,default='developer');p.add_argument('--adopt',action='store_true');a=p.parse_args();root=Path(a.data_dir)
if root.exists():p.error('Choose a new directory; existing workspaces are not modified.')
x=Plans(root/'workspace.sqlite3');s=x.actions.store.apply('demo',{});c=next(c for c in s['claims'] if c['evidence']);x.actions.store.apply('review',{'claim_id':c['id'],'decision':'approve','note':'Synthetic demonstration only'})
spec={'role':a.role,'claim_id':c['id'],'slots':{k:[] for k in ROLES[a.role]},'interpretations':['The announcement may warrant evaluation; this is an unverified interpretation, not an additional source fact.']}
draft=x.draft(spec)
for name,value in [('role-spec.json',spec),('role-draft.json',draft)]:
    (root/name).write_bytes((json.dumps(value,ensure_ascii=True,indent=2)+'\n').encode('ascii'))
result={'drafted':True,'adopted':False,'executed':False,'missing_reference_slots':list(spec['slots'])}
if a.adopt:result.update(adopted=True,action_id=x.adopt(draft,owner='Synthetic owner'))
print(json.dumps(result))
