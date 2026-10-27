"""Prove a tagged workbook changed nothing but the tag columns.

Compares the output against its base cell by cell (raw XML of every cell,
so formulas, cached values and style ids all count) and checks every tag cell
against tagging_matrix.json. Other zip parts must be byte-identical, except
the tables/sheet parts an append legitimately extends. Network-free.

  python3 -I verify_workbook.py --base in.xlsx --out out.xlsx --matrix tagging_matrix.json
"""
import argparse,hashlib,html,json,re,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))  # works under python -I
import write_workbook as ww

def cells(xml):
    out={}
    for r in re.finditer(r'<(?:\w+:)?row\b[^>]*\br="(\d+)"[^>]*>(.*?)</(?:\w+:)?row>',xml,re.S):
        for c in ww.CELL.finditer(r.group(2)):out[c.group(1)+c.group(2)]=c.group(0)
    return out

def value(cell):
    t=ww.cell_text(cell)
    if t is None:return None
    t=html.unescape(t)
    return float(t) if re.search(r'\bt="n"',cell) else t

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--out',required=True);ap.add_argument('--matrix',required=True);ap.add_argument('--sheet',default='SKU估算明细')
    args=ap.parse_args()
    m=json.loads(Path(args.matrix).read_text(encoding='utf-8'))
    zb=zipfile.ZipFile(args.base);zo=zipfile.ZipFile(args.out)
    path=ww.sheet_path(zb,args.sheet)
    other_diff=[n for n in zb.namelist() if n!=path and not n.startswith('xl/tables/') and zb.read(n)!=zo.read(n)]
    missing=sorted(set(zb.namelist())^set(zo.namelist()))
    cb=cells(zb.read(path).decode('utf-8'));co=cells(zo.read(path).decode('utf-8'))
    header={value(co[k]):re.match(r'[A-Z]+',k).group(0) for k in co if re.fullmatch(r'[A-Z]+1',k)}
    tagcols={header[h]:i for i,h in enumerate(m['headers'])}
    changed_other=[k for k in cb if re.match(r'[A-Z]+',k).group(0) not in tagcols and cb[k]!=co.get(k)]
    added_other=[k for k in co if k not in cb and re.match(r'[A-Z]+',k).group(0) not in tagcols]
    bad=[]
    for i,row in enumerate(m['matrix'],2):
        for col,j in tagcols.items():
            got=value(co.get('%s%d'%(col,i),''));want=row[j]
            if isinstance(want,(int,float)) and got is not None:ok=abs(float(got)-float(want))<1e-9
            else:ok=(got or None)==(want if want!='' else None)
            if not ok:bad.append(('%s%d'%(col,i),want,got))
    res={'base':Path(args.base).name,'out':Path(args.out).name,'outSHA256':hashlib.sha256(Path(args.out).read_bytes()).hexdigest(),
         'otherZipPartsChanged':other_diff,'zipPartsAddedOrRemoved':missing,
         'nonTagCellsCompared':sum(1 for k in cb if re.match(r'[A-Z]+',k).group(0) not in tagcols),
         'nonTagCellsChanged':len(changed_other),'nonTagCellsAdded':len(added_other),
         'formulaCells':sum('<x:f' in v or '<f' in v for v in co.values()),
         'tagCellsChecked':len(m['matrix'])*len(tagcols),'tagCellMismatches':len(bad),'mismatchSample':bad[:5],
         'ok':not (other_diff or missing or changed_other or added_other or bad)}
    print(json.dumps(res,ensure_ascii=False,indent=1))
    raise SystemExit(0 if res['ok'] else 1)

if __name__=='__main__':main()
