const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('dartabend/static/turnier-blau.user.js','utf8').replace('setInterval(tick,4000);','unsafeWindow.fixture={matchFullscreen,leaveMatchFullscreen,watch,setJob:job=>currentJob=job};');
async function fixture(){
  let entered=0,exited=0,blocked=false,finished=false,statsReady=true,gone=false,saveFails=false;
  const listeners={};
  const job={id:'job',phase:'playing',autodarts_match_id:'match',user_ids:['a','b'],lobby_payload:{legs:2},participants:[{name:'Alice',account_name:'Alice'},{name:'Bob',account_name:'Bob'}]};
  const doc={readyState:'loading',hidden:false,fullscreenElement:null,addEventListener:(name,fn)=>listeners[name]=fn,
    documentElement:{requestFullscreen:async()=>{entered++;if(blocked)throw Error('user gesture');doc.fullscreenElement=doc.documentElement;listeners.fullscreenchange?.();}},
    exitFullscreen:async()=>{exited++;doc.fullscreenElement=null;listeners.fullscreenchange?.();}};
  class XHR{open(){}setRequestHeader(){}}
  const token='h.'+Buffer.from(JSON.stringify({sub:'host'})).toString('base64url')+'.s';
  const location={href:'https://play.autodarts.com/',pathname:'/'};
  const context={document:doc,location,URL,Headers,Map,WeakMap,crypto:{randomUUID:()=> 'fixture-browser-instance'},atob:s=>Buffer.from(s,'base64').toString(),
    unsafeWindow:{XMLHttpRequest:XHR,fetch:async()=>({})},GM_getValue:(k,d)=>d,GM_setValue(){},GM_registerMenuCommand(){},
    GM_xmlhttpRequest:r=>{
      const path=new URL(r.url).pathname;let status=200,data;
      if(path.endsWith('/state')){status=gone?404:200;data={finished};}
      else if(path.endsWith('/stats')){status=statsReady?200:404;data={players:[{userId:'a'},{userId:'b'}],matchStats:[{legsWon:2},{legsWon:1}]};}
      else if(path.endsWith('/result')){status=saveFails?401:200;data={saved:true};}
      else throw Error(path);
      r.onload({status,responseText:JSON.stringify(data)});
    }};
  vm.runInNewContext(source,context);const fsx=context.unsafeWindow.fixture;
  fsx.setJob(job);const xhr=new XHR();xhr.open('GET','https://api.autodarts.com/fixture');xhr.setRequestHeader('Authorization','Bearer '+token);
  await fsx.matchFullscreen(job);assert.equal(entered,0,'Do not enter fullscreen before the match page loads');
  location.pathname='/matches/match';await fsx.watch(job);assert.equal(entered,1);assert.equal(doc.fullscreenElement,doc.documentElement);
  await fsx.watch(job);assert.equal(entered,1,'No repeated request on each poll');
  finished=true;statsReady=false;await fsx.watch(job);assert.equal(exited,1,'Leave on finish even while statistics are pending');
  listeners.pointerdown();await Promise.resolve();assert.equal(entered,1,'Do not re-enter a finished match on click');
  statsReady=true;saveFails=true;await assert.rejects(fsx.watch(job));assert.equal(exited,1,'A failed result import must not keep fullscreen active');
  finished=false;saveFails=false;job.autodarts_match_id='match2';location.pathname='/matches/match2';
  await fsx.watch(job);assert.equal(entered,2,'A subsequent match enters again');
  doc.fullscreenElement=null;listeners.fullscreenchange();await fsx.watch(job);assert.equal(entered,2,'Respect manually leaving fullscreen');
  job.autodarts_match_id='match3';location.pathname='/matches/match3';blocked=true;
  await fsx.watch(job);assert.equal(entered,3);assert.equal(doc.fullscreenElement,null);
  blocked=false;listeners.pointerdown();await Promise.resolve();assert.equal(entered,4,'A real click retries after a blocked automatic request');
  gone=true;await fsx.watch(job);assert.equal(exited,2,'Confirmed archive result leaves fullscreen after live match 404');
  gone=false;finished=false;job.autodarts_match_id='match4';location.pathname='/matches/match4';doc.fullscreenElement=doc.documentElement;
  await fsx.watch(job);finished=true;await fsx.watch(job);assert.equal(exited,3,'Adopt document fullscreen started by Tools for Autodarts');
  doc.fullscreenElement={video:true};await fsx.leaveMatchFullscreen();assert.equal(exited,3,'Do not close an unrelated video fullscreen');
  console.log('Match navigation, automatic entry, gesture fallback, manual exit, finish and archive exit passed');
}
fixture().catch(e=>{console.error(e);process.exitCode=1;});
