"""把报告里的备注（侧边备注 + 格子备注）存进 data/notes.json，之后每次生成都会带上它们。
用法：python import_notes.py 某个导出或另存的报告.html"""
import os,sys,re,json,time,html
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import q3paths
def extract(s):
    side=''.join(re.findall(r'<aside class="note[^"]*".*?</aside>',s,re.S))
    m=re.search(r'<div id="xnd"[^>]*>(.*?)</div>',s,re.S)
    cells=html.unescape(m.group(1)).strip() if m else ''
    json.loads(cells or '{}')
    return side,cells or '{}'
if __name__=='__main__':
    side,cells=extract(open(sys.argv[1],encoding='utf-8').read())
    out=os.path.join(q3paths.DATA,'notes.json')
    json.dump({'ts':int(time.time()*1000),'side':side,'cells':cells,'from':os.path.basename(sys.argv[1])},open(out,'w',encoding='utf-8'),ensure_ascii=False)
    print('已存入',out,'侧边备注',side.count('<aside'),'条，格子备注',len(json.loads(cells)),'条')
