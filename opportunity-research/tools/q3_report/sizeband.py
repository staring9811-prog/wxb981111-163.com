import q3paths
"""统一尺寸段（含 28″）：18″ 15–21、24″ 21–26、28″ 26–29、30″ 29–33、36″ 33–39、42″ 39–45、48″ 45–54、60″ 54–66、72″+ ≥66（英寸，下限含上限不含）。
Amazon 用打标表里每个子体的 D9 宽（各月取中位数）。"""
import pandas as pd,os,pickle
BANDS=[(15,21,'18″'),(21,26,'24″'),(26,29,'28″'),(29,33,'30″'),(33,39,'36″'),(39,45,'42″'),(45,54,'48″'),(54,66,'60″'),(66,999,'72″+')]
def band(w):
    try: w=float(w)
    except (TypeError,ValueError): return None
    for lo,hi,b in BANDS:
        if lo<=w<hi: return b
    return None
_C=q3paths.DATA+'/amz_width.pkl'
def amz_band():
    if os.path.exists(_C): return pickle.load(open(_C,'rb'))
    df=pd.read_pickle(q3paths.INPUT+'/统一打标/统一打标_分析用.pkl')
    w=df.groupby('子ASIN')['D9宽(in)'].median()
    out={a:band(v) for a,v in w.items() if band(v)}
    pickle.dump(out,open(_C,'wb')); return out
