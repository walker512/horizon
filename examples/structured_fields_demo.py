"""Original synthetic example; writes only into a new explicitly selected directory."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horizon.fields import Fields
p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True);a=p.parse_args();root=Path(a.data_dir)
if root.exists():p.error('Choose a new directory; existing workspaces are not modified.')
f=Fields(root/'workspace.sqlite3');ids=[]
for value in ('2.50','3.00'):
    statement='Synthetic base input price is '+value+' USD per million tokens.'
    state=f.store.apply('source',{'title':'Original synthetic model sheet','url':'https://example.invalid/model-v1','kind':'primary','text':statement,'availability':'full'})
    snap=state['sources'][0]['latest']['id'];old={c['id'] for c in state['claims']}
    state=f.store.apply('claim',{'text':statement,'topic':'synthetic-model-pricing'});c=next(c for c in state['claims'] if c['id'] not in old)
    state=f.store.apply('evidence',{'claim_id':c['id'],'snapshot_id':snap,'quote':statement,'relation':'supports'})
    claim=next(x for x in state['claims'] if x['id']==c['id']);e=claim['evidence'][0]['id'];f.store.apply('review',{'claim_id':c['id'],'decision':'approve'})
    d={'scope':{'provider':'Synthetic','model':'model-v1','channel':'direct','region':'global','tier':'standard','conditions':'Uncached text input; synchronous base service'},'field':'price_input','unit':'USD/million_tokens','value':value,'qualifier':'exact','effective_date':'','raw_value':value,'note':'Synthetic human mapping; no real price, date or usage impact asserted.'}
    ids.append(f.add(c['id'],e,d))
report=f.compare(*ids);(root/'comparison.json').write_bytes((json.dumps(report,ensure_ascii=True,indent=2)+'\n').encode('ascii'))
print(json.dumps({'observation_ids':ids,'delta':report['delta'],'review_required':report['review_required'],'note':'Old evidence is now historical; inspect comparison.json, not a current price endorsement.'}))
