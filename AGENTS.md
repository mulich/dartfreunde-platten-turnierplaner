# Dartfreunde Platten – Turnierplaner

This is a standalone application, separate from the parent Autodarts portal.
Work only in this repository unless the user asks for changes elsewhere.

The user has requested that the GitHub repository stay current. After completing
future user-requested code changes, run the relevant tests, commit the scoped
changes, and push them to this repository. Never upload databases, backups,
credentials or unrelated files. The authorized historical data is bundled in
`dartabend/history.json`; preserve it and the idempotent import behavior.

Preserve the clean blue Dartfreunde Platten design, German UI, and round-robin
rules. Missing historical results remain unknown; do not manufacture scores or
final winners. Keep score changes explicit and retain import provenance.

Run `python -m pytest -q` and `node --check dartabend/static/app.js` before pushing.
GitHub Actions tests changes and publishes the Docker image from main. Keep
`compose.server.yaml` and the deployment instructions consistent with that image.
