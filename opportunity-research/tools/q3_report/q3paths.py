"""Q3 浴室柜报告的路径配置。代码在本目录；数据在 Q3_DATA（默认 ./data，不入库）。"""
import os
CODE=os.path.dirname(os.path.abspath(__file__))
DATA=os.path.abspath(os.environ.get('Q3_DATA',os.path.join(CODE,'data')))
CLEAN=os.path.join(DATA,'clean')                      # 小平台干净父体数据 hd/wf/lw/lw_fix.pkl
INPUT=os.path.join(DATA,'input_data_v2')              # 从 input/data_v2 摘出来的少量文件
TAG=os.path.join(DATA,'tag.xlsx')                     # wen 的小平台打标
