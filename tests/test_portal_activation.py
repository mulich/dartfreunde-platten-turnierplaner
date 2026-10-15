import io
import json
from urllib.error import URLError

from dartabend import portal


def test_portal_request_filters_guests_and_uses_existing_server_guard(monkeypatch):
    monkeypatch.setenv('DARTPORTAL_URL','http://portal:8000')
    requests = []
    def send(request,timeout):
        requests.append(request)
        assert timeout == 5
        return io.StringIO('{"players":[{"status":"scheduled"}]}')
    monkeypatch.setattr(portal,'urlopen',send)
    result = portal.activate('tournament', [{'name':'Anna','account_name':'Anna123'},{'name':'Guest','account_name':None}])
    assert result['status'] == 'requested'
    request = requests[0]
    assert request.full_url == 'http://portal:8000/api/automation/tournament-sessions'
    assert request.get_header('Origin') == 'http://portal:8000'
    assert json.loads(request.data)['players'] == [{'name':'Anna','account_name':'Anna123'}]


def test_portal_failure_is_actionable_and_never_retries_writes(monkeypatch):
    monkeypatch.setenv('DARTPORTAL_URL','http://portal:8000')
    calls = []
    def fail(*args,**kwargs):
        calls.append(True)
        raise URLError('fixture')
    monkeypatch.setattr(portal,'urlopen',fail)
    assert portal.activate('t',[{'name':'A','account_name':'a'}])['status'] == 'error'
    assert len(calls) == 1
    assert portal.activate('t',[{'name':'Guest','account_name':None}])['status'] == 'local'
    assert len(calls) == 1
