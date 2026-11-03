/* 利润测算引擎：由 tools/利润测算台/index.html 的脚本原样移植（计算、导入、参数、利润表、导出逐字保留）。
 * 只改三处，均以【判定台改动】标出：初始方案从服务端读；历史库存服务端（局域网共享，AC-F24-02）；起始步骤。 */
"use strict";
/* ---------------- defaults ---------------- */
const RATES = {"tail":[[1,8.2207,0.8],[2,8.2317,0.8],[3,8.2413,0.8],[4,8.253,0.8],[5,8.264,0.8],[6,8.2753,1.6],[7,8.4749,1.6],[8,8.4819,1.6],[9,8.617,1.6],[10,8.6101,1.6],[11,8.6517,1.6],[12,8.748,1.6],[13,8.8714,1.6],[14,9.02,1.6],[15,9.1986,1.6],[16,9.3575,1.6],[17,9.4331,1.6],[18,9.711,1.6],[19,10.1413,1.6],[20,10.3176,1.6],[21,10.4726,2.4],[22,10.6435,2.4],[23,10.929,2.4],[24,11.3435,2.4],[25,11.6161,2.4],[26,11.9938,2.4],[27,12.0991,2.4],[28,12.5825,2.4],[29,12.7925,2.4],[30,13.0633,2.4],[31,12.1104,2.4],[32,12.1545,2.4],[33,12.4887,2.4],[34,12.8367,2.4],[35,13.0203,2.4],[36,13.3679,2.4],[37,13.5523,2.4],[38,13.7515,2.4],[39,14.0999,2.4],[40,14.1169,2.4],[41,14.5605,2.4],[42,14.6695,2.4],[43,15.1218,2.4],[44,15.3405,2.4],[45,15.4289,2.4],[46,15.7215,2.4],[47,15.9269,2.4],[48,16.1933,2.4],[49,16.2911,2.4],[50,16.4097,2.4],[51,16.688,3.7],[52,16.6932,3.7],[53,16.7926,3.7],[54,16.8102,3.7],[55,16.8209,3.7],[56,16.9,3.7],[57,17.0819,3.7],[58,17.1363,3.7],[59,17.2642,3.7],[60,17.522,3.7],[61,17.5497,3.7],[62,17.8729,3.7],[63,17.96,3.7],[64,18.0534,3.7],[65,18.1353,3.7],[66,18.199,3.7],[67,18.2992,3.7],[68,18.5464,3.7],[69,18.6799,3.7],[70,19.0202,3.7],[71,19.1006,4.2],[72,19.3298,4.2],[73,19.4495,4.2],[74,19.5337,4.2],[75,19.6766,4.2],[76,20.104,4.2],[77,20.3287,4.2],[78,20.4818,4.2],[79,20.9029,4.2],[80,21.2302,4.2],[81,21.4213,4.2],[82,21.7821,4.2],[83,21.7998,4.2],[84,22.162,4.2],[85,22.4382,4.2],[86,23.0764,4.2],[87,23.1828,4.2],[88,23.6245,4.2],[89,24.0571,4.2],[90,23.9912,4.2],[91,24.0036,4.2],[92,24.198,4.2],[93,24.2754,4.2],[94,24.6011,4.2],[95,24.8433,4.2],[96,25.1419,4.2],[97,25.6593,4.2],[98,25.8167,4.2],[99,26.0915,4.2],[100,26.2609,4.2],[101,26.478,5],[102,26.5274,5],[103,26.683,5],[104,26.6947,5],[105,27.403,5],[106,27.4508,5],[107,27.6648,5],[108,27.7837,5],[109,28.3244,5],[110,28.8718,5],[111,29.1019,5],[112,29.22,5],[113,29.3776,5],[114,29.9124,5],[115,30.2027,5],[116,30.4336,5],[117,30.6222,5],[118,30.8861,5],[119,31.2672,5],[120,31.5751,5],[121,31.6021,5],[122,31.9621,5],[123,32.4627,5],[124,32.5387,5],[125,32.5968,5],[126,33.0673,5],[127,33.4449,5],[128,33.5528,5],[129,33.8169,5],[130,34.1841,5],[131,34.5235,5],[132,34.643,5],[133,34.7342,5],[134,35.1601,5],[135,35.5303,5],[136,35.7956,5],[137,35.947,5],[138,36.5488,5],[139,36.7462,5],[140,37.0092,5],[141,37.123,5],[142,37.4352,5],[143,37.4604,5],[144,38.6445,5],[145,38.726,5],[146,38.7352,5],[147,39.1076,5],[148,39.1272,5],[149,39.4521,5],[150,39.5931,5]],"surch":[["常规","无异常收费",0,0],["AHS-操作附加费-超尺寸","最长边>48inches",4.83,5.45],["AHS-操作附加费-超尺寸","第二长边>30inches",4.83,5.45],["AHS-操作附加费-超尺寸","105inches<围长=长度+2x(宽+高）<130inches",4.83,5.45],["AHS-操作附加费-超立方体积","体积（最长边*次长边*2*最短边）＞105inch（266.7cm）",4.83,5.45],["AHS-操作附加费-超重","称重重量>50lb（22.68kg）",7.17,5.45],["OS-超尺寸附加费-超第一长边","单边尺寸超过96英寸",40.2,54.25],["OS-超尺寸附加费-超围长","当130inches<围长=长度+2x(宽+高）<165inches",40.2,54.25],["OS-超尺寸附加费-超立方体积","体积(最长边*次长边*最短边)>17280 cubic inches(0.28m³)",40.2,54.25],["OS-超尺寸附加费-超重","单包裹实际重量>110lbs(49.90kg)",40.2,54.25],["超大包裹，LTL单独核算","第一长度>108inches",1875,545],["超大包裹，LTL单独核算","称重重量>150lbs",1875,545],["超大包裹，LTL单独核算","围长=长度+2x(宽+高）>165inches",1875,545],["住宅附加费","所有地址默认为住宅地址",2.93,1.7]],"cg":[["Bin - Small",2.33,12.35,0.17],["Bin - Large",3.03,15.1,0.17],["Bin - Heavy",3.69,15.42,0.17],["Standard - Small",6.03,17.05,0.2],["Standard - Medium",7.37,23.78,0.24],["Standard - Large",11.51,49.83,0.31],["Standard - Oversize",11.51,52.43,0.34],["Large Parcel - Standard","/","/","/"]]};
const CATS = ["家具","汽配","工业机械","农机花园","其他"];
const COST_CUR = {USD:"USD FOB（不含税）", RMB_TAX:"RMB 含税", RMB_NET:"RMB 未税"};
/* Platforms beyond Amazon. Each one is configured by P.plat[k]; the same engine settles all of them. */
const PLATS = [{k:"lowesVC",name:"Lowe's VC"},{k:"lowesSC",name:"Lowe's SC"},{k:"hd",name:"Home Depot"},{k:"wf",name:"Wayfair"}];
const SHIP = {self:"我们发货（尾程+燃油）",handling:"平台发货（只付订单处理费）",none:"平台仓（无尾程费用）"};
const AMZ = [{k:"fbm",name:"Amazon FBM"},{k:"cg",name:"Amazon CG"},{k:"fba",name:"Amazon FBA"}];
function platDefaults(){ return {
  lowesVC:{on:true,markup:1.7,disc:10,ship:"handling",fixed:0.78,ads:10,fx:1,comm:5.2,refund:10,storage:2,outbound:0},
  lowesSC:{on:true,markup:1,disc:30,ship:"self",fixed:0.78,ads:10,fx:1,comm:15,refund:10,storage:2,outbound:0},
  hd:{on:true,markup:1.6,disc:25,ship:"handling",fixed:0.70,ads:10,fx:1,comm:3.22,refund:10,storage:2,outbound:0},
  wf:{on:true,markup:2.1,disc:25,ship:"none",fixed:0,ads:10,fx:1,comm:4,refund:5,storage:2,outbound:4}}; }
function defaultParams(){ return {
  rate:6.8, promo:10, fxLoss:1, refund:8, tax:13, residential:false,
  listFactor:1.15, targetMargin:15, bulk:{plat:"all",pct:15,r99:true,promo:true}, seaView:0, detailChan:"amz:fbm", showAmz:{fbm:true,cg:true,fba:true}, plat:platDefaults(),
  commission:{threshold:200, furnLow:15, furnHigh:10, 汽配:12, 工业机械:12, 农机花园:15, 其他:15},
  sea:[{name:"FOB整柜·近三个月",rmb:100891,cbm:68},{name:"FOB整柜·近六个月",rmb:62891,cbm:68}],
  fbm:{dimDiv:250, lbPerKg:2.2046226, ceilLb:2.2, fuel:29.5},
  fba:{dimDiv:139, fuel:3.5, peakMode:"auto", peakStart:"2026-10-15", peakEnd:"2027-01-14",
       osLen:96, osLG:130, os50:17, os70:21, os150:25,
       tiers:[
        {name:"小号大件",w:50,l:37,m:28,n:20,lg:130,base:7.55,peak:8.59,per:0.38,from:1},
        {name:"大号大件",w:50,l:59,m:33,n:33,lg:130,base:9.35,peak:10.39,per:0.38,from:1},
        {name:"超大件 0–50 lb",w:50,l:"",m:"",n:"",lg:"",base:26.33,peak:29.06,per:0.38,from:1},
        {name:"超大件 50–70 lb",w:70,l:"",m:"",n:"",lg:"",base:37.32,peak:40.13,per:0.75,from:51},
        {name:"超大件 70–150 lb",w:150,l:"",m:"",n:"",lg:"",base:51.32,peak:55.74,per:0.75,from:71},
        {name:"超大件 150 lb+",w:"",l:"",m:"",n:"",lg:"",base:194.95,peak:203.46,per:0.19,from:151}]},
  tail:RATES.tail.map(r=>({lb:r[0],fee:r[1],handling:r[2]})),
  surch:RATES.surch.map(r=>({type:r[0],rule:r[1],base:r[2],peak:r[3]})),
  cg:RATES.cg.map(r=>({bucket:r[0],pick:num(r[1]),ship:num(r[2]),perLb:num(r[3])}))
};}
const SAMPLE = [
  {name:"24寸 单包",desc:"FLUTED 白橡木/胡桃木，24寸台下盆，岗石台面，双门缓关",category:"家具",peak:"非旺季",price:269,cost:102,costCur:"USD",adj:0,pk:[[93,57,38,41]]},
  {name:"30寸 双包",desc:"FLUTED 三抽屉，2AC+1USB+1TypeC（ETL）",category:"家具",peak:"非旺季",price:369,cost:140.5,costCur:"USD",adj:-5,pk:[[90,57,33,28],[93,57,15,28]]},
  {name:"30寸 单包",desc:"FLUTED 两抽屉，实木腿",category:"家具",peak:"非旺季",price:339,cost:130,costCur:"USD",adj:0,pk:[[93,57,40,47]]},
  {name:"36寸 双包（图一）",desc:"FLUTED 3抽屉，居中台盆",category:"家具",peak:"非旺季",price:419,cost:164,costCur:"USD",adj:0,pk:[[106,58,33,37.5],[94.5,56,15,27]]},
  {name:"36寸 双包",desc:"FLUTED 3抽屉，居中台盆",category:"家具",peak:"非旺季",price:399,cost:155,costCur:"USD",adj:0,pk:[[106,58,32,34],[94.5,56,14,23]]}
];

/* ---------------- state ---------------- */
/* 【判定台改动 1/3】初始方案来自服务端（window.PDT.init）；没有时沿用本浏览器的草稿，再没有用示例数据。 */
let P = (window.PDT && PDT.init && PDT.init.params) ? PDT.init.params : (load("pc_params") || defaultParams());
let products = (window.PDT && PDT.init && PDT.init.products) ? PDT.init.products : (load("pc_products") || sampleProducts());
let step = 1, wbIn = null, mapState = null, dl = null;
function sampleProducts(){ return SAMPLE.map(s=>({id:uid(),name:s.name,desc:s.desc,supplier:"",category:s.category,peak:s.peak,price:s.price,cost:s.cost,costCur:s.costCur,adj:s.adj,
  prices:{},pkgs:s.pk.map(p=>({l:p[0],w:p[1],h:p[2],kg:p[3]}))})); }
