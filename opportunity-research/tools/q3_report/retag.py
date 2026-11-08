"""把改标同时写进：① data/tag_override.csv（报告最高优先级）② 原始打标库
   Amazon → data/pdt.sqlite3 的 tag 表；小平台 → data/tag.xlsx 的“确认：xx”列。
   尺寸、价格带、主色（小平台）原始库里没有对应列，只写 ①。"""
import csv,os,sqlite3,shutil,datetime
import q3paths
OV=os.path.join(q3paths.DATA,'tag_override.csv')
AMZ_COL={'拆装':'装','形态':'形态','尺寸':'尺寸段','台面':'台面材质','柜体':'柜体材质','主色':'主色','元素':'元素'}
SMALL_SHEET={'homedepot':'Home Depot','wayfair':'Wayfair','lowes':"Lowe's"}
SMALL_COL={'拆装':'确认：拆装/整装','台面':'确认：台面材质','柜体':'确认：柜体材质','元素':'确认：元素','形态':'确认：形态'}
ATTRS=['拆装','形态','尺寸','价格带','台面','柜体','主色','元素']
def _ov_write(edits,note):
    rows=list(csv.DictReader(open(OV,encoding='utf-8'))) if os.path.exists(OV) else []
    idx={(r['渠道'],r['商品ID'],r['属性']):r for r in rows}
    for e in edits:
        k=(e['ch'],e['pid'],e['attr'])
        if k in idx: idx[k]['改成']=e['val']; idx[k]['备注']=note
        else:
            r={'渠道':k[0],'商品ID':k[1],'属性':k[2],'改成':e['val'],'备注':note}; rows.append(r); idx[k]=r
    with open(OV,'w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['渠道','商品ID','属性','改成','备注']); w.writeheader(); w.writerows(rows)
def _amz_write(edits,now):
    c=sqlite3.connect(os.path.join(q3paths.DATA,'pdt.sqlite3')); n=0
    for e in edits:
        t=AMZ_COL.get(e['attr'])
        if not t: continue
        cur=c.execute("update tag set value=?,source='manual',status='confirmed',confidence=1,confirmed_at=? where channel='amazon' and item_id=? and tag=?",(e['val'],now,e['pid'],t))
        if cur.rowcount==0:
            c.execute("insert into tag(channel,item_id,tag,value,confidence,source,status,auto_value,candidates,img_group,confirm_mode,confirmed_at,month,config_version,category) values('amazon',?,?,?,1,'manual','confirmed','','[]','','',?,'',1,'浴室柜')",(e['pid'],t,e['val'],now))
        n+=1
    c.commit(); c.close(); return n
def _small_write(edits):
    es=[e for e in edits if e['ch'] in SMALL_SHEET and e['attr'] in SMALL_COL]
    if not es: return 0
    import openpyxl
    p=q3paths.TAG
    if not os.path.exists(p+'.原始备份.xlsx'): shutil.copy(p,p+'.原始备份.xlsx')
    wb=openpyxl.load_workbook(p); n=0
    for e in es:
        ws=wb[SMALL_SHEET[e['ch']]]; h={c.value:i+1 for i,c in enumerate(ws[1])}
        for row in range(2,ws.max_row+1):
            if str(ws.cell(row,1).value)==e['pid']:
                ws.cell(row,h[SMALL_COL[e['attr']]]).value=e['val']; n+=1; break
    wb.save(p); return n
def apply(edits,note='报告弹窗改标'):
    edits=[e for e in edits if e.get('ch') and e.get('pid') and e.get('attr') in ATTRS and str(e.get('val','')).strip()]
    now=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    _ov_write(edits,f'{note} {now}')
    a=_amz_write([e for e in edits if e['ch']=='amazon'],now)
    s=_small_write(edits)
    return {'改标':len(edits),'写回Amazon打标库':a,'写回小平台打标表':s}
