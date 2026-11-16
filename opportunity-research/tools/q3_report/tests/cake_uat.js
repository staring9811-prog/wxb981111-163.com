// 蛋糕下钻 A 类验收（见 蛋糕下钻_验收标准.md）。用法：node cake_uat.js <报告或 demo 的 HTML 路径>
// Playwright 的 CSS 选择器会穿透 open shadow root，所以 demo 和嵌在报告里的版本用同一套选择器。
const {chromium}=require('playwright');
const path=require('path');
const file=process.argv[2];
if(!file){console.error('用法：node cake_uat.js <html>');process.exit(2)}
(async()=>{
  const b=await chromium.launch();const p=await b.newPage({viewport:{width:1440,height:900}});
  const errs=[];p.on('pageerror',e=>errs.push(String(e)));
  await p.goto('file://'+path.resolve(file));await p.evaluate(()=>localStorage.clear());await p.reload();await p.waitForTimeout(1500);
  if(await p.$('nav a[href="#s2c"]')){await p.click('nav a[href="#s2c"]');await p.waitForTimeout(600)}
  const R=[];const ok=(k,c,why)=>R.push([k,!!c,why||'']);
  const txt=s=>p.$eval(s,e=>e.textContent);
  const rows=()=>p.$$eval('#tbl tr.row',x=>x.map(r=>({v:r.dataset.v,c:[...r.cells].map(c=>c.textContent)})));
  const head=()=>p.$$eval('#tbl tr:first-child th',x=>x.map(e=>e.textContent));
  // 第一层
  let h=await head(),r=await rows(),t=await txt('#tth'),sub=await txt('#tsub');
  const iBen=h.indexOf('占本层'),iAll=h.indexOf('占全部');
  ok('G1 标题写路径和占全部',/全部/.test(t)&&/按「元素」分/.test(t)&&/占全部/.test(sub),t+' | '+sub.slice(0,40));
  ok('G2 两列且第一层相等',iBen>0&&iAll>0&&r.every(x=>x.c[iBen]===x.c[iAll]),'');
  const big1=r.filter(x=>/大蛋糕/.test(x.c[0])).map(x=>x.v),small1=r.filter(x=>/小蛋糕/.test(x.c[0]));
  const real1=r.filter(x=>x.v!=='未标').map(x=>[x.v,+x.c[1].replace(/,/g,'')]).filter(x=>x[1]>0).sort((a,b)=>b[1]-a[1]);let cum=0;const T1=real1.reduce((s,x)=>s+x[1],0),exp1=[];for(const x of real1){exp1.push(x[0]);cum+=x[1];if(cum>=T1*0.5)break}
  ok('G3 第一层只标大蛋糕，且是从大到小合计一半销量的那几块',big1.slice().sort().join()===exp1.slice().sort().join()&&!small1.length,big1.join('、')+' | 应为 '+exp1.join('、'));
  const iT=h.findIndex(x=>/^涨跌/.test(x));ok('B1 第一层能看到涨跌列，且写明比较期',iT>0&&/对比|vs/.test(h[iT])&&r.some(x=>/[+-]\d+%/.test(x.c[iT])),h[iT]);
  ok('B3 有「这一层看点」结论卡',/大蛋糕/.test(await txt('#insight'))&&/一句话/.test(await txt('#insight'))&&/我们/.test(await txt('#insight')),'');
  ok('G6 未标显示为未识别且不标大蛋糕',r.filter(x=>x.v==='未标').every(x=>/未识别/.test(x.c[0])&&!/大蛋糕|主战场/.test(x.c[0])),'');
  const ins1=await txt('#insight');
  ok('B2 看点卡写明主力块覆盖（这 N 块大蛋糕进了 M 块）',/\d+ 块，进了 \d+ 块/.test(ins1),ins1.slice(0,80));
  ok('G3 大蛋糕图例写明比较口径（本渠道 + 维度）',/本渠道所有「元素」组合/.test(await txt('#insight')+await p.$eval('body',e=>e.textContent))||await p.$$eval('*',x=>x.some(e=>e.shadowRoot&&/本渠道所有「元素」组合/.test(e.shadowRoot.textContent))),'');
  ok('G6 不再出现「全市场」字样',!(await p.$$eval('*',x=>x.some(e=>e.shadowRoot&&/全市场/.test(e.shadowRoot.textContent.replace(/不是全市场/g,'')))))&&!/全市场/.test((await p.$eval('#tbl',e=>e.closest('section,div').textContent)).replace(/不是全市场/g,'')),'');
  ok('P1 热力图或看点卡给出具体机会格子',/机会.*(×|›|\(|（)/.test(ins1)||await p.$$eval('table.hm .oo',x=>x.length)>0,'');
  ok('O2 有「在跌 / 太小 / 布局偏重」的调整提示',/在跌|太小|布局偏重|没有「我们有产品/.test(ins1),'');
  ok('B2 第一层能看到我们的 SPU 数，含未布局的大蛋糕判断',r.every(x=>/SPU|未布局|不参与判断/.test(x.c[h.indexOf('我们')])),'');
  // 第二、三层
  await p.click('#tbl tr.row');await p.waitForTimeout(450);
  await p.click('#tbl tr.row');await p.waitForTimeout(450);
  h=await head();r=await rows();t=await txt('#tth');
  const iB=h.indexOf('占本层');
  ok('G1 第三层标题带两级路径',(t.match(/›/g)||[]).length===1&&/按「尺寸」分/.test(t),t);
  ok('G3 小蛋糕 = 占本层 ≥ 20% 且占全部 ≥ 0.3%',r.filter(x=>x.v!=='未标').every(x=>/小蛋糕|主战场/.test(x.c[0])===(parseFloat(x.c[iB])>=20&&parseFloat(x.c[h.indexOf('占全部')])>=0.3)),'');
  ok('G3 标签有悬停说明',await p.$$eval('#tbl .cks',x=>x.every(e=>/主战场|大蛋糕|细分龙头|缺标签/.test(e.title)||e.querySelectorAll('i[title]').length)),'');
  // 价格段 + 更多指标
  await p.click('#btog');await p.waitForTimeout(250);
  ok('P2 展开价格段',await p.$$eval('#tbl tr.band',x=>x.length)>0,'');
  await p.click('#mxbtn');for(const k of ['top3','low','revper'])await p.click('#mxpop input[data-mx="'+k+'"]');
  await p.keyboard.press('Escape');await p.waitForTimeout(200);h=await head();
  ok('P2 高级指标列',['头部集中度','低分占比','评价门槛','我们售价 / 价差'].every(x=>h.includes(x)),h.join('|'));
  // 竞品清单
  await p.click('#tbl tr.row');await p.waitForTimeout(500);
  ok('P3 竞品清单（图、标题链接、价格、评分、月销）',await p.$$eval('#drawer.on #db tr',x=>x.length)>1&&await p.$$eval('#drawer #db a[href]',x=>x.length)>0,'');
  await p.keyboard.press('Escape');await p.waitForTimeout(300);
  // 退出方式
  const depth=async()=>(await txt('#crumbs')).split('›').length-1;
  const d0=await depth();await p.keyboard.press('Escape');await p.waitForTimeout(450);
  ok('G4 Esc 返回上一层',await depth()===d0-1,'');
  await p.click('#back');await p.waitForTimeout(450);ok('G4 返回按钮',await depth()===d0-2,'');
  await p.click('#donut path');await p.waitForTimeout(450);await p.click('#center');await p.waitForTimeout(450);ok('G4 饼图进入、点中心返回',await depth()===d0-2,'');
  // 运营：悬浮式 reeded
  await p.click('#tbl tr.row[data-v="竖棱"]');await p.waitForTimeout(450);await p.click('#tbl tr.row[data-v="悬浮式"]');await p.waitForTimeout(450);
  r=await rows();h=await head();
  const ig=h.indexOf('我们售价 / 价差');
  ok('O1 悬浮式竖棱各尺寸有我们价差',['24″','30″','36″','48″'].every(s=>{const x=r.find(y=>y.v===s);return x&&/%/.test(x.c[ig])}),'');
  // 产品管理：改价后我们价差变化
  const before=r.find(y=>y.v==='24″').c[ig];
  await p.click('[data-pmopen]');await p.waitForTimeout(300);
  const idx=await p.$$eval('#pm-body input.pmi[data-pf="name"]',x=>x.findIndex(e=>/24悬浮式reeded/.test(e.value)));
  await p.fill('#pm-body input.pmi[data-pf="price"][data-i="'+idx+'"]','400');await p.click('[data-pm="save"]');await p.waitForTimeout(300);
  await p.keyboard.press('Escape');await p.waitForTimeout(300);
  r=await rows();const after=r.find(y=>y.v==='24″').c[ig];
  ok('O3 改价后我们价差立即更新',idx>=0&&before!==after,before+' → '+after);
  // 运营：点我们的产品标签跳到它所在格子
  const tg=await p.$('[data-ourk]');
  if(tg){await tg.click();await p.waitForTimeout(500)}
  ok('O1 点我们的产品标签能跳到它所在格子并展开价格段',!!tg&&await depth()>=1&&await p.$$eval('#tbl tr.band',x=>x.length)>0,'');
  ok('P2 价格段区间不重叠（$a–b / $b 以上）',await p.$$eval('#tbl tr.band',x=>x.every(r=>!/\$(\d+)–\1\b/.test(r.textContent))),'');
  ok('无脚本报错',!errs.length,errs.join(' | ').slice(0,300));
  R.forEach(x=>console.log((x[1]?'PASS ':'FAIL ')+x[0]+(x[2]?'　'+x[2]:'')));
  console.log('通过 '+R.filter(x=>x[1]).length+'/'+R.length);
  await b.close();process.exit(R.every(x=>x[1])?0:1);
})();
