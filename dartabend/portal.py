"""Request existing portal sessions once when a tournament is created."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def activate(tournament_id, participants):
    accounts = [p for p in participants if p['account_name']]
    if not accounts:
        return {'status': 'local', 'message': 'Nur lokale Spieler.'}
    origin = os.getenv('DARTPORTAL_URL', 'http://192.168.178.137:18080').rstrip('/')
    if not origin:
        return {'status': 'disabled', 'message': 'Automatischer Sitzungsstart deaktiviert.'}
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        return {'status': 'error', 'message': 'DARTPORTAL_URL muss eine Server-Adresse ohne Zugangsdaten sein.'}
    try:
        request = Request(origin+'/api/automation/tournament-sessions',
                          data=json.dumps({'tournament_id': tournament_id, 'players': accounts}).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': origin}, method='POST')
        with urlopen(request, timeout=5) as response:
            data = json.load(response)
        if not isinstance(data.get('players'), list):
            raise ValueError('Invalid response')
        missing = any(p.get('status') in ('missing', 'ambiguous') for p in data['players'])
        return {'status': 'partial' if missing else 'requested',
                'message': 'Einige Account-Sitzungen fehlen oder sind nicht eindeutig. Im Dartportal prüfen.' if missing else 'Account-Sitzungen im Dartportal angefordert.'}
    except Exception:
        return {'status': 'error', 'message': 'Dartportal nicht erreichbar oder Anmeldung erforderlich. Account-Sitzungen dort manuell öffnen.'}
