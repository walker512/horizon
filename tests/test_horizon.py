"""Synthetic offline regressions. No accounts, real news or external requests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from horizon.model import Store, digest
from horizon.server import bounded_json
from horizon.export import html_brief, markdown, withholding_note

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'workspace.sqlite3')
        state = self.store.apply('demo', {})
        self.claim = next(c for c in state['claims'] if c['evidence'])['id']
        self.source = next(s for s in state['sources'] if s['kind']=='primary')['id']
    def current(self):
        return next(c for c in self.store.state()['claims'] if c['id']==self.claim)
    def review(self, decision='approve'):
        return self.store.apply('review', {'claim_id':self.claim,'decision':decision,'note':'Synthetic review'})
    def fresh(self):
        return Store(Path(self.tmp.name)/'import.sqlite3')
    def test_demo_provenance(self):
        c=self.current();self.assertEqual(c['known_origin_groups'],1);self.assertEqual(len(c['evidence']),2)
    def test_demo_no_overwrite(self):
        before=self.store.portable()['tables']
        with self.assertRaises(ValueError):self.store.apply('demo',{})
        self.assertEqual(before,self.store.portable()['tables'])
    def test_approve_then_correction(self):
        self.review();self.assertEqual(self.current()['status'],'editor-approved')
        self.store.apply('demo-update',{})
        self.assertEqual(self.current()['status'],'needs-review')
        self.assertTrue(any(e['stale'] for e in self.current()['evidence']))
        with self.assertRaises(ValueError):self.review()
    def test_unchanged_claim_preserves_review(self):
        self.review();c=self.current();self.store.apply('claim',{'id':c['id'],'text':c['text'],'topic':c['topic']})
        self.assertEqual(self.current()['status'],'editor-approved')
    def test_edit_restore_does_not_revive(self):
        self.review();c=self.current()
        for value in ['Synthetic changed claim',c['text']]:self.store.apply('claim',{'id':c['id'],'text':value,'topic':c['topic']})
        self.assertEqual(self.current()['status'],'needs-review')
        self.store=Store(self.store.path)
        self.assertEqual(self.current()['status'],'needs-review')
        self.review();self.assertEqual(self.current()['status'],'editor-approved')
    def test_metadata_restore_does_not_revive(self):
        self.review();s=next(s for s in self.store.state()['sources'] if s['id']==self.source)
        for title in ['Synthetic changed title',s['title']]:self.store.apply('source-meta',{'id':self.source,'title':title})
        self.assertEqual(self.current()['status'],'needs-review')
    def test_no_support_approval_blocked(self):
        c=next(c for c in self.store.state()['claims'] if not c['evidence'])
        with self.assertRaises(ValueError):self.store.apply('review',{'claim_id':c['id'],'decision':'approve'})
    def test_refutation_blocks_approval(self):
        e=self.current()['evidence'][0]
        self.store.apply('evidence',{'claim_id':self.claim,'snapshot_id':e['snapshot_id'],'quote':e['quote'],'relation':'refutes'})
        self.assertEqual(self.current()['status'],'conflicted')
        with self.assertRaises(ValueError):self.review()
    def test_withhold_and_stale_export(self):
        self.store.apply('demo-update',{});self.review('withhold');c=self.current()
        self.assertEqual(c['status'],'needs-review');self.assertTrue(withholding_note(c).startswith('Withheld by editor.'))
        h=html_brief(self.store.state());m=markdown(self.store.state())
        self.assertIn('Withheld by editor.',h);self.assertIn('Older source version',h)
        self.assertIn('OLDER SOURCE VERSION',m)
        self.store.apply('claim',{'id':self.claim,'text':'Synthetic revision'})
        self.assertTrue(withholding_note(self.current()).startswith('Earlier withholding'))
    def test_snapshot_immutable_and_idempotent(self):
        self.store.apply('demo-update',{});first=self.store.portable()['tables']['snapshots']
        self.store.apply('demo-update',{});self.assertEqual(first,self.store.portable()['tables']['snapshots'])
        s=next(s for s in self.store.state()['sources'] if s['id']==self.source)
        self.assertEqual(len(s['snapshots']),2);self.assertIn('17 May',s['snapshots'][1]['text'])
    def test_selection_must_match(self):
        e=self.current()['evidence'][0]
        with self.assertRaises(ValueError):self.store.apply('evidence',{'claim_id':self.claim,'snapshot_id':e['snapshot_id'],'quote':'not in source','relation':'supports'})
    def test_import_resets_approval(self):
        self.review();other=self.fresh();state=other.apply('import',self.store.portable())
        self.assertFalse(any(c['status']=='editor-approved' for c in state['claims']))
        self.assertEqual(len(state['sources']),3)
    def test_import_refuses_nonempty(self):
        with self.assertRaises(ValueError):self.store.apply('import',self.store.portable())
    def test_import_missing_snapshots_atomic(self):
        payload=self.store.portable();payload['tables']['snapshots']=[];payload['tables']['evidence']=[]
        other=self.fresh()
        with self.assertRaises(ValueError):other.apply('import',payload)
        self.assertEqual(other.state()['sources'],[]);self.assertEqual(other.state()['claims'],[])
    def test_import_empty_full_atomic(self):
        payload=self.store.portable();s=next(s for s in payload['tables']['snapshots'] if s['availability']=='full')
        s['text']='';s['hash']=digest(['',s['availability'],s['error']]);other=self.fresh()
        with self.assertRaises(ValueError):other.apply('import',payload)
        self.assertEqual(other.state()['sources'],[])
    def test_import_bad_hash_atomic(self):
        payload=self.store.portable();payload['tables']['snapshots'][0]['hash']='bad';other=self.fresh()
        with self.assertRaises(ValueError):other.apply('import',payload)
        self.assertEqual(other.state()['sources'],[])
    def test_failed_snapshot_cannot_contain_article(self):
        with self.assertRaises(ValueError):self.store.apply('snapshot',{'source_id':self.source,'availability':'failed','text':'invented article'})
    def test_export_escapes_content(self):
        self.store.apply('claim',{'text':'<script>alert("synthetic")</script> *bold*'})
        h=html_brief(self.store.state());m=markdown(self.store.state())
        self.assertNotIn('<script>',h);self.assertIn('&lt;script&gt;',h)
        self.assertIn(r'\*bold\*',m);self.assertNotIn('<script>',m)
    def test_url_rejects_credentials_and_script(self):
        for url in ['javascript:alert(1)','https://user:password@example.org/']:
            with self.assertRaises(ValueError):self.store.apply('source',{'title':'Synthetic','url':url,'text':'Text'})
    def test_bounded_json_deep(self):
        with self.assertRaisesRegex(ValueError,'maximum depth'):bounded_json('['*20000+'0'+']'*20000)
    def test_unicode_exact_prefix_selection(self):
        state=self.store.apply('source',{'title':'Synthetic Unicode','url':'https://example.org/unicode','text':'甲😀重复；重复'})
        snap=next(s for s in state['sources'] if s['url'].endswith('/unicode'))['latest']
        self.store.apply('evidence',{'claim_id':self.claim,'snapshot_id':snap['id'],'quote':'重复','prefix':'甲😀重复；','relation':'context'})
        e=self.current()['evidence'][-1];self.assertEqual(e['start'],5);self.assertEqual(e['quote'],'重复')
    def test_feed_is_summary(self):
        xml='<rss><channel><item><title>Synthetic entry</title><link>/post</link><description>Supplied excerpt</description></item></channel></rss>'
        self.store.apply('feed',{'xml':xml,'feed_url':'https://example.org/feed'})
        s=next(s for s in self.store.state()['sources'] if s['url']=='https://example.org/post')
        self.assertEqual(s['latest']['availability'],'summary')
    def test_feed_dtd_rejected_atomic(self):
        before=self.store.portable()['tables']
        with self.assertRaises(ValueError):self.store.apply('feed',{'xml':'<!DOCTYPE rss><rss/>','feed_url':'https://example.org/feed'})
        self.assertEqual(before,self.store.portable()['tables'])
    def test_bounded_json_valid(self):
        self.assertEqual(bounded_json('{"synthetic":[1,2]}'),{'synthetic':[1,2]})

if __name__=='__main__':unittest.main()
