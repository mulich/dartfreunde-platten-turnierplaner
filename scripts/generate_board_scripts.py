"""Generate account-detecting agents and retain existing installation URLs."""
from pathlib import Path
import json
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from dartabend.integration import BOARDS

template = (root / 'scripts/board-bridge.template.js').read_text()
boards = json.dumps([dict(name=name, account=name.lower(), id=ident) for name, ident in BOARDS.items()])
for slug, label in [('board', 'Automatisch'), *[(name.lower(), name) for name in BOARDS]]:
    script = template.replace('__BOARDS__', boards).replace('__BOARD_NAME__', label).replace('__BOARD_SLUG__', slug)
    for directory in [root / 'dartabend/static', root.parent / 'app/static']:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f'turnier-{slug}.user.js').write_text(script)
