import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dartabend.main import app, database
from dartabend.integration import BOARDS, GameSettings

ADMIN={}
INSTANCE='first-browser-instance-1234'


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TOURNAMENT_DB',str(tmp_path/'test.sqlite3'))
    monkeypatch.setenv('TOURNAMENT_HISTORY','')
    with TestClient(app) as c:yield c


def create(client,players=None):
    for name in players or ['Alice','Bob','Carol','Dave']:
        client.post('/api/player-profiles',json={'name':name,'account_name':name})
    response=client.post('/api/tournaments',json={'name':'Integration','players':players or ['Alice','Bob','Carol','Dave'],'boards':2})
    assert response.status_code==201
    t=response.json()
    assert client.post(f"/api/tournaments/{t['id']}/automation",headers=ADMIN,json={'enabled':True}).status_code==200
    return t


def pair(client,board='Rot'):
    return {'X-Board-ID':BOARDS[board]}


def poll(client,headers,instance=INSTANCE,ready=True):
    r=client.post('/api/bridge/poll',headers=headers,json={'instance':instance,'ready':ready,'status':'Fixture'})
    assert r.status_code==200,r.text
    return r.json()['job']


def state(client,headers,job,phase,**kwargs):
    r=client.post(f"/api/bridge/jobs/{job['id']}/state",headers=headers,json={'instance':INSTANCE,'phase':phase,**kwargs})
    assert r.status_code==200,r.text
    return r.json()['job']


def playing(client,headers,job):
    job=state(client,headers,job,'creating')
    job=state(client,headers,job,'lobby',lobby_id='confirmed-lobby',user_ids=['alice-id','bob-id'])
    job=state(client,headers,job,'starting')
    return state(client,headers,job,'playing',autodarts_match_id='confirmed-match')


def test_emergency_restart_requires_lobby_and_orders_delays(client, monkeypatch):
    create(client)
    headers = pair(client)
    job = poll(client, headers)
    url = f"/api/integration/jobs/{job['id']}/restart"
    assert client.post(url).status_code == 409
    job = state(client, headers, job, 'creating')
    job = state(client, headers, job, 'lobby', lobby_id='old-lobby', user_ids=['alice-id','bob-id'])
    assert client.post(url).status_code == 200
    job = poll(client, headers)
    operation = job['restart_id']
    assert client.post(url).status_code == 200
    assert poll(client, headers)['restart_id'] == operation
    assert client.post(f"/api/bridge/jobs/{job['id']}/state", headers=headers,
                       json={'instance':INSTANCE,'phase':'starting'}).status_code == 409
    clock = __import__('time').time() + 10
    monkeypatch.setattr('dartabend.integration.time.time', lambda: clock)
    progress = f"/api/bridge/jobs/{job['id']}/restart"
    def step(value, **extra):
        return client.post(progress, headers=headers, json={'instance':INSTANCE,'restart_id':operation,'step':value,**extra})
    assert step('accounts').status_code == 409
    assert step('deleted',restart_id='wrong').status_code == 409
    assert step('deleted').status_code == 200
    pending = poll(client, headers)
    state(client, headers, pending, 'restarting', error='Accountzentrale: HTTP 401')
    for _ in range(20):
        assert client.post(url).json()['resuming'] is True
    resumed = poll(client, headers)
    assert resumed['restart_id'] == operation
    assert resumed['restart_step'] == 'accounts'
    assert resumed['restart_after'] == pending['restart_after']
    assert resumed['error'] == ''
    client.post(f"/api/tournaments/{pending['match']['tournament_id']}/automation", json={'enabled':False})
    assert client.post(url).status_code == 409
    client.post(f"/api/tournaments/{pending['match']['tournament_id']}/automation", json={'enabled':True})
    assert step('accounts').status_code == 409
    clock += 2
    assert step('accounts').status_code == 200
    assert step('complete').status_code == 409
    clock += 3
    new = step('complete').json()['job']
    assert new['id'] != job['id'] and new['phase'] == 'queued'
    assert new['lobby_id'] is None and new['user_ids'] is None
    assert new['participants'] == job['participants']
    assert step('complete').status_code == 404


def test_emergency_restart_never_resets_started_matches(client):
    create(client)
    headers = pair(client)
    job = playing(client, headers, poll(client, headers))
    assert client.post(f"/api/integration/jobs/{job['id']}/restart").status_code == 409
    assert poll(client, headers)['autodarts_match_id'] == 'confirmed-match'


