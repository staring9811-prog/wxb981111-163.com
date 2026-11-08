"""HTML 同步：报告里内嵌三样会变动的东西——改标、Amazon 商品页判定、备注。
build_block()：生成时写进 HTML；extract()：从任意一份报告 HTML 里取出来；merge()：按时间合并进 data/。"""
import os,re,csv,json,time,datetime
import q3paths
D=q3paths.DATA
OV=os.path.join(D,'tag_override.csv'); PDP=os.path.join(D,'amz_pdp_tags.json'); NOTES=os.path.join(D,'notes.json'); META=os.path.join(D,'sync_meta.json')
FIELDS=['渠道','商品ID','属性','改成','备注','时间']
def _ts_of(r):
    t=(r.get('时间') or '').strip()
    if t:
        try: return datetime.datetime.fromisoformat(t).timestamp()
        except Exception: pass
    m=re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',r.get('备注') or '')
    if m: return datetime.datetime.fromisoformat(m.group(1)).timestamp()
    return 0.0
def read_ov():
    if not os.path.exists(OV): return []
    rows=list(csv.DictReader(open(OV,encoding='utf-8')))
    for r in rows: r.setdefault('时间','')
    return rows
def write_ov(rows):
    with open(OV,'w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def meta():
    return json.load(open(META,encoding='utf-8')) if os.path.exists(META) else {}
def build_block():
    pdp=json.load(open(PDP,encoding='utf-8')) if os.path.exists(PDP) else {}
    m=meta(); pts=m.get('pdp_ts') or (int(os.path.getmtime(PDP)*1000) if os.path.exists(PDP) else 0)
    notes=json.load(open(NOTES,encoding='utf-8')) if os.path.exists(NOTES) else {'ts':0,'side':'','cells':'{}'}
    blk={'v':1,'generated':int(time.time()*1000),'overrides':read_ov(),'pdp':{'ts':pts,'tags':pdp},'notes':notes}
    return json.dumps(blk,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
def extract(html):
    m=re.search(r'<script type="application/json" id="q3sync">(.*?)</script>',html,re.S)
    if not m: raise SystemExit('这个 HTML 里没有同步数据（可能是旧版本报告）。')
    return json.loads(m.group(1))
def merge(blk,src=''):
    rep=[]
    # 1) 改标：同一 渠道+商品ID+属性 取时间较新的
    mine={(r['渠道'],r['商品ID'],r['属性']):r for r in read_ov()}
    add=upd=0;conf=[]
    for r in blk.get('overrides',[]):
        k=(r['渠道'],r['商品ID'],r['属性']); o=mine.get(k)
        if o is None: mine[k]=r; add+=1
        elif o.get('改成')!=r.get('改成'):
            if _ts_of(r)>_ts_of(o):
                conf.append(f"{k[0]} {k[1]} {k[2]}：{o.get('改成')} → {r.get('改成')}（对方更新）"); mine[k]=r; upd+=1
            else: conf.append(f"{k[0]} {k[1]} {k[2]}：保留 {o.get('改成')}（本地更新，对方是 {r.get('改成')}）")
    write_ov(list(mine.values()))
    rep.append(f'改标：新增 {add} 条，更新 {upd} 条，现共 {len(mine)} 条')
    if conf: rep.append('两边都改过、值不同的（按时间取新）：\n  '+'\n  '.join(conf))
    # 2) 商品页判定：版本较新的整份替换
    p=blk.get('pdp') or {}; m=meta(); cur=m.get('pdp_ts') or (int(os.path.getmtime(PDP)*1000) if os.path.exists(PDP) else 0)
    local=json.load(open(PDP,encoding='utf-8')) if os.path.exists(PDP) else {}
    if p.get('tags')==local: rep.append('商品页判定：两边一致，未变')
    elif p.get('tags') and p.get('ts',0)>cur:
        json.dump(p['tags'],open(PDP,'w',encoding='utf-8'),ensure_ascii=False); m['pdp_ts']=p['ts']; json.dump(m,open(META,'w'))
        rep.append(f"商品页判定：换成对方较新的版本（{len(p['tags'])} 个 ASIN）")
    else: rep.append('商品页判定：本地版本较新，保留本地')
    # 3) 备注：取较新的
    n=blk.get('notes') or {}; old=json.load(open(NOTES,encoding='utf-8')) if os.path.exists(NOTES) else {'ts':0}
    if n.get('ts',0)>old.get('ts',0):
        if os.path.exists(NOTES): json.dump(old,open(NOTES+'.bak','w',encoding='utf-8'),ensure_ascii=False)
        json.dump(n,open(NOTES,'w',encoding='utf-8'),ensure_ascii=False); rep.append('备注：换成对方较新的版本（旧的存为 notes.json.bak）')
    else: rep.append('备注：本地已是最新，未变')
    return rep
