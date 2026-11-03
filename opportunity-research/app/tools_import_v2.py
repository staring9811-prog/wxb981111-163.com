"""导入第二轮数据（2024-10 至 2026-09，含已打标结果）到本机数据库，供 wen 首次使用和回归测试。

用法（在 app 目录）：
    python tools_import_v2.py                 # 只导 Amazon 与搜索量，并预计算扫描、重算评分
    python tools_import_v2.py --channels      # 同时导入其他渠道 VP 样本（渠道VP/浴室柜_2026_渠道VP_20261103.xlsx）
    python tools_import_v2.py --suspect       # 再导入“标为 2026-10 实为 9 月”的待核文件，演示“疑似月份错误”
    python tools_import_v2.py --channel-history homedepot   # 只导入 Home Depot 历史回补缓存（../input/data_v2/渠道历史/homedepot/）并重建 2024-01 起的月度历史
数据目录用环境变量 PDT_DATA 指定（默认 app/data）。原始数据在 ../input/data_v2（不入库）。
"""
from pdt.core.seed import main

if __name__ == '__main__':
    main()
