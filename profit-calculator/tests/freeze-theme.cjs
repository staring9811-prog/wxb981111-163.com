const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'..','index.html'),'utf8');
for(const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
const source=html.slice(html.indexOf('function freezeTableKeys('),html.indexOf('function positionFrozenHeaders('));
const ctx={};vm.createContext(ctx);vm.runInContext(source,ctx);
const cell=(rowSpan=1,colSpan=1,width=120)=>({rowSpan,colSpan,style:{},classList:{values:[],add(x){this.values.push(x)}},getBoundingClientRect:()=>({width})});
const h=cell(),name=cell(2),pkg=cell(),continuation=cell(),nextName=cell();
ctx.freezeTableKeys({rows:[{cells:[h,cell()]},{cells:[name,pkg]},{cells:[continuation]},{cells:[nextName,cell()]}]},1);
assert(name.classList.values.includes('fz'));assert(!continuation.classList.values.includes('fz'));assert(nextName.classList.values.includes('fz'));
const a=cell(2),b=cell(2),sub=cell();ctx.freezeTableKeys({rows:[{cells:[a,b,cell(1,3)]},{cells:[sub]}]},2);
assert.equal(b.style.left,'120px');assert(!sub.classList.values.includes('fz'));
const init=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
for(const [saved,want] of [[null,'light'],['dark','dark'],['light','light']]){
 const document={documentElement:{dataset:{}}};vm.runInNewContext(init,{document,localStorage:{getItem:()=>saved}});assert.equal(document.documentElement.dataset.theme,want);
}
assert(html.includes('id="btnTheme"'));assert(html.includes('window.addEventListener("scroll",scheduleFrozenTables'));
console.log('PASS: scripts compile; merged product rows freeze only product names; two-row headers keep correct column offsets; default light and remembered theme work.');