def test_emergency_restart_userscript_runtime():
    subprocess.run(['node','tests/board-restart.cjs'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True,text=True)


def test_match_fullscreen_lifecycle_runtime():
    subprocess.run(['node','tests/board-fullscreen.cjs'],cwd=Path(__file__).resolve().parents[1],check=True,capture_output=True,text=True)


def test_restart_retry_button_remains_available_and_requests_same_job():
    script = Path(__file__).resolve().parents[1]/'dartabend/static/integration.js'
    code = r'''
    const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
    const listeners=[],requests=[],messages=[],confirmations=[];
    const main={innerHTML:'',addEventListener:(name,fn)=>listeners.push(fn)};
    const ctx={main,state:{page:'integration'},esc:x=>x,boardColor:x=>x,
      api:async(path,options)=>{requests.push([path,options]);return {boards:[],jobs:[{id:'job-123',phase:'restarting',board:'Rot',number:1,lobby_id:'lobby-123',error:'HTTP 401'}]};},
      confirm:text=>{confirmations.push(text);return true;},toast:text=>messages.push(text)};
    vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
    (async()=>{
      await ctx.renderIntegration();
      assert.match(main.innerHTML,/data-restart-lobby="job-123">Neustart fortsetzen/);
      assert.match(main.innerHTML,/data-reset-job="job-123"/);
      const button={textContent:'Neustart fortsetzen',dataset:{restartLobby:'job-123'},matches:q=>q==='[data-restart-lobby]'};
      await listeners[0]({target:{closest:()=>button}});
      assert.match(confirmations[0],/offenen Neustart-Schritt/);
      assert.equal(requests[1][0],'/api/integration/jobs/job-123/restart');
      assert.equal(requests[1][1].method,'POST');
      assert.match(messages[0],/offenen Schritt/);
    })().catch(e=>{console.error(e);process.exitCode=1;});
    '''
    subprocess.run(['node','-e',code,str(script)],check=True,capture_output=True,text=True)


def test_board_identity_without_application_passwords(client,monkeypatch):
    monkeypatch.delenv('TOURNAMENT_ADMIN_KEY',raising=False)
    assert client.post('/api/integration/boards/Rot/pair').status_code==404
    assert client.post('/api/bridge/poll',json={'instance':INSTANCE}).status_code==401
    assert client.post('/api/bridge/poll',headers={'X-Board-ID':'invalid'},json={'instance':INSTANCE}).status_code==401
    assert poll(client,pair(client)) is None
    t=create(client)
    assert client.post(f"/api/tournaments/{t['id']}/automation",json={'enabled':False}).status_code==200


def test_claim_exclusivity_and_wave_barrier(client):
    t=create(client);red=pair(client);blue=pair(client,'Blau')
    job=poll(client,red)
    assert job['board_id']==BOARDS['Rot']
    assert job['lobby_payload']['bullOffMode']=='Off'
    assert poll(client,red)['id']==job['id']
    assert poll(client,red,'second-browser-instance-5678') is None
    other=poll(client,blue)
    assert other['match']['wave']==job['match']['wave']
    # A finished match on one board must still wait for the other board in that wave.
    active=playing(client,red,job)
    body={'instance':INSTANCE,'autodarts_match_id':'confirmed-match','user_ids':['alice-id','bob-id'],'score1':2,'score2':1}
    assert client.post(f"/api/bridge/jobs/{active['id']}/result",headers=red,json=body).status_code==200
    assert poll(client,red) is None
    assert client.post(f"/api/bridge/jobs/{other['id']}/state",headers=red,json={'instance':INSTANCE,'phase':'creating'}).status_code==404


def test_result_validation_idempotency_and_manual_conflicts(client):
    t=create(client,['Alice','Bob']);headers=pair(client)
    job=playing(client,headers,poll(client,headers))
    url=f"/api/bridge/jobs/{job['id']}/result"
    result={'instance':INSTANCE,'autodarts_match_id':'confirmed-match','user_ids':['alice-id','bob-id'],'score1':2,'score2':1}
    assert client.post(url,headers=headers,json={**result,'score1':1,'score2':0}).status_code==422
    assert client.post(url,headers=headers,json={**result,'user_ids':['bob-id','alice-id']}).status_code==409
    assert client.post(url,headers=headers,json={**result,'autodarts_match_id':'wrong-match'}).status_code==409
    assert client.post(url,headers=headers,json=result).status_code==200
    assert client.post(url,headers=headers,json=result).status_code==200
    detail=client.get(f"/api/tournaments/{t['id']}").json()
    assert detail['matches'][0]['revision']==1 and detail['played']==1
    assert client.put(f"/api/tournaments/{t['id']}/matches/{job['match_id']}",json={'score1':3,'score2':1,'revision':1}).status_code==409
    reply=client.post('/api/bridge/poll',headers=headers,json={'instance':INSTANCE,'ready':False}).json()
    assert reply['completed_match_id']=='confirmed-match'


@pytest.mark.parametrize('phase', ['queued', 'creating', 'lobby', 'starting', 'playing', 'restarting'])
def test_manual_score_retires_linked_job_when_paused(client, phase):
    t = create(client, ['Alice', 'Bob'])
    headers = pair(client)
    job = poll(client, headers)
    if phase != 'queued':
        job = state(client, headers, job, 'creating')
    if phase not in ('queued', 'creating'):
        job = state(client, headers, job, 'lobby', lobby_id='confirmed-lobby', user_ids=['alice-id','bob-id'])
    if phase in ('starting', 'playing'):
        job = state(client, headers, job, 'starting')
    if phase == 'playing':
        job = state(client, headers, job, 'playing', autodarts_match_id='confirmed-match')
    if phase == 'restarting':
        assert client.post(f"/api/integration/jobs/{job['id']}/restart").status_code == 200
    url = f"/api/tournaments/{t['id']}/matches/{job['match_id']}"
    score = {'score1':2, 'score2':1, 'revision':0}
    assert client.put(url, json=score).status_code == 409
    client.post(f"/api/tournaments/{t['id']}/automation", json={'enabled':False})
    # A stale edit must leave the linked job untouched.
    assert client.put(url, json={**score, 'revision':99}).status_code == 409
    assert poll(client, headers)['id'] == job['id']
    saved = client.put(url, json=score)
    assert saved.status_code == 200, saved.text
    assert saved.json()['played'] == 1
    assert saved.json()['matches'][0]['revision'] == 1
    assert client.get('/api/integration').json()['jobs'] == []
    client.post(f"/api/tournaments/{t['id']}/automation", json={'enabled':True})
    assert poll(client, headers) is None
    late = {'instance':INSTANCE, 'autodarts_match_id':'confirmed-match', 'user_ids':['alice-id','bob-id'], 'score1':0, 'score2':2}
    assert client.post(f"/api/bridge/jobs/{job['id']}/result", headers=headers, json=late).status_code == 404
    assert client.get(f"/api/tournaments/{t['id']}").json()['matches'][0]['score1'] == 2


def test_paused_result_does_not_race_manual_input_and_clear_allows_new_job(client):
    t = create(client, ['Alice','Bob'])
    headers = pair(client)
    job = playing(client, headers, poll(client, headers))
    client.post(f"/api/tournaments/{t['id']}/automation", json={'enabled':False})
    late = {'instance':INSTANCE, 'autodarts_match_id':'confirmed-match', 'user_ids':['alice-id','bob-id'], 'score1':2, 'score2':0}
    assert client.post(f"/api/bridge/jobs/{job['id']}/result", headers=headers, json=late).status_code == 409
    url = f"/api/tournaments/{t['id']}/matches/{job['match_id']}"
    cleared = client.put(url, json={'score1':None, 'score2':None, 'revision':0})
    assert cleared.status_code == 200 and cleared.json()['played'] == 0
    client.post(f"/api/tournaments/{t['id']}/automation", json={'enabled':True})
    new = poll(client, headers)
    assert new['id'] != job['id'] and new['revision'] == 1
    assert client.post(f"/api/bridge/jobs/{job['id']}/result", headers=headers, json=late).status_code == 404


def test_pause_abort_and_reset_preserve_score_and_block_external_actions(client):
    t=create(client,['Alice','Bob']);headers=pair(client)
    job=poll(client,headers)
    assert client.post(f"/api/integration/jobs/{job['id']}/reset",headers=ADMIN).status_code==409
    client.post(f"/api/tournaments/{t['id']}/automation",headers=ADMIN,json={'enabled':False})
    assert poll(client,headers)['paused']
    assert client.post(f"/api/bridge/jobs/{job['id']}/state",headers=headers,json={'instance':INSTANCE,'phase':'creating'}).status_code==409
    assert client.post(f"/api/integration/jobs/{job['id']}/reset",headers=ADMIN).status_code==200
    assert poll(client,headers) is None
    client.post(f"/api/tournaments/{t['id']}/automation",headers=ADMIN,json={'enabled':True})
    job=playing(client,headers,poll(client,headers))
    assert client.post(f"/api/tournaments/{t['id']}/abort").status_code==200
    assert poll(client,headers) is None
    body={'instance':INSTANCE,'autodarts_match_id':'confirmed-match','user_ids':['alice-id','bob-id'],'score1':2,'score2':0}
    assert client.post(f"/api/bridge/jobs/{job['id']}/result",headers=headers,json=body).status_code==409
    assert client.delete(f"/api/tournaments/{t['id']}").status_code==200
    assert poll(client,headers) is None


@pytest.mark.parametrize('retire', ['abort', 'pause'])
def test_old_tournament_jobs_do_not_block_new_tournament(client, retire):
    old = create(client)
    headers = pair(client)
    stale = state(client, headers, poll(client, headers), 'creating')
    stale = state(client, headers, stale, 'lobby', lobby_id='old-lobby', user_ids=['alice-id','bob-id'])
    if retire == 'abort':
        client.post(f"/api/tournaments/{old['id']}/abort")
        assert poll(client, headers) is None
    else:
        client.post(f"/api/tournaments/{old['id']}/automation",json={'enabled':False})
        assert poll(client, headers)['paused']
    new = create(client)
    # Another instance must not be held by the old job's unexpired lease.
    other_instance = 'new-board-instance-5678'
    assert poll(client, headers, other_instance, ready=False) is None
    fresh = poll(client, headers, other_instance)
    assert fresh['id'] != stale['id']
    assert fresh['match']['tournament_id'] == new['id']
    assert fresh['phase'] == 'queued' and not fresh['paused']
    with database() as db:
        saved = dict(db.execute('SELECT * FROM bridge_jobs WHERE id=?',(stale['id'],)).fetchone())
        assert saved['lobby_id'] == 'old-lobby' and saved['phase'] == 'lobby'
        assert saved['owner'] == INSTANCE
    # Retiring a tournament does not delete its physical Autodarts lobby.
    assert client.get(f"/api/tournaments/{old['id']}").json()['played'] == 0


def test_single_automated_tournament_and_game_settings(client):
    create(client)
    second=client.post('/api/tournaments',json={'name':'Other','players':['Alice','Bob'],'boards':2}).json()
    assert client.post(f"/api/tournaments/{second['id']}/automation",headers=ADMIN,json={'enabled':True}).status_code==409
    assert GameSettings(length_mode='first_to',length=4).lobby()['legs']==4
    assert GameSettings(length=5).target==3
    assert client.post('/api/tournaments',json={'name':'Invalid','players':['Alice','Bob'],'game_settings':{'length':4}}).status_code==422


def test_userscript_adapters_and_generated_copies():
    root=Path(__file__).parents[1]
    script=root/'dartabend/static/turnier-blau.user.js'
    code=r'''
    const assert=require('node:assert/strict');
    const {resolvePlayers,finalResult,correctLobby,completedArchiveResult}=require(process.argv[1]);
    const friends=[{requestStatus:'Accepted',user:{id:'alice',name:'Alice'}},{requestStatus:'Accepted',user:{id:'bob',name:'Bob'}}];
    assert.deepEqual(resolvePlayers(['ALICE','Bob'],friends,{id:'host',name:'Board'}).map(p=>p.id),['alice','bob']);
    assert.throws(()=>resolvePlayers(['Missing'],friends,{}));
    assert.throws(()=>resolvePlayers(['Alice'],[...friends,{requestStatus:'Accepted',user:{id:'other',name:'Alice'}}],{}));
    const payload={variant:'X01',isPrivate:true,bullOffMode:'Off',legs:2,settings:{baseScore:501,inMode:'Straight',outMode:'Double',bullMode:'25/50',maxRounds:50}};
    const job={user_ids:['alice','bob'],match:{player1:'Alice',player2:'Bob'},lobby_payload:payload,autodarts_match_id:'match'};
    const stats={players:[{userId:'bob',name:'Bob'},{userId:'alice',name:'Alice'}],matchStats:[{legsWon:1},{legsWon:2}]};
    assert.deepEqual(finalResult({finished:true},stats,job),{score1:2,score2:1,user_ids:['alice','bob'],autodarts_match_id:'match'});
    assert.equal(finalResult({finished:false},stats,job),null);
    assert.deepEqual(completedArchiveResult(stats,job),{score1:2,score2:1,user_ids:['alice','bob'],autodarts_match_id:'match'});
    assert.equal(completedArchiveResult({...stats,id:'different-match'},job),null);
    assert.equal(completedArchiveResult({...stats,matchStats:[{legsWon:0},{legsWon:1}]},job),null);
    assert.equal(completedArchiveResult({...stats,players:[{userId:'wrong'},{userId:'alice'}]},job),null);
    assert.equal(completedArchiveResult(null,job),null);
    assert.equal(finalResult({finished:true},{...stats,matchStats:[{legsWon:1},{legsWon:1}]},job),null);
    assert.equal(finalResult({finished:true},{...stats,players:[{userId:'wrong'},{userId:'alice'}]},job),null);
    const lobby={...payload,players:[{userId:'alice',boardId:'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'},{userId:'bob',boardId:'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'}]};
    assert.equal(correctLobby(lobby,job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'),true);
    assert.equal(correctLobby({...lobby,hasReferee:true},job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'),false);
    assert.equal(correctLobby(lobby,job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4','host'),false);
    assert.equal(correctLobby({...lobby,players:lobby.players.map(p=>({...p,hostId:'host'}))},job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4','host'),true);
    assert.equal(correctLobby({...lobby,players:[...lobby.players].reverse()},job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'),false);
    assert.equal(correctLobby({...lobby,legs:3},job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'),false);
    assert.equal(correctLobby({...lobby,players:[{...lobby.players[0],isPending:true},lobby.players[1]]},job,'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'),false);
    '''
    subprocess.run(['node','-e',code,str(script)],check=True,capture_output=True,text=True)
    template=(root/'scripts/board-bridge.template.js').read_text()
    boards=json.dumps([dict(name=name,account=name.lower(),id=ident) for name,ident in BOARDS.items()])
    for slug,label in [('board','Automatisch'), *[(name.lower(),name) for name in BOARDS]]:
        fixed=json.dumps(dict(name=label,account=slug,id=BOARDS[label])) if label in BOARDS else 'null'
        expected=template.replace('__FIXED_BOARD__',fixed).replace('__BOARDS__',boards).replace('__BOARD_NAME__',label).replace('__BOARD_SLUG__',slug)
        assert (root/f'dartabend/static/turnier-{slug}.user.js').read_text()==expected


def test_legacy_rules_and_changes_do_not_rewrite_results(client):
    t=create(client)
    tid=t['id']
    client.post(f'/api/tournaments/{tid}/automation',headers=ADMIN,json={'enabled':False})
    with database() as db:
        db.execute("UPDATE tournaments SET game_settings='{}' WHERE id=?",(tid,))
    assert client.get(f'/api/tournaments/{tid}').json()['game_settings_known'] is False
    assert client.post(f'/api/tournaments/{tid}/automation',headers=ADMIN,json={'enabled':True}).status_code==409
    path=f'/api/tournaments/{tid}/game-settings'
    updated=client.post(path,headers=ADMIN,json={'length':5})
    assert updated.status_code==200
    assert updated.json()['game_settings_known'] is True
    assert updated.json()['game_settings']['length']==5
    client.post(f'/api/tournaments/{tid}/automation',headers=ADMIN,json={'enabled':True})
    assert client.post(path,headers=ADMIN,json={'length':3}).status_code==409
    headers=pair(client)
    job=poll(client,headers)
    assert job['lobby_payload']['legs']==3
    client.post(f'/api/tournaments/{tid}/automation',headers=ADMIN,json={'enabled':False})
    assert client.post(path,headers=ADMIN,json={'length':3}).status_code==409
    assert client.post(f"/api/integration/jobs/{job['id']}/reset",headers=ADMIN).status_code==200
    assert client.post(path,headers=ADMIN,json={'length':3}).status_code==200


def test_userscript_runtime_lobby_invitation_start_and_result():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run(['node','tests/bridge-flow.cjs'],cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


def test_userscript_proxy_errors_distinguish_basic_auth_and_board_key():
    script=Path(__file__).resolve().parents[1]/'dartabend/static/turnier-blau.user.js'
    code=r'''
    const assert=require('node:assert/strict');
    const {parseResponse}=require(process.argv[1]);
    const planner='https://turnier.mulich.de/api/bridge/poll';
    const basic={status:401,responseHeaders:'Content-Type: text/html\r\nWWW-Authenticate: Basic realm="Authorization required"',responseText:'<html><h1>401 Authorization Required</h1></html>'};
    assert.throws(()=>parseResponse(basic,planner),e=>e.status===401 && e.service==='planner' && e.message.includes('Website-Passwortschutz') && e.message.includes('anmelden'));
    assert.throws(()=>parseResponse(basic,'https://dartportal.mulich.de/api/automation/lobby-recovery'),e=>e.service==='portal' && e.message.startsWith('Accountzentrale:') && e.message.includes('Accountzentrale anmelden') && !e.message.startsWith('Autodarts:'));
    assert.throws(()=>parseResponse(basic,'http://192.168.178.137:18080/api/automation/lobby-recovery','http://192.168.178.137:18080'),e=>e.service==='portal' && e.message.startsWith('Accountzentrale:'));
    assert.throws(()=>parseResponse(basic,'https://api.autodarts.com/gs/v0/lobbies'),e=>e.service==='autodarts' && e.message.includes('Anmeldung') && !e.message.includes('Passwortschutz'));
    assert.throws(()=>parseResponse({status:401,responseText:JSON.stringify({detail:'Board-Schlüssel ungültig.'})},planner),e=>e.service==='planner'&&e.message.includes('Board-Schlüssel ungültig.')&&!e.message.includes('Basic-Auth'));
    assert.throws(()=>parseResponse({...basic,status:200,responseHeaders:''},planner),/HTML-Seite statt JSON/);
    assert.throws(()=>parseResponse({status:502,responseText:'Bad Gateway'},planner),/HTTP 502/);
    assert.throws(()=>parseResponse({status:401,responseText:'{"detail":"Token expired"}'},'https://api.autodarts.com/bs/v0/boards/id'),e=>e.service==='autodarts' && e.status===401);
    assert.deepEqual(parseResponse({status:200,responseText:'{"job":null}'},planner),{job:null});
    assert.deepEqual(parseResponse({status:200,response:{job:null}},planner),{job:null});
    assert.equal(parseResponse({status:204,responseText:''},'https://api.autodarts.com/gs/v0/lobbies/id/players/by-index/0'),null);
    '''
    subprocess.run(['node','-e',code,str(script)],check=True,capture_output=True,text=True)


def test_lobby_null_list_is_empty_but_invalid_responses_are_rejected():
    script=Path(__file__).resolve().parents[1]/'dartabend/static/turnier-blau.user.js'
    code=r'''
    const assert=require('node:assert/strict');
    const {normalizeLobby}=require(process.argv[1]);
    const empty={id:'lobby',host:{id:'host'},isPrivate:true,players:null};
    assert.deepEqual(normalizeLobby(empty,'lobby').players,[]);
    assert.equal(empty.players,null);
    const players=[{userId:'account'}];
    assert.equal(normalizeLobby({...empty,players},'lobby').players,players);
    assert.throws(()=>normalizeLobby({...empty,id:'other'},'lobby'),/unvollständig/);
    assert.throws(()=>normalizeLobby({id:'lobby'},'lobby'),/unvollständig/);
    assert.throws(()=>normalizeLobby({...empty,players:[null]},'lobby'),/Spielerliste/);
    assert.throws(()=>normalizeLobby(null,'lobby'),/unvollständig/);
    '''
    subprocess.run(['node','-e',code,str(script)],check=True,capture_output=True,text=True)


def test_board_account_detection_before_automation():
    root=Path(__file__).parents[1]
    subprocess.run(['node','tests/board-account.cjs'],cwd=root,check=True,capture_output=True,text=True)


def test_fixed_board_token_renewal_and_stale_unauthorized_response():
    root=Path(__file__).parents[1]
    subprocess.run(['node','tests/board-session.cjs'],cwd=root,check=True,capture_output=True,text=True)
