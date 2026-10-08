const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('dartabend/static/turnier-blau.user.js','utf8');
const board='faa2cd5f-5d19-4e68-9749-1b7b95c753d4';
async function run({foreign=false,busy=false,lost=false}={}) {
  let tick,clock=100,lobby=true,portalAttempts=0;
  let job={id:'old-job',phase:'restarting',lobby_id:'old-lobby',restart_id:'operation',restart_step:'delete',restart_after:0,user_ids:['alice','local:bob']};
  const calls=[],storage=new Map();
  const token='header.'+Buffer.from(JSON.stringify({sub:'host'})).toString('base64url')+'.signature';
  class XHR {open(){}setRequestHeader(){}}
  class Clock extends Date {static now(){return clock*1000;}}
  function route(r) {
    const url=new URL(r.url),body=r.data?JSON.parse(r.data):{};calls.push([url.origin,url.pathname,r.method]);
    if(url.origin==='https://turnier.mulich.de') {
      assert(!JSON.stringify(r).includes(token));
      if(url.pathname==='/api/bridge/poll')return {job:{...job,restart_ready:clock>=job.restart_after}};
      if(url.pathname.endsWith('/state'))return {job};
      if(url.pathname.endsWith('/restart')) {
        assert.equal(body.restart_id,'operation');
        if(body.step==='deleted')job={...job,restart_step:'accounts',restart_after:clock+2};
        else if(body.step==='accounts')job={...job,restart_step:'wait',restart_after:clock+3};
        else {assert.equal(body.step,'complete');job={id:'new-job',phase:'queued'};}
        return {job:{...job,restart_ready:clock>=job.restart_after}};
      }
    }
    if(url.origin==='https://dartportal.mulich.de') {
      assert.equal(r.headers.Origin,'https://dartportal.mulich.de');
      assert.equal(r.anonymous,false);assert.equal(r.headers.Authorization,undefined);assert(!JSON.stringify(r).includes(token));
      assert.deepEqual(body.user_ids,['alice']);assert.equal(body.lobby_id,'old-lobby');
      portalAttempts++;
      if(lost&&portalAttempts===1)throw new Error('Network');
      return {recovered:['alice'],operation_id:'operation'};
    }
    assert.equal(url.origin,'https://api.autodarts.com');
    if(url.pathname.startsWith('/bs/'))return {id:board,matchId:busy?'unrelated-match':null};
    if(url.pathname==='/gs/v0/lobbies/old-lobby') {
      if(r.method==='DELETE'){lobby=false;return {};}
      return lobby?{id:'old-lobby',host:{id:foreign?'foreign':'host'},players:[]}:{_http:404};
    }
    throw new Error('Unknown route '+r.url);
  }
  const location={href:'https://play.autodarts.com/'};
  const context={Date:Clock,URL,Headers,crypto:{randomUUID:()=> 'instance-browser-fixture'},location,
    atob:s=>Buffer.from(s,'base64').toString(),unsafeWindow:{XMLHttpRequest:XHR,fetch:async()=>({}),location},
    document:{readyState:'loading',addEventListener:()=>{}},GM_getValue:(k,d)=>storage.has(k)?structuredClone(storage.get(k)):d,
    GM_setValue:(k,v)=>storage.set(k,structuredClone(v)),GM_registerMenuCommand:()=>{},setInterval:fn=>{tick=fn;},
    GM_xmlhttpRequest:r=>{try{const result=route(r);r.onload({status:result._http||200,responseText:JSON.stringify(result)});}catch(e){if(e.message==='Network')r.onerror();else throw e;}}};
  vm.runInNewContext(source,context);
  const xhr=new XHR();xhr.open('GET','https://api.autodarts.com/as/v0/friends');xhr.setRequestHeader('Authorization','Bearer '+token);
  await tick();
  if(foreign||busy){assert.equal(job.restart_step,'delete');assert(!calls.some(c=>c[2]==='DELETE'));assert.equal(portalAttempts,0);return;}
  assert.equal(job.restart_step,'accounts');assert.equal(portalAttempts,0);
  await tick();assert.equal(portalAttempts,0);clock+=2;await tick();
  if(lost){assert.equal(job.restart_step,'accounts');await tick();}
  assert.equal(job.restart_step,'wait');await tick();assert.equal(job.phase,'restarting');clock+=3;await tick();
  assert.equal(job.phase,'queued');assert.equal(job.id,'new-job');
  assert.equal(calls.filter(c=>c[2]==='DELETE').length,1);
  assert.equal(portalAttempts,lost?2:1);
  assert(!calls.some(c=>c[1].includes('/invitations/')));
}
(async()=>{await run();await run({lost:true});await run({foreign:true});await run({busy:true});console.log('Emergency lobby recovery order, delays and failure guards passed');})().catch(e=>{console.error(e);process.exit(1);});
