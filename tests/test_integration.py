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
    assert poll(client,headers)['paused']
    body={'instance':INSTANCE,'autodarts_match_id':'confirmed-match','user_ids':['alice-id','bob-id'],'score1':2,'score2':0}
    assert client.post(f"/api/bridge/jobs/{job['id']}/result",headers=headers,json=body).status_code==409
    assert client.delete(f"/api/tournaments/{t['id']}").status_code==200
    assert poll(client,headers) is None


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
    const {resolvePlayers,finalResult,correctLobby}=require(process.argv[1]);
    const friends=[{requestStatus:'Accepted',user:{id:'alice',name:'Alice'}},{requestStatus:'Accepted',user:{id:'bob',name:'Bob'}}];
    assert.deepEqual(resolvePlayers(['ALICE','Bob'],friends,{id:'host',name:'Board'}).map(p=>p.id),['alice','bob']);
    assert.throws(()=>resolvePlayers(['Missing'],friends,{}));
    assert.throws(()=>resolvePlayers(['Alice'],[...friends,{requestStatus:'Accepted',user:{id:'other',name:'Alice'}}],{}));
    const payload={variant:'X01',isPrivate:true,bullOffMode:'Off',legs:2,settings:{baseScore:501,inMode:'Straight',outMode:'Double',bullMode:'25/50',maxRounds:50}};
    const job={user_ids:['alice','bob'],match:{player1:'Alice',player2:'Bob'},lobby_payload:payload,autodarts_match_id:'match'};
    const stats={players:[{userId:'bob',name:'Bob'},{userId:'alice',name:'Alice'}],matchStats:[{legsWon:1},{legsWon:2}]};
    assert.deepEqual(finalResult({finished:true},stats,job),{score1:2,score2:1,user_ids:['alice','bob'],autodarts_match_id:'match'});
    assert.equal(finalResult({finished:false},stats,job),null);
    assert.equal(finalResult({finished:true},{...stats,matchStats:[{legsWon:1},{legsWon:1}]},job),null);
    assert.equal(finalResult({finished:true},{...stats,players:[{userId:'wrong'},{userId:'alice'}]},job),null);
    const lobby={...payload,players:[{userId:'alice',boardId:'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'},{userId:'bob',boardId:'faa2cd5f-5d19-4e68-9749-1b7b95c753d4'}]};
    assert.equal(correctLobby(lobby,job),true);
    assert.equal(correctLobby({...lobby,players:[...lobby.players].reverse()},job),false);
    assert.equal(correctLobby({...lobby,legs:3},job),false);
    assert.equal(correctLobby({...lobby,players:[{...lobby.players[0],isPending:true},lobby.players[1]]},job),false);
    '''
    subprocess.run(['node','-e',code,str(script)],check=True,capture_output=True,text=True)
    template=(root/'scripts/board-bridge.template.js').read_text()
    for board,ident in BOARDS.items():
        expected=template.replace('__BOARD_NAME__',board).replace('__BOARD_ID__',ident).replace('__BOARD_SLUG__',board.lower())
        assert (root/f'dartabend/static/turnier-{board.lower()}.user.js').read_text()==expected


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
    assert.throws(()=>parseResponse({status:401,responseText:JSON.stringify({detail:'Board-Schlüssel ungültig.'})},planner),e=>e.service==='planner'&&e.message.includes('Board-Schlüssel ungültig.')&&!e.message.includes('Basic-Auth'));
    assert.throws(()=>parseResponse({...basic,status:200,responseHeaders:''},planner),/HTML-Seite statt JSON/);
    assert.throws(()=>parseResponse({status:502,responseText:'Bad Gateway'},planner),/HTTP 502/);
    assert.throws(()=>parseResponse({status:401,responseText:'{"detail":"Token expired"}'},'https://api.autodarts.com/bs/v0/boards/id'),e=>e.service==='autodarts' && e.status===401);
    assert.deepEqual(parseResponse({status:200,responseText:'{"job":null}'},planner),{job:null});
    assert.deepEqual(parseResponse({status:200,response:{job:null}},planner),{job:null});
    assert.equal(parseResponse({status:204,responseText:''},'https://api.autodarts.com/gs/v0/lobbies/id/players/by-index/0'),null);
    '''
    subprocess.run(['node','-e',code,str(script)],check=True,capture_output=True,text=True)
