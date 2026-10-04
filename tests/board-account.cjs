// Real agent runtime: identity must be resolved before any planner or board request.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('dartabend/static/turnier-board.user.js','utf8');
const boards={blau:'faa2cd5f-5d19-4e68-9749-1b7b95c753d4',rot:'ad381dc0-7e86-45a1-9fa8-61c8b18ec89b',schwarz:'6e390006-cdba-4ac5-b0bb-0e03eb880af6'};
async function check(name,expected,id='host') {
  let tick,intervals=0;const calls=[];
  class XHR{open(){}setRequestHeader(){}}
  const context={URL,Headers,WeakMap,Map,crypto:{randomUUID:()=> 'identity-test-instance'},location:{href:'https://play.autodarts.com/'},atob:x=>Buffer.from(x,'base64').toString(),
    unsafeWindow:{XMLHttpRequest:XHR,fetch:async()=>({})},document:{readyState:'loading',addEventListener:()=>{}},
    GM_getValue:(k,d)=>d,GM_setValue:()=>{},GM_registerMenuCommand:()=>{},setInterval:fn=>{tick=fn;intervals++;},
    GM_xmlhttpRequest:r=>{calls.push(r);const path=new URL(r.url).pathname;let result;
      if(path==='/us/v0/users/host')result={id,name};
      else if(path==='/bs/v0/boards/'+expected)result={id:expected,matchId:null};
      else if(path==='/api/bridge/poll'){assert.equal(r.headers['X-Board-ID'],expected);result={job:null};}
      else throw Error('Unexpected request: '+path);
      r.onload({status:200,responseText:JSON.stringify(result)});
    }};
  vm.runInNewContext(source,context);vm.runInNewContext(source,context);assert.equal(intervals,1);
  await tick();assert.equal(calls.length,0,'No requests before login');
  function login(sub){const xhr=new XHR();xhr.open('GET','https://api.autodarts.com/fixture');xhr.setRequestHeader('Authorization','Bearer h.'+Buffer.from(JSON.stringify({sub})).toString('base64url')+'.s');}
  login('host');await tick();
  if(!expected){assert.equal(calls.length,1);assert(calls[0].url.includes('/us/v0/users/'));return;}
  assert.equal(calls.length,3);assert(calls[1].url.endsWith('/bs/v0/boards/'+expected));
  // Token refresh of the same account keeps operating, but switching accounts stops all requests.
  login('host');await tick();const count=calls.length;assert.equal(count,5);
  login('different-host');await tick();assert.equal(calls.length,count);
  login('host');await tick();assert.equal(calls.length,count,'Reload required after account switch');
}
(async()=>{for(const [name,id] of Object.entries(boards))await check(' '+name.toUpperCase()+' ',id);await check('Alice',null);await check('rot',null,'wrong-profile-id');console.log('All board accounts, unknown accounts, profile mismatch, duplicate agent and account switching passed');})().catch(e=>{console.error(e);process.exit(1);});
