import pytest
from fastapi.testclient import TestClient
from dartabend.main import app,database
from dartabend.integration import BOARDS


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('TOURNAMENT_DB',str(tmp_path/'profiles.sqlite3'))
    monkeypatch.setenv('TOURNAMENT_HISTORY','')
    with TestClient(app) as c:yield c


def test_profiles_aliases_persist_without_rewriting_history(client):
    muli=next(p for p in client.get('/api/player-profiles').json() if p['name']=='Muli')
    saved=client.put(f"/api/player-profiles/{muli['id']}",json={**muli,'account_name':'UniqueMuli'}).json()
    t=client.post('/api/tournaments',json={'name':'History','players':['Muli','Guest']}).json()
    assert t['player_accounts']=={'Muli':'UniqueMuli','Guest':None}
    renamed=client.put(f"/api/player-profiles/{muli['id']}",json={**saved,'name':'Michael'}).json()
    assert client.get(f"/api/tournaments/{t['id']}").json()['players']==['Muli','Guest']
    assert client.get(f"/api/tournaments/{t['id']}").json()['player_accounts']['Muli']=='UniqueMuli'
    assert client.post('/api/player-profiles',json={'name':'New','account_name':'uniquemuli'}).status_code==409
    assert client.put(f"/api/player-profiles/{muli['id']}",json={**saved,'name':'Stale'}).status_code==409
    assert client.delete(f"/api/player-profiles/{muli['id']}?revision={renamed['revision']}").status_code==200
    with TestClient(app) as restarted:
        assert 'Muli' not in restarted.get('/api/players').json()
        assert 'Michael' not in restarted.get('/api/players').json()
        assert restarted.get(f"/api/tournaments/{t['id']}").json()['player_accounts']['Muli']=='UniqueMuli'
    assert client.post('/api/player-profiles',json={'name':'Michael','account_name':None}).status_code==201


def test_pending_job_freezes_account_guest_mapping(client):
    client.post('/api/player-profiles',json={'name':'Alice','account_name':'ActualAlice'})
    t=client.post('/api/tournaments',json={'name':'Mixed','players':['Alice','Bob']}).json()
    client.post(f"/api/tournaments/{t['id']}/automation",json={'enabled':True})
    headers={'X-Board-ID':BOARDS[t['matches'][0]['board']]}
    body={'instance':'profile-fixture-browser','ready':True}
    job=client.post('/api/bridge/poll',headers=headers,json=body).json()['job']
    expected=[{'name':name,'account_name':'ActualAlice' if name=='Alice' else None} for name in [job['match']['player1'],job['match']['player2']]]
    assert job['participants']==expected
    alice=next(p for p in client.get('/api/player-profiles').json() if p['name']=='Alice')
    assert client.put(f"/api/player-profiles/{alice['id']}",json={**alice,'account_name':'ChangedAccount'}).status_code==200
    assert client.post('/api/bridge/poll',headers=headers,json=body).json()['job']['participants']==expected


def test_profile_conflicts_and_validation(client):
    assert client.post('/api/player-profiles',json={'name':'  '}).status_code==422
    assert client.post('/api/player-profiles',json={'name':'PAUSE'}).status_code==422
    assert client.post('/api/player-profiles',json={'name':'muli'}).status_code==409
    a=client.post('/api/player-profiles',json={'name':'One'}).json()
    b=client.post('/api/player-profiles',json={'name':'Two'}).json()
    assert client.put(f"/api/player-profiles/{a['id']}",json={**a,'name':'Two'}).status_code==409
    assert client.delete(f"/api/player-profiles/{b['id']}?revision=10").status_code==409


def test_local_players_are_registered_and_result_imported(client):
    t=client.post('/api/tournaments',json={'name':'Guests','players':['Guest A','Guest B']}).json()
    client.post(f"/api/tournaments/{t['id']}/automation",json={'enabled':True})
    headers={'X-Board-ID':BOARDS[t['matches'][0]['board']]}
    ident='guests-fixture-browser-1'
    job=client.post('/api/bridge/poll',headers=headers,json={'instance':ident,'ready':True}).json()['job']
    path=f"/api/bridge/jobs/{job['id']}"
    assert client.post(path+'/state',headers=headers,json={'instance':ident,'phase':'creating'}).status_code==200
    users=['local:'+p['name'].lower() for p in job['participants']]
    assert client.post(path+'/state',headers=headers,json={'instance':ident,'phase':'lobby','lobby_id':'lobby','user_ids':['wrong','ids']}).status_code==422
    assert client.post(path+'/state',headers=headers,json={'instance':ident,'phase':'lobby','lobby_id':'lobby','user_ids':users}).status_code==200
    assert client.post(path+'/state',headers=headers,json={'instance':ident,'phase':'starting'}).status_code==200
    assert client.post(path+'/state',headers=headers,json={'instance':ident,'phase':'playing','autodarts_match_id':'match'}).status_code==200
    assert client.post(path+'/result',headers=headers,json={'instance':ident,'autodarts_match_id':'match','user_ids':users,'score1':2,'score2':1}).status_code==200
    assert client.get(f"/api/tournaments/{t['id']}").json()['played']==1