function load(k){ try{ const v=localStorage.getItem(k); return v?JSON.parse(v):null; }catch(e){ return null; } }
function save(){ try{ localStorage.setItem("pc_params",JSON.stringify(P)); localStorage.setItem("pc_products",JSON.stringify(products)); }catch(e){} }
function uid(){ return Math.random().toString(36).slice(2,9); }
function num(v){ if(v===null||v===undefined||v==="") return NaN; if(typeof v==="number") return v; const s=String(v).replace(/[,，\s$¥￥]/g,"").replace(/[^\d.\-]/g,""); return s===""?NaN:parseFloat(s); }
function nz(v){ const n=num(v); return isFinite(n)?n:0; }
function esc(s){ return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
const f2=v=>isFinite(v)?v.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}):"–";
const f1=v=>isFinite(v)?v.toFixed(1):"–";
const f0=v=>isFinite(v)?String(Math.round(v)):"–";
const pct=v=>isFinite(v)?(v*100).toFixed(1)+"%":"–";
const money=v=>isFinite(v)?(v<0?"(":"")+"$"+f2(Math.abs(v))+(v<0?")":""):"–";
const cls=v=>!isFinite(v)?"":v<0?"neg":"pos";
function toast(t){ const d=document.createElement("div"); d.className="toast"; d.textContent=t; document.body.appendChild(d); setTimeout(()=>d.remove(),2600); }

/* ---------------- calculation (mirrors the original workbook) ---------------- */
const ceil=x=>Math.ceil(Math.round(x*1e9)/1e9);
function costUSD(p){ const c=nz(p.cost); let v = p.costCur==="RMB_TAX"? c/(1+P.tax/100)/P.rate : p.costCur==="RMB_NET"? c/P.rate : c; return v+nz(p.adj); }
function taxNote(p){ return p.costCur==="RMB_TAX"?`已去税 ${P.tax}%`:p.costCur==="RMB_NET"?"税点不适用（未税价）":"税点不适用（FOB）"; }
function commission(price,cat){ const c=P.commission; if(cat==="家具") return price<=c.threshold? price*c.furnLow/100 : c.threshold*c.furnLow/100+(price-c.threshold)*c.furnHigh/100; const r=c[cat]; return price*(isFinite(num(r))?num(r):c["其他"])/100; }
function fbaPeak(){ if(P.fba.peakMode==="on") return true; if(P.fba.peakMode==="off") return false; const t=new Date(); const d=t.getFullYear()+"-"+String(t.getMonth()+1).padStart(2,"0")+"-"+String(t.getDate()).padStart(2,"0"); return d>=P.fba.peakStart && d<=P.fba.peakEnd; }
function exceptionType(J,K,L,N,P_,V){
  if(J>108||P_>150||V>165) return "超大包裹，LTL单独核算";
  if(J>=96) return "OS-超尺寸附加费-超第一长边";
  if(N>=17280) return "OS-超尺寸附加费-超立方体积";
  if(V>=130) return "OS-超尺寸附加费-超围长";
  if(P_>=110) return "OS-超尺寸附加费-超重";
  if(P_>=50) return "AHS-操作附加费-超重";
  if(N>=10368) return "AHS-操作附加费-超立方体积";
  if(J>=48||K>=30||V>=105) return "AHS-操作附加费-超尺寸";
  return "常规";
}
function cgBucket(J,K,L,P_,V){
  const bb = P_<120&&P_/J<50&&L<36&&J<72&&(Math.sqrt((72+K)**2+(J/2)**2)-72+2)<45;
  const bc = P_<120&&P_/J<50&&K<36&&J<72&&(Math.sqrt((72+L)**2+(J/2)**2)-72+2)<45;
  const bd = P_<120&&P_/K<50&&J<36&&K<72&&(Math.sqrt((72+L)**2+(L/2)**2)-72+2)<45;
  if(!(bb||bc||bd)) return "Standard - Oversize";
  if(J<=19&&K<=12&&L<=6&&P_<=25) return "Bin - Small";
  if(J<=26&&K<=17&&L<=14&&P_<=25) return "Bin - Large";
  if(J<=26&&K<=17&&L<=14&&P_>25&&P_<=50) return "Bin - Heavy";
  if(J<=48&&K<=30&&L<=30&&V<=130&&P_<=70) return "Standard - Small";
  if(J<=108&&V<=165&&P_<=70) return "Standard - Medium";
  if(J<=108&&V<=165&&P_>70&&P_<=120) return "Standard - Large";
  if(J<=108&&V<=165&&P_<=150) return "Standard - Oversize";
  return "null";
}
function fbaFee(L,M,N,W,LG){
  const pk=fbaPeak(); const lim=(v,x)=>x===""||x===null||x===undefined||!isFinite(num(x))||v<=num(x);
  let t=P.fba.tiers.find(t=>lim(W,t.w)&&lim(L,t.l)&&lim(M,t.m)&&lim(N,t.n)&&lim(LG,t.lg)) || P.fba.tiers[P.fba.tiers.length-1];
  let fee=((pk?nz(t.peak):nz(t.base)) + Math.max(0,ceil(W-nz(t.from)))*nz(t.per))*(1+P.fba.fuel/100);
  let os=0; if(W<=150&&(L>P.fba.osLen||LG>P.fba.osLG)) os = W<=50?P.fba.os50:W<=70?P.fba.os70:P.fba.os150;
  return {fee:Math.round((fee+os)*100)/100, tier:t.name, os};
}
function calcPkg(p,g){
  const cm=[nz(g.l),nz(g.w),nz(g.h)].sort((a,b)=>b-a);
  const kg=nz(g.kg);
  const J=Math.ceil(cm[0]/2.54),K=Math.ceil(cm[1]/2.54),L=Math.ceil(cm[2]/2.54);
  const M=cm[0]*cm[1]*cm[2]/1e6, N=J*K*L, O=N/P.fbm.dimDiv;
  const Pw=ceil(Math.max(kg*P.fbm.lbPerKg,O)), R=ceil(kg*P.fbm.ceilLb), T=O, V=J+2*(K+L);
  const W=exceptionType(J,K,L,N,Pw,V);
  const U=(W==="OS-超尺寸附加费-超第一长边"||W==="OS-超尺寸附加费-超围长")?Math.max(R,T,90):Math.max(T,R);
  const tr=P.tail.find(t=>nz(t.lb)===Pw); const tail=tr?nz(tr.fee):0, handling=tr?nz(tr.handling):0;
  const peak=p.peak==="旺季"; const sr=P.surch.find(s=>s.type===W); let surch=sr?nz(sr.base)+(peak?nz(sr.peak):0):0;
  let resi=0; if(P.residential){ const rr=P.surch.find(s=>s.type==="住宅附加费"); resi=rr?nz(rr.base)+(peak?nz(rr.peak):0):0; }
  const fbmBase=tail+handling+surch+resi, fbmFuel=fbmBase*nz(P.fbm.fuel)/100, fbmTotal=fbmBase+fbmFuel;
  const bucket=cgBucket(J,K,L,Pw,V); const cr=P.cg.find(c=>c.bucket===bucket);
  const cgShip=cr?nz(cr.ship):0, cgLb=cr?nz(cr.perLb)*U:0, cgPick=cr?nz(cr.pick):0;
  const ltl=(J>108||V>165||Pw>150)?"LTL":(J>106||V>163||Pw>145)?"LTL预警":"小包裹";
  const sea=P.sea.map(s=>M*nz(s.rmb)/nz(s.cbm)/P.rate);
  const fl=Math.round(cm[0]/2.54*100)/100, fm=Math.round(cm[1]/2.54*100)/100, fn=Math.round(cm[2]/2.54*100)/100;
  const ulb=kg*2.20462; const fw=Math.round((ulb>150?ulb:Math.max(ulb,fl*Math.max(fm,2)*Math.max(fn,2)/P.fba.dimDiv))*100)/100;
  const flg=Math.round((fl+2*(fm+fn))*100)/100; const fb=fbaFee(fl,fm,fn,fw,flg);
  return {cm,kg,J,K,L,M,N,O,Pw,R,T,U,V,W,tail,handling,surch,resi,fbmFuel,fbmTotal,bucket,cgShip,cgLb,cgPick,ltl,sea,fl,fm,fn,fw,flg,fba:fb.fee,fbaTier:fb.tier,fbaOs:fb.os,noTail:!tr};
}
function calcProduct(p){
  const pk=p.pkgs.map(g=>calcPkg(p,g));
  const price=nz(p.price), cost=costUSD(p);
  const promo=price*P.promo/100, fx=price*P.fxLoss/100, comm=commission(price,p.category), refund=price*P.refund/100;
  const fees=promo+fx+comm+refund;
  const sum=f=>pk.reduce((a,x)=>a+f(x),0);
  const fbmShip=sum(x=>x.fbmTotal), cgShip=sum(x=>x.cgShip+x.cgLb+x.cgPick), fbaShip=sum(x=>x.fba);
  const sc=P.sea.map((s,i)=>{ const sea=sum(x=>x.sea[i]); const base=price-cost-sea-fees;
    return {sea, fbm:base-fbmShip, cg:base-cgShip, fba:base-fbaShip}; });
  const warn=[]; pk.forEach((x,i)=>{ const tag=p.pkgs.length>1?`包裹${i+1}：`:""; if(x.ltl!=="小包裹") warn.push(tag+x.ltl); if(x.noTail) warn.push(tag+"计费重超出尾程表，FBM尾程按 0 计"); if(x.bucket==="null") warn.push(tag+"CG 无匹配档位，CG 运费按 0 计"); });
  const res={pk,price,cost,promo,fx,comm,refund,fees,fbmShip,cgShip,fbaShip,sc,warn};
  res.plat=calcPlatforms(p,res);
  return res;
}
/* Settle one product on every platform. Retail prices: list (上架) and promo (促销, the one that matters).
   Missing list price → Amazon price × listFactor; missing promo → list × (1 − default discount);
   promo only → list = promo ÷ (1 − discount). Settlement price = retail ÷ markup. */
function platPrices(p,r,k){
  const c=P.plat[k], pr=(p.prices&&p.prices[k])||{}, disc=nz(c.disc)/100;
  let list=num(pr.list), promo=num(pr.promo), est=false;
  if(!(list>0)){ if(promo>0&&disc<1) list=promo/(1-disc); else { list=r.price*nz(P.listFactor); est=true; } }
  if(!(promo>0)) promo=list*(1-disc);
  return {list,promo,est,listSet:num(pr.list)>0,promoSet:num(pr.promo)>0};
}
function calcPlatforms(p,r){
  const out={}, sum=f=>r.pk.reduce((a,x)=>a+f(x),0);
  for(const pl of PLATS){
    const c=P.plat[pl.k]; const pp=platPrices(p,r,pl.k);
    const logi=c.ship==="self"?sum(x=>x.fbmTotal):c.ship==="handling"?sum(x=>x.handling):0;
    const pct=(nz(c.ads)+nz(c.fx)+nz(c.comm)+nz(c.refund)+nz(c.storage)+nz(c.outbound))/100;
    const mk=nz(c.markup)||1, fixed=nz(c.fixed);
    const sc=P.sea.map((s,i)=>{
      const sea=sum(x=>x.sea[i]), base=r.cost+sea+logi+fixed;
      const at=retail=>{ const settle=retail/mk, fees=settle*pct, profit=settle-base-fees; return {retail,settle,fees,profit,margin:settle>0?profit/settle:NaN}; };
      const need=m=>{ const d=1-pct-m; return d>0?base/d*mk:NaN; };
      return {sea,base,list:at(pp.list),promo:at(pp.promo),breakeven:need(0),target:need(nz(P.targetMargin)/100)};
    });
    out[pl.k]=Object.assign(pp,{noPrice:!(pp.list>0),disc:pp.list>0?1-pp.promo/pp.list:NaN,logi,fixed,pct,mk,sc});
  }
  return out;
}

const seaIdx=()=>{ const i=Math.round(nz(P.seaView)); return i>=0&&i<P.sea.length?i:0; };
const platOn=()=>PLATS.filter(pl=>P.plat[pl.k]&&P.plat[pl.k].on!==false);
const amzOn=()=>AMZ.filter(a=>P.showAmz[a.k]!==false);

