"""把一份报告 HTML 里带的改标、商品页判定、备注合并进 data/，然后重新生成报告。
用法：python import_from_html.py 报告.html      （Windows 也可以把 HTML 拖到“导入HTML.bat”上）"""
import os,sys,subprocess
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import q3paths,sync
if len(sys.argv)<2: raise SystemExit('用法：python import_from_html.py 报告.html')
blk=sync.extract(open(sys.argv[1],encoding='utf-8').read())
print('\n'.join(sync.merge(blk)))
if '--no-build' not in sys.argv:
    r=subprocess.run([sys.executable,'-X','utf8',os.path.join(q3paths.CODE,'run.py')])
    if r.returncode: raise SystemExit('重新生成失败，请把上面的报错发给 Claude')
