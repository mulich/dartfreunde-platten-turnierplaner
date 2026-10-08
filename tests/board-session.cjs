const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('dartabend/static/turnier-blau.user.js','utf8');
const board='faa2cd5f-5d19-4e68-9749-1b7b95c753d4',api='https://api.autodarts.com';
const token=label=>'h.'+Buffer.from(JSON.stringify({sub:'host',label})).toString('base64url')+'.s';
(async()=>{
 let tick,deferred,defer=false;const calls=[];
 class XHR {open(){}setRequestHeader(){}}
 const context={URL,Headers,WeakMap,Map,crypto:{randomUUID:()=> 'session-fixture-instance'},location:{href:'https://play.autodarts.com/'},atob:x=>Buffer.from(x,'base64').toString(),
  unsafeWindow:{XMLHttpRequest:XHR,fetch:async()=>({ok:true,clone:()=>({json:async()=>({access_token:token('renewed')})})})},
  document:{readyState:'loading',addEventListener(){}},GM_getValue:(k,d)=>d,GM_setValue(){},GM_registerMenuCommand(){},setInterval:fn=>{tick=fn;},
  GM_xmlhttpRequest:r=>{calls.push(r);const path=new URL(r.url).pathname;
   if(path==='/bs/v0/boards/'+board){if(defer){deferred=r;return;}r.onload({status:200,responseText:JSON.stringify({id:board,matchId:null})});}
   else if(path==='/api/bridge/poll'){assert.equal(r.headers['X-Board-ID'],board);assert(!JSON.stringify(r).includes(token('renewed')));r.onload({status:200,responseText:'{"job":null}'});}
   else throw Error('Fixed board must not look up account names: '+path);
  }};
 vm.runInNewContext(source,context);
 await tick();assert.equal(calls.length,0);
 // No outgoing Authorization is required to learn the renewed token.
 await context.unsafeWindow.fetch(api+'/auth/v1/refresh');await new Promise(resolve=>setImmediate(resolve));await tick();
 assert.equal(calls[0].headers.Authorization,'Bearer '+token('renewed'));
 function capture(value){const xhr=new XHR();xhr.open('GET',api+'/fixture');xhr.setRequestHeader('Authorization',value);}
 capture('Bearer '+token('old'));defer=true;const waiting=tick();await Promise.resolve();assert(deferred);
 capture('Bearer '+token('newer'));deferred.onload({status:401,responseText:'{"detail":"Expired"}'});await waiting;
 defer=false;await tick();assert.equal(calls.at(-2).headers.Authorization,'Bearer '+token('newer'),'Delayed 401 must not clear the renewed token');
 capture('Bearer malformed');await tick();assert.equal(calls.at(-2).headers.Authorization,'Bearer '+token('newer'),'Malformed header must not lock the account');
 console.log('Fixed board without account lookup, refresh response capture and delayed-401 recovery passed');
})().catch(e=>{console.error(e);process.exit(1);});
