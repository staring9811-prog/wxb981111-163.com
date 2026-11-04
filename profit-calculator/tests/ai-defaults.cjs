const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'..','index.html'),'utf8');
let saved=null,request;const ctx={localStorage:{getItem:()=>saved},AI_MODEL:'unused-anthropic-fallback',sampleFn:null,parseLoose:JSON.parse,fetch:async(url,options)=>{request={url,options};return {ok:true,json:async()=>({choices:[{message:{content:'{"items":[]}'},finish_reason:'stop'}]})}}};
vm.createContext(ctx);
vm.runInContext(html.slice(html.indexOf('const AI_DEFAULTS='),html.indexOf('const aiKey=')),ctx);
vm.runInContext(html.slice(html.indexOf('function aiChannel()'),html.indexOf('function aiModeText()')),ctx);
vm.runInContext(html.slice(html.indexOf('async function aiCall('),html.indexOf('function normItems(')),ctx);
(async()=>{
 assert.equal(vm.runInContext("aiCfg()",ctx).prov,'openai');assert.equal(vm.runInContext("aiCfg()",ctx).base,'https://api.deepseek.com');assert.equal(vm.runInContext("aiCfg()",ctx).model,'deepseek-flash');
 const existing={prov:'anthropic',base:'https://existing.example',model:'existing-model',key:'test-local-token'};saved=JSON.stringify(existing);assert.equal(JSON.stringify(vm.runInContext("aiCfg()",ctx)),JSON.stringify(existing));
 saved=JSON.stringify({prov:'openai',base:'https://api.deepseek.com',model:'deepseek-flash',key:'test-local-token'});
 await ctx.aiCall('test quote');assert.equal(request.url,'https://api.deepseek.com/chat/completions');const body=JSON.parse(request.options.body);assert.equal(body.model,'deepseek-flash');assert.equal(request.options.headers.authorization,'Bearer test-local-token');
 assert(!html.includes('test-local-token'));assert(html.includes('button.title=dark?"切换浅色界面":"切换深色界面"'));
 console.log('PASS: OpenAI/DeepSeek/Flash defaults; existing provider/model/key preserved; official endpoint/model/request format; icon accessibility; no test token in deliverable.');
})().catch(e=>{console.error(e);process.exit(1)});
