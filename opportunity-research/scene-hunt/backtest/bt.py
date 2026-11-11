import json,glob,re,sys,csv
D=sys.argv[1]; out=sys.argv[2]
STOP={"for","with","the","and","a","of","to","in","on","my","your","&","-"}
def norm(w):
    w=w.lower()
    return w[:-1] if len(w)>3 and w.endswith("s") and not w.endswith("ss") else w
def toks(s): return [norm(w) for w in re.findall(r"[a-z0-9]+",s.lower()) if w not in STOP]
rows=[];pages=set()
for f in sorted(glob.glob(f"{D}/page*.json")):
    t=open(f).read().strip()
    try:
        d=json.loads(t)
        if isinstance(d,list): d=json.loads(d[0]['text'])
    except Exception as e:
        print("bad",f,e); continue
    pages.add(d['data']['page'])
    for it in d['data']['items']:
        kw=it.get('keywords') or ''
        kt=set(toks(kw))
        rel={r['asin']:r for r in (it.get('relationAsinList') or [])}
        def has_all(title): 
            tt=set(toks(title or '')); return bool(kt) and kt<=tt
        named=sum(1 for r in rel.values() if r.get('title') and has_all(r['title']))
        ara=sorted(it.get('araAsinList') or [],key=lambda a:-(a.get('conversionShareRate') or 0))
        top=ara[0] if ara else {}
        tr=rel.get(top.get('asin'),{})
        ttitle=tr.get('title') or ''
        missing=[w for w in kt if w not in set(toks(ttitle))] if ttitle else None
        share=it.get('araShareRate') or 0; click=it.get('araClickRate') or 0
        sigA = bool(ttitle) and share>=0.25 and (top.get('conversionShareRate') or 0)>=0.15 and missing and named<=4
        sigB = click>=0.20 and share<=0.05
        rows.append(dict(page=f.split("/")[-1],brand=int(bool(it.get("hasBrandWord"))),yoy=it.get("searchMonthlyCr"),avgPrice=it.get("avgPrice"),keyword=kw,searches=it.get('searches'),pr=it.get('purchaseRate'),products=it.get('products'),
            click=click,share=share,named=named,top_asin=top.get('asin'),top_share=top.get('conversionShareRate'),
            top_title=ttitle[:110],missing=" ".join(missing) if missing else "",sigA=int(bool(sigA)),sigB=int(bool(sigB))))
with open(out,"w",newline="") as fo:
    w=csv.DictWriter(fo,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("pages",len(pages),"keywords",len(rows),"A",sum(r['sigA'] for r in rows),"B",sum(r['sigB'] for r in rows))
