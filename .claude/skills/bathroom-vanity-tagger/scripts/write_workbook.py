"""Write tag columns into an xlsx without touching any other cell.

The workbook is edited at the XML level: only the cells of the 16 tag columns
in the detail sheet change. Every other cell, formula cached value, style,
table, validation and sheet keeps its original bytes, so sales numbers cannot
drift. Two modes, chosen automatically from the header row:

- replace: the tag headers already exist (a workbook this skill tagged before);
  each tag cell keeps its style and gets the new value.
- append: the tag headers are missing; the columns are added after the last
  column, with column widths and the sheet's table range extended.

Network-free. Usage:
  python3 -I write_workbook.py --base in.xlsx --matrix tagging_matrix.json --out out.xlsx
"""
import argparse,json,re,zipfile
from pathlib import Path
from xml.sax.saxutils import escape

def col_letter(n):
    s=''
    while n:n,r=divmod(n-1,26);s=chr(65+r)+s
    return s

def col_number(letters):
    n=0
    for ch in letters:n=n*26+ord(ch)-64
    return n

def sheet_path(z,name):
    wb=z.read('xl/workbook.xml').decode('utf-8')
    rels=z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    m=re.search(r'<(?:\w+:)?sheet\b[^>]*\bname="'+re.escape(escape(name,{'"':'&quot;'}))+r'"[^>]*\br:id="([^"]+)"',wb) or re.search(r'<(?:\w+:)?sheet\b[^>]*\br:id="([^"]+)"[^>]*\bname="'+re.escape(name)+r'"',wb)
    if not m:raise SystemExit('sheet not found: '+name)
    t=re.search(r'<Relationship\b[^>]*\bId="'+re.escape(m.group(1))+r'"[^>]*\bTarget="([^"]+)"',rels) or re.search(r'<Relationship\b[^>]*\bTarget="([^"]+)"[^>]*\bId="'+re.escape(m.group(1))+r'"',rels)
    target=t.group(1).lstrip('/')
    return target if target.startswith('xl/') else 'xl/'+target

def cell_text(cell):
    v=re.search(r'<(?:\w+:)?v>(.*?)</(?:\w+:)?v>',cell,re.S)
    if v:return v.group(1)
    t=re.search(r'<(?:\w+:)?t[^>]*>(.*?)</(?:\w+:)?t>',cell,re.S)
    return t.group(1) if t else None

def make_cell(p,ref,style,value):
    s=' s="%s"'%style if style is not None else ''
    if value is None or value=='':return '<%sc r="%s"%s />'%(p,ref,s)
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        v=float(value);num=str(int(v)) if v.is_integer() else repr(v)
        return '<%sc r="%s"%s t="n"><%sv>%s</%sv></%sc>'%(p,ref,s,p,num,p,p)
    return '<%sc r="%s"%s t="str"><%sv>%s</%sv></%sc>'%(p,ref,s,p,escape(str(value)),p,p)

def root_prefix(xml,tag):
    # Namespace prefix of the root element. The XML declaration is optional:
    # parts written by openpyxl and similar tools start directly with the root tag.
    return re.match(r'(?:<\?xml[^>]*\?>\s*)?<(\w+:)?'+tag+r'\b',xml).group(1) or ''

