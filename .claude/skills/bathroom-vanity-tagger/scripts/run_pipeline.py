"""One-shot local run: tag -> write workbook -> verify -> reports -> handoff.

  python3 -I run_pipeline.py --data-root <02_数据源/BathroomVanities_202606_09_expansion> \
      --base-xlsx <上一版或未打标的.xlsx> --out-dir <输出目录> [--base-analysis <上一版.analysis.json>] \
      [--base-evidence <上一版tags.json>] [--name BathroomVanities_..._已打标_v12] [tag_cached 的开关]

Needs Python 3.10+ and openpyxl (pip install openpyxl). No network.
"""
import argparse,json,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent

def run(*cmd):
    print('>',' '.join(str(c) for c in cmd[1:]),flush=True)
    subprocess.run([sys.executable,'-I',*cmd],check=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-root',required=True);ap.add_argument('--base-xlsx',required=True);ap.add_argument('--out-dir',required=True)
    ap.add_argument('--base-analysis');ap.add_argument('--base-evidence');ap.add_argument('--name',default='BathroomVanities_已打标')
    ap.add_argument('--changes',help='本版规则变更说明 JSON 列表文件')
    args,extra=ap.parse_known_args()
    out=Path(args.out_dir);work=out/'_work';work.mkdir(parents=True,exist_ok=True)
    run(HERE/'selftest.py')
    run(HERE/'tag_cached.py','--data-root',args.data_root,'--out-dir',work,*extra)
    xlsx=out/(args.name+'.xlsx')
    run(HERE/'write_workbook.py','--base',args.base_xlsx,'--matrix',work/'tagging_matrix.json','--out',xlsx)
    verify=work/'verify.json'
    with open(verify,'w',encoding='utf-8') as f:
        subprocess.run([sys.executable,'-I',str(HERE/'verify_workbook.py'),'--base',args.base_xlsx,'--out',str(xlsx),'--matrix',str(work/'tagging_matrix.json')],check=True,stdout=f)
    v=json.loads(verify.read_text(encoding='utf-8'))
    if not v['ok']:raise SystemExit('verify failed: '+json.dumps(v,ensure_ascii=False)[:500])
    rep=[HERE/'feasibility_report.py','--tag-dir',work,'--data-root',args.data_root,'--out-xlsx',out/'浴室柜打标可行性评估.xlsx','--out-md',out/'浴室柜打标可行性评估.md']
    if args.base_evidence:rep+=['--base-evidence',args.base_evidence]
    run(*rep)
    run(HERE/'distribution.py','--tag-dir',work,'--out-md',out/'浴室柜各字段打标分布.md','--out-xlsx',out/'浴室柜各字段打标分布.xlsx')
    (out/(args.name+'.tags.json')).write_bytes((work/'tagging_evidence.json').read_bytes())
    if args.base_analysis:
        h=[HERE/'update_handoff.py','--base-analysis',args.base_analysis,'--tag-dir',work,'--verify',verify,'--workbook',xlsx,'--evidence-name',args.name+'.tags.json','--out',out/(args.name+'.analysis.json')]
        if args.changes:h+=['--changes',args.changes]
        run(*h)
    print(json.dumps({'workbook':str(xlsx),'verify':{k:v[k] for k in ('ok','nonTagCellsChanged','tagCellMismatches','outSHA256')},'outputs':sorted(p.name for p in out.iterdir() if p.is_file())},ensure_ascii=False,indent=1))

if __name__=='__main__':main()
