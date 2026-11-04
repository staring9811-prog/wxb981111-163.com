const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'..','index.html'),'utf8');
for(const m of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
const start=html.indexOf('const PC_RELEASE='),end=html.indexOf('document.getElementById("btnCheckUpdate").addEventListener',start);
const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:false,disabled:false,checked:true});return nodes.get(id)};
const data=new Map([['pc_products','[]'],['pc_params','{"rate":7}'],['pc_ai_cfg','{"key":"test-local-token","model":"local-model"}'],['unrelated','keep']]);
let failKey=null,offers=[],requests=[];
const ctx={products:[{id:'p1',name:'test',pkgs:[{l:10,w:20,h:30,kg:5}]}],P:{rate:7},qlib:{mode:'local',items:[{factory:'test',items:[]}]},hist:{mode:'local',items:[]},
 localStorage:{getItem:k=>data.has(k)?data.get(k):null,setItem:(k,v)=>{if(k===failKey){failKey=null;throw Error('quota')}data.set(k,String(v));},removeItem:k=>data.delete(k)},
 document:{getElementById:node},window:{confirm:()=>true},offer:async(...args)=>offers.push(args),stamp:()=>"test",Date,AbortController,setTimeout,clearTimeout,
 DOMParser:class{parseFromString(text){return {querySelector:q=>q.includes('pc-app-version')?{content:text.includes('older')?'1.0.0':'1.2.0'}:q.includes('pc-data-schema')?{content:'1'}:{}}}},
 fetch:async(...args)=>{requests.push(args);return {ok:true,text:async()=>'<html>new-system-only</html>'};}}
vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);const run=s=>vm.runInContext(s,ctx);
(async()=>{
 assert.equal(run('compareAppVersions("1.10.0","1.2.0")'),1);
 const before=new Map(data);const backup=run('makeFullBackup(true)');
 assert.equal(JSON.parse(backup.data.pc_ai_cfg).key,'test-local-token');
 assert(!JSON.parse(run('makeFullBackup(false)').data.pc_ai_cfg).key);
 // Invalid/new schema and unknown keys cannot change local state.
 for(const bad of [{...backup,schema:2},{...backup,data:{...backup.data,unexpected:'x'}},{...backup,data:{pc_ai_cfg:'{}'}}]){
  assert.throws(()=>ctx.restoreLocalData(bad));assert.deepEqual(data,before);
 }
 // Restoring a backup without credentials retains destination credentials.
 ctx.restoreLocalData(run('makeFullBackup(false)'));assert.equal(JSON.parse(data.get('pc_ai_cfg')).key,'test-local-token');assert.equal(data.get('unrelated'),'keep');
 // A write failure after a previous successful write rolls back all touched data.
 const baseline=new Map(data),changed=JSON.parse(JSON.stringify(backup));changed.data.pc_products='[{"name":"changed"}]';changed.data.pc_params='{"rate":8}';
 failKey='pc_params';assert.throws(()=>ctx.restoreLocalData(changed),/已恢复原数据/);assert.deepEqual(data,baseline);
 // Version checking never mutates product data or sends credentials/state.
 await ctx.checkSystemUpdate(true);assert.equal(requests.length,1);assert.equal(requests[0][1].credentials,'omit');assert(!requests[0][1].body);assert(!requests[0][1].headers);
 assert.equal(data.get('pc_ai_cfg'),baseline.get('pc_ai_cfg'));
 // Download is gated on a fresh complete backup and explicit confirmation.
 await ctx.downloadSystemUpdate();assert.equal(offers.length,0);
 await ctx.exportFullBackup();assert.equal(offers.length,1);
 await ctx.downloadSystemUpdate();assert.equal(offers.length,2);assert.equal(offers[1][0],'index.html');assert(!offers[1][1].includes('test-local-token'));
 assert(data.has('pc_update_snapshot'));assert.equal(data.get('unrelated'),'keep');
 console.log('PASS: version ordering; full credential backup; optional key retention; invalid-backup rejection; quota rollback; update request excludes private state; fresh-backup gate; system-only download.');
})().catch(e=>{console.error(e);process.exit(1)});
