"""一条命令重新生成 Q3 浴室柜报告：python run.py
数据目录：环境变量 Q3_DATA，默认本目录下 data/（结构见 README.md）。输出：data/Q3浴室柜_市场与渠道数据报告.html"""
import os,sys,runpy,time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import q3paths
os.chdir(q3paths.DATA)
for f in ['calc.py','calc2.py','calc3.py','gen.py','gen3.py']:
    t=time.time(); print(f'== {f}',flush=True)
    runpy.run_path(os.path.join(q3paths.CODE,f),run_name='__main__')
    print(f'   用时 {time.time()-t:.1f}s',flush=True)
print('完成：',os.path.join(q3paths.DATA,'Q3浴室柜_市场与渠道数据报告.html'))
