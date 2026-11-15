"""利润测算台同步：把 wen 的原工具 tools/利润测算台/index.html 自动转成判定台里的利润测算页（PAGE-F24-01）。

用法（在 app 目录下）：
    python tools_sync_profit.py                       # 读 ../tools/利润测算台/index.html
    python tools_sync_profit.py --from 某处/index.html  # 读别处的原工具；成功后复制到 ../tools/利润测算台/index.html
    python tools_sync_profit.py --from git:origin/claude/eager-babbage-7wu6sw:profit-calculator/index.html
                                                      # 先 git fetch 该分支，再取文件；成功后同样复制过来
    python tools_sync_profit.py --check               # 只检查能否同步，不写文件

做什么：
1. 从原工具 HTML 抽出脚本、样式、页面主体；
2. 按下面的“补丁清单”逐条改：每条 = 锚点原文 → 替换内容 + 说明 + 对应【判定台改动】编号；
   样式统一加 #pc-root 前缀、去掉整页样式（见 CSS_RULES）；
3. 校验：每个锚点在原工具里恰好出现一次；默认参数段与计算段逐字保留；
   用 node 跑原工具与新 engine.js 的计算段，同一组输入（与测试 FLOW-17 相同）结果逐项相同；
4. 全部通过才写 pdt/static/profit/engine.js、profit.css、pdt/templates/_profit_sections.html 和同步记录 pdt/profit_sync.json。

任何一步不通过就停下，报出是哪一条、原工具哪一段变了，旧文件一律不动——这时需要找 AI 改补丁清单（见 开发约定.md“利润测算台更新流程”）。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
REPO = APP.parent
DEFAULT_SRC = REPO / "tools" / "利润测算台" / "index.html"
OUT_ENGINE = APP / "pdt" / "static" / "profit" / "engine.js"
OUT_CSS = APP / "pdt" / "static" / "profit" / "profit.css"
OUT_HTML = APP / "pdt" / "templates" / "_profit_sections.html"
PAGE = APP / "pdt" / "templates" / "tools_profit.html"
STAMP = APP / "pdt" / "profit_sync.json"


class SyncError(Exception):
    """同步停下：说明哪一条、原工具哪一段变了。"""


# ================================================================ 补丁清单
# 每条：no 序号，file 改哪个产物（js / html），mark 对应【判定台改动】编号（1/4～4/4；“附带修正”= 判定台验收时修的问题），
# why 说明，anchor 锚点原文（必须在原工具里恰好出现一次），new 替换内容。
# 锚点也可以写成 (开头原文, 结尾原文)：表示从开头到其后第一次出现的结尾整段替换（只用于整段换成服务端版本、内部改动与判定台无关的代码）。
MARKS = {
    "1/4": "初始方案从服务端读（window.PDT.init）",
    "2/4": "AI 识别报价单走服务端与费用闸门，浏览器不存 Key",
    "3/4": "报价库、历史库存服务端；“当前版本”= 服务端方案",
    "4/4": "起始步骤由服务端指定",
    "附带修正": "判定台验收时修的界面问题（DESIGN-14）",
}

PATCHES = [
    # ---------------------------------------------------------------- 1/4 初始方案
    dict(no=1, file="js", mark="1/4", why="初始方案来自服务端（window.PDT.init）；没有时沿用本浏览器草稿，再没有用示例数据",
         anchor='''let P = load("pc_params") || defaultParams();
let products = load("pc_products") || sampleProducts();
''',
         new='''/* 【判定台改动 1/4】初始方案来自服务端（window.PDT.init）；没有时沿用本浏览器的草稿，再没有用示例数据。 */
let P = (window.PDT && PDT.init && PDT.init.params) ? PDT.init.params : (load("pc_params") || defaultParams());
let products = (window.PDT && PDT.init && PDT.init.products) ? PDT.init.products : (load("pc_products") || sampleProducts());
'''),
    # ---------------------------------------------------------------- 2/4 AI 识别走服务端
    dict(no=2, file="js", mark="2/4", why="AI 渠道判断与提示文字：只用设置页所选大模型；aiCall 改为“准备 → 费用确认 → 服务端识别 → 取回 JSON”",
         anchor='''const aiCfg=()=>{ const d={prov:"auto",base:"",model:"",key:""}; try{ return Object.assign(d,JSON.parse(localStorage.getItem("pc_ai_cfg")||"{}")); }catch(e){ return d; } };
const aiKey=()=>aiCfg().key;
/* Which channel a call will use: Claude via the claude.ai viewer, or the user's own Anthropic / OpenAI-compatible API. */
function aiChannel(){ const c=aiCfg(); if(c.prov==="auto") return sampleFn?"sample":c.key?(c.base?"openai":"anthropic"):"none"; if(!c.key) return sampleFn&&c.prov==="auto"?"sample":"none"; return c.prov; }
function aiModeText(){ const el=document.getElementById("aiMode"); if(!el) return; const c=aiCfg(), ch=aiChannel();
  el.textContent=ch==="sample"?"使用你的 Claude 账号识别":ch==="anthropic"?`使用 Anthropic API（${c.model||AI_MODEL}）`:ch==="openai"?`使用 ${c.base||"OpenAI 兼容接口"}（${c.model||"未填模型"}）`:"尚未连接 AI：在 claude.ai 链接里打开，或在下方“AI 接口设置”接入你的 API";
  const pv=document.getElementById("aiProv"); if(pv&&document.activeElement!==pv){ pv.value=c.prov; document.getElementById("aiBase").value=c.base; document.getElementById("aiModel").value=c.model; document.getElementById("aiKey").placeholder=c.key?"已保存（重新填写可替换）":"填写后保存"; } }
''',
         new='''/* 【判定台改动 2/4】AI 识别报价单改走服务端：浏览器不直连大模型、不存 API Key（NFR-008、AC-F16-05）。
   用设置页所选大模型，先在费用确认弹窗（CMP-F16-01）确认再识别，费用记入同一费用记录；提示词 aiPrompt 原样在服务端使用。 */
const aiCfg=()=>({prov:"server"});
function aiChannel(){ return (window.PDT&&PDT.llm)?"server":"none"; }
function aiModeText(){ const el=document.getElementById("aiMode"); if(!el) return;
  el.innerHTML=aiChannel()==="server"?`使用设置页的大模型（${esc(PDT.llm)}）· 识别前先确认费用`:`大模型未连接：请到 <a href="/settings/keys">密钥与大模型</a> 填写密钥；也可以用左边的手动导入`; }
const aiKeys=()=>[...new Set(qlib.items.flatMap(q=>(q.items||[]).map(i=>i.key)).filter(Boolean))].slice(0,80);
async function aiPost(url,body){ const r=await fetch(url,{method:"POST",headers:{"content-type":"application/json",accept:"application/json"},body:JSON.stringify(body)}); const j=await r.json().catch(()=>({})); if(!r.ok) throw {code:"http_"+r.status,message:j.detail||("请求失败 "+r.status)}; return j; }
/* 准备识别内容 → 弹费用确认 → 服务端识别 → 取回 JSON（与原工具 aiCall 的返回相同）。 */
function aiCall(payload,{onStatus}={}){
  return new Promise(async(ok,no)=>{
    let tok; try{ tok=(await aiPost("/tools/profit/ai/prepare",payload)).token; }catch(e){ no(e); return; }
    const target="quote:"+tok;
    const on=ev=>{ const j=ev.detail; if(!j||j.target!==target) return; window.removeEventListener("pdt:job-started",on); onStatus&&onStatus("AI 识别中…");
      const poll=()=>fetch("/jobs/"+j.id,{headers:{accept:"application/json"}}).then(r=>r.json()).then(s=>{
        if(s.status==="running"||s.status==="queued"){ setTimeout(poll,1500); return; }
        fetch("/tools/profit/ai/"+tok,{headers:{accept:"application/json"}}).then(r=>r.json()).then(res=>{
          if(res.status==="done") ok(res.out); else no({code:res.code||s.status,message:res.error||s.error||("识别没有完成："+s.status)}); }); });
      poll(); };
    window.addEventListener("pdt:job-started",on);
    const b=document.createElement("button"); b.type="button"; b.hidden=true; b.dataset.costKind="profit_ai_quote"; b.dataset.costTarget=target; b.dataset.costParams="{}";
    document.body.appendChild(b); b.click(); b.remove(); onStatus&&onStatus("请在弹窗里确认费用后开始识别；取消则不识别、不花钱。");
  }); }
'''),
    dict(no=3, file="js", mark="2/4",
         why="提示词 aiPrompt 移到服务端 pdt/core/profit_ai.py（逐字相同，测试核对）。原工具改了提示词时这一条会停下：要同步改服务端提示词",
         anchor='''function aiPrompt(body){
  const keys=[...new Set(qlib.items.flatMap(q=>(q.items||[]).map(i=>i.key)).filter(Boolean))].slice(0,80);
  return `你是外贸采购助理。下面是一份工厂报价单，格式不固定（可能有多个工作表、合并单元格、中英文混排、一个产品占多行、多包裹）。请提取每个产品的报价信息。

只输出一个 JSON 对象，不要任何解释文字。格式：
{"factory":"工厂名，找不到就空字符串","quote_date":"YYYY-MM-DD，找不到就空字符串","items":[{"name":"型号或品名","desc":"材质/颜色/配置，简短","match_key":"规格键","price":数字或null,"price_currency":"USD 或 RMB","price_tax":"FOB 或 含税 或 未税","price_rmb_tax":数字或null,"moq":数字或null,"packages":[{"l":数字,"w":数字,"h":数字,"dim_unit":"cm 或 mm 或 in","weight":数字或null,"weight_unit":"kg 或 lb"}],"notes":"拿不准的地方，没有就空字符串"}]}

规则：
1. packages 用外箱/纸箱/包装尺寸和毛重，不要用产品本身尺寸或净重；一个产品分几个箱子就列几个 package。
2. price 填 FOB 美元价；price_rmb_tax 填人民币含税价（国内交货/出厂含税价），两者都有就都填。只有人民币未税价时，填在 price 并标 price_currency 为 RMB、price_tax 为未税。看不出含税与否时按含税处理并在 notes 说明。
3. 同一型号只是颜色不同、价格和包装都相同，合并成一条，颜色写进 desc。
4. match_key 用于跨工厂对比同一规格，格式如“30寸 落地式”“24寸 单盆”：尺寸写成“数字+寸”，再加最能区分款式的一两个词。${keys.length?"已有这些规格键，同规格请原样复用："+keys.join("、"):""}
5. 不要编造：表里没有的数填 null，并在 notes 说明。

报价单内容：
${body}`; }
''',
         new='''/* aiPrompt：提示词原样移到服务端 pdt/core/profit_ai.py（ai_prompt），浏览器不再拼接。 */
'''),
    dict(no=4, file="js", mark="2/4", why="原工具浏览器直连 Claude / Anthropic / OpenAI 兼容接口的 aiCall 整段去掉（判定台的 aiCall 见第 2 条）",
         anchor=('async function aiCall(prompt,{images=[],pdf=null,signal,onProgress}={}){\n',
                 '  return parseLoose((j.content||[]).filter(b=>b.type==="text").map(b=>b.text).join(""));\n}\n'),
         new=''),
    dict(no=5, file="js", mark="2/4", why="识别入口：大模型未连接时提示去设置页；准备服务端识别内容（不再拼提示词）",
         anchor='''  const st=document.getElementById("aiStatus"), stop=document.getElementById("btnAiStop"), go_=document.getElementById("btnAi");
  const ext=(file.name.split(".").pop()||"").toLowerCase(); let prompt, images=[], pdf=null, note="";
''',
         new='''  const st=document.getElementById("aiStatus"), go_=document.getElementById("btnAi");
  if(aiChannel()==="none"){ st.innerHTML=`大模型未连接：请到 <a href="/settings/keys">密钥与大模型</a> 填写密钥后再识别；手动导入照常可用。`; return; }
  const ext=(file.name.split(".").pop()||"").toLowerCase(); let payload={name:file.name,keys:aiKeys()}, note="";
'''),
    dict(no=6, file="js", mark="2/4", why="截图作为图片、表格作为文字交给服务端；PDF 提示截图或另存 Excel（系统所选大模型接口只接收文字和图片）",
         anchor='''    if(["png","jpg","jpeg","webp"].includes(ext)){ images=[file]; prompt=aiPrompt("（见附带的报价单图片）"); }
    else if(ext==="pdf"){ pdf=file; prompt=aiPrompt("（见附带的 PDF 报价单）"); }
    else { const wb=XLSX.read(new Uint8Array(await file.arrayBuffer()),{type:"array"}); const t=sheetText(wb); if(t.cut) note="（表格太长，只发送了前约 7 万字，后面的产品请拆分文件再识别）"; prompt=aiPrompt(t.text); }
''',
         new='''    if(["png","jpg","jpeg","webp"].includes(ext)){ payload.kind="image"; payload.media_type=file.type||"image/png"; payload.data=await fileB64(file); }
    else if(ext==="pdf"){ st.textContent="PDF 请截图成图片上传，或另存为 Excel 再识别（系统所选大模型接口只接收文字和图片）。"; return; }
    else { const wb=XLSX.read(new Uint8Array(await file.arrayBuffer()),{type:"array"}); const t=sheetText(wb); if(t.cut) note="（表格太长，只发送了前约 7 万字，后面的产品请拆分文件再识别）"; payload.kind="text"; payload.text=t.text; }
'''),
    dict(no=7, file="js", mark="2/4", why="去掉浏览器端的停止按钮与计时（识别在服务端任务里跑，进度由费用确认后的任务状态给出）",
         anchor='''  aiCtl=new AbortController(); stop.hidden=false; go_.disabled=true; const t0=Date.now(); let chars=0;
  const tick=setInterval(()=>{ st.textContent=`AI 识别中… 已用 ${Math.round((Date.now()-t0)/1000)} 秒${chars?`，已输出 ${chars} 字`:""}${note}`; },1000);
  st.textContent="AI 识别中…"+note;
''',
         new='''  go_.disabled=true; const t0=Date.now();
'''),
    dict(no=8, file="js", mark="2/4", why="调用服务端识别",
         anchor='''    const out=await aiCall(prompt,{images,pdf,signal:aiCtl.signal,onProgress:n=>{chars=n;}});
''',
         new='''    const out=await aiCall(payload,{onStatus:s=>{ st.textContent=s+note; }});
'''),
    dict(no=9, file="js", mark="2/4", why="错误提示换成服务端的错误码（月度上限等）",
         anchor='''    const msg={cancelled:"已停止。",not_granted:"你没有允许这个页面使用 Claude。",rate_limited:"调用太频繁或已达用量上限，请稍后再试。",sampling_disabled:"你的账号当前不能在页面里使用 Claude。",invalid_json:"AI 返回的格式不对，请再试一次。",refused:"AI 拒绝处理这份内容。"}[e&&e.code];
''',
         new='''    const msg={invalid_json:"AI 返回的格式不对，请再试一次。",stopped_cap:"大模型本月已达上限，未识别。",refused:"AI 拒绝处理这份内容。"}[e&&e.code];
'''),
    dict(no=10, file="js", mark="2/4", why="收尾不再有计时器与停止按钮",
         anchor='''  }finally{ clearInterval(tick); stop.hidden=true; go_.disabled=false; aiCtl=null; }
''',
         new='''  }finally{ go_.disabled=false; }
'''),
    dict(no=11, file="js", mark="2/4", why="停止按钮已去掉",
         anchor='''document.getElementById("btnAiStop").addEventListener("click",()=>aiCtl&&aiCtl.abort());
''',
         new=''),
    dict(no=12, file="js", mark="2/4", why="原“AI 接口设置”（本浏览器存 Key）去掉，密钥在设置页",
         anchor='''document.getElementById("btnAiKeySave").addEventListener("click",()=>{ const c=aiCfg(), v=document.getElementById("aiKey").value.trim();
  c.prov=document.getElementById("aiProv").value; c.base=document.getElementById("aiBase").value.trim(); c.model=document.getElementById("aiModel").value.trim(); if(v) c.key=v;
  if(c.prov==="openai"&&!c.model){ toast("OpenAI 兼容接口需要填写模型名"); return; }
  try{ localStorage.setItem("pc_ai_cfg",JSON.stringify(c)); }catch(e){} document.getElementById("aiKey").value=""; aiModeText(); toast("AI 接口设置已保存在本浏览器"); });
document.getElementById("btnAiKeyClear").addEventListener("click",()=>{ const c=aiCfg(); c.key=""; try{ localStorage.setItem("pc_ai_cfg",JSON.stringify(c)); }catch(e){} aiModeText(); toast("已清除 API Key"); });
document.getElementById("aiProv").addEventListener("change",e=>{ const v=e.target.value, b=document.getElementById("aiBase"), m=document.getElementById("aiModel");
  b.placeholder=v==="openai"?"https://api.deepseek.com/v1":"https://api.anthropic.com"; m.placeholder=v==="openai"?"例如 deepseek-chat、qwen-vl-max":AI_MODEL; });
''',
         new='''/* 原“AI 接口设置”（本浏览器存 Key、直连大模型）已去掉：密钥在设置页。 */
'''),
    # ---------------------------------------------------------------- 3/4 报价库存服务端
    dict(no=13, file="js", mark="3/4", why="报价库从服务端读（/tools/profit/quotes），局域网内有权限的人看到同一份",
         anchor='''function saveLocalQ(){ try{ localStorage.setItem("pc_quotes",JSON.stringify(qlib.items)); return true; }catch(e){ toast("本浏览器存储空间不足，请删除一些旧报价"); return false; } }
function initQuotes(db,id){ qlib.mode="cloud"; qlib.loading=true; qlib.col=db.doc("data/users/"+id+"/lib").collection("quotes"); quotesChanged();
  qlib.col.orderBy("savedAtMs","desc").onSnapshot(snap=>{ qlib.loading=false; qlib.items=snap.docs.map(d=>Object.assign({id:d.id},d.data())); quotesChanged(); },
    err=>{ qlib.loading=false; qlib.err=err&&err.code||"unavailable"; quotesChanged(); }); }
''',
         new='''/* 【判定台改动 3/4】报价库存服务端（/tools/profit/quotes），局域网内有权限的人看到同一份（AC-F24-02）。 */
function initQuotes(){ qlib.mode="server"; qlib.loading=true; quotesChanged();
  fetch("/tools/profit/quotes",{headers:{accept:"application/json"}}).then(r=>r.json()).then(j=>{ qlib.loading=false; qlib.items=j.items||[]; quotesChanged(); })
    .catch(()=>{ qlib.loading=false; qlib.err="unavailable"; quotesChanged(); }); }
'''),
    dict(no=14, file="js", mark="3/4", why="只读账号不能存报价",
         anchor='''  if(qlib.mode==="pending"){ toast("报价库还在连接，请稍等几秒"); return false; }
''',
         new='''  if(window.PDT&&PDT.readonly){ toast("当前账号只能查看"); return false; }
'''),
    dict(no=15, file="js", mark="3/4", why="存报价、改报价、删报价走服务端接口",
         anchor='''  const rec=Object.assign({},q,{savedAtMs:Date.now(),count:q.items.length});
  try{ if(qlib.mode==="cloud") await qlib.col.add(rec); else { qlib.items.unshift(Object.assign({id:uid()},rec)); if(!saveLocalQ()){ qlib.items.shift(); return false; } quotesChanged(); }
    toast(`已存进报价库：${q.factory} · ${q.version}`); return true; }
  catch(e){ toast(e&&e.code==="quota_exceeded"?"报价库已满，请删除一些旧版本":"保存失败，请稍后再试"); return false; } }
async function qUpdate(id,patch){ try{ if(qlib.mode==="cloud") await qlib.col.doc(id).update(patch); else { const it=qlib.items.find(x=>x.id===id); if(it){ Object.assign(it,patch); saveLocalQ(); quotesChanged(); } } }catch(e){ toast("修改失败，请稍后再试"); } }
async function qDelete(id){ try{ if(qlib.mode==="cloud") await qlib.col.doc(id).delete(); else { qlib.items=qlib.items.filter(x=>x.id!==id); saveLocalQ(); quotesChanged(); } qSel.delete(id); toast("已删除"); }catch(e){ toast("删除失败，请稍后再试"); } }
''',
         new='''  try{ const it=await aiPost("/tools/profit/quotes",q); qlib.items.unshift(it); quotesChanged(); toast(`已存进报价库：${q.factory} · ${q.version}`); return true; }
  catch(e){ toast("保存失败，请稍后再试："+(e.message||e)); return false; } }
async function qUpdate(id,patch){ try{ const it=await aiPost("/tools/profit/quotes/"+id,patch); const i=qlib.items.findIndex(x=>x.id===id); if(i>=0) qlib.items[i]=it; quotesChanged(); }catch(e){ toast("修改失败，请稍后再试"); } }
async function qDelete(id){ try{ await aiPost("/tools/profit/quotes/"+id+"/delete"); qlib.items=qlib.items.filter(x=>x.id!==id); qSel.delete(id); quotesChanged(); toast("已删除"); }catch(e){ toast("删除失败，请稍后再试"); } }
'''),
    dict(no=16, file="js", mark="3/4", why="报价库存放位置说明；对比指标选项提前填（附带修正 DESIGN-14：读取中或没有版本时下拉框不留空）",
         anchor='''  document.getElementById("qMode").textContent=qlib.mode==="cloud"?"保存在你的 claude.ai 账号里，只有你能看到":qlib.mode==="local"?"保存在本浏览器里（清缓存会丢失）":"正在连接报价库…";
''',
         new='''  /* 对比指标的选项（采购成本 / 落地成本 / 各渠道利润，即 qMetricVal 支持的全部取值）先填上：报价库还在读取或没有版本时也不留空下拉框 */
  const ms=METRICS(); if(!ms.some(x=>x[0]===P.qMetric)) P.qMetric="cost";
  document.getElementById("qMetric").innerHTML=ms.map(([v,l])=>`<option value="${v}" ${v===P.qMetric?"selected":""}>${esc(l)}</option>`).join("");
  document.getElementById("qMode").textContent=qlib.mode==="server"?"保存在系统上（wen 电脑），局域网内有权限的人看到同一份":"正在连接报价库…";
'''),
    dict(no=17, file="js", mark="附带修正", why="对比指标选项已在 renderS6 开头填过（见第 16 条），这里去掉原位置",
         anchor='''  const ms=METRICS(); if(!ms.some(x=>x[0]===P.qMetric)) P.qMetric="cost";
  document.getElementById("qMetric").innerHTML=ms.map(([v,l])=>`<option value="${v}" ${v===P.qMetric?"selected":""}>${esc(l)}</option>`).join("");
''',
         new=''),
    # ---------------------------------------------------------------- 3/4 历史库存服务端、当前版本 = 服务端方案
    dict(no=18, file="js", mark="3/4", why="历史库存服务端（/tools/profit/plans）；只读和审批者只能看、打开、导出",
         anchor='''function saveLocalHist(){ try{ localStorage.setItem("pc_history",JSON.stringify(hist.items)); return true; }catch(e){ toast("本浏览器存储空间不足，请删除一些旧版本"); return false; } }
''',
         new='''/* 【判定台改动 3/4】历史库存服务端（/tools/profit/plans），局域网内有权限的人看到同一份（AC-F24-02）。
   列表、改名、打开、保存回当前版本、另存为新版本、用当前覆盖、导出 .json、删除的界面与原工具相同；只读和审批者只能看、打开、导出。 */
const canEdit=()=>!(window.PDT&&PDT.readonly);
async function api(url,body){ const r=await fetch(url,{method:"POST",headers:{"content-type":"application/json",accept:"application/json"},body:body===undefined?undefined:JSON.stringify(body)}); const j=await r.json().catch(()=>({})); if(!r.ok) throw new Error(j.detail||("HTTP "+r.status)); return j; }
'''),
    dict(no=19, file="js", mark="3/4", why="历史库、报价库在页面打开时从服务端读（原工具连 claude.ai 账号库或本浏览器）",
         anchor=('  for(let i=0;i<20&&!(window.claude&&typeof window.claude.use==="function");i++) await new Promise(r=>setTimeout(r,100));\n',
                 '  if(qlib.mode==="pending"){ qlib.mode="local"; qlib.items=load("pc_quotes")||[]; quotesChanged(); }\n'),
         new='''  try{ const r=await fetch("/tools/profit/plans",{headers:{accept:"application/json"}}); hist.items=(await r.json()).items||[]; hist.mode="server"; }
  catch(e){ hist.mode="server"; hist.err="unavailable"; }
  histChanged();
'''),
    dict(no=20, file="js", mark="3/4",
         why="“当前版本”= 服务端方案：记在 PDT.cur（id 即服务端方案号），同步 PDT.planId，“保存”存回该方案、决策卡回写也写到该方案；不再记在本浏览器 pc_cur",
         anchor='''function getCur(){ try{ return JSON.parse(localStorage.getItem("pc_cur")||"null"); }catch(e){ return null; } }
function setCur(c){ try{ if(c) localStorage.setItem("pc_cur",JSON.stringify(c)); else localStorage.removeItem("pc_cur"); }catch(e){} renderSaveBar(); }
''',
         new='''function getCur(){ return (window.PDT&&PDT.cur)||null; }
function setCur(c){ if(window.PDT){ PDT.cur=c; PDT.planId=c?c.id:null; if(c) PDT.planName=c.name; if(PDT.onCur) PDT.onCur(c,c&&hist.items.find(x=>x.id===c.id)); } renderSaveBar(); }
'''),
    dict(no=21, file="js", mark="3/4", why="保存内容带上决策卡回写结果（方案已关联决策卡时卡片随方案更新；缺必填时只存方案）",
         anchor='''const snapshot=()=>({count:products.length,names:products.map(p=>p.name).slice(0,20),products:clone(products),params:clone(P)});
''',
         new='''function pdtExtra(it){ return (window.PDT&&typeof PDT.extra==="function")?PDT.extra(it):{}; }
const snapshot=it=>Object.assign({count:products.length,names:products.map(p=>p.name).slice(0,20),products:clone(products),params:clone(P)},pdtExtra(it||hist.items.find(x=>x.id===(getCur()||{}).id)));
'''),
    dict(no=22, file="js", mark="3/4", why="只读账号不能保存",
         anchor='''  if(hist.mode==="pending"){ toast("历史库还在连接，请稍等几秒再保存"); return null; }
''',
         new='''  if(!canEdit()){ toast("当前账号只能查看"); return null; }
'''),
    dict(no=23, file="js", mark="3/4", why="另存为新版本：在服务端新建方案",
         anchor='''  const now=Date.now();
  const rec=Object.assign({name:(name||"").trim()||defaultName(),savedAtMs:now,savedAt:new Date(now).toISOString()},snapshot());
  try{ let id;
    if(hist.mode==="cloud"){ const ref=await hist.col.add(rec); id=ref&&ref.id; }
    else { id=uid(); hist.items.unshift(Object.assign({id},rec)); if(!saveLocalHist()){ hist.items.shift(); return null; } histChanged(); }
    toast("已存为新版本："+rec.name); return id?{id,name:rec.name}:null;
  }catch(e){ toast(e&&e.code==="quota_exceeded"?"历史库已满，请删除一些旧版本后再保存":"保存失败，请稍后再试"); return null; }
''',
         new='''  const rec=Object.assign({name:(name||"").trim()||defaultName()},snapshot());
  try{ const it=await api("/tools/profit/plans",rec); hist.items.unshift(it); histChanged(); toast("已存为新版本："+it.name); return {id:it.id,name:it.name}; }
  catch(e){ toast("保存失败，请稍后再试："+e.message); return null; }
'''),
    dict(no=24, file="js", mark="3/4", why="保存回当前版本 / 用当前覆盖 / 改名：更新服务端方案",
         anchor='''    if(hist.mode==="cloud") await hist.col.doc(id).update(patch);
    else { const it=hist.items.find(x=>x.id===id); if(!it) return false; Object.assign(it,patch); if(!saveLocalHist()) return false; histChanged(); }
    return true;
  }catch(e){ toast("保存失败，请稍后再试"); return false; }
''',
         new='''    const it=await api("/tools/profit/plans/"+id,patch); const i=hist.items.findIndex(x=>x.id===id); if(i>=0) hist.items[i]=it; histChanged();
    return true;
  }catch(e){ toast("保存失败，请稍后再试："+e.message); return false; }
'''),
    dict(no=25, file="js", mark="3/4", why="删除服务端方案",
         anchor='''    if(hist.mode==="cloud") await hist.col.doc(id).delete();
    else { hist.items=hist.items.filter(x=>x.id!==id); saveLocalHist(); histChanged(); }
''',
         new='''    await api("/tools/profit/plans/"+id+"/delete"); hist.items=hist.items.filter(x=>x.id!==id); histChanged();
'''),
    dict(no=26, file="js", mark="3/4", why="打开方案后告诉判定台（回写决策卡时默认选该方案回写过的产品）",
         anchor='''migrate(); save(); setCur({id:it.id,name:it.name,sig:sigOf()}); toast("已打开："''',
         new='''migrate(); save(); setCur({id:it.id,name:it.name,sig:sigOf()}); if(window.PDT&&PDT.onOpened) PDT.onOpened(it); toast("已打开："'''),
    dict(no=27, file="js", mark="3/4", why="历史库存放位置说明",
         anchor='''  document.getElementById("histMode").textContent= hist.mode==="cloud"?"保存在你的 claude.ai 账号里，只有你自己能看到，换电脑也在":hist.mode==="local"?"保存在本浏览器里（清缓存会丢失，重要版本请另存 .json）":"正在连接历史库…";
  document.getElementById("histMsg").innerHTML= hist.err?`<p class="msg">历史库暂时连不上，刷新页面后再试。</p>`: hist.slow?`<p class="msg">历史库响应较慢，下面的列表可能不是最新的。</p>`:"";
  if(hist.mode==="pending"||hist.loading){ document.getElementById("histTable").innerHTML=`<p class="muted" style="padding:12px">正在读取历史库…</p>`; return; }
''',
         new='''  document.getElementById("histMode").textContent="保存在系统上（wen 电脑），局域网内有权限的人看到同一份";
  document.getElementById("histMsg").innerHTML= hist.err?`<p class="msg">历史库暂时连不上，刷新页面后再试。</p>`:"";
  if(hist.mode==="pending"){ document.getElementById("histTable").innerHTML=`<p class="muted" style="padding:12px">正在连接历史库…</p>`; return; }
'''),
    dict(no=28, file="js", mark="3/4", why="历史库表格：加“保存人”“关联决策卡”两列；只读账号名称不可改",
         anchor='''  document.getElementById("histTable").innerHTML=`<table><thead><tr><th>名称（可改）</th><th>保存时间</th><th>产品数</th><th>包含产品</th><th>汇率</th><th>操作</th></tr></thead><tbody>${hist.items.map(it=>`<tr>
    <td><input class="wide" style="width:240px" data-hname="${esc(it.id)}" value="${esc(it.name)}">''',
         new='''  const ed=canEdit();
  document.getElementById("histTable").innerHTML=`<table><thead><tr><th>名称${ed?"（可改）":""}</th><th>保存时间</th><th>保存人</th><th>产品数</th><th>包含产品</th><th>关联决策卡</th><th>汇率</th><th>操作</th></tr></thead><tbody>${hist.items.map(it=>`<tr>
    <td>${ed?`<input class="wide" style="width:240px" data-hname="${esc(it.id)}" value="${esc(it.name)}">`:esc(it.name)}'''),
    dict(no=29, file="js", mark="3/4", why="保存人列",
         anchor='''    <td class="n">${fmtTime(it.savedAtMs)}${it.renamedAtMs?`<br><span class="note">改名 ${fmtTime(it.renamedAtMs).slice(5,16)}</span>`:""}</td>
''',
         new='''    <td class="n">${fmtTime(it.savedAtMs)}${it.renamedAtMs?`<br><span class="note">改名 ${fmtTime(it.renamedAtMs).slice(5,16)}</span>`:""}</td>
    <td class="c">${esc(it.by||"")}</td>
'''),
    dict(no=30, file="js", mark="3/4", why="关联决策卡列",
         anchor='''    <td style="max-width:320px;white-space:normal" class="note">${esc((it.names||[]).join("、"))}</td>
''',
         new='''    <td style="max-width:320px;white-space:normal" class="note">${esc((it.names||[]).join("、"))}</td>
    <td class="note">${it.card_id?`<a href="/cards/${esc(it.card_id)}">${esc(it.card_name||("决策卡 "+it.card_id))}</a>`:"—"}</td>
'''),
    dict(no=31, file="js", mark="3/4", why="只读账号不显示“用当前覆盖”“删除”",
         anchor='''<button class="btn sm" data-hact="open" data-id="${esc(it.id)}">打开</button> <button class="btn sm" data-hact="overwrite" data-id="${esc(it.id)}" title="把当前测算存进这个版本，并把它设为当前版本">用当前覆盖</button> <button class="btn sm" data-hact="json" data-id="${esc(it.id)}">导出.json</button> <button class="btn sm danger" data-hact="del" data-id="${esc(it.id)}">删除</button>''',
         new='''<button class="btn sm" data-hact="open" data-id="${esc(it.id)}">打开</button>${ed?` <button class="btn sm" data-hact="overwrite" data-id="${esc(it.id)}" title="把当前测算存进这个版本，并把它设为当前版本">用当前覆盖</button>`:""} <button class="btn sm" data-hact="json" data-id="${esc(it.id)}">导出.json</button>${ed?` <button class="btn sm danger" data-hact="del" data-id="${esc(it.id)}">删除</button>`:""}'''),
    dict(no=32, file="js", mark="3/4", why="服务端方案号是数字：改名时按数字号找方案",
         anchor='''hist.items.find(x=>x.id===t.dataset.hname)''',
         new='''hist.items.find(x=>String(x.id)===t.dataset.hname)'''),
    dict(no=33, file="js", mark="3/4", why="服务端方案号是数字：按钮上的号转成数字",
         anchor='''const id=b.dataset.id, it=hist.items.find(x=>x.id===id);''',
         new='''const id=+b.dataset.id, it=hist.items.find(x=>x.id===id);'''),
    dict(no=34, file="js", mark="3/4", why="用当前覆盖某个版本时带上该版本关联决策卡的回写结果",
         anchor='''new Date(now).toISOString()},snapshot())).then(ok=>{ if(ok){ setCur({id,name:it.name,sig:sigOf()}); toast("已覆盖："+it.name); } });''',
         new='''new Date(now).toISOString()},snapshot(it))).then(ok=>{ if(ok){ setCur({id,name:it.name,sig:sigOf()}); toast("已覆盖："+it.name); } });'''),
    dict(no=35, file="js", mark="3/4", why="报价库在页面打开时从服务端读（原工具 12 秒后退回本浏览器）",
         anchor='''setTimeout(()=>{ if(qlib.mode==="pending"){ qlib.mode="local"; qlib.items=load("pc_quotes")||[]; quotesChanged(); } aiModeText(); },12000);
''',
         new='''initQuotes();

'''),
    dict(no=36, file="js", mark="4/4", why="起始步骤：从决策卡进入、打开方案时由服务端指定",
         anchor='''let st=4; try{ st=+(localStorage.getItem("pc_step")||4)||4; if(st<1||st>6) st=4; }catch(e){}
''',
         new='''let st=4; try{ st=+(localStorage.getItem("pc_step")||4)||4; if(st<1||st>6) st=4; }catch(e){}
if(window.PDT && PDT.step) st=PDT.step;  /* 【判定台改动 4/4】起始步骤：从决策卡进入、打开方案时由服务端指定 */
'''),
    dict(no=37, file="js", mark="3/4", why="页面打开的服务端方案就是“当前版本”（点“保存”存回它）；从决策卡新建时没有当前版本",
         anchor='''go(st);''',
         new='''if(window.PDT) setCur(PDT.planId?{id:PDT.planId,name:PDT.planName||"",sig:sigOf()}:null);  /* 【判定台改动 3/4】当前版本 = 页面打开的服务端方案 */
go(st);'''),
    # ---------------------------------------------------------------- 页面主体
    dict(no=38, file="html", mark="2/4", why="PDF 说明：系统所选大模型接口只接收文字和图片",
         anchor='''；PDF 仅在本地填了 API Key 时可用。''',
         new='''；PDF 请截图成图片或另存为 Excel。'''),
    dict(no=39, file="html", mark="2/4", why="停止按钮去掉（识别在服务端任务里跑）",
         anchor='''<button class="btn" id="btnAiStop" hidden>停止</button>''',
         new=''),
    dict(no=40, file="html", mark="2/4", why="“AI 接口设置”整块换成去设置页的说明（密钥只存在系统上）",
         anchor=('      <details id="aiCfg"', '      </details>\n'),
         new='''      <p class="note">大模型用 <a href="/settings/keys">密钥与大模型</a> 里所选的提供方，密钥只存在系统上；识别前先确认费用，费用记入 <a href="/settings/budget">预算与费用</a>。</p>
'''),
    dict(no=41, file="html", mark="3/4", why="存放位置说明：方案和报价存在系统上",
         anchor='''<p class="note">数据自动保存在本浏览器里；换电脑或清缓存前，请在第 4 步“保存方案”导出 .json。</p>''',
         new='''<p class="note">方案和报价保存在系统上（历史库、报价库），局域网内有权限的人看到同一份；还没保存的编辑暂存在本浏览器。</p>'''),
    dict(no=42, file="html", mark="3/4", why="变量页说明：保存到历史库后存在系统上",
         anchor='''改完立即作用于利润测算表，并自动存在本浏览器。''',
         new='''改完立即作用于利润测算表；保存到历史库后存在系统上。'''),
]

# ---------------------------------------------------------------- 样式规则
# 原工具样式：整页样式（颜色变量、body、页头）不要，其余规则统一加 #pc-root 前缀；下面这些按选择器特别处理。
# 选择器在原工具里找不到时停下（说明原工具的页面结构变了）。
CSS_DROP = [":root", '@media (prefers-color-scheme: dark)', ':root[data-theme="dark"]', "*", "body", "body::before", ".wrap",
            "header.bar", "header.bar .wrap", "h1", "h1 small"]
CSS_REPLACE = {
    # 原工具提示条：判定台的 .toast 默认透明（配 .is-on 用），原工具直接挂在 body 下的提示条单独显示
    ".toast": "body>.toast{position:fixed;right:24px;bottom:24px;z-index:80;opacity:1}",
    # 变量抽屉打开时把内容区让出右边（原工具让的是 main.wrap，判定台是 #pc-root）
    "body.drawer-open main.wrap": "body.drawer-open #pc-root{margin-right:calc(min(620px,100vw) + 8px)}",
}
CSS_HEAD = """/* 原利润测算台样式（由 tools_sync_profit.py 从原工具生成，勿手改），限定在 #pc-root 内，颜色映射到判定台 tokens。 */
#pc-root{--surface2:var(--surface-raised);--ink:var(--fg);--line:var(--border);--accent-ink:var(--accent-on);--accent-soft:var(--accent-tint);
--input:var(--surface);--input-line:var(--border-control);--pos:var(--success);--pos-soft:var(--success-tint);--neg:var(--danger);--neg-soft:var(--danger-tint);
--warn-soft:var(--warn-tint);--f-ui:inherit;--f-head:inherit;--f-num:var(--font-mono);--r:var(--radius-md);font-size:var(--text-sm)}
"""

JS_HEAD = """/* 利润测算引擎：由 tools_sync_profit.py 从 tools/利润测算台/index.html（wen 的原工具）自动生成，勿手改——改原工具后重跑同步脚本。
 * 默认参数、计算、导入、变量面板与抽屉、计算说明、利润表、国内出货、旺季 / 海运对比、报价库对比、导出逐字保留。
 * 只改四处，均以【判定台改动】标出：1/4 初始方案从服务端读；2/4 AI 识别走服务端与费用闸门；3/4 报价库与历史库存服务端（“当前版本”= 服务端方案）；4/4 起始步骤。 */