/* ---------------- bulk: set platform list prices from the Amazon price ---------------- */
let bulkUndo=null;
function renderBulk(){
  const b=P.bulk;
  const html=`<span class="muted">批量调平台价：</span>
    <select data-bp="plat" aria-label="平台"><option value="all" ${b.plat==="all"?"selected":""}>全部平台</option>${PLATS.map(pl=>`<option value="${pl.k}" ${b.plat===pl.k?"selected":""}>${esc(pl.name)}</option>`).join("")}</select>
    <span>上架价比 Amazon 售价高</span><input type="number" step="any" data-bp="pct" value="${esc(b.pct)}" aria-label="高出百分比"><span>%</span>
    <label class="chk"><input type="checkbox" data-bp="r99" ${b.r99?"checked":""}>尾数 .99</label>
    <label class="chk"><input type="checkbox" data-bp="promo" ${b.promo?"checked":""}>促销价按默认折扣重算</label>
    <button class="btn sm primary" data-bp="go">应用到全部产品</button>
    ${bulkUndo?`<button class="btn sm" data-bp="undo">撤销上次调整</button>`:""}`;
  document.querySelectorAll(".bulkPlat").forEach(el=>el.innerHTML=html);
}
function bulkApply(){
  const b=P.bulk, f=1+nz(b.pct)/100, ks=b.plat==="all"?PLATS.map(pl=>pl.k):[b.plat];
  bulkUndo={prices:Object.fromEntries(products.map(p=>[p.id,clone(p.prices||{})])),listFactor:P.listFactor};
  let n=0, skip=0;
  products.forEach(p=>{ const a=num(p.price); if(!(a>0)){ skip++; return; } p.prices=p.prices||{}; n++;
    let v=a*f; v=b.r99?Math.max(0.99,Math.ceil(v-1e-9)-0.01):Math.round(v*100)/100;
    ks.forEach(k=>{ const o=p.prices[k]=p.prices[k]||{}; o.list=Math.round(v*100)/100; if(b.promo) o.promo=""; }); });
  if(b.plat==="all") P.listFactor=Math.round(f*10000)/10000;
  save(); render();
  toast(`已调整 ${n} 个产品的${b.plat==="all"?"全部平台":PLATS.find(pl=>pl.k===b.plat).name}上架价（Amazon 售价 × ${f.toFixed(2)}）`+(skip?`，${skip} 个没有 Amazon 售价已跳过`:""));
}
function bulkRevert(){ if(!bulkUndo) return; products.forEach(p=>{ if(bulkUndo.prices[p.id]) p.prices=bulkUndo.prices[p.id]; }); P.listFactor=bulkUndo.listFactor; bulkUndo=null; save(); render(); toast("已撤销上次批量调整"); }
document.addEventListener("change",e=>{ const t=e.target.closest("[data-bp]"); if(!t||!t.closest(".bulkPlat")) return; const k=t.dataset.bp;
  if(k==="plat") P.bulk.plat=t.value; else if(k==="pct") P.bulk.pct=t.value===""?0:num(t.value); else if(k==="r99"||k==="promo") P.bulk[k]=t.checked; else return;
  save(); renderBulk(); });
document.addEventListener("click",e=>{ const t=e.target.closest("[data-bp]"); if(!t||!t.closest(".bulkPlat")) return;
  if(t.dataset.bp==="go") bulkApply(); else if(t.dataset.bp==="undo") bulkRevert(); });

/* ---------------- step navigation ---------------- */
function go(n){ step=n; for(let i=1;i<=5;i++) document.getElementById("s"+i).hidden=i!==n;
  document.querySelectorAll("#steps button").forEach(b=>{ if(+b.dataset.step===n) b.setAttribute("aria-current","step"); else b.removeAttribute("aria-current"); });
  render(); try{ localStorage.setItem("pc_step",n);}catch(e){} window.scrollTo(0,0); }
document.getElementById("steps").addEventListener("click",e=>{ const b=e.target.closest("button"); if(b) go(+b.dataset.step); });
document.addEventListener("click",e=>{ const b=e.target.closest("[data-go]"); if(b) go(+b.dataset.go); });
function render(){ renderBulk(); if(step===1) renderS1(); if(step===2) renderS2(); if(step===3) renderS3(); if(step===4) renderS4(); if(step===5) renderS5(); }