CELL=re.compile(r'<(?:\w+:)?c\b[^>]*?\br="([A-Z]+)(\d+)"[^>]*?(?:/>|>.*?</(?:\w+:)?c>)',re.S)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',required=True);ap.add_argument('--matrix',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--sheet',default='SKU估算明细')
    args=ap.parse_args()
    m=json.loads(Path(args.matrix).read_text(encoding='utf-8'));headers=m['headers'];matrix=m['matrix']
    zin=zipfile.ZipFile(args.base);path=sheet_path(zin,args.sheet)
    xml=zin.read(path).decode('utf-8')
    p=root_prefix(xml,'worksheet')
    rows=list(re.finditer(r'(<%srow\b[^>]*\br="(\d+)"[^>]*>)(.*?)(</%srow>)'%(p,p),xml,re.S))
    if rows[0].group(2)!='1':raise SystemExit('expected header in row 1')
    header={cell_text(c.group(0)):c.group(1) for c in CELL.finditer(rows[0].group(3))}
    if len(rows)-1!=len(matrix):raise SystemExit('row count mismatch: sheet %d data rows, matrix %d'%(len(rows)-1,len(matrix)))
    mode='replace' if all(h in header for h in headers) else 'append'
    if mode=='append' and any(h in header for h in headers):raise SystemExit('some but not all tag headers present; refusing to guess')
    last=max(col_number(c.group(1)) for c in CELL.finditer(rows[0].group(3)))
    cols={h:(header[h] if mode=='replace' else col_letter(last+i+1)) for i,h in enumerate(headers)}
    targets={v:i for i,v in enumerate(cols[h] for h in headers)}
    head_style=re.search(r'\bs="(\d+)"',next(CELL.finditer(rows[0].group(3))).group(0))
    out=[];pos=0;changed=0
    for k,r in enumerate(rows):
        out.append(xml[pos:r.start()]);pos=r.end()
        body=r.group(3);n=int(r.group(2))
        values=headers if k==0 else matrix[k-1]
        if mode=='replace':
            def repl(c):
                if c.group(1) not in targets or int(c.group(2))!=n:return c.group(0)
                st=re.search(r'\bs="(\d+)"',c.group(0))
                return make_cell(p,c.group(1)+c.group(2),st.group(1) if st else None,values[targets[c.group(1)]])
            new=CELL.sub(repl,body)
            missing=[cl for cl in targets if not re.search(r'\br="%s%d"'%(cl,n),body)]
            if missing:raise SystemExit('row %d lacks tag cells %s; rebuild from the untagged source instead'%(n,missing))
        else:
            style=head_style.group(1) if (k==0 and head_style) else None
            new=body+''.join(make_cell(p,cols[h]+str(n),style,values[i]) for i,h in enumerate(headers))
        changed+=new!=body
        out.append(r.group(1)+new+r.group(4))
    out.append(xml[pos:])
    xml2=''.join(out)
    files={path:xml2}
    if mode=='append':
        width=''.join('<%scol min="%d" max="%d" width="%d" customWidth="1" />'%(p,last+i+1,last+i+1,40 if h=='打标说明' else 18) for i,h in enumerate(headers))
        xml2=re.sub(r'</%scols>'%p,width+'</%scols>'%p,xml2,count=1);files[path]=xml2
        # Extend the sheet's table (if any) so filters cover the new columns.
        relpath=path.rsplit('/',1)[0]+'/_rels/'+path.rsplit('/',1)[1]+'.rels'
        if relpath in zin.namelist():
            for t in re.findall(r'Target="([^"]*tables/[^"]+)"',zin.read(relpath).decode('utf-8')):
                tp='xl/tables/'+t.rsplit('/',1)[1]
                tx=zin.read(tp).decode('utf-8');tq=root_prefix(tx,'table')
                ref=re.search(r'\bref="([A-Z]+\d+):([A-Z]+)(\d+)"',tx)
                tx=tx.replace(ref.group(0),'ref="%s:%s%s"'%(ref.group(1),col_letter(last+len(headers)),ref.group(3)),1)
                cnt=int(re.search(r'<%stableColumns count="(\d+)"'%tq,tx).group(1))
                ids=[int(x) for x in re.findall(r'<%stableColumn id="(\d+)"'%tq,tx)]
                extra=''.join('<%stableColumn id="%d" name="%s" />'%(tq,max(ids)+i+1,escape(h,{'"':'&quot;'})) for i,h in enumerate(headers))
                tx=re.sub(r'<%stableColumns count="\d+"'%tq,'<%stableColumns count="%d"'%(tq,cnt+len(headers)),tx,count=1).replace('</%stableColumns>'%tq,extra+'</%stableColumns>'%tq,1)
                tx=re.sub(r'(<%sautoFilter\b[^>]*\bref=")[A-Z]+\d+:[A-Z]+(\d+)"'%tq,lambda mm:mm.group(1)+ref.group(1)+':'+col_letter(last+len(headers))+mm.group(2)+'"',tx)
                files[tp]=tx
    with zipfile.ZipFile(args.out,'w') as zout:
        for info in zin.infolist():
            data=files[info.filename].encode('utf-8') if info.filename in files else zin.read(info.filename)
            zout.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED)
    print(json.dumps({'mode':mode,'sheet':args.sheet,'sheetXML':path,'rowsWritten':len(rows)-1,'rowsChanged':changed-1 if changed else 0,'tagColumns':{h:cols[h] for h in headers}},ensure_ascii=False))

if __name__=='__main__':main()
