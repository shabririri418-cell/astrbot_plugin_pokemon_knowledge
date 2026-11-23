import re,unicodedata
from functools import lru_cache

def title_key(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(text)).replace('_',' ').casefold())

@lru_cache(maxsize=512)
def variants(text):
    try:
        from opencc import OpenCC
        global _CONVERTERS
        if '_CONVERTERS' not in globals():_CONVERTERS=(OpenCC('t2s'),OpenCC('s2t'))
        return tuple(dict.fromkeys([text]+[converter.convert(text) for converter in _CONVERTERS]))
    except ImportError:return (text,)

def search_tokens(text):
    text=unicodedata.normalize('NFKC',str(text)).casefold()
    tokens=['w'+word for word in re.findall(r'[a-z0-9]+',text) if len(word)>1 or word.isdigit()]
    for run in re.findall(r'[\u3400-\u9fff\u3040-\u30ff]+',text):
        tokens.extend('c'+format(ord(a),'x')+'x'+format(ord(b),'x') for a,b in zip(run,run[1:]))
    return list(dict.fromkeys(tokens))

def index_text(text):
    return ' '.join(dict.fromkeys(token for version in variants(text) for token in search_tokens(version)))

def candidate_keys(query):
    query=title_key(query)[:160];keys={query}
    for run in re.findall(r'[\u3400-\u9fff\u3040-\u30ff]+',query):
        for length in range(2,min(24,len(run))+1):
            keys.update(run[i:i+length] for i in range(len(run)-length+1))
    keys.update(re.findall(r"[a-z][a-z0-9.:'’♀♂-]{1,60}",query))
    return sorted(keys,key=len,reverse=True)[:800]
