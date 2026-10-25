"""Request existing portal sessions once when a tournament is created."""
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


def portal_origin():
    origin = os.getenv('DARTPORTAL_URL', 'http://192.168.178.137:18080').rstrip('/')
    if not origin:
        return None
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('DARTPORTAL_URL muss eine Server-Adresse ohne Zugangsdaten sein.')
    return origin


def post(origin, path, body, timeout=5):
    request = Request(origin+path, data=json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json', 'Origin': origin}, method='POST')
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def abort_game(board_id, lobby_id, match_id):
    """Ask the account portal to delete a lobby or abort a match without scoring."""
    try:
        origin = portal_origin()
    except ValueError as error:
        return {'status': 'error', 'message': str(error)}
    if not origin:
        return {'status': 'disabled', 'message': 'DARTPORTAL_URL ist nicht gesetzt.'}
    attempts = ([('/api/lobbies/'+quote(lobby_id, safe='')+'/abort', {})] if lobby_id and not match_id else []) + \
               [('/api/boards/'+quote(board_id, safe='')+'/abort', {'match_id': match_id or lobby_id})]
    message = 'Nichts abzubrechen.'
    for path, body in attempts:
        try:
            post(origin, path, body, timeout=20)
            return {'status': 'aborted', 'message': 'Lobby gelöscht.' if 'lobbies' in path else 'Match ohne Wertung abgebrochen.'}
        except HTTPError as error:
            try:
                message = json.load(error).get('detail') or message
            except Exception:
                message = f'Portal antwortet mit HTTP {error.code}.'
        except Exception:
            message = 'Dartportal nicht erreichbar.'
    return {'status': 'error', 'message': message}


def activate(tournament_id, participants):
    accounts = [p for p in participants if p['account_name']]
    if not accounts:
        return {'status': 'local', 'message': 'Nur lokale Spieler.'}
    try:
        origin = portal_origin()
    except ValueError as error:
        return {'status': 'error', 'message': str(error)}
    if not origin:
        return {'status': 'disabled', 'message': 'Automatischer Sitzungsstart deaktiviert.'}
    try:
        data = post(origin, '/api/automation/tournament-sessions', {'tournament_id': tournament_id, 'players': accounts})
        if not isinstance(data.get('players'), list):
            raise ValueError('Invalid response')
        missing = any(p.get('status') in ('missing', 'ambiguous') for p in data['players'])
        return {'status': 'partial' if missing else 'requested',
                'message': 'Einige Account-Sitzungen fehlen oder sind nicht eindeutig. Im Dartportal prüfen.' if missing else 'Account-Sitzungen im Dartportal angefordert.'}
    except Exception:
        return {'status': 'error', 'message': 'Dartportal nicht erreichbar oder Anmeldung erforderlich. Account-Sitzungen dort manuell öffnen.'}
