"""Import user-supplied RSS/Atom bytes. No network access or article fetching."""
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin
from .model import safe_url, text

class Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}:self.hidden+=1
        if tag in {'p','br','div','li','h1','h2','h3'} and not self.hidden:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style'} and self.hidden:self.hidden-=1
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def plain(value):
    p=Plain();p.feed(value or '');p.close()
    return '\n'.join(line.strip() for line in ''.join(p.parts).splitlines() if line.strip())

def parse_feed(xml,feed_url):
    xml=text(xml,'Feed XML',2000000)
    base=safe_url(feed_url)
    if re.search(r'<!\s*(DOCTYPE|ENTITY)',xml,re.I):raise ValueError('DTD/entity declarations are not accepted.')
    try:root=ET.fromstring(xml)
    except ET.ParseError as e:raise ValueError('Invalid RSS/Atom XML: '+str(e)) from e
    tag=lambda e:e.tag.rsplit('}',1)[-1]
    if tag(root) not in {'rss','feed','RDF'}:raise ValueError('Expected RSS or Atom feed.')
    entries=[e for e in root.iter() if tag(e) in {'item','entry'}]
    if len(entries)>200:raise ValueError('Import at most 200 entries per feed file.')
    output=[]
    for entry in entries:
        def get(*names):
            for name in names:
                for child in entry:
                    if tag(child)==name:return ''.join(child.itertext())
            return ''
        link=''
        for child in entry:
            if tag(child)=='link' and child.get('rel','alternate')=='alternate':
                link=child.get('href') or (child.text or '')
                if link.strip():break
        if not link.strip():raise ValueError('Feed entry has no article link; import skipped atomically, not silently.')
        url=safe_url(urljoin(base,link.strip()))
        title=plain(get('title')).strip() or 'Untitled feed item'
        content=plain(get('encoded','content','description','summary')).strip()
        if not content:content=title
        output.append({'title':title[:300],'url':url,'kind':'report','origin_group':'','text':content,'availability':'summary','error':''})
    if not output:raise ValueError('This feed has no entries.')
    return output