"""

# 与测试 FLOW-17 相同的一组输入，在 node 里分别跑原工具与生成的 engine.js
HARNESS = """
var window = {}; var PDT = undefined; var localStorage = {getItem: function(){ return null; }, setItem: function(){}};
var document = {getElementById: function(){ return {addEventListener: function(){}}; }, querySelectorAll: function(){ return []; }, addEventListener: function(){}};
%s
products.forEach(function(p, i){ p.costRmb = Math.round(p.cost * 7.25 * 100) / 100; });
P.sea.push({name: "国内整柜·近三个月", rmb: 98000, cbm: 68});
P.sea.push({name: "国内整柜·近六个月", rmb: 61000, cbm: 68});
function one(r){ return {cost: r.cost, price: r.price, sc: r.sc, fbmShip: r.fbmShip, cgShip: r.cgShip, fbaShip: r.fbaShip, warn: r.warn,
  plat: Object.fromEntries(Object.entries(r.plat).map(function(kv){ var x = kv[1]; return [kv[0], {list: x.list, promo: x.promo, sc: x.sc}]; })),
  rows: chanList().map(function(ch){ var v = chanVal(r, ch, 0); return {channel: ch.name, profit: v.ok ? v.profit : null}; })}; }
var R = products.map(function(p){ return {p: p, r: calcProduct(p)}; });
var out = {R: R.map(function(x){ return Object.assign({name: x.p.name}, one(x.r)); }),
  dom: domData(R).map(function(x){ return {name: x.p.name, fob: one(x.f), dom: one(x.d)}; }),
  scen: scenData(R).map(function(x){ return {name: x.p.name, off: one(x.n), on: one(x.k)}; }),
  plans: cmpPlans(), seaFob: seaList("fob"), seaDom: seaList("dom")};
