"""Generate identical board agents for the planner and account-portal downloads."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from dartabend.integration import BOARDS

template = (root / 'scripts/board-bridge.template.js').read_text()
for name, ident in BOARDS.items():
    script = template.replace('__BOARD_NAME__', name).replace('__BOARD_ID__', ident).replace('__BOARD_SLUG__', name.lower())
    for directory in [root / 'dartabend/static', root.parent / 'app/static']:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f'turnier-{name.lower()}.user.js').write_text(script)
