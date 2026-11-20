"""Deterministic main-article identity check; reads independently acquired bytes only."""
from html.parser import HTMLParser
import hashlib
import re
import unicodedata

SCHEMA='h028-main-article-text/v1'
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
BLOCK={'p','div','main','section','article','h1','h2','h3','h4','h5','h6','li','tr','td','th','pre','blockquote','ul','ol'}

class SnapshotError(ValueError):pass

class _Article(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.target_depth=None;self.matches=0;self.closed=False;self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);classes=set(attrs.get('class','').split())
        if tag not in VOID:self.stack.append((tag,classes))
        if 'content__default' in classes and any(t=='main' and 'page' in c for t,c in self.stack):
            self.matches+=1
            if self.matches!=1:raise SnapshotError('main article selector is ambiguous')
            self.target_depth=len(self.stack)
        if self.target_depth is not None and (tag in BLOCK or tag in {'br','hr'}):self.parts.append(' ')
    def handle_endtag(self,tag):
        if self.target_depth is not None and tag in BLOCK:self.parts.append(' ')
        indices=[i for i,(name,_) in enumerate(self.stack) if name==tag]
        if indices:
            index=indices[-1]
            if self.target_depth is not None and index+1==self.target_depth:
                self.target_depth=None;self.closed=True
            del self.stack[index:]
    def handle_data(self,data):
        if self.target_depth is not None and not any(t in {'script','style','noscript'} for t,_ in self.stack):self.parts.append(data)

def article_identity(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>5242880:raise SnapshotError('invalid or oversized official HTML')
    try:content=raw.decode('utf-8-sig')
    except UnicodeError as exc:raise SnapshotError('official HTML is not UTF-8') from exc
    parser=_Article();parser.feed(content);parser.close()
    if parser.matches!=1 or not parser.closed:raise SnapshotError('complete main.page/content__default article is not available')
    text=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',''.join(parser.parts))).strip()
    if not text:raise SnapshotError('empty main article')
    return {'schema_version':SCHEMA,'selector':'main.page > .content__default','normalization':'HTMLParser convert_charrefs; block/BR boundaries; ignore script/style/noscript; NFKC; collapse whitespace; preserve case','source_raw_sha256':hashlib.sha256(raw).hexdigest(),'main_text_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'main_text_characters':len(text),'matches':parser.matches,'complete':True}
