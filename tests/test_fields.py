"""Original synthetic model values; never current provider pricing claims."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from horizon.fields import Fields,FieldError,validate
from horizon.actions import ActionError
from horizon.backup import backup,restore
ROOT=Path(__file__).resolve().parents[1]
def spec(value='2.50',field='price_input',unit='USD/million_tokens'):
    return {'scope':{'provider':'Synthetic','model':'model-v1','channel':'direct','region':'global','tier':'standard','conditions':'Uncached text input; standard synchronous service'},'field':field,'unit':unit,'value':value,'qualifier':'exact','effective_date':'','raw_value':str(value),'note':'Human mapping of this synthetic quoted value; not a semantic machine check.'}
class FieldTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.f=Fields(self.p/'db'/'workspace.sqlite3');self.i=0
    def evidence(self,word='2.50',url=None):
        self.i+=1;url=url or 'https://example.invalid/'+str(self.i)
        self.f.store.apply('source',{'title':'Synthetic model','url':url,'kind':'primary','text':'Synthetic price/value: '+word,'availability':'full'})
        source=next(s for s in self.f.store.state()['sources'] if s['url']==url)
        before={x['id'] for x in self.f.store.state()['claims']};state=self.f.store.apply('claim',{'text':'Synthetic value is '+word});c=next(x['id'] for x in state['claims'] if x['id'] not in before)
        self.f.store.apply('evidence',{'claim_id':c,'snapshot_id':source['latest']['id'],'quote':'Synthetic price/value: '+word,'relation':'supports'})
        self.f.store.apply('review',{'claim_id':c,'decision':'approve'})
        claim=next(c1 for c1 in self.f.store.state()['claims'] if c1['id']==c);return c,claim['evidence'][0]['id'],source['id']
    def add(self,value='2.50',**kw):
        d=spec(value,**kw);c,e,_=self.evidence(str(value));return self.f.add(c,e,d)
    def test_create_quote_time(self):
        o=self.add();r=self.f.show(o);self.assertEqual(r['basis_status'],'current_editorial_basis');self.assertFalse(r['semantic_mapping_verified']);self.assertTrue(r['selected_evidence']['source_observed_at']);self.assertEqual(r['spec']['effective_date'],'')
    def test_exact_decimal(self):
        a=self.add('0.1');b=self.add('0.3');r=self.f.compare(a,b);self.assertEqual(r['delta'],'0.2');self.assertFalse(r['chronology_inferred'])
    def test_context_and_max_output_not_mix(self):
        a=self.add(1000000,field='context_window',unit='tokens');b=self.add(128000,field='max_output',unit='tokens');self.assertIsNone(self.f.compare(a,b)['delta'])
    def test_integer_delta(self):
        a=self.add(10,field='request_limit',unit='requests/minute');b=self.add(20,field='request_limit',unit='requests/minute');self.assertEqual(self.f.compare(a,b)['delta'],'10')
    def test_scope_dimensions(self):
        a=self.add()
        for k in ('provider','model','channel','region','tier','conditions'):
            d=spec();d['scope'][k]='different';c,e,_=self.evidence();b=self.f.add(c,e,d);self.assertEqual(self.f.compare(a,b)['comparison'],'incomparable_scope_or_unit')
    def test_unknown_scope_not_comparable(self):
        ids=[]
        for value in ('2.50','3'):
            d=spec(value);d['scope']['region']=None;c,e,_=self.evidence(value);ids.append(self.f.add(c,e,d))
        r=self.f.compare(*ids);self.assertEqual(r['comparison'],'unknown_scope');self.assertIsNone(r['delta'])
    def test_currency_and_period_not_convert(self):
        a=self.add();b=self.add(unit='EUR/million_tokens');self.assertIsNone(self.f.compare(a,b)['delta'])
        a=self.add(10,field='request_limit',unit='requests/minute');b=self.add(10,field='request_limit',unit='requests/day');self.assertIsNone(self.f.compare(a,b)['delta'])
    def test_qualifier_not_exact(self):
        a=self.add()
        for q in ('from','up_to','unknown'):
            d=spec();d['qualifier']=q
            if q=='unknown':d['value']=None;d['raw_value']=''
            c,e,_=self.evidence();b=self.f.add(c,e,d);self.assertEqual(self.f.compare(a,b)['comparison'],'non_exact_or_unknown')
    def test_license_no_legal_inference(self):
        a=self.add('License A',field='license',unit='identifier');b=self.add('License B',field='license',unit='identifier');r=self.f.compare(a,b);self.assertEqual(r['comparison'],'label_changed_no_legal_inference');self.assertIsNone(r['delta'])
    def test_missing_value_in_quote(self):
        c,e,_=self.evidence('other')
        with self.assertRaises(FieldError):self.f.add(c,e,spec())
    def test_unapproved_rejected(self):
        c,e,_=self.evidence();self.f.store.apply('review',{'claim_id':c,'decision':'withhold'})
        with self.assertRaises(ActionError):self.f.add(c,e,spec())
    def test_wrong_evidence_rejected(self):
        c,e,_=self.evidence()
        with self.assertRaises(FieldError):self.f.add(c,'missing',spec())
    def test_immutable_historical_and_stale(self):
        c,e,sid=self.evidence();a=self.f.add(c,e,spec());before=self.f.show(a)['basis']
        self.f.store.apply('snapshot',{'source_id':sid,'text':'Synthetic revised value: 3','availability':'full'})
        r=self.f.show(a);self.assertEqual(r['basis'],before);self.assertEqual(r['basis_status'],'needs_review')
        b=self.add('3');out=self.f.compare(a,b);self.assertTrue(out['review_required']);self.assertEqual(out['delta'],'0.50')
    def test_claim_edited_reverted_stays_stale(self):
        c,e,_=self.evidence();a=self.f.add(c,e,spec());old=next(c1 for c1 in self.f.store.state()['claims'] if c1['id']==c)['text']
        self.f.store.apply('claim',{'id':c,'text':'Changed'});self.f.store.apply('claim',{'id':c,'text':old});self.assertEqual(self.f.show(a)['basis_status'],'needs_review')
    def test_withdraw_preserves(self):
        a=self.add();b=self.add('3');before=self.f.show(a)['basis'];self.f.withdraw(a,'Corrected mapping');self.assertEqual(self.f.show(a)['basis'],before);self.assertEqual(self.f.compare(a,b)['comparison'],'withdrawn')
        with self.assertRaises(FieldError):self.f.withdraw(a,'Again')
    def test_schema_rejects(self):
        changes=[('value',2.5),('value',True),('value','NaN'),('value','1e999'),('value','-1'),('value','1.1234567'),('qualifier','guess'),('unit','USD/token'),('effective_date','2026-02-30'),('effective_date','yesterday'),('note','')]
        for k,v in changes:
            d=spec();d[k]=v
            with self.assertRaises(ValueError):validate(d)
        for v in (True,1.0,-1,10**13):
            d=spec(v,'context_window','tokens')
            with self.assertRaises(ValueError):validate(d)
    def test_unknown_strict(self):
        d=spec();d['qualifier']='unknown'
        with self.assertRaises(FieldError):validate(d)
        d['value']=None;d['raw_value']='';self.assertEqual(validate(d),d)
    def test_exact_schema(self):
        d=spec();d['extra']='x'
        with self.assertRaises(FieldError):validate(d)
        d=spec();del d['scope']['region']
        with self.assertRaises(FieldError):validate(d)
    def test_rollback(self):
        c,e,_=self.evidence()
        with patch.object(self.f.store,'log',side_effect=ValueError('fail')):
            with self.assertRaises(ValueError):self.f.add(c,e,spec())
        self.assertEqual(self.f.listing(),[])
    def test_backup_restore_observations_and_review_reset(self):
        a=self.add();backup(self.p/'db'/'workspace.sqlite3',self.p/'copy');restore(self.p/'copy',self.p/'restored',True);g=Fields(self.p/'restored'/'workspace.sqlite3');self.assertEqual(g.show(a)['spec'],self.f.show(a)['spec']);self.assertEqual(g.show(a)['basis_status'],'needs_review')
    def test_cli(self):
        c,e,_=self.evidence();s=self.p/'spec.json';s.write_text(json.dumps(spec()))
        def cli(*args):return subprocess.run([sys.executable,'-m','horizon.fields','--data-dir',str(self.p/'db'),*args],cwd=ROOT,capture_output=True,text=True,timeout=5)
        r=cli('add','--claim-id',c,'--evidence-id',e,'--spec',str(s));self.assertEqual(r.returncode,0,r.stderr);a=json.loads(r.stdout)['id'];self.assertEqual(cli('list').returncode,0);self.assertEqual(cli('show',a).returncode,0);out=self.p/'compare.json';self.assertEqual(cli('compare',a,a,'--out',str(out)).returncode,0);self.assertEqual(cli('compare',a,a,'--out',str(out)).returncode,2);self.assertEqual(cli('withdraw',a,'--note','Wrong scope').returncode,0)
if __name__=='__main__':unittest.main()
