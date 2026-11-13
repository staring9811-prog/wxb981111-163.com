const { chromium } = require('playwright'); const fs=require('fs');
(async()=>{
 const scen=JSON.parse(fs.readFileSync('scen.json','utf8'));
 const b=await chromium.launch(); const p=await b.newPage();
 p.on('pageerror',e=>console.error('PAGEERR',e.message));
 await p.goto('file://'+process.argv[2]); await p.waitForTimeout(1500);
 const out=await p.evaluate((scen)=>{
  P=defaultParams(); migrate&&migrate();
  const res=[];
  for(const s of scen.skus){ for(const t of ['low','mid','high']){
    const tp=s.tiers[t]; const prices={};
    const map={lowesVC:'lw',lowesSC:'lw',hd:'hd',wf:'wf'};
    for(const k in map){ const v=tp[map[k]]; if(v) prices[k]={promo:v}; }
    const prod={id:s.id+t,name:s.name,desc:'',category:'其他',peak:'非旺季',price:tp.amz,cost:s.cost,costCur:s.costCur,adj:0,pack:s.pack,prices,pkgs:s.pkgs.map(g=>({l:g[0],w:g[1],h:g[2],kg:g[3]}))};
    const r=calcProduct(prod); const sc=r.sc[0];
    const row={sku:s.id,tier:t,amzPrice:tp.amz,cost:r.cost,sea:sc.sea,fees:r.fees,comm:r.comm,promo:r.promo,refund:r.refund,fx:r.fx,
      fbmShip:r.fbmShip,fbaShip:r.fbaShip,ltl:r.ltl.on,ltlCost:r.ltl.cost,fbm:sc.fbm,fba:sc.fba,warn:r.warn,
      fbaTier:r.pk.map(x=>x.fbaTier), seaAlt:r.sc[1].sea, plat:{}};
    for(const k in r.plat){ const pl=r.plat[k], x=pl.sc[0]; row.plat[k]={retail:x.promo.retail,settle:x.promo.settle,base:x.base,logi:pl.logi,fixed:pl.fixed,fees:x.promo.fees,profit:x.promo.profit,margin:x.promo.margin,priced:!!(prices[k]),breakeven:x.breakeven,target:x.target,mk:pl.mk,pct:pl.pct}; }
    res.push(row);
  }}
  return {res,params:{rate:P.rate,promo:P.promo,fx:P.fxLoss,refund:P.refund,tax:P.tax,comm:P.commission['其他'],sea:P.sea,ltl:P.ltl,fbmFuel:P.fbm.fuel,plat:P.plat,target:P.targetMargin,peak:fbaPeak()}};
 },scen);
 fs.writeFileSync('calc_out.json',JSON.stringify(out,null,1)); await b.close();
 for(const r of out.res){ console.log(r.sku,r.tier,'amz$',r.amzPrice,'cost',r.cost.toFixed(0),'sea',r.sea.toFixed(0),'FBM',r.fbm.toFixed(0),(r.fbm/r.amzPrice*100).toFixed(0)+'%','FBA',r.fba.toFixed(0),'| '+Object.entries(r.plat).map(([k,v])=>k+':'+(v.priced?(v.retail.toFixed(0)+'→'+v.profit.toFixed(0)+'/'+(v.margin*100).toFixed(0)+'%'):'-')).join(' '), r.warn.join(';')); }
})();