/* ---------------- step 1: import ---------------- */
const FIELDS=[
  {k:"name",label:"品名 / 型号",pats:[/物品名称/,/品名/,/产品名称/,/型号/,/款号/,/名称/,/^sku/i,/item/i,/product/i]},
  {k:"desc",label:"材质 / 描述",pats:[/材质/,/描述/,/规格/,/说明/,/desc/i]},
  {k:"supplier",label:"供应商",pats:[/供应商/,/工厂/,/厂家/,/supplier/i]},
  {k:"category",label:"品类",pats:[/品类/,/类目/]},
  {k:"peak",label:"FBM旺季",pats:[/旺季/]},
  {k:"l",label:"长",pats:[/^长\s*[(（]?\s*cm/i,/^长\s*$/,/包装长/,/箱长/,/长度/,/^length/i]},
  {k:"w",label:"宽",pats:[/^宽\s*[(（]?\s*cm/i,/^宽\s*$/,/包装宽/,/箱宽/,/宽度/,/^width/i]},
  {k:"h",label:"高",pats:[/^高\s*[(（]?\s*cm/i,/^高\s*$/,/包装高/,/箱高/,/高度/,/^height/i]},
  {k:"dims",label:"尺寸（长*宽*高 在同一列）",pats:[/外箱尺寸/,/包装尺寸/,/纸箱尺寸/,/^尺寸/,/dimension/i]},
  {k:"kg",label:"毛重",pats:[/毛重/,/质量重量/,/^重量/,/gross/i,/weight/i]},
  {k:"cost",label:"出厂价 / 采购价",pats:[/出厂目标价/,/出厂价/,/采购价/,/^fob/i,/单价/,/报价/,/^价格/]},
  {k:"price",label:"售价（List Price $）",pats:[/list\s*price/i,/售价/,/零售价/,/定价/]},
  {k:"vcList",label:"Lowe's VC 上架价",pats:[/VC\s*前台/i]},
  {k:"scPromo",label:"Lowe's SC 促销价",pats:[]},
  {k:"hdList",label:"Home Depot 上架价",pats:[]},
  {k:"wfList",label:"Wayfair 上架价",pats:[]}
];
const norm=s=>String(s??"").replace(/\s+/g," ").trim();
function renderS1(){
  const n=products.length, k=products.reduce((a,p)=>a+p.pkgs.length,0);
  document.getElementById("projInfo").textContent = n? `已有 ${n} 个产品、${k} 个包裹。导入新报价表时可选择替换或追加。` : "还没有产品。";
}
function readFile(f){
  const r=new FileReader();
  r.onload=e=>{ try{ wbIn=XLSX.read(new Uint8Array(e.target.result),{type:"array"}); setupMap(); }catch(err){ toast("无法读取这个文件："+err.message); } };
  r.readAsArrayBuffer(f);
}
function sheetRows(name){ return XLSX.utils.sheet_to_json(wbIn.Sheets[name],{header:1,defval:"",raw:true,blankrows:true}); }
function bestSheet(){ let best=wbIn.SheetNames[0],sc=-1; for(const n of wbIn.SheetNames){ const s=scoreHeader(sheetRows(n)).score; if(s>sc){sc=s;best=n;} } return best; }
function scoreHeader(rows){ let best={row:0,score:0}; for(let r=0;r<Math.min(rows.length,20);r++){ let s=0; for(const c of rows[r]){ const t=norm(c); if(!t) continue; if(FIELDS.some(f=>f.pats.some(p=>p.test(t)))) s++; } if(s>best.score) best={row:r,score:s}; } return best; }
function guessMap(hdr){
  const m={}; const used=new Set();
  for(const f of FIELDS){ m[f.k]=-1; for(const p of f.pats){ const i=hdr.findIndex((h,ix)=>!used.has(ix)&&p.test(norm(h))); if(i>=0){ m[f.k]=i; used.add(i); break; } } }
  if(m.l>=0&&m.w>=0&&m.h>=0) m.dims=-1;
  return m;
}
function setupMap(){
  const sheet=bestSheet(); const rows=sheetRows(sheet); const hr=scoreHeader(rows).row;
  mapState={sheet,header:hr,map:guessMap(rows[hr]||[])};
  const hdr=rows[hr]||[]; const hc=i=>i>=0?norm(hdr[i]):"";
  document.getElementById("unitDim").value=/in/i.test(hc(mapState.map.l)+hc(mapState.map.dims))&&!/cm/i.test(hc(mapState.map.l))?"in":"cm";
  document.getElementById("unitWt").value=/lb|磅/i.test(hc(mapState.map.kg))?"lb":"kg";
  const ch=hc(mapState.map.cost); document.getElementById("unitCost").value=/rmb|元|¥|￥|人民币/i.test(ch)?(/未税|不含税/.test(ch)?"RMB_NET":"RMB_TAX"):"USD";
  document.getElementById("mapArea").hidden=false; drawMap(); document.getElementById("mapArea").scrollIntoView({behavior:"smooth"});
}
function drawMap(){
  const ss=document.getElementById("mapSheet"); ss.innerHTML=wbIn.SheetNames.map(n=>`<option ${n===mapState.sheet?"selected":""}>${esc(n)}</option>`).join("");
  document.getElementById("mapHeader").value=mapState.header+1;
  const rows=sheetRows(mapState.sheet); const hdr=rows[mapState.header]||[];
  const opts=i=>`<option value="-1">（无）</option>`+hdr.map((h,ix)=>`<option value="${ix}" ${ix===i?"selected":""}>${XLSX.utils.encode_col(ix)} · ${esc(norm(h).slice(0,24)||"(空)")}</option>`).join("");
  document.getElementById("mapFields").innerHTML=FIELDS.map(f=>`<label class="f">${f.label}<select data-map="${f.k}">${opts(mapState.map[f.k])}</select></label>`).join("");
  const parsed=parseRows();
  const body=parsed.slice(0,40).map(p=>p.pkgs.map((g,gi)=>`<tr class="${gi?"":"first"}"><td>${gi?"":esc(p.name)}</td><td class="c">${gi+1}</td><td class="n">${f1(g.l)}</td><td class="n">${f1(g.w)}</td><td class="n">${f1(g.h)}</td><td class="n">${f1(g.kg)}</td><td class="n">${gi?"":f2(num(p.cost))}</td><td class="n">${gi?"":f2(num(p.price))}</td><td>${gi?"":esc(p.category)}</td></tr>`).join("")).join("");
  document.getElementById("mapPreview").innerHTML=`<table><thead><tr><th>品名</th><th>包裹</th><th>长 cm</th><th>宽 cm</th><th>高 cm</th><th>毛重 kg</th><th>出厂价</th><th>售价 $</th><th>品类</th></tr></thead><tbody>${body||`<tr><td colspan="9" class="muted">没有识别到数据行，请检查表头行和列对应。</td></tr>`}</tbody></table>`;
  document.getElementById("mapCount").textContent=`识别到 ${parsed.length} 个产品、${parsed.reduce((a,p)=>a+p.pkgs.length,0)} 个包裹（预览按 cm / kg 换算后显示）`;
}
function parseRows(){
  const rows=sheetRows(mapState.sheet); const m=mapState.map;
  const kd=document.getElementById("unitDim").value==="in"?2.54:1, kw=document.getElementById("unitWt").value==="lb"?0.45359237:1;
  const cur=document.getElementById("unitCost").value, defCat=document.getElementById("defCat").value;
  const get=(r,k)=>m[k]>=0?r[m[k]]:"";
  const out=[]; let cur_p=null;
  for(let i=mapState.header+1;i<rows.length;i++){
    const r=rows[i]; if(!r) continue;
    let l=num(get(r,"l")),w=num(get(r,"w")),h=num(get(r,"h"));
    if(!(l>0&&w>0&&h>0)&&m.dims>=0){ const d=String(get(r,"dims")).split(/[*xX×＊]/).map(num); if(d.length>=3){[l,w,h]=d;} }
    const hasDims=l>0&&w>0&&h>0; const name=norm(get(r,"name"));
    if(!hasDims&&!name) continue;
    if(!hasDims&&name&&!isFinite(num(get(r,"cost")))&&!isFinite(num(get(r,"price")))) continue;
    const pkg={l:hasDims?+(l*kd).toFixed(2):"",w:hasDims?+(w*kd).toFixed(2):"",h:hasDims?+(h*kd).toFixed(2):"",kg:isFinite(num(get(r,"kg")))?+(num(get(r,"kg"))*kw).toFixed(3):""};
    if(!name&&cur_p){ cur_p.pkgs.push(pkg); if(!isFinite(num(cur_p.cost))&&isFinite(num(get(r,"cost")))) cur_p.cost=num(get(r,"cost")); if(!isFinite(num(cur_p.price))&&isFinite(num(get(r,"price")))) cur_p.price=num(get(r,"price")); continue; }
    const cat=norm(get(r,"category")); const pk=norm(get(r,"peak"));
    cur_p={id:uid(),name:name||("产品"+(out.length+1)),desc:norm(get(r,"desc")),supplier:norm(get(r,"supplier")),category:CATS.includes(cat)?cat:(cat||defCat),peak:pk==="旺季"?"旺季":"非旺季",
      price:isFinite(num(get(r,"price")))?num(get(r,"price")):"",cost:isFinite(num(get(r,"cost")))?num(get(r,"cost")):"",costCur:cur,adj:0,pkgs:[pkg],prices:{}};
    const pv=k=>{ const v=num(get(r,k)); return isFinite(v)&&v>0?v:""; };
    if(pv("vcList")) cur_p.prices.lowesVC={list:pv("vcList")}; if(pv("scPromo")) cur_p.prices.lowesSC={promo:pv("scPromo")};
    if(pv("hdList")) cur_p.prices.hd={list:pv("hdList")}; if(pv("wfList")) cur_p.prices.wf={list:pv("wfList")};
    out.push(cur_p);
  }
  return out;
}
const fileIn=document.getElementById("file"); fileIn.addEventListener("change",()=>{ if(fileIn.files[0]) readFile(fileIn.files[0]); });
const drop=document.getElementById("drop");
drop.addEventListener("dragover",e=>{e.preventDefault();drop.classList.add("over");});
drop.addEventListener("dragleave",()=>drop.classList.remove("over"));
drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("over"); const f=e.dataTransfer.files[0]; if(f) readFile(f);});
document.getElementById("mapSheet").addEventListener("change",e=>{ mapState.sheet=e.target.value; const rows=sheetRows(mapState.sheet); mapState.header=scoreHeader(rows).row; mapState.map=guessMap(rows[mapState.header]||[]); drawMap(); });
document.getElementById("mapHeader").addEventListener("change",e=>{ mapState.header=Math.max(0,(parseInt(e.target.value)||1)-1); mapState.map=guessMap(sheetRows(mapState.sheet)[mapState.header]||[]); drawMap(); });
document.getElementById("mapFields").addEventListener("change",e=>{ const s=e.target.closest("[data-map]"); if(s){ mapState.map[s.dataset.map]=+s.value; drawMap(); } });
["unitDim","unitWt","unitCost","defCat"].forEach(id=>document.getElementById(id).addEventListener("change",()=>mapState&&drawMap()));
document.getElementById("btnImport").addEventListener("click",()=>{ const ps=parseRows(); if(!ps.length){ toast("没有可导入的数据行"); return; }
  products = document.getElementById("importMode").value==="append"? products.concat(ps) : ps; save(); toast(`已导入 ${ps.length} 个产品`); go(2); });
document.getElementById("btnSample").addEventListener("click",()=>{ products=sampleProducts(); save(); toast("已加载示例数据"); go(2); });
document.getElementById("btnBlank").addEventListener("click",()=>{ products.push(blankProduct()); save(); go(2); });
document.getElementById("btnLoadJson").addEventListener("click",()=>document.getElementById("jsonFile").click());
document.getElementById("jsonFile").addEventListener("change",e=>{ const f=e.target.files[0]; if(!f) return; const r=new FileReader(); r.onload=()=>{ try{ const d=JSON.parse(r.result); if(d.products) products=d.products; if(d.params) P=Object.assign(defaultParams(),d.params); migrate(); save(); toast("方案已打开"); go(4);}catch(err){ toast("文件格式不对："+err.message);} }; r.readAsText(f); e.target.value=""; });
function blankProduct(){ return {id:uid(),name:"新产品",desc:"",supplier:"",category:"家具",peak:"非旺季",price:"",cost:"",costCur:"USD",adj:0,prices:{},pkgs:[{l:"",w:"",h:"",kg:""}]}; }
const catOpts=sel=>CATS.map(c=>`<option ${c===sel?"selected":""}>${c}</option>`).join("");
document.getElementById("unitCost").innerHTML=Object.entries(COST_CUR).map(([k,v])=>`<option value="${k}">${v}</option>`).join("");
document.getElementById("defCat").innerHTML=catOpts("家具");
document.getElementById("bulkCat").innerHTML=catOpts("家具");

/* ---------------- step 2: confirm ---------------- */
function renderS2(){
  const issues=[];
  const rows=products.map((p,pi)=>{
    const n=p.pkgs.length; const c=costUSD(p); const rr=calcProduct(p);
    if(!(nz(p.price)>0)) issues.push(`${p.name}：缺售价`); if(!(nz(p.cost)>0)) issues.push(`${p.name}：缺出厂价`);
    return p.pkgs.map((g,gi)=>{
      const bad=k=>!(nz(g[k])>0)?' style="border-color:var(--neg)"':"";
      if(gi===0&&[g.l,g.w,g.h,g.kg].some(v=>!(nz(v)>0))) issues.push(`${p.name}：包裹尺寸或毛重不完整`);
      const pc= nz(g.l)*nz(g.w)*nz(g.h)/1e6;
      const head = gi? "" : `
        <td rowspan="${n}"><input class="wide" data-p="${pi}" data-k="name" value="${esc(p.name)}"></td>
        <td rowspan="${n}"><textarea data-p="${pi}" data-k="desc">${esc(p.desc)}</textarea></td>
        <td rowspan="${n}"><input data-p="${pi}" data-k="supplier" value="${esc(p.supplier)}" style="width:90px"></td>
        <td rowspan="${n}"><select data-p="${pi}" data-k="category">${catOpts(p.category)}</select></td>
        <td rowspan="${n}"><select data-p="${pi}" data-k="peak"><option ${p.peak!=="旺季"?"selected":""}>非旺季</option><option ${p.peak==="旺季"?"selected":""}>旺季</option></select></td>
        <td rowspan="${n}"><input type="number" step="any" data-p="${pi}" data-k="price" value="${esc(p.price)}"${!(nz(p.price)>0)?' style="border-color:var(--neg)"':""}></td>
        ${PLATS.map(pl=>{ const x=rr.plat[pl.k], pr=(p.prices&&p.prices[pl.k])||{}; return `<td rowspan="${n}"><div class="pp">
          <label>上架<input type="number" step="any" data-p="${pi}" data-plat="${pl.k}" data-pk="list" value="${esc(pr.list??"")}" placeholder="${x.list>0?f2(x.list):"–"}"></label>
          <label>促销<input type="number" step="any" data-p="${pi}" data-plat="${pl.k}" data-pk="promo" value="${esc(pr.promo??"")}" placeholder="${x.promo>0?f2(x.promo):"–"}"></label>
          <span class="note">${x.list>0?pct(x.disc)+" off":""}${x.est?" · 估算":""}</span></div></td>`; }).join("")}
        <td rowspan="${n}"><input type="number" step="any" data-p="${pi}" data-k="cost" value="${esc(p.cost)}"${!(nz(p.cost)>0)?' style="border-color:var(--neg)"':""}></td>
        <td rowspan="${n}"><select data-p="${pi}" data-k="costCur">${Object.entries(COST_CUR).map(([k,v])=>`<option value="${k}" ${k===p.costCur?"selected":""}>${v}</option>`).join("")}</select></td>
        <td rowspan="${n}"><input type="number" step="any" data-p="${pi}" data-k="adj" value="${esc(p.adj)}" title="例如减去排插、子抽等差价，填负数"></td>
        <td rowspan="${n}" class="n"><b>${money(c)}</b><br><span class="note">${nz(p.price)>0?pct(c/nz(p.price))+" 占比":""}</span><br><span class="note">${taxNote(p)}</span></td>`;
      return `<tr class="${gi?"":"first"}">${head}
        <td class="c">${gi+1}</td>
        <td><input type="number" step="any" data-p="${pi}" data-g="${gi}" data-k="l" value="${esc(g.l)}"${bad("l")}></td>
        <td><input type="number" step="any" data-p="${pi}" data-g="${gi}" data-k="w" value="${esc(g.w)}"${bad("w")}></td>
        <td><input type="number" step="any" data-p="${pi}" data-g="${gi}" data-k="h" value="${esc(g.h)}"${bad("h")}></td>
        <td><input type="number" step="any" data-p="${pi}" data-g="${gi}" data-k="kg" value="${esc(g.kg)}"${bad("kg")}></td>
        <td class="n">${pc?pc.toFixed(4):"–"}</td>
        <td class="c" style="white-space:nowrap"><button class="btn sm" data-act="addPkg" data-p="${pi}">+包裹</button> ${n>1?`<button class="btn sm danger" data-act="delPkg" data-p="${pi}" data-g="${gi}">删包裹</button>`:""} ${gi===0?`<button class="btn sm danger" data-act="delProd" data-p="${pi}">删产品</button>`:""}</td>
      </tr>`;
    }).join("");
  }).join("");
  document.getElementById("confirmTable").innerHTML=`<table><thead><tr>
    <th>品名</th><th>材质 / 描述</th><th>供应商</th><th>品类</th><th>FBM旺季</th><th>Amazon 售价 $</th>${PLATS.map(pl=>`<th>${esc(pl.name)} $<br><span class="note">上架 / 促销</span></th>`).join("")}<th>出厂价</th><th>出厂价币种</th><th>成本调整 $</th><th>采购成本 $</th>
    <th>包裹</th><th>长 cm</th><th>宽 cm</th><th>高 cm</th><th>毛重 kg</th><th>体积 m³</th><th>操作</th></tr></thead>
    <tbody>${rows||`<tr><td colspan="${17+PLATS.length}" class="muted">还没有产品，点“+ 新增产品”或回到第 1 步导入报价表。</td></tr>`}</tbody></table>`;
  document.getElementById("checkMsg").innerHTML = issues.length? `<p class="msg">请补全：${issues.slice(0,8).map(esc).join("；")}${issues.length>8?" …":""}</p>` : products.length? `<p class="msg ok">${products.length} 个产品的尺寸、毛重、成本和售价都已填写。</p>`:"";
}
const ct=document.getElementById("confirmTable");
ct.addEventListener("change",e=>{ const t=e.target;
  if(t.dataset.plat){ const p=products[+t.dataset.p]; p.prices=p.prices||{}; const o=p.prices[t.dataset.plat]=p.prices[t.dataset.plat]||{}; o[t.dataset.pk]=t.value===""?"":num(t.value); save(); renderS2(); return; }
  if(!t.dataset.k) return; const p=products[+t.dataset.p]; const numK=["price","cost","adj","l","w","h","kg"].includes(t.dataset.k);
  const v=numK?(t.value===""?"":num(t.value)):t.value; if(t.dataset.g!==undefined) p.pkgs[+t.dataset.g][t.dataset.k]=v; else p[t.dataset.k]=v; save(); renderS2(); });
ct.addEventListener("click",e=>{ const b=e.target.closest("[data-act]"); if(!b) return; const pi=+b.dataset.p;
  if(b.dataset.act==="addPkg") products[pi].pkgs.push({l:"",w:"",h:"",kg:""});
  if(b.dataset.act==="delPkg") products[pi].pkgs.splice(+b.dataset.g,1);
  if(b.dataset.act==="delProd"){ if(b.dataset.confirm!=="1"){ b.dataset.confirm="1"; b.textContent="确认删除?"; setTimeout(()=>{ if(b.isConnected){ b.dataset.confirm=""; b.textContent="删产品"; } },3000); return; } products.splice(pi,1); }
  save(); renderS2(); });
document.getElementById("btnAddProd").addEventListener("click",()=>{ products.push(blankProduct()); save(); renderS2(); });
document.getElementById("btnBulkCat").addEventListener("click",()=>{ const v=document.getElementById("bulkCat").value; products.forEach(p=>p.category=v); save(); renderS2(); });
document.getElementById("btnBulkPeak").addEventListener("click",()=>{ const v=document.getElementById("bulkPeak").value; products.forEach(p=>p.peak=v); save(); renderS2(); });

/* ---------------- step 3: params ---------------- */
function fld(path,label,opt={}){ const v=getPath(path); const t=opt.type||"number";
  if(t==="select") return `<label class="f">${label}<select data-path="${path}">${opt.options.map(([k,l])=>`<option value="${k}" ${String(v)===String(k)?"selected":""}>${l}</option>`).join("")}</select></label>`;
  if(t==="date") return `<label class="f">${label}<input type="date" data-path="${path}" value="${esc(v)}"></label>`;
  if(t==="check"){ const lb=opt.labels||["不计入","计入"]; return `<label class="f">${label}<select data-path="${path}" data-bool="1"><option value="0" ${!v?"selected":""}>${lb[0]}</option><option value="1" ${v?"selected":""}>${lb[1]}</option></select></label>`; }
  return `<label class="f">${label}<input type="number" step="any" data-path="${path}" value="${esc(v)}"></label>`; }
function getPath(p){ return p.split(".").reduce((o,k)=>o==null?o:o[k],P); }
function setPath(p,v){ const ks=p.split("."); let o=P; for(let i=0;i<ks.length-1;i++) o=o[ks[i]]; o[ks[ks.length-1]]=v; }
function renderS3(){
  document.getElementById("pBase").innerHTML=[fld("rate","汇率（RMB/USD）"),fld("promo","推广 %"),fld("fxLoss","汇损 %"),fld("refund","退款 %"),fld("tax","采购税点 %（仅 RMB 含税价适用，FOB 不适用）"),fld("residential","FBM住宅附加费",{type:"check"}),fld("fbm.fuel","尾程燃油附加费 %（FBM、Lowe's SC 等我们发货的渠道）"),fld("fbm.dimDiv","FBM体积重除数"),fld("fbm.lbPerKg","kg→lb（计费重）"),fld("fbm.ceilLb","kg→lb（实重取整）")].join("");
  document.getElementById("pPlatBase").innerHTML=[fld("listFactor","平台上架价系数（× Amazon 售价）"),fld("targetMargin","目标利润率 %（反推目标促销价）")].join("");
  document.getElementById("pPlat").innerHTML=PLATS.map(pl=>{ const b="plat."+pl.k+"."; return `<div class="card"><div class="t">${esc(pl.name)}</div><div class="kv">${[
    fld(b+"on","结果里",{type:"check",labels:["隐藏","显示"]}),fld(b+"ship","发货方",{type:"select",options:Object.entries(SHIP)}),
    fld(b+"markup","加价倍率"),fld(b+"disc","默认促销折扣 %"),fld(b+"fixed","平台订单费 $/单"),fld(b+"ads","推广 %"),fld(b+"fx","汇损 %"),fld(b+"comm","佣金 %"),fld(b+"refund","退款 %"),fld(b+"storage","仓储费 %"),fld(b+"outbound","出仓费 %")].join("")}</div></div>`; }).join("");
  document.getElementById("pComm").innerHTML=[fld("commission.threshold","家具阈值 $"),fld("commission.furnLow","家具 ≤阈值 %"),fld("commission.furnHigh","家具 >阈值部分 %"),fld("commission.汽配","汽配 %"),fld("commission.工业机械","工业机械 %"),fld("commission.农机花园","农机花园 %"),fld("commission.其他","其他 %")].join("");
  document.getElementById("pSea").innerHTML=`<table><thead><tr><th>方案名称</th><th>整柜价 RMB</th><th>计算体积 CBM</th><th>$/m³</th><th></th></tr></thead><tbody>${P.sea.map((s,i)=>`<tr>
    <td><input data-sea="${i}" data-k="name" value="${esc(s.name)}" style="width:150px"></td>
    <td><input type="number" step="any" data-sea="${i}" data-k="rmb" value="${esc(s.rmb)}" style="width:90px"></td>
    <td><input type="number" step="any" data-sea="${i}" data-k="cbm" value="${esc(s.cbm)}" style="width:60px"></td>
    <td class="n">${f2(nz(s.rmb)/nz(s.cbm)/P.rate)}</td>
    <td>${P.sea.length>1?`<button class="btn sm danger" data-delsea="${i}">删</button>`:""}</td></tr>`).join("")}</tbody></table>`;
  document.getElementById("pFbaBase").innerHTML=[fld("fba.fuel","燃油/物流附加费 %"),fld("fba.dimDiv","FBA体积重除数"),fld("fba.peakMode","FBA旺季费率",{type:"select",options:[["auto","按日期自动"],["on","始终旺季"],["off","始终非旺季"]]}),fld("fba.peakStart","旺季开始",{type:"date"}),fld("fba.peakEnd","旺季结束",{type:"date"}),fld("fba.osLen","超长判定：最长边 > in"),fld("fba.osLG","超长判定：长+围长 > in"),fld("fba.os50","超长附加 ≤50lb $"),fld("fba.os70","超长附加 ≤70lb $"),fld("fba.os150","超长附加 ≤150lb $")].join("")+`<p class="note" style="grid-column:1/-1">当前按 <b>${fbaPeak()?"旺季":"非旺季"}</b> 费率计算。</p>`;
  const tf=(i,k,w=64)=>`<input ${k==="name"?"":'type="number" step="any"'} data-tier="${i}" data-k="${k}" value="${esc(P.fba.tiers[i][k])}" style="width:${w}px">`;
  document.getElementById("pFbaTiers").innerHTML=`<table><thead><tr><th>档位</th><th>重量 ≤ lb</th><th>最长边 ≤</th><th>次长边 ≤</th><th>最短边 ≤</th><th>长+围长 ≤</th><th>非旺季基础费 $</th><th>旺季基础费 $</th><th>续重 $/lb</th><th>起算 lb</th></tr></thead><tbody>${P.fba.tiers.map((t,i)=>`<tr><td>${tf(i,"name",130)}</td><td>${tf(i,"w")}</td><td>${tf(i,"l")}</td><td>${tf(i,"m")}</td><td>${tf(i,"n")}</td><td>${tf(i,"lg")}</td><td>${tf(i,"base",76)}</td><td>${tf(i,"peak",76)}</td><td>${tf(i,"per")}</td><td>${tf(i,"from")}</td></tr>`).join("")}</tbody></table>`;
  document.getElementById("pTail").innerHTML=`<table><thead><tr><th>计费重 lb</th><th>加权平均运费 $</th><th>订单处理费 $</th></tr></thead><tbody>${P.tail.map((t,i)=>`<tr><td class="n">${t.lb}</td><td><input type="number" step="any" data-tail="${i}" data-k="fee" value="${esc(t.fee)}"></td><td><input type="number" step="any" data-tail="${i}" data-k="handling" value="${esc(t.handling)}"></td></tr>`).join("")}</tbody></table>`;
  document.getElementById("pSurch").innerHTML=`<table><thead><tr><th>异常费用项</th><th>规则</th><th>附加费（加权平均）$</th><th>旺季附加 $</th></tr></thead><tbody>${P.surch.map((s,i)=>`<tr><td>${esc(s.type)}</td><td class="note">${esc(s.rule)}</td><td><input type="number" step="any" data-surch="${i}" data-k="base" value="${esc(s.base)}"></td><td><input type="number" step="any" data-surch="${i}" data-k="peak" value="${esc(s.peak)}"></td></tr>`).join("")}</tbody></table><p class="note" style="padding:0 8px">同一异常类型有多条规则时取第一条的费用。旺季产品 = 附加费 + 旺季附加。</p>`;
  document.getElementById("pCg").innerHTML=`<table><thead><tr><th>Product Bucket</th><th>Pick Only $</th><th>Pick&amp;Ship 基础 $</th><th>每磅 $/LB</th></tr></thead><tbody>${P.cg.map((c,i)=>`<tr><td>${esc(c.bucket)}</td>${["pick","ship","perLb"].map(k=>`<td><input type="number" step="any" data-cg="${i}" data-k="${k}" value="${Number.isFinite(c[k])?c[k]:""}"></td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
const s3=document.getElementById("s3");
s3.addEventListener("change",e=>{ const t=e.target; let v=t.type==="number"?(t.value===""?"":num(t.value)):t.value;
  if(t.dataset.path){ if(t.dataset.bool) v=t.value==="1"; setPath(t.dataset.path,v); }
  else if(t.dataset.sea!==undefined) P.sea[+t.dataset.sea][t.dataset.k]=v;
  else if(t.dataset.tier!==undefined) P.fba.tiers[+t.dataset.tier][t.dataset.k]=v;
  else if(t.dataset.tail!==undefined) P.tail[+t.dataset.tail][t.dataset.k]=v;
  else if(t.dataset.surch!==undefined) P.surch[+t.dataset.surch][t.dataset.k]=v;
  else if(t.dataset.cg!==undefined) P.cg[+t.dataset.cg][t.dataset.k]=v;
  else return; save(); const open=[...s3.querySelectorAll("details")].map(d=>d.open); renderS3(); s3.querySelectorAll("details").forEach((d,i)=>d.open=open[i]); });
s3.addEventListener("click",e=>{ const b=e.target.closest("[data-delsea]"); if(b){ P.sea.splice(+b.dataset.delsea,1); save(); renderS3(); } });
document.getElementById("btnAddSea").addEventListener("click",()=>{ P.sea.push({name:"新海运方案",rmb:100000,cbm:68}); save(); renderS3(); });
document.getElementById("btnResetParams").addEventListener("click",e=>{ const b=e.currentTarget; if(b.dataset.confirm!=="1"){ b.dataset.confirm="1"; b.textContent="再点一次确认恢复"; setTimeout(()=>{b.dataset.confirm="";b.textContent="恢复默认参数";},3000); return; } P=defaultParams(); save(); b.dataset.confirm=""; b.textContent="恢复默认参数"; renderS3(); toast("参数已恢复默认"); });
document.getElementById("btnRateImport").addEventListener("click",()=>document.getElementById("rateFile").click());
document.getElementById("rateFile").addEventListener("change",e=>{ const f=e.target.files[0]; if(!f) return; const r=new FileReader(); r.onload=ev=>{ try{
    const wb=XLSX.read(new Uint8Array(ev.target.result),{type:"array"}); const msgs=[];
    const tn=wb.SheetNames.find(n=>/^尾程运费/.test(n.trim())); if(tn){ const rows=XLSX.utils.sheet_to_json(wb.Sheets[tn],{header:1,defval:""});
      const tail=rows.slice(1).filter(r=>isFinite(num(r[0]))&&isFinite(num(r[2]))).map(r=>({lb:num(r[0]),fee:num(r[2]),handling:nz(r[3])})); if(tail.length){P.tail=tail; msgs.push(`尾程 ${tail.length} 档`);}
      const su=rows.slice(1).filter(r=>norm(r[6])&&isFinite(num(r[8]))).map(r=>({type:norm(r[6]),rule:norm(r[7]),base:num(r[8]),peak:nz(r[10])})); if(su.length){P.surch=su; msgs.push(`异常附加费 ${su.length} 条`);} }
    const cn=wb.SheetNames.find(n=>/CG尾程运费/.test(n)); if(cn){ const rows=XLSX.utils.sheet_to_json(wb.Sheets[cn],{header:1,defval:""});
      const cg=rows.filter(r=>/^(Bin|Standard|Large)/.test(norm(r[0]))).map(r=>({bucket:norm(r[0]),pick:num(r[3]),ship:num(r[4]),perLb:num(r[5])})); if(cg.length){P.cg=cg; msgs.push(`CG ${cg.length} 档`);} }
    save(); renderS3(); toast(msgs.length?"已导入："+msgs.join("、"):"没找到“尾程运费”或“CG尾程运费”工作表");
  }catch(err){ toast("无法读取："+err.message);} }; r.readAsArrayBuffer(f); e.target.value=""; });

/* ---------------- step 4: results ---------------- */
function renderS4(){
  document.getElementById("quickParams").innerHTML=[fld("rate","汇率"),fld("promo","推广 %"),fld("fxLoss","汇损 %"),fld("refund","退款 %"),fld("fbm.fuel","尾程燃油 %"),fld("targetMargin","目标利润率 %"),(products.some(p=>p.costCur==="RMB_TAX")?fld("tax","税点 %（RMB含税）"):`<label class="f">税点 %<input value="FOB 不适用" disabled style="width:100px;text-align:center"></label>`),
    ...P.sea.map((s,i)=>fld(`sea.${i}.rmb`,esc(s.name)+" RMB")),fld("fba.peakMode","FBA费率",{type:"select",options:[["auto","按日期"],["on","旺季"],["off","非旺季"]]})].join("")+`<span class="note">更多变量见“参数设置”</span>`;
  const R=products.map(p=>({p,r:calcProduct(p)}));
  renderAll(R);
  document.getElementById("detailChan").innerHTML=DETAIL_OPTS().map(([v,l])=>`<option value="${v}" ${v===P.detailChan?"selected":""}>${esc(l)}</option>`).join("");
  if(!R.length){ document.getElementById("resCards").innerHTML=`<p class="muted">还没有产品。回到第 1 步导入报价表，或加载示例数据。</p>`; document.getElementById("resSummary").innerHTML=""; document.getElementById("resDetail").innerHTML=""; document.getElementById("resMix").innerHTML=""; return; }
  const si=seaIdx(), CH=chanList();
  document.querySelectorAll(".seaName").forEach(e=>e.textContent="海运方案："+P.sea[si].name);
  // cards: every visible channel for the selected sea plan
  document.getElementById("resCards").innerHTML=R.map(({p,r})=>`<div class="card">
    <div class="t">${esc(p.name)}<span>${p.pkgs.length}包 · 采购 ${money(r.cost)}</span></div>
    <div class="mini2">${CH.map(ch=>{ const v=chanVal(r,ch,si); return `<span class="l">${esc(ch.name)}</span><span class="v ${v.ok?cls(v.profit):""}">${v.ok?money(v.profit)+" · "+pct(v.profit/v.rev):"缺价格"}</span>`; }).join("")}</div>
    ${r.warn.length?`<div>${r.warn.map(w=>`<span class="chip warn">${esc(w)}</span>`).join(" ")}</div>`:""}
  </div>`).join("");
  renderMix(R);
  renderDetail(R);
  // detail
  const D=detailRows(R);
  document.getElementById("resDetail").innerHTML=`<table><thead><tr>${D.head.map(h=>`<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${D.rows.map((row,ri)=>`<tr class="${D.first[ri]?"first":""}">${row.map((v,ci)=>typeof v==="number"?`<td class="n">${(D.fmt[ci]||String)(v)}</td>`:`<td>${D.chip[ci]?chip(v):esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
/* All visible channels in one list, in the same order everywhere on the page. */
const chanList=()=>[...amzOn().map(a=>({id:"amz:"+a.k,name:a.name,amz:a.k})),...platOn().map(pl=>({id:"plat:"+pl.k,name:pl.name+" 促销",plat:pl.k}))];
function chanVal(r,ch,si){ if(ch.amz) return {ok:r.price>0,rev:r.price,profit:r.sc[si][ch.amz]};
  const x=r.plat[ch.plat]; if(x.noPrice) return {ok:false,rev:NaN,profit:NaN}; const s=x.sc[si].promo; return {ok:true,rev:s.settle,profit:s.profit}; }
const DETAIL_OPTS=()=>[...AMZ.map(a=>[`amz:${a.k}`,a.name]),...PLATS.flatMap(pl=>[[`plat:${pl.k}:promo`,`${pl.name} · 促销价`],[`plat:${pl.k}:list`,`${pl.name} · 上架价`]])];
/* One channel's waterfall for one product: price → settlement → each deduction → profit. */
function breakdown(r,id,si){
  const [g,k,mode]=id.split(":"), sum=f=>r.pk.reduce((a,x)=>a+f(x),0), fuel=`燃油 ${P.fbm.fuel}%`;
  const fbmSteps=()=>[["尾程派送",sum(x=>x.tail)],["订单处理",sum(x=>x.handling)],["尾程异常",sum(x=>x.surch)],...(P.residential?[["住宅附加",sum(x=>x.resi)]]:[]),[fuel,sum(x=>x.fbmFuel)]];
  if(g==="amz"){
    const logi=k==="fbm"?fbmSteps():k==="cg"?[["CG 派送基础",sum(x=>x.cgShip)],["CG 每磅费",sum(x=>x.cgLb)],["CG 拣货费",sum(x=>x.cgPick)]]:[["FBA 配送费",r.fbaShip]];
    const steps=[["采购成本",r.cost],["海运费",r.sc[si].sea],...logi,["推广",r.promo],["汇损",r.fx],["佣金",r.comm],["退款",r.refund]];
    const profit=r.sc[si][k]; return {priceLabel:"售价",price:r.price,settle:r.price,steps,profit,margin:r.price?profit/r.price:NaN,edit:"amz"};
  }
  const x=r.plat[k], c=P.plat[k], m=mode==="list"?"list":"promo";
  if(x.noPrice) return null;
  const sc=x.sc[si], v=sc[m], st=v.settle;
  const logi=c.ship==="self"?fbmSteps():c.ship==="handling"?[["订单处理",sum(x=>x.handling)]]:[];
  const pctSteps=[["推广",c.ads],["汇损",c.fx],["佣金",c.comm],["退款",c.refund],["仓储费",c.storage],["出仓费",c.outbound]].filter(a=>nz(a[1])>0).map(a=>[`${a[0]} ${a[1]}%`,st*nz(a[1])/100]);
  const steps=[["采购成本",r.cost],["海运费",sc.sea],...logi,...(nz(c.fixed)>0?[["平台订单费",nz(c.fixed)]]:[]),...pctSteps];
  return {priceLabel:m==="list"?"上架价":"促销价",price:m==="list"?x.list:x.promo,settle:st,mk:x.mk,steps,profit:v.profit,margin:v.margin,edit:m,est:x.est&&!(m==="promo"?x.promoSet:x.listSet)};
}
function renderAll(R){
  const si=seaIdx(), A=amzOn(), L=platOn();
  document.getElementById("chanBar").innerHTML=`<label class="f" style="flex-direction:row;align-items:center;gap:6px">海运方案<select data-seaview="1">${P.sea.map((s,i)=>`<option value="${i}" ${i===si?"selected":""}>${esc(s.name)}</option>`).join("")}</select></label><span class="muted">显示：</span>`+
    AMZ.map(a=>`<label class="chk"><input type="checkbox" data-chan="amz:${a.k}" ${P.showAmz[a.k]!==false?"checked":""}>${esc(a.name)}</label>`).join("")+
    PLATS.map(pl=>`<label class="chk"><input type="checkbox" data-chan="plat:${pl.k}" ${P.plat[pl.k].on!==false?"checked":""}>${esc(pl.name)}</label>`).join("");
  if(!R.length){ document.getElementById("resAll").innerHTML=""; return; }
  if(!A.length&&!L.length){ document.getElementById("resAll").innerHTML=`<p class="muted" style="padding:12px">上面至少勾选一个渠道。</p>`; return; }
  const h1=A.map(a=>`<th class="grp" colspan="3">${esc(a.name)}</th>`).join("")+L.map(pl=>`<th class="grp" colspan="4">${esc(pl.name)}<br><span class="note">${esc(SHIP[P.plat[pl.k].ship]||"")}</span></th>`).join("");
  const h2=A.map(()=>`<th>售价 $</th><th>利润</th><th>利润率</th>`).join("")+L.map(()=>`<th>促销价 $</th><th>促销利润</th><th>促销利润率<br><span class="note">上架价利润率</span></th><th>保本 / 目标价</th>`).join("");
  const body=R.map(({p,r},pi)=>`<tr><td>${esc(p.name)}</td><td class="n">${f2(r.cost)}</td>`+
    A.map(a=>{ const v=r.sc[si][a.k]; return `<td class="n">${f2(r.price)}</td><td class="n ${cls(v)}">${money(v)}</td><td class="n ${cls(v)}">${pct(v/r.price)}</td>`; }).join("")+
    L.map(pl=>{ const x=r.plat[pl.k], s=x.sc[si];
      if(x.noPrice) return `<td colspan="4" class="muted">缺价格：先填 Amazon 售价或平台价</td>`;
      return `<td class="pc"><input type="number" step="any" data-pp="${pi}" data-plat="${pl.k}" value="${x.promoSet?esc(num(p.prices[pl.k].promo)):""}" placeholder="${f2(x.promo)}" aria-label="${esc(pl.name)} 促销价"> ${x.est&&!x.promoSet?'<span class="chip warn" title="上架价按 Amazon 售价 × 系数估算">估</span>':""}<br><span class="note">上架 $${f2(x.list)} · ${pct(x.disc)} off</span></td>
        <td class="n ${cls(s.promo.profit)}">${money(s.promo.profit)}</td>
        <td class="n ${cls(s.promo.profit)}"><b>${pct(s.promo.margin)}</b><br><span class="note">上架 ${pct(s.list.margin)}</span></td>
        <td class="n">${money(s.breakeven)}<br><span class="note">${esc(P.targetMargin)}%：${money(s.target)}</span></td>`; }).join("")+`</tr>`).join("");
  document.getElementById("resAll").innerHTML=`<table><thead><tr><th rowspan="2">品名</th><th rowspan="2">采购成本 $</th>${h1}</tr><tr>${h2}</tr></thead><tbody>${body}</tbody></table>`;
}
document.getElementById("chanBar").addEventListener("change",e=>{ const t=e.target;
  if(t.dataset.seaview){ P.seaView=+t.value; }
  else if(t.dataset.chan){ const [g,k]=t.dataset.chan.split(":"); if(g==="amz") P.showAmz[k]=t.checked; else P.plat[k].on=t.checked; }
  else return; save(); renderS4(); });
document.getElementById("resAll").addEventListener("change",e=>{ const t=e.target; if(t.dataset.pp===undefined) return; const p=products[+t.dataset.pp]; p.prices=p.prices||{};
  const o=p.prices[t.dataset.plat]=p.prices[t.dataset.plat]||{}; o.promo=t.value===""?"":num(t.value); save(); setTimeout(renderS4); });
function renderDetail(R){
  const si=seaIdx(), id=P.detailChan||"amz:fbm", B=R.map(({p,r})=>breakdown(r,id,si));
  const ref=B.find(b=>b); if(!ref){ document.getElementById("resSummary").innerHTML=`<p class="muted" style="padding:12px">缺价格：先填 Amazon 售价或平台价。</p>`; return; }
  const plat=id.startsWith("plat:"), labels=ref.steps.map(a=>a[0]);
  const head=`<tr><th rowspan="2">品名</th><th rowspan="2">${ref.priceLabel} $</th>${plat?`<th rowspan="2">结算价 $<br><span class="note">÷ ${esc(ref.mk)}</span></th>`:""}<th class="grp" colspan="${labels.length}">扣除项 $</th><th rowspan="2">利润 $</th><th rowspan="2">利润率</th></tr><tr>${labels.map(l=>`<th>${esc(l)}</th>`).join("")}</tr>`;
  const body=R.map(({p,r},pi)=>{ const b=B[pi]; if(!b) return `<tr><td>${esc(p.name)}</td><td colspan="${labels.length+(plat?5:4)}" class="muted">缺价格</td></tr>`;
    const [,k]=id.split(":"), pr=plat?((p.prices&&p.prices[k])||{}):null;
    const priceCell=plat?`<td class="pc"><input type="number" step="any" data-sp="${pi}" data-k="plat" data-plat="${k}" data-pk="${b.edit}" value="${esc(pr[b.edit]??"")}" placeholder="${f2(b.price)}"> ${b.est?'<span class="chip warn" title="按 Amazon 售价 × 系数估算">估</span>':""}</td>`
      :`<td><input type="number" step="any" data-sp="${pi}" data-k="price" value="${esc(p.price)}"></td>`;
    const cells=b.steps.map((a,i)=>i===0?`<td><input type="number" step="any" data-sp="${pi}" data-k="costUSD" value="${isFinite(r.cost)?Math.round(r.cost*100)/100:""}" title="${esc(COST_CUR[p.costCur])}${p.costCur!=="USD"?"，按当前汇率/税点反算出厂价":""}"></td>`:`<td class="n">${f2(a[1])}</td>`).join("");
    return `<tr><td>${esc(p.name)}</td>${priceCell}${plat?`<td class="n">${f2(b.settle)}</td>`:""}${cells}<td class="n ${cls(b.profit)}"><b>${money(b.profit)}</b></td><td class="n ${cls(b.profit)}">${pct(b.margin)}</td></tr>`; }).join("");
  document.getElementById("resSummary").innerHTML=`<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}
document.getElementById("detailChan").addEventListener("change",e=>{ P.detailChan=e.target.value; save(); renderS4(); });
function chip(v){ if(!v) return ""; const c=/LTL|OS-/.test(v)?"bad":/AHS|预警/.test(v)?"warn":/常规|小包裹/.test(v)?"ok":""; return `<span class="chip ${c}">${esc(v)}</span>`; }
function detailRows(R){
  const head=["品名","包裹","长cm","宽cm","高cm","毛重kg","第一长边in","第二长边in","第三长边in","体积m³","立方英寸","FBM体积重lb","FBM计费重lb","实重lb(取整)","围长in","尾程异常类型","最终计费重lb",
    ...P.sea.map(s=>"海运费$ "+s.name),"FBM尾程派送$","订单处理费$","尾程异常费$",...(P.residential?["住宅附加费$"]:[]),`FBM燃油附加费$ (${P.fbm.fuel}%)`,"FBM尾程合计$","CG配送类型","CG派送基础$","CG每磅费用$","CG拣货费$","LTL预警",
    "FBA最长边in","FBA次长边in","FBA最短边in","FBA发货重量lb","FBA长+围长in","FBA档位","FBA费用$"];
  const F=[null,null,f1,f1,f1,f1,f0,f0,f0,v=>v.toFixed(4),f0,f1,f0,f0,f0,null,f1,...P.sea.map(()=>f2),f2,f2,f2,...(P.residential?[f2]:[]),f2,f2,null,f2,f2,f2,null,f2,f2,f2,f2,f2,null,f2];
  const chipCols=head.map(h=>h==="尾程异常类型"||h==="LTL预警");
  const rows=[], first=[];
  R.forEach(({p,r})=>r.pk.forEach((x,gi)=>{ first.push(gi===0); rows.push([gi?"":p.name,gi+1,x.cm[0],x.cm[1],x.cm[2],x.kg,x.J,x.K,x.L,x.M,x.N,x.O,x.Pw,x.R,x.V,x.W,x.U,...x.sea,x.tail,x.handling,x.surch,...(P.residential?[x.resi]:[]),x.fbmFuel,x.fbmTotal,x.bucket,x.cgShip,x.cgLb,x.cgPick,x.ltl,x.fl,x.fm,x.fn,x.fw,x.flg,x.fbaTier,x.fba]); }));
  return {head,rows,first,fmt:F,chip:chipCols};
}
document.getElementById("resSummary").addEventListener("change",e=>{ const t=e.target; if(t.dataset.sp===undefined) return; const p=products[+t.dataset.sp]; const v=t.value===""?"":num(t.value);
  if(t.dataset.k==="plat"){ p.prices=p.prices||{}; const o=p.prices[t.dataset.plat]=p.prices[t.dataset.plat]||{}; o[t.dataset.pk]=v; }
  else if(t.dataset.k==="price") p.price=v;
  else { if(v===""){ p.cost=""; } else { const base=v-nz(p.adj); p.cost=Math.round((p.costCur==="RMB_TAX"? base*(1+P.tax/100)*P.rate : p.costCur==="RMB_NET"? base*P.rate : base)*10000)/10000; } }
  save(); setTimeout(renderS4); });
document.getElementById("resMix").addEventListener("change",e=>{ const t=e.target; if(t.dataset.qty===undefined) return; const v=num(t.value); products[+t.dataset.qty].qty=isFinite(v)&&v>=0?v:1; save(); setTimeout(renderS4); });
document.getElementById("btnQtyReset").addEventListener("click",()=>{ products.forEach(p=>p.qty=1); save(); renderS4(); });
const qtyOf=p=>{ const q=num(p.qty); return isFinite(q)&&q>=0?q:1; };
function mixData(R){
  const si=seaIdx(), CH=chanList(), tq=R.reduce((a,{p})=>a+qtyOf(p),0), cost=R.reduce((a,{p,r})=>a+qtyOf(p)*r.cost,0);
  const tot=CH.map(ch=>{ let profit=0,rev=0,ok=true; R.forEach(({p,r})=>{ const v=chanVal(r,ch,si); if(!v.ok){ ok=false; return; } profit+=qtyOf(p)*v.profit; rev+=qtyOf(p)*v.rev; }); return {ch,profit:ok?profit:NaN,rev:ok?rev:NaN}; });
  return {si,CH,tq,cost,tot};
}
function renderMix(R){
  const M=mixData(R);
  if(!M.CH.length){ document.getElementById("resMix").innerHTML=`<p class="muted" style="padding:12px">上面至少勾选一个渠道。</p>`; return; }
  const body=R.map(({p,r},pi)=>{ const q=qtyOf(p); return `<tr><td>${esc(p.name)}</td><td><input type="number" min="0" step="any" data-qty="${pi}" value="${q}"></td><td class="n">${M.tq?pct(q/M.tq):"–"}</td>${M.CH.map(ch=>{ const v=chanVal(r,ch,M.si); const x=v.ok?q*v.profit:NaN; return `<td class="n ${cls(x)}">${v.ok?money(x):"缺价格"}</td>`; }).join("")}</tr>`; }).join("");
  const foot=`<tr class="first"><td><b>合计利润</b></td><td class="n"><b>${f1(M.tq)}</b></td><td class="n">100%</td>${M.tot.map(t=>`<td class="n ${cls(t.profit)}"><b>${money(t.profit)}</b></td>`).join("")}</tr>
    <tr><td colspan="3" style="text-align:right">合计销售额 <span class="note">（平台为结算价）</span></td>${M.tot.map(t=>`<td class="n">${f2(t.rev)}</td>`).join("")}</tr>
    <tr><td colspan="3" style="text-align:right"><b>综合利润率</b></td>${M.tot.map(t=>`<td class="n ${cls(t.profit)}"><b>${t.rev?pct(t.profit/t.rev):"–"}</b></td>`).join("")}</tr>`;
  document.getElementById("resMix").innerHTML=`<table><thead><tr><th>品名</th><th>销量</th><th>销量占比</th>${M.CH.map(ch=>`<th>${esc(ch.name)}</th>`).join("")}</tr></thead><tbody>${body}${foot}</tbody></table>`;
}
document.getElementById("quickParams").addEventListener("change",e=>{ const t=e.target; if(!t.dataset.path) return; setPath(t.dataset.path,t.type==="number"?(t.value===""?"":num(t.value)):t.value); save(); renderS4(); });

/* ---------------- export ---------------- */
async function offer(filename,data,mime){
  if(dl){ try{ await dl.save({filename,data}); document.getElementById("exportMsg").textContent="已导出 "+filename; return; }catch(err){ if(err&&err.code==="declined") return; if(err&&!["unavailable","not_granted","capability_disabled","capability_removed"].includes(err.code)){ toast("导出失败："+(err.message||err.code)); return; } } }
  try{ const url=URL.createObjectURL(new Blob([data],{type:mime})); const a=document.createElement("a"); a.href=url; a.download=filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),4000); document.getElementById("exportMsg").textContent="已导出 "+filename; }
  catch(err){ toast("当前环境不支持下载文件"); }
}
function stamp(){ const d=new Date(); return d.getFullYear()+String(d.getMonth()+1).padStart(2,"0")+String(d.getDate()).padStart(2,"0"); }
document.getElementById("btnExport").addEventListener("click",()=>{
  const R=products.map(p=>({p,r:calcProduct(p)})); const wb=XLSX.utils.book_new(); const r2=v=>isFinite(v)?Math.round(v*100)/100:"";
  const sumHead=["品名","材质/描述","供应商","品类","FBM旺季","包裹数","售价$","出厂价","出厂价币种","税点","成本调整$","采购成本$","采购占比","推广$","汇损$","佣金$","退款$","FBM尾程合计$(含燃油)","CG尾程合计$","FBA费合计$"];
  P.sea.forEach(s=>sumHead.push(`[${s.name}]海运费$`,`[${s.name}]FBM利润$`,`[${s.name}]FBM利润率`,`[${s.name}]CG利润$`,`[${s.name}]CG利润率`,`[${s.name}]FBA利润$`,`[${s.name}]FBA利润率`));
  sumHead.push("提示");
  const sum=[sumHead,...R.map(({p,r})=>[p.name,p.desc,p.supplier,p.category,p.peak,p.pkgs.length,r2(r.price),nz(p.cost),COST_CUR[p.costCur],taxNote(p),nz(p.adj),r2(r.cost),r.price?Math.round(r.cost/r.price*1000)/1000:"",r2(r.promo),r2(r.fx),r2(r.comm),r2(r.refund),r2(r.fbmShip),r2(r.cgShip),r2(r.fbaShip),
    ...r.sc.flatMap(s=>[r2(s.sea),r2(s.fbm),r.price?Math.round(s.fbm/r.price*1000)/1000:"",r2(s.cg),r.price?Math.round(s.cg/r.price*1000)/1000:"",r2(s.fba),r.price?Math.round(s.fba/r.price*1000)/1000:""]),r.warn.join("；")])];
  const ws1=XLSX.utils.aoa_to_sheet(sum); ws1["!cols"]=sumHead.map((h,i)=>({wch:i<2?22:12}));
  const D=detailRows(R); const ws2=XLSX.utils.aoa_to_sheet([D.head,...D.rows.map(r=>r.map(v=>typeof v==="number"?Math.round(v*10000)/10000:v))]); ws2["!cols"]=D.head.map(()=>({wch:12}));
  const par=[["参数","值"],["汇率 RMB/USD",P.rate],["推广 %",P.promo],["汇损 %",P.fxLoss],["退款 %",P.refund],["采购税点 %（仅 RMB 含税价适用，FOB 不适用）",P.tax],["FBM住宅附加费",P.residential?"计入":"不计入"],["FBM尾程燃油附加费 %（尾程派送+订单处理+异常+住宅 合计后再加）",P.fbm.fuel],
    ["家具佣金阈值 $",P.commission.threshold],["家具 ≤阈值 %",P.commission.furnLow],["家具 >阈值部分 %",P.commission.furnHigh],["汽配 %",P.commission.汽配],["工业机械 %",P.commission.工业机械],["农机花园 %",P.commission.农机花园],["其他 %",P.commission.其他],
    ...P.sea.map(s=>[`海运方案：${s.name}`,`${s.rmb} RMB / ${s.cbm} CBM = $${f2(nz(s.rmb)/nz(s.cbm)/P.rate)}/m³`]),
    ["平台上架价系数（× Amazon 售价）",P.listFactor],["目标利润率 %",P.targetMargin],
    ...PLATS.flatMap(pl=>{ const c=P.plat[pl.k]; return [[`${pl.name}`,`${c.on!==false?"显示":"隐藏"}；${SHIP[c.ship]||c.ship}；加价倍率 ${c.markup}；默认促销折扣 ${c.disc}%；平台订单费 $${c.fixed}`],[`${pl.name} 比例费`,`推广 ${c.ads}% · 汇损 ${c.fx}% · 佣金 ${c.comm}% · 退款 ${c.refund}% · 仓储 ${c.storage}% · 出仓 ${c.outbound}%`]]; }),
    ["FBA 燃油/物流附加费 %",P.fba.fuel],["FBA 体积重除数",P.fba.dimDiv],["FBA 费率",fbaPeak()?"旺季":"非旺季"],["FBA 旺季区间",P.fba.peakStart+" ~ "+P.fba.peakEnd],["导出日期",new Date().toLocaleString()]];
  const ws3=XLSX.utils.aoa_to_sheet(par); ws3["!cols"]=[{wch:26},{wch:40}];
  const M=mixData(R), L=platOn(), A=amzOn(), si=seaIdx(), sn=P.sea[si].name, r3=v=>isFinite(v)?Math.round(v*1000)/1000:"";
  const mh=["品名","销量","销量占比",...M.CH.map(c=>`${c.name}利润$`)];
  const mix=[[`海运方案：${sn}（Amazon 按售价，平台按促销价）`],mh,...R.map(({p,r})=>{ const q=qtyOf(p); return [p.name,q,M.tq?r3(q/M.tq):"",...M.CH.map(c=>{ const v=chanVal(r,c,si); return v.ok?r2(q*v.profit):""; })]; }),
    ["合计利润",M.tq,1,...M.tot.map(t=>r2(t.profit))],["合计销售额","","",...M.tot.map(t=>r2(t.rev))],["综合利润率","","",...M.tot.map(t=>t.rev?r3(t.profit/t.rev):"")]];
  const ch=["品名","采购成本$",...A.flatMap(a=>[`${a.name}售价$`,`${a.name}利润$`,`${a.name}利润率`]),...L.flatMap(pl=>[`${pl.name}上架价$`,`${pl.name}促销价$`,`${pl.name}促销利润$`,`${pl.name}促销利润率`,`${pl.name}上架利润率`,`${pl.name}保本促销价$`,`${pl.name}目标促销价$(${P.targetMargin}%)`])];
  const all=[[`海运方案：${sn}`],ch,...R.map(({p,r})=>[p.name,r2(r.cost),...A.flatMap(a=>{ const v=r.sc[si][a.k]; return [r2(r.price),r2(v),r.price?r3(v/r.price):""]; }),
    ...L.flatMap(pl=>{ const x=r.plat[pl.k], s=x.sc[si]; return x.noPrice?["","","","","","",""]:[r2(x.list),r2(x.promo),r2(s.promo.profit),r3(s.promo.margin),r3(s.list.margin),r2(s.breakeven),r2(s.target)]; })])];
  const wsA=XLSX.utils.aoa_to_sheet(all); wsA["!cols"]=ch.map((h,i)=>({wch:i?13:22}));
  const ph=["品名","平台","海运方案","发货方","上架价$","促销价$","折扣","价格来源","加价倍率","促销结算价$","采购成本$","海运费$","物流费$","平台订单费$","促销比例费$","促销利润$","促销利润率","上架结算价$","上架利润$","上架利润率","保本促销价$",`目标促销价$(${P.targetMargin}%)`];
  const pd=[ph]; R.forEach(({p,r})=>PLATS.forEach(pl=>{ const x=r.plat[pl.k]; if(x.noPrice) return; P.sea.forEach((sea,i)=>{ const s=x.sc[i];
    pd.push([p.name,pl.name,sea.name,SHIP[P.plat[pl.k].ship]||"",r2(x.list),r2(x.promo),r3(x.disc),x.est&&!x.promoSet?"估算":"填写",x.mk,r2(s.promo.settle),r2(r.cost),r2(s.sea),r2(x.logi),r2(x.fixed),r2(s.promo.fees),r2(s.promo.profit),r3(s.promo.margin),r2(s.list.settle),r2(s.list.profit),r3(s.list.margin),r2(s.breakeven),r2(s.target)]); }); }));
  const wsP=XLSX.utils.aoa_to_sheet(pd); wsP["!cols"]=ph.map((h,i)=>({wch:i?12:22}));
  const ws0=XLSX.utils.aoa_to_sheet(mix); ws0["!cols"]=mh.map((h,i)=>({wch:i?16:22}));
  XLSX.utils.book_append_sheet(wb,wsA,"全渠道对比"); XLSX.utils.book_append_sheet(wb,ws0,"综合利润"); XLSX.utils.book_append_sheet(wb,ws1,"Amazon利润汇总"); XLSX.utils.book_append_sheet(wb,wsP,"多平台明细"); XLSX.utils.book_append_sheet(wb,ws2,"包裹明细"); XLSX.utils.book_append_sheet(wb,ws3,"参数");
  offer(`利润测算_${stamp()}.xlsx`,new Uint8Array(XLSX.write(wb,{bookType:"xlsx",type:"array"})),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
});
document.getElementById("btnSaveJson").addEventListener("click",()=>offer(`利润测算方案_${stamp()}.json`,JSON.stringify({version:1,params:P,products},null,1),"application/json"));

/* ---------------- boot ---------------- */
/* ---------------- history library ---------------- */
/* 【判定台改动 2/3】历史库存服务端（/tools/profit/plans），局域网内有权限的人看到同一份（AC-F24-02）。
   列表、改名、打开、用当前覆盖、导出 .json、删除的界面与原工具相同；只读和审批者只能看、打开、导出。 */
const hist={mode:"pending",items:[],col:null,slow:false,err:""};
const clone=o=>JSON.parse(JSON.stringify(o));
const fmtTime=ms=>{ const d=new Date(ms); return isNaN(d)?"–":d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")+" "+String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0")+":"+String(d.getSeconds()).padStart(2,"0"); };
function defaultName(){ const d=new Date(); return (products[0]?products[0].name+(products.length>1?` 等${products.length}款`:""):"利润测算")+" "+fmtTime(d).slice(5,16); }
function histChanged(){ document.getElementById("histCount").textContent=hist.items.length; if(step===5) renderS5(); }
const canEdit=()=>!(window.PDT&&PDT.readonly);
async function api(url,body){ const r=await fetch(url,{method:"POST",headers:{"content-type":"application/json",accept:"application/json"},body:body===undefined?undefined:JSON.stringify(body)}); const j=await r.json().catch(()=>({})); if(!r.ok) throw new Error(j.detail||("HTTP "+r.status)); return j; }
async function initHistory(){
  try{ const r=await fetch("/tools/profit/plans",{headers:{accept:"application/json"}}); hist.items=(await r.json()).items||[]; hist.mode="server"; }
  catch(e){ hist.mode="server"; hist.err="unavailable"; }
  histChanged();
}
function pdtExtra(){ return (window.PDT&&typeof PDT.extra==="function")?PDT.extra():{}; }
async function histSave(name){
  if(!canEdit()){ toast("当前账号只能查看"); return; }
  if(!products.length){ toast("没有产品可以保存"); return; }
  const rec=Object.assign({name:(name||"").trim()||defaultName(),products:clone(products),params:clone(P)},pdtExtra());
  try{ const it=await api("/tools/profit/plans",rec); hist.items.unshift(it); if(window.PDT) PDT.planId=it.id; histChanged(); toast("已保存到历史库："+it.name); if(window.PDT&&PDT.onSaved) PDT.onSaved(it); }
  catch(e){ toast("保存失败，请稍后再试："+e.message); }
}
async function histUpdate(id,patch){
  try{ const it=await api("/tools/profit/plans/"+id,patch); const i=hist.items.findIndex(x=>x.id===id); if(i>=0) hist.items[i]=it; histChanged(); if(window.PDT&&PDT.onSaved) PDT.onSaved(it); }
  catch(e){ toast("修改失败，请稍后再试："+e.message); }
}
async function histDelete(id){
  try{ await api("/tools/profit/plans/"+id+"/delete"); hist.items=hist.items.filter(x=>x.id!==id); histChanged(); toast("已删除"); }
  catch(e){ toast("删除失败，请稍后再试："+e.message); }
}
function histOpen(id){ const it=hist.items.find(x=>x.id===id); if(!it) return;
  products=clone(it.products||[]); P=Object.assign(defaultParams(),clone(it.params||{})); migrate(); save(); if(window.PDT){ PDT.planId=it.id; if(PDT.onOpened) PDT.onOpened(it); } toast("已打开："+it.name); go(4); }
function renderS5(){
  document.getElementById("histName2").placeholder=defaultName();
  document.getElementById("histMode").textContent="保存在系统上（wen 电脑），局域网内有权限的人看到同一份";
  document.getElementById("histMsg").innerHTML= hist.err?`<p class="msg">历史库暂时连不上，刷新页面后再试。</p>`:"";
  if(hist.mode==="pending"){ document.getElementById("histTable").innerHTML=`<p class="muted" style="padding:12px">正在连接历史库…</p>`; return; }
  if(!hist.items.length){ document.getElementById("histTable").innerHTML=`<p class="muted" style="padding:12px 16px">还没有保存过版本。在“利润测算表”或上面点“保存”，当前的产品和参数就会存成第一个版本。</p>`; return; }
  const ed=canEdit();
  document.getElementById("histTable").innerHTML=`<table><thead><tr><th>名称${ed?"（可改）":""}</th><th>保存时间</th><th>保存人</th><th>产品数</th><th>包含产品</th><th>关联决策卡</th><th>汇率</th><th>操作</th></tr></thead><tbody>${hist.items.map(it=>`<tr>
    <td>${ed?`<input class="wide" style="width:240px" data-hname="${esc(it.id)}" value="${esc(it.name)}">`:esc(it.name)}</td>
    <td class="n">${fmtTime(it.savedAtMs)}${it.renamedAtMs?`<br><span class="note">改名 ${fmtTime(it.renamedAtMs).slice(5,16)}</span>`:""}</td>
    <td class="c">${esc(it.by||"")}</td>
    <td class="c">${esc(it.count)}</td>
    <td style="max-width:320px;white-space:normal" class="note">${esc((it.names||[]).join("、"))}</td>
    <td class="note">${it.card_id?`<a href="/cards/${esc(it.card_id)}">${esc(it.card_name||("决策卡 "+it.card_id))}</a>`:"—"}</td>
    <td class="n">${esc(it.params&&it.params.rate)}</td>
    <td class="c" style="white-space:nowrap"><button class="btn sm" data-hact="open" data-id="${esc(it.id)}">打开</button>${ed?` <button class="btn sm" data-hact="overwrite" data-id="${esc(it.id)}">用当前覆盖</button>`:""} <button class="btn sm" data-hact="json" data-id="${esc(it.id)}">导出.json</button>${ed?` <button class="btn sm danger" data-hact="del" data-id="${esc(it.id)}">删除</button>`:""}</td>
  </tr>`).join("")}</tbody></table>`;
}
document.getElementById("btnHistSave").addEventListener("click",()=>{ const i=document.getElementById("histName"); histSave(i.value); i.value=""; });
document.getElementById("btnHistSave2").addEventListener("click",()=>{ const i=document.getElementById("histName2"); histSave(i.value); i.value=""; });
const ht=document.getElementById("histTable");
ht.addEventListener("change",e=>{ const t=e.target; if(t.dataset.hname===undefined) return; const v=t.value.trim(); const it=hist.items.find(x=>String(x.id)===t.dataset.hname); if(!it) return; if(!v){ t.value=it.name; return; } if(v!==it.name) histUpdate(it.id,{name:v}); });
ht.addEventListener("click",e=>{ const b=e.target.closest("[data-hact]"); if(!b) return; const id=+b.dataset.id, it=hist.items.find(x=>x.id===id); if(!it) return; const act=b.dataset.hact;
  const confirm2=(label)=>{ if(b.dataset.confirm==="1") return true; b.dataset.confirm="1"; const old=b.textContent; b.textContent=label; setTimeout(()=>{ if(b.isConnected){ b.dataset.confirm=""; b.textContent=old; } },3000); return false; };
  if(act==="open"){ if(confirm2("替换当前测算?")) histOpen(id); }
  if(act==="overwrite"){ if(confirm2("确认覆盖?")){ histUpdate(id,Object.assign({products:clone(products),params:clone(P)},pdtExtra(it))); toast("已覆盖："+it.name); } }
  if(act==="del"){ if(confirm2("确认删除?")) histDelete(id); }
  if(act==="json") offer(`${it.name.replace(/[\\/:*?"<>|]/g,"_")}.json`,JSON.stringify({version:1,name:it.name,savedAt:it.savedAt,params:it.params,products:it.products},null,1),"application/json");
});
initHistory();

// fill keys added in newer versions
function migrate(){ const d=defaultParams(); for(const k in d) if(P[k]===undefined) P[k]=d[k]; for(const k in d.fba) if(P.fba[k]===undefined) P.fba[k]=d.fba[k]; for(const k in d.commission) if(P.commission[k]===undefined) P.commission[k]=d.commission[k]; for(const k in d.fbm) if(P.fbm[k]===undefined) P.fbm[k]=d.fbm[k];
  for(const k in d.showAmz) if(P.showAmz[k]===undefined) P.showAmz[k]=d.showAmz[k];
  for(const k in d.bulk) if(P.bulk[k]===undefined) P.bulk[k]=d.bulk[k];
  for(const k in d.plat){ if(!P.plat[k]) P.plat[k]=d.plat[k]; else for(const f in d.plat[k]) if(P.plat[k][f]===undefined) P.plat[k][f]=d.plat[k][f]; }
  if(!(nz(P.seaView)>=0&&nz(P.seaView)<P.sea.length)) P.seaView=0;
  products.forEach(p=>{ if(!p.prices||typeof p.prices!=="object") p.prices={}; }); }
migrate();
/* 【判定台改动 3/3】起始步骤：服务端指定（从决策卡进入、打开方案）优先，否则沿用本浏览器上次的步骤。 */
let st=4; try{ st=+(localStorage.getItem("pc_step")||4)||4; if(st<1||st>5) st=4; }catch(e){}
if(window.PDT && PDT.step) st=PDT.step;
go(st);
