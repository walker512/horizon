"""Portable editorial brief. Every decision is human supplied, not fact checked."""
import html
import re
from .model import now

STATUSES={'editor-approved':'Editor-approved wording (not fact verification)','needs-review':'Needs editorial re-review','conflicted':'Conflicting linked passages','withheld':'Withheld by editor','unreviewed':'Not reviewed'}

def withholding_note(claim):
    if claim['decision'] != 'withhold':
        return ''
    if claim['review_signature'] == claim['signature']:
        return 'Withheld by editor. This does not approve the claim or resolve stale evidence.'
    return 'Earlier withholding decision; the reviewed material has since changed.'

def md(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', html.escape(str(value), quote=False))

def markdown(state):
    lines=['# Horizon editorial brief','',f'Exported: {now()}','',
    'Human-curated evidence links, not automatic fact verification. Quoted passages and origin groupings were supplied by the editor. Source availability and revisions are shown explicitly.','',
    'Origin groups describe declared common provenance, not proven independent corroboration. A supporting quotation does not establish the truth of its claim.','']
    for c in state['claims']:
        lines.extend(['## '+md(c['text'].replace('\n',' ')),'', '**Status:** '+STATUSES[c['status']],f'**Topic:** {md(c["topic"])}',f'**Provenance:** {c["known_origin_groups"]} declared origin groups; {c["unknown_origin_sources"]} source(s) with unknown origin.',''])
        if withholding_note(c):lines.extend(['Editorial disposition: '+withholding_note(c),''])
        if c['review_note']:lines.extend(['Editor note: '+md(c['review_note']),''])
        if not c['evidence']:lines.extend(['No linked evidence.',''])
        for e in c['evidence']:
            lines.extend([f'- **{e["relation"]}** · {md(e["source_title"])} · {e["kind"]} · {e["availability"]}'+(' · **OLDER SOURCE VERSION: REVIEW REQUIRED**' if e['stale'] else ''),f'  Source: <{e["source_url"].replace(">","%3E").replace("<","%3C")}>',f'  Snapshot: `{e["snapshot_id"]}` · chars {e["start"]}–{e["end"]}'])
            lines.extend('  > '+md(line) for line in e['quote'].splitlines())
            if e['note']:lines.append('  Editor annotation: '+md(e['note']))
            lines.append('')
    lines.extend(['## Source retrieval coverage',''])
    for s in state['sources']:
        snap=s['latest']
        lines.append(f'- {md(s["title"])}: {snap["availability"] if snap else "no snapshot"}; {len(s["snapshots"])} version(s).')
        if snap and snap['error']:lines.append('  Recorded limitation: '+md(snap['error']))
    return '\n'.join(lines)+'\n'

def html_brief(state):
    esc=lambda value:html.escape(str(value),quote=True)
    cards=[]
    for c in state['claims']:
        entries=[]
        for e in c['evidence']:
            entries.append(f'<div class="evidence"><p><b>{esc(e["relation"])}</b> · <a href="{esc(e["source_url"])}" rel="noopener noreferrer">{esc(e["source_title"])}</a> · {esc(e["kind"])} · {esc(e["availability"])}</p><blockquote>{esc(e["quote"])}</blockquote><p class="muted">Snapshot {esc(e["snapshot_id"])} · characters {e["start"]}–{e["end"]}</p>{"<p class=warn>Older source version. Editorial re-review required.</p>" if e["stale"] else ""}<p>{esc(e["note"])}</p></div>')
        cards.append(f'<article><span class="status {esc(c["status"])}">{esc(STATUSES[c["status"]])}</span><h2>{esc(c["text"])}</h2><p>{esc(withholding_note(c))}</p><p class="muted">{esc(c["topic"])} · {c["known_origin_groups"]} declared origin groups · {c["unknown_origin_sources"]} source(s) with unknown origin</p><p>{esc(c["review_note"])}</p>{"".join(entries) or "<p>No linked evidence.</p>"}</article>')
    coverage=''.join(f'<li>{esc(s["title"])}: {esc(s["latest"]["availability"] if s["latest"] else "no snapshot")} · {len(s["snapshots"])} version(s). {esc(s["latest"]["error"] if s["latest"] else "")}</li>' for s in state['sources'])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>Horizon editorial brief</title><style>*{{box-sizing:border-box}}body{{overflow-wrap:anywhere;font:16px/1.6 system-ui;margin:0;background:#f6f5f1;color:#243137}}main{{max-width:900px;margin:auto;padding:40px 22px}}h1{{font-size:42px;letter-spacing:-2px}}article{{background:white;border:1px solid #d8dfdd;border-radius:12px;padding:25px;margin:24px 0}}.muted{{color:#60716d;font-size:13px}}.status{{font-size:12px;text-transform:uppercase;font-weight:700;letter-spacing:.04em}}.needs-review,.conflicted,.warn{{color:#9c4d19}}.editor-approved{{color:#23614f}}blockquote{{margin:14px 0;border-left:3px solid #759c8e;padding:10px 18px;background:#f0f5f2;white-space:pre-wrap}}a{{color:#145c6b}}.evidence{{border-top:1px solid #e5e9e7;margin-top:20px}}.notice{{padding:18px;background:#e5eee9;border-radius:9px}}p{{white-space:pre-wrap}}@media print{{article{{break-inside:avoid}}}}</style></head><body><main><p class="muted">HORIZON · EDITORIAL EVIDENCE WORKBENCH · walker512</p><h1>Evidence before headlines.</h1><p class="muted">Exported {esc(now())}</p><div class="notice">Human-curated quotations and editorial decisions. Not automatic fact verification. Origin groups describe declared common provenance, not proven independent corroboration. Links do not establish that a claim is true.</div>{''.join(cards)}<h2>Source retrieval coverage</h2><ul>{coverage}</ul></main></body></html>'''
