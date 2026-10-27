"""Carry an analysis.json handoff forward to a new tagged workbook.

Sales rules, row manifest and coverage stay as in the previous handoff; only
the workbook binding, per-row taggingStatus, export audit and tagging block
are replaced. Network-free.

  python3 -I update_handoff.py --base-analysis v2.analysis.json --tag-dir OUT \
      --verify verify.json --workbook v3.xlsx --evidence-name v3.tags.json --out v3.analysis.json
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))  # works under python -I
from tag_cached import FEASIBILITY

def main():
    ap=argparse.ArgumentParser()
    for a in ('--base-analysis','--tag-dir','--verify','--workbook','--evidence-name','--out'):ap.add_argument(a,required=True)
    ap.add_argument('--changes',help='JSON list of human-readable rule changes for this version')
    args=ap.parse_args()
    d=json.loads(Path(args.base_analysis).read_text(encoding='utf-8'))
    tag=Path(args.tag_dir);verify=json.loads(Path(args.verify).read_text(encoding='utf-8'))
    summary=json.loads((tag/'tagging_summary.json').read_text(encoding='utf-8'))
    matrix=json.loads((tag/'tagging_matrix.json').read_text(encoding='utf-8'))
    state=matrix['headers'].index('打标状态')
    if len(matrix['matrix'])!=len(d['rowManifest']):raise SystemExit('row count differs from base rowManifest')
    previous={k:d[k] for k in ('schemaVersion','workbook','workbookSHA256')}
    d['schemaVersion']='analysis-handoff-tagged-%s'%summary['ruleVersion'].split('tagger-')[-1]
    d['workbook']=Path(args.workbook).name;d['workbookSHA256']=verify['outSHA256']
    for m,row in zip(d['rowManifest'],matrix['matrix']):m['taggingStatus']=row[state]
    d['taggingExportAudit']={'method':'XML级只改16个标签列；其余单元格逐个比较原始XML','base':verify['base'],'nonTagCellsCompared':verify['nonTagCellsCompared'],'nonTagCellsChanged':verify['nonTagCellsChanged'],'formulaCells':verify['formulaCells'],'tagCellsChecked':verify['tagCellsChecked'],'tagCellMismatches':verify['tagCellMismatches'],'otherZipPartsChanged':verify['otherZipPartsChanged'],'outputSHA256':verify['outSHA256'],'newAPICalls':0}
    t=d['tagging']
    t.update({'ruleVersion':summary['ruleVersion'],'evidenceFile':args.evidence_name,'summary':summary,'previousHandoff':previous,
              'feasibilityLegend':FEASIBILITY,
              'feasibilityPolicy':'逐行逐字段读取tags.json中rows[].feasibility；A/A2可用于属性分析（A2单列业务口径），B仅候选，C不作确定标签，D待用户确认规则，E/F/G为现有数据无法打标及原因。',
              'dimensionRules':{'enabled':summary.get('dimensionRulesEnabled',False),
                                'DIM-DWH-ORDER':'无方向“a x b x c inches”按D×W×H读取，仅当中间值与已选宽度相差≤1in；交叉核对样本深/高一致率约99%。未启用时只在JSON候选与可行性表中给出。',
                                'DIM-DW-SWAP':'同一来源标W与已选宽度不符而标D≈已选宽度时判为D/W互换；未启用时深度留空并标冲突，启用后取该来源标W值作深度。'},
              'heightIssue':'v2中137行高度=3in（SKU“3H”为3孔龙头位）已修复：无单位且不在a×b×c尺寸串中的nH不再作为高度，证据中记为rejectedCandidates。'})
    if args.changes:t['changesFromPrevious']=json.loads(Path(args.changes).read_text(encoding='utf-8'))
    Path(args.out).write_text(json.dumps(d,ensure_ascii=False,indent=1),encoding='utf-8')
    print(json.dumps({'out':args.out,'schemaVersion':d['schemaVersion'],'rows':len(d['rowManifest'])},ensure_ascii=False))

if __name__=='__main__':main()
