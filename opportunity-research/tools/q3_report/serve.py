"""本地打开报告并允许在商品弹窗里改标：python serve.py  → 浏览器打开 http://127.0.0.1:8765
改标会写进 tag_override.csv 和原始打标库，然后整份报告重算，页面自动刷新。只监听本机。"""
import os,sys,json,subprocess,threading,webbrowser
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import q3paths,retag
OUT=os.path.join(q3paths.DATA,'Q3浴室柜_市场与渠道数据报告.html')
LOCK=threading.Lock()
def rebuild():
    r=subprocess.run(
        [sys.executable,'-X','utf8',os.path.join(q3paths.CODE,'run.py')],
        capture_output=True,encoding='utf-8',errors='replace',
        env=dict(os.environ,Q3_DATA=q3paths.DATA),
    )
    if r.returncode: raise RuntimeError(r.stderr[-2000:])
class H(BaseHTTPRequestHandler):
    def _send(self,code,body,ctype='application/json; charset=utf-8'):
        b=body if isinstance(body,bytes) else body.encode('utf-8')
        self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/api/ping'): return self._send(200,json.dumps({'ok':True}))
        if self.path in ('/','/index.html') or self.path.startswith('/?'):
            return self._send(200,open(OUT,'rb').read(),'text/html; charset=utf-8')
        self._send(404,'{}')
    def do_POST(self):
        if self.path=='/api/notes':
            # 浏览器里的备注自动存到 data/notes.json；只收比现存更新的
            d=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode('utf-8'))
            f=os.path.join(q3paths.DATA,'notes.json')
            old=json.load(open(f,encoding='utf-8')) if os.path.exists(f) else {'ts':0}
            if int(d.get('ts',0))>=int(old.get('ts',0)):
                json.dump({'ts':int(d['ts']),'side':d.get('side',''),'cells':d.get('cells','{}'),'from':'浏览器自动保存'},open(f,'w',encoding='utf-8'),ensure_ascii=False)
            return self._send(200,'{"ok":true}')
        if self.path!='/api/retag': return self._send(404,'{}')
        try:
            d=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode('utf-8'))
            with LOCK:
                st=retag.apply(d.get('edits',[]))
                try:
                    rebuild()
                except RuntimeError as error:
                    print(error,file=sys.stderr,flush=True)
                    return self._send(500,json.dumps({
                        'ok':False,'saved':True,
                        'err':'改标已写入数据源，报告重算失败。改标记录已保留，可再次点击保存重试。',
                    },ensure_ascii=False))
            self._send(200,json.dumps({'ok':True,**st},ensure_ascii=False))
        except Exception as e:
            self._send(500,json.dumps({'ok':False,'err':str(e)},ensure_ascii=False))
    def log_message(self,*a): pass
if __name__=='__main__':
    if not os.path.exists(OUT): print('先生成报告…'); rebuild()
    port=int(os.environ.get('Q3_PORT','8765')); url=f'http://127.0.0.1:{port}/'
    print('报告已打开：',url,'（关掉这个窗口就停止）');
    try: webbrowser.open(url)
    except Exception: pass
    ThreadingHTTPServer(('127.0.0.1',port),H).serve_forever()
