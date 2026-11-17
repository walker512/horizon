"""Original synthetic end-to-end dossier workflow. No network or third-party content."""
import argparse,base64,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horizon.projects import Projects,markdown
from horizon.radar import Radar

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-dir',required=True);a=ap.parse_args();out=Path(a.data_dir);out.mkdir(exist_ok=False)
    ps=Projects(out/'workspace.sqlite3');radar=Radar(ps.store.path);q=radar.add('Synthetic samples','not sent to any service',2);ids=[];profiles=[]
    items=[{'id':i,'full_name':'synthetic/'+n,'stargazers_count':1,'created_at':'2026-01-01T00:00:00Z','description':'Original synthetic example','language':'Python','fork':False,'archived':False} for i,n in ((1,'SortKit'),(2,'SortBox'))]
    radar.collect(q,lambda *a:json.dumps({'items':items,'total_count':2,'incomplete_results':False}).encode())
    for item in items:
        pid=ps.select(q,item['id']);ids.append(pid)
        txt='SYNTHETIC DEMO. Solves list sorting. Candidate alternative: SampleSort. Requires Python 3. No real project capability is asserted.'
        def transport(n,readme):
            if not readme:return json.dumps({'id':item['id'],'full_name':n,'private':False,'default_branch':'main','archived':False,'license':None}).encode()
            b=txt.encode();return json.dumps({'type':'file','encoding':'base64','content':base64.b64encode(b).decode(),'size':len(b),'sha':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'path':'README.md'}).encode()
        run=ps.collect(pid,True,transport);entries=[]
        for category,quote in (('purpose','Solves list sorting.'),('alternatives','Candidate alternative: SampleSort.'),('barrier','Requires Python 3.')):
            state=ps.store.apply('claim',{'text':quote,'topic':'Synthetic project dossier'});cid=state['claims'][0]['id'];ps.store.apply('evidence',{'claim_id':cid,'snapshot_id':run['detail']['parts']['readme']['snapshot_id'],'quote':quote,'relation':'supports'})
            state=ps.store.apply('review',{'claim_id':cid,'decision':'approve','note':'Scripted approval of original synthetic fixture only; real dossiers require human review.'});c=next(c for c in state['claims'] if c['id']==cid)
            entries.append({'category':category,'criterion':category,'definition':'Human comparison of README-declared '+category,'unit':'text','platform':'Linux','version_scope':'Observed default branch; release version unverified','state':'known','value':quote,'raw_value':quote,'claim_id':cid,'evidence_id':c['evidence'][0]['id'],'note':'Original synthetic fixture mapping, not semantic verification.'})
        spec={'project_version':None,'entries':entries};(out/('spec-'+str(item['id'])+'.json')).write_text(json.dumps(spec,indent=2)+'\n');profiles.append(ps.add(pid,spec))
    result=ps.compare(profiles);(out/'comparison.json').write_text(json.dumps(result,ensure_ascii=True,indent=2)+'\n');(out/'comparison.md').write_text(markdown(result))
    # Local correction deliberately invalidates the first dossier; no action is executed.
    old=ps.show(profiles[0]);part=old['observation']['parts']['readme'];ps.store.apply('snapshot',{'source_id':part['source_id'],'text':'SYNTHETIC CORRECTION: Requires Python 4, not Python 3.','availability':'summary'})
    ps.withdraw(profiles[1],'Synthetic demonstration of human mapping withdrawal.')
    (out/'after-correction.json').write_text(json.dumps(ps.compare(profiles),ensure_ascii=True,indent=2)+'\n')
    print(json.dumps({'project_ids':ids,'profile_ids':profiles,'network_used':False,'outputs':['comparison.json','comparison.md','after-correction.json']}))
if __name__=='__main__':main()