console.log(JSON.stringify(out));
"""
CALC_MARKS = [("/* ---------------- defaults ---------------- */", "/* ---------------- state ---------------- */"),
              ("/* ---------------- calculation (mirrors the original workbook) ---------------- */",
               "/* ---------------- bulk: set platform list prices from the Amazon price ---------------- */")]


# ================================================================ 抽取
def _between(src: str, a: str, b: str, what: str, last=False) -> str:
    i = src.find(a)
    j = src.rfind(b) if last else src.find(b, i + len(a))
    if i < 0 or j < 0 or j < i:
        raise SyncError(f"原工具结构变了：找不到{what}（{a!r} … {b!r}）。")
    return src[i + len(a):j]


def extract(html: str) -> dict:
    return dict(css=_between(html, "<style>\n", "</style>", "样式段"),
                body=_between(html, '<main class="wrap">\n', "</main>", "页面主体 <main class=\"wrap\">"),
                nav=_between(html, '<nav class="steps" id="steps">', "</nav>", "步骤栏"),
                js=_between(html, "<script>\n", "</script>", "脚本段", last=True))


# ================================================================ 补丁
def _near(src: str, anchor: str) -> str:
    """锚点找不到时：在原工具里找最像的一段，给出差异，说明原工具哪一段变了。"""
    lines, al = src.splitlines(), [x for x in anchor.splitlines() if x.strip()]
    if not al:
        return ""
    best = max(range(len(lines)), key=lambda i: difflib.SequenceMatcher(None, lines[i], al[0]).ratio())
    seg = lines[best:best + len(al)]
    diff = "\n".join(difflib.unified_diff(al, seg, "补丁清单里的锚点", f"原工具第 {best + 1} 行起", lineterm="", n=0))
    return diff[:3000]


def locate(src: str, p: dict) -> tuple[int, int]:
    a = p["anchor"]
    where = f"补丁 #{p['no']}（{p['file']}，【判定台改动 {p['mark']}】{p['why']}）"
    if isinstance(a, tuple):
        start, end = a
        n = src.count(start)
        if n != 1:
            raise SyncError(f"{where}：整段开头在原工具里出现 {n} 次（应为 1 次）。\n{_near(src, start) if n == 0 else ''}")
        i = src.index(start)
        j = src.find(end, i + len(start))
        if j < 0:
            raise SyncError(f"{where}：整段结尾在开头之后找不到。\n{_near(src[i:], end)}")
        return i, j + len(end)
    n = src.count(a)
    if n != 1:
        msg = f"{where}：锚点在原工具里出现 {n} 次（应为 1 次）。"
        if n == 0:
            msg += "原工具这一段变了，差异（- 锚点，+ 原工具现在）：\n" + _near(src, a)
        raise SyncError(msg)
    i = src.index(a)
    return i, i + len(a)


def apply_patches(src: str, kind: str, patches=None) -> str:
    """先在原文里定位全部锚点（各自恰好一次、互不重叠），再一次拼出结果，替换内容不会被后面的锚点误中。"""
    spans = sorted(((*locate(src, p), p) for p in (patches or PATCHES) if p["file"] == kind), key=lambda x: x[0])
    for (a0, a1, p), (b0, _b1, q) in zip(spans, spans[1:]):
        if b0 < a1:
            raise SyncError(f"补丁 #{p['no']} 与 #{q['no']} 的锚点重叠，补丁清单要调整。")
    out, pos = [], 0
    for i, j, p in spans:
        out += [src[pos:i], p["new"]]
        pos = j
    return "".join(out) + src[pos:]


# ================================================================ 样式
def _blocks(css: str):
    """把样式切成顶层块：(选择器或 @规则, 内容)。内容里的大括号按层数配对。"""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            if css[i:].strip():
                raise SyncError(f"样式结尾有无法解析的内容：{css[i:i + 80]!r}")
            return
        depth, k = 1, j + 1
        while depth and k < n:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        if depth:
            raise SyncError("样式大括号不配对，原工具样式可能写坏了。")
        yield css[i:j].strip(), css[j + 1:k - 1]
        i = k


def _prefix(sel: str) -> str:
    out = []
    for s in sel.split(","):
        s = s.strip()
        if s in CSS_REPLACE or s.startswith(("html", "body", ":root")):
            raise SyncError(f"样式选择器 {s!r} 作用于整页，需要在 CSS_REPLACE 里写判定台的对应做法。")
        out.append(s if s.startswith("#pc-root") else "#pc-root " + s)
    return ",".join(out)


def transform_css(css: str) -> str:
    seen, lines = set(), []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # 注释不带进判定台

    def rule(sel, body, indent=""):
        if sel in CSS_REPLACE:
            seen.add(sel)
            return indent + CSS_REPLACE[sel]
        return f"{indent}{_prefix(sel)}{{{body.strip()}}}"

    for sel, body in _blocks(css):
        if sel in CSS_DROP:
            seen.add(sel)
            continue
        if sel.startswith("@media"):
            inner = [(s, b) for s, b in _blocks(body)]
            parts = [rule(s, b) for s, b in inner]
            lines.append(f"{sel}{{" + "".join(parts) + "}")
        elif sel.startswith("@"):
            raise SyncError(f"样式里出现新的 {sel}，需要人工适配。")
        else:
            lines.append(rule(sel, body))
    miss = [s for s in CSS_DROP + list(CSS_REPLACE) if s not in seen]
    if miss:
        raise SyncError(f"样式规则在原工具里找不到：{miss}（原工具页面结构变了，CSS_DROP / CSS_REPLACE 要调整）。")
    return CSS_HEAD + "\n".join(lines) + "\n"


# ================================================================ 步骤栏（在 tools_profit.html 里手写，核对是否与原工具一致）
def check_nav(nav: str) -> None:
    page = PAGE.read_text(encoding="utf-8")
    steps = re.findall(r'data-step="(\d)"><b>\d</b>([^<]+)<', nav)
    for n, label in steps:
        if not re.search(rf'data-step="{n}"[^>]*><b>{n}</b>{re.escape(label.strip())}<', page):
            raise SyncError(f"原工具步骤栏第 {n} 步是“{label.strip()}”，tools_profit.html 不一致：步骤栏在判定台模板里手写，需要人工改。")
    for h in re.findall(r'data-help="([^"]+)"', nav):
        if f'data-help="{h}"' not in page:
            raise SyncError(f"原工具步骤栏有“计算说明”按钮 data-help=\"{h}\"，tools_profit.html 没有：需要人工改。")
    for n in re.findall(r'data-step="(\d)"', nav):
        if f'data-step="{n}"' not in page:
            raise SyncError(f"原工具步骤栏有第 {n} 步，tools_profit.html 没有：需要人工改。")


# ================================================================ 校验
def _head(src: str) -> str:
    a = src.index("/* All visible channels in one list")
    b = src.index("function renderDetail(R)")
    return src[:src.index("/* ---------------- bulk")] + src[a:b]


def _node_run(code: str, tmp: Path, name: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise SyncError("需要 node 才能校验计算结果（装 Node.js 后重跑）；没有校验不写文件。")
    p = tmp / name
    p.write_text(code, encoding="utf-8")
    r = subprocess.run([node, str(p)], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise SyncError(f"node 跑{name}出错：\n{r.stderr[-2000:]}")
    return json.loads(r.stdout)


def verify(orig_js: str, engine: str) -> None:
    for a, b in CALC_MARKS:
        i, j = orig_js.find(a), orig_js.find(b)
        if i < 0 or j < 0:
            raise SyncError(f"原工具结构变了：找不到计算段标记 {a!r} 或 {b!r}，校验无法定位，需要找 AI。")
        if orig_js[i:j] not in engine:
            raise SyncError(f"生成的 engine.js 没有逐字保留原工具的 {a.strip('/* -')} 段（有补丁改到了计算），需要找 AI。")
    with tempfile.TemporaryDirectory() as d:
        base = _node_run(HARNESS % _head(orig_js), Path(d), "原工具.js")
        got = _node_run(HARNESS % _head(engine), Path(d), "engine.js")
    bad = [k for k in base if got.get(k) != base[k]]
    if bad:
        raise SyncError(f"同一组输入，生成的 engine.js 与原工具计算结果不同：{bad}，需要找 AI。")
    if not base["R"]:
        raise SyncError("校验输入没有产品（原工具示例数据变了），需要找 AI 调整校验。")


# ================================================================ 生成
def build(html: str, patches=None) -> dict:
    """原工具 HTML → {engine.js, profit.css, _profit_sections.html} 的内容；任何一步不通过抛 SyncError。"""
    x = extract(html)
    engine = JS_HEAD + apply_patches(x["js"], "js", patches)
    body = apply_patches(x["body"], "html", patches)
    out = {OUT_ENGINE: engine, OUT_CSS: transform_css(x["css"]), OUT_HTML: "{% raw %}\n" + body + "{% endraw %}\n"}
    check_nav(x["nav"])
    verify(x["js"], engine)
    return out


def read_source(spec: str | None) -> tuple[str, str]:
    if not spec:
        return DEFAULT_SRC.read_text(encoding="utf-8"), str(DEFAULT_SRC.relative_to(REPO.parent))
    if spec.startswith("git:"):
        ref, _, path = spec[4:].partition(":")
        if not path:
            raise SyncError("git 来源写成 git:<分支引用>:<文件路径>，例如 git:origin/claude/eager-babbage-7wu6sw:profit-calculator/index.html")
        remote, _, branch = ref.partition("/")
        if branch:
            r = subprocess.run(["git", "fetch", remote, branch], cwd=REPO, capture_output=True, text=True)
            if r.returncode:
                raise SyncError(f"git fetch {remote} {branch} 失败：{r.stderr.strip()}")
        r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO, capture_output=True)
        if r.returncode:
            raise SyncError(f"git show {ref}:{path} 失败：{r.stderr.decode('utf-8', 'replace').strip()}")
        return r.stdout.decode("utf-8"), spec
    p = Path(spec)
    return p.read_text(encoding="utf-8"), str(p)


def file_sha(path: Path) -> str:
    """原工具文件的哈希（按字节）；判定台启动时与同步记录比对，不同就在利润测算页提示“原工具有更新”。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:  # Windows 上也保持 \n 换行，与仓库一致
        f.write(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 wen 的利润测算台原工具同步进判定台（生成 engine.js / profit.css / _profit_sections.html）。")
    ap.add_argument("--from", dest="src", help="原工具来源：文件路径，或 git:<分支引用>:<文件路径>（先 fetch 再取）。默认 ../tools/利润测算台/index.html")
    ap.add_argument("--check", action="store_true", help="只检查能否同步，不写任何文件")
    a = ap.parse_args(argv)
    try:
        html, label = read_source(a.src)
        out = build(html)
    except SyncError as e:
        print("同步停下，没有改动任何文件。\n" + str(e) + "\n\n这种情况需要找 AI：把上面这段发给 AI，让它按原工具的新写法调整 tools_sync_profit.py 的补丁清单后重跑。", file=sys.stderr)
        return 1
    changed = [p for p, t in out.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    print(f"原工具：{label}（{len(html.splitlines())} 行）")
    print(f"补丁清单 {len(PATCHES)} 条全部命中；样式 {len(CSS_DROP)} 条去掉、{len(CSS_REPLACE)} 条改写；计算结果与原工具逐项相同。")
    if a.check:
        print("只检查：" + ("需要更新 " + "、".join(p.name for p in changed) if changed else "系统已是这一版，无需更新"))
        return 0
    for p in changed:
        write(p, out[p])
    if a.src and (a.src.startswith("git:") or Path(a.src).resolve() != DEFAULT_SRC.resolve()):
        write(DEFAULT_SRC, html)  # 原工具原样放到 tools/ 下，之后的同步与测试都以它为准
        print(f"已把原工具复制到 {DEFAULT_SRC.relative_to(REPO.parent)}")
    write(STAMP, json.dumps({"source_sha256": file_sha(DEFAULT_SRC), "source": label, "synced_at": datetime.now().isoformat(timespec="seconds"),
                             "patches": len(PATCHES)}, ensure_ascii=False, indent=1) + "\n")
    print("已更新：" + ("、".join(str(p.relative_to(APP)) for p in changed) if changed else "无（系统已是这一版）") + "；同步记录 pdt/profit_sync.json")
    print("请重启判定台后打开 /tools/profit 看一眼；改过补丁清单时再跑 python -m pytest tests/test_tools.py -q。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
