// Exercise the actual userscript runtime with isolated API responses and no network.
const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
const source=fs.readFileSync('dartabend/static/turnier-blau.user.js','utf8');
const board='faa2cd5f-5d19-4e68-9749-1b7b95c753d4';
async function exercise(ambiguous=false,local=false,guests=false) {
  let tick,lobby,ended=false,done=false;const calls=[], storage=new Map();
  let job={id:'job-1',phase:'queued',user_ids:null,match:{player1:'Alice',player2:'Bob'},lobby_payload:{variant:'X01',isPrivate:true,bullOffMode:'Off',legs:2,settings:{baseScore:501,inMode:'Straight',outMode:'Double',bullMode:'25/50',maxRounds:50}}};
  if(local)job.participants=[{name:'Alice',account_name:guests?null:'Alice'},{name:'Bob',account_name:null}];
  const key='dfp-turnier-'+board;
  storage.set(key,{key:'board-key-fixture',enabled:true});
  const token='header.'+Buffer.from(JSON.stringify({sub:'host'})).toString('base64url')+'.signature';
  class XHR {open(){}setRequestHeader(){}}
  const location={href:'https://play.autodarts.com/',assign:url=>calls.push({navigate:url})};
  function route(r){
    calls.push(r);const url=new URL(r.url), path=url.pathname, body=r.data?JSON.parse(r.data):{};
    if(url.origin==='https://turnier.mulich.de'){
      assert.equal(r.headers['X-Board-ID'],board);assert.equal(r.headers.Authorization,undefined);assert.equal(r.anonymous,false);
      assert(!JSON.stringify(r).includes(token));
      if(path==='/api/bridge/poll')return {job:done?null:job};
      if(path.endsWith('/state')){job={...job,...body};return {job};}
      if(path.endsWith('/result')){assert.equal(body.score1,2);assert.equal(body.score2,1);assert.deepEqual(body.user_ids,[guests?'local:alice':'alice',local?'local:bob':'bob']);done=true;return {saved:true};}
      throw Error('Unknown planner route '+path);
    }
    assert.equal(url.origin,'https://api.autodarts.com');assert.equal(r.headers.Authorization,'Bearer '+token);
    if(path==='/bs/v0/boards/'+board)return {id:board,matchId:job.autodarts_match_id};
    if(path==='/as/v0/friends')return ['Alice','Bob'].map(name=>({requestStatus:'Accepted',user:{id:name.toLowerCase(),name}}));
    if(path==='/us/v0/users/host')return {id:'host',name:'Board Blau'};
    if(path==='/gs/v0/lobbies'&&r.method==='POST'){
      if(ambiguous)throw Error('Ambiguous external write');
      lobby={id:'lobby-1',...body,host:{id:'host'},players:[{userId:'host',boardId:board}]};return lobby;
    }
    if(path==='/gs/v0/lobbies/lobby-1')return lobby;
    if(path.endsWith('/players/by-index/0')&&r.method==='DELETE'){lobby.players.splice(0,1);return {};}
    if(path==='/gs/v0/lobbies/lobby-1/players'&&r.method==='POST'){assert(['Alice','Bob'].includes(body.name));assert.equal(body.boardId,board);lobby.players.unshift({name:body.name,boardId:board});return {};}
    if(path.includes('/invitations/')){lobby.players.unshift({userId:path.split('/').pop(),isPending:true,boardId:null});return {};}
    if(path.includes('/players/by-index/')&&path.endsWith('/host')){lobby.players[Number(path.split('/').at(-2))].boardId=body.boardId;return {};}
    if(path.endsWith('/players/move/to-index')){const p=lobby.players.splice(body.index,1)[0];lobby.players.splice(body.toIndex,0,p);return {};}
    if(path.endsWith('/start')){assert.deepEqual(lobby.players.map(p=>p.userId || ('local:'+p.name.toLowerCase())),[guests?'local:alice':'alice',local?'local:bob':'bob']);assert(lobby.players.every(p=>p.boardId===board&&!p.isPending));return {id:'match-1'};}
    if(path==='/gs/v0/matches/match-1/state')return {finished:ended};
    if(path==='/as/v0/matches/match-1/stats')return {players:[local?{name:'Bob'}:{userId:'bob'},guests?{name:'Alice'}:{userId:'alice'}],matchStats:[{legsWon:1},{legsWon:2}]};
    throw Error('Unknown Autodarts route '+path);
  }
  const context={URL,Headers,WeakMap,Map,crypto:{randomUUID:()=> 'fixture-browser-instance-123'},location,atob:x=>Buffer.from(x,'base64').toString(),
    unsafeWindow:{XMLHttpRequest:XHR,fetch:async()=>({}),location},
    document:{readyState:'loading',addEventListener:()=>{}},
    GM_getValue:(k,d)=>storage.has(k)?structuredClone(storage.get(k)):d,
    GM_setValue:(k,v)=>storage.set(k,structuredClone(v)),GM_registerMenuCommand:()=>{},
    GM_xmlhttpRequest:r=>{try{const result=route(r);r.onload({status:200,responseText:JSON.stringify(result)});}catch(e){if(e.message==='Ambiguous external write')r.onerror();else throw e;}},
    setInterval:fn=>{tick=fn;},prompt:()=>null};
  vm.runInNewContext(source,context);
  const xhr=new XHR();xhr.open('GET','https://api.autodarts.com/as/v0/friends');xhr.setRequestHeader('Authorization','Bearer '+token);
  await tick();
  if(ambiguous){assert.equal(job.phase,'creating');await tick();assert.equal(calls.filter(c=>c.url?.endsWith('/gs/v0/lobbies')&&c.method==='POST').length,1);assert(!calls.some(c=>c.url?.includes('/invitations/')));return;}
  assert.equal(job.phase,guests?'playing':'lobby');assert.equal(lobby.players.length,2);assert.equal(lobby.players.filter(p=>p.isPending).length,guests?0:local?1:2);
  await tick(); // Invitations are pending; retries must not duplicate them.
  assert.equal(calls.filter(c=>c.url?.includes('/invitations/')).length,guests?0:local?1:2);
  lobby.players.forEach(p=>p.isPending=false);
  await tick();assert.equal(job.phase,'playing');assert(!done);
  assert(calls.some(c=>c.navigate==='https://play.autodarts.com/matches/match-1'));
  ended=true;await tick();assert(done);
  assert.equal(calls.filter(c=>c.url?.endsWith('/start')).length,1);
  assert.equal(calls.filter(c=>c.url?.endsWith('/gs/v0/lobbies')&&c.method==='POST').length,1);
}
(async()=>{await exercise();await exercise(true);await exercise(false,true);await exercise(false,true,true);process.stdout.write('Board flow and ambiguous-write recovery passed\n');})().catch(e=>{console.error(e);process.exit(1);});
