import csv,re,sys
STOP={"for","with","the","and","a","of","to","in","on","my","your"}
def norm(w): return w[:-1] if len(w)>3 and w.endswith("s") and not w.endswith("ss") else w
def toks(s): return [norm(w) for w in re.findall(r"[a-z0-9]+",s.lower()) if w not in STOP]
R=list(csv.DictReader(open(sys.argv[1])))
def refined(r):
    if r['sigA']!='1': return False
    kw=r['keyword']
    if re.search(r"\d",kw): return False
    kt=toks(kw); tt=set(toks(r['top_title']))
    if not kt or kt[-1] not in tt: return False
    miss=[w for w in kt if w not in tt]
    return bool(miss) and miss!=[kt[-1]]
A=[r for r in R if refined(r)]
N=[r for r in A if r['yoy']=='']
print('rows',len(R),'| A',sum(r['sigA']=='1' for r in R),'| refined',len(A),'| refined+new',len(N))
for r in sorted(N,key=lambda r:-int(r['searches'])):
    print(r['searches'],'|',r['keyword'],'| miss',r['missing'],'| n',r['named'],'| s',round(float(r['top_share']),2),'| $',r['avgPrice'],'|',r['top_title'][:65])
