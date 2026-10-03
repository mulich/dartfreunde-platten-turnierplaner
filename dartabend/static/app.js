const main = document.querySelector('#main');
const dialog = document.querySelector('#create-dialog');
const state = { page: 'active', list: [], tournament: null, tab: 'matches', board: '', pending: false, search: '' };
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => new Date(value).toLocaleDateString('de-DE', {day:'2-digit',month:'short',year:'numeric'});
const boardColor = board => ({Rot:'red',Blau:'blue',Schwarz:'black'}[board]);
const isArchived = t => Boolean(t.archived_at || t.finished_at);
const percent = t => Math.round(t.played / t.total * 100);
let toastTimer;
function toast(message) { const el = document.querySelector('#toast'); el.textContent = message; el.classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('visible'), 3800); }
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: {'Content-Type':'application/json', ...options.headers} });
  let data;
  try { data = await response.json(); } catch { throw new Error('Der Server hat keine gültige Antwort geliefert.'); }
  if (!response.ok) {
    let message = data.detail;
    if (Array.isArray(message)) message = message.map(e => e.msg.replace(/^Value error, /, '')).join('\n');
    throw new Error(message || 'Die Anfrage konnte nicht ausgeführt werden.');
  }
  return data;
}
function setNav() {
  document.querySelectorAll('[data-page]').forEach(el => el.classList.toggle('selected', el.dataset.page === state.page));
  document.querySelector('#active-count').textContent = state.list.filter(t => !isArchived(t)).length;
  document.querySelector('#archive-count').textContent = state.list.filter(t => isArchived(t)).length;
}
function renderList() {
  setNav();
  const archive = state.page === 'archive';
  main.innerHTML = `<div class="page-heading"><div><span class="eyebrow">${archive?'ARCHIV':'TURNIERE'}</span><h1>Dartfreunde Platten</h1></div><button class="button primary" data-create>＋ Neues Turnier</button></div>
  <div class="stats"><div class="stat"><div><div class="stat-number">${state.list.filter(t=>!isArchived(t)).length}</div><div class="stat-label">Laufende Turniere</div></div><span class="stat-icon">◫</span></div><div class="stat"><div><div class="stat-number">${state.list.filter(t=>isArchived(t)).length}</div><div class="stat-label">Turniere im Archiv</div></div><span class="stat-icon">♜</span></div><div class="stat"><div><div class="stat-number">${state.list.reduce((n,t)=>n+t.played,0)}</div><div class="stat-label">Gespielte Begegnungen</div></div><span class="stat-icon">◎</span></div></div>
  <div class="section-heading"><h3>${archive?'Vergangene Turniere':'Laufende Turniere'}</h3><input class="search" id="search" type="search" placeholder="Turnier suchen …" aria-label="Turnier suchen" value="${esc(state.search)}"></div><div id="list-content"></div>`;
  renderCards();
  document.querySelector('#search').addEventListener('input', e => {state.search=e.target.value;renderCards();});
}
function renderCards() {
  const archive = state.page === 'archive';
  const list = state.list.filter(t => isArchived(t) === archive && t.name.toLocaleLowerCase('de').includes(state.search.toLocaleLowerCase('de')));
  document.querySelector('#list-content').innerHTML = list.length ? `<div class="tournament-list">${list.map(t=>`<a class="tournament-card" href="#tournament/${t.id}"><div class="card-top"><span class="badge ${archive?'':'active'}">${archive?(t.played<t.total?'Importiert · unvollständig':'✓ Vollständig'):'● Läuft'}</span><span class="badge date">${date(t.created_at)}</span></div><h3>${esc(t.name)}</h3><div class="card-meta">${t.players} Spieler &nbsp;·&nbsp; ${t.boards} Scheiben &nbsp;·&nbsp; Jeder gegen jeden</div><div class="progress"><span style="width:${percent(t)}%"></span></div><div class="progress-caption"><span>${t.played} von ${t.total} Spielen</span><span>${percent(t)} %</span></div><div class="card-bottom"><span>${archive?(t.winner?`1. Platz: ${esc(t.winner)}`:`${t.total-t.played} Spiele ohne Ergebnis`):'Zum Spielplan'}</span><span>↗</span></div></a>`).join('')}</div>` : `<div class="empty"><span class="empty-symbol">${archive?'◷':'◎'}</span><h3>${state.search?'Kein passendes Turnier':archive?'Keine abgeschlossenen Turniere':'Keine laufenden Turniere'}</h3><p>${state.search?'Versuche einen anderen Suchbegriff.':archive?'Abgeschlossene Turniere werden hier angezeigt.':'Ein neues Turnier anlegen, um einen Spielplan zu erstellen.'}</p>${!archive&&!state.search?'<button class="button" data-create>＋ Erstes Turnier erstellen</button>':''}</div>`;
}
function renderDetail() {
  const t=state.tournament;
  state.page=isArchived(t)?'archive':'active'; setNav();
  main.innerHTML=`<button class="back" data-back>← Zurück zu ${isArchived(t)?'Archiv':'Turnieren'}</button><div class="page-heading detail-heading"><div><span class="eyebrow">DARTFREUNDE PLATTEN</span><h1>${esc(t.name)}</h1><p class="detail-meta">${date(t.created_at)} &nbsp;·&nbsp; ${t.players.length} Spieler &nbsp;·&nbsp; ${t.boards} Scheiben &nbsp;·&nbsp; Jeder gegen jeden</p></div><div class="detail-actions"><button class="button small" data-refresh>↻ Aktualisieren</button>${isArchived(t)?'<button class="button small" data-reopen>Für Korrektur öffnen</button>':`<button class="button small ${t.played===t.total?'primary':''}" data-finish ${t.played!==t.total?'disabled title="Erst alle Spiele eintragen"':''}>✓ Turnier abschließen</button>`}</div></div>
  ${t.source_file?`<div class="finished-note">Excel-Import: ${esc(t.source_file)}${t.played<t.total?`<br>${t.total-t.played} Spiele ohne Ergebnis. Die Tabelle zeigt den erfassten Zwischenstand.`:isArchived(t)?`<br>1. Platz: <strong>${t.standings.filter(p=>p.rank===1).map(p=>esc(p.name)).join(' / ')}</strong>`:''}${(t.source_notes||[]).map(note=>`<br>${esc(note)}`).join('')}</div>`:isArchived(t)?`<div class="finished-note">Abgeschlossen am ${date(t.finished_at)} · 1. Platz: <strong>${t.standings.filter(p=>p.rank===1).map(p=>esc(p.name)).join(' / ')}</strong></div>`:''}
  <div class="detail-progress"><div class="progress"><span style="width:${percent(t)}%"></span></div><span>${t.played} / ${t.total} Spiele abgeschlossen</span></div>
  <div class="tabs" role="tablist" aria-label="Turnieransichten">${[['matches','Spielplan'],['table','Tabelle'],['players','Spieler & Verteilung']].map(([id,label])=>`<button role="tab" aria-selected="${state.tab===id}" class="tab ${state.tab===id?'selected':''}" data-tab="${id}">${label}</button>`).join('')}</div><section id="detail-content"></section>`;
  renderDetailContent();
}
function renderDetailContent() {
  const t=state.tournament;
  const content=document.querySelector('#detail-content');
  if(state.tab==='table') {
    content.innerHTML=`<div class="table-wrap"><table><thead><tr><th>Platz</th><th>Spieler</th><th>Punkte</th><th>Spiele</th><th>Siege</th><th>Niederlagen</th><th>Legs +</th><th>Legs −</th><th>Differenz</th></tr></thead><tbody>${t.standings.map(p=>`<tr class="${p.rank===1?'leader':''}"><td class="rank">${p.rank}</td><td>${esc(p.name)}</td><td class="points">${p.points}</td><td>${p.played}</td><td>${p.wins}</td><td>${p.losses}</td><td>${p.legs_for}</td><td>${p.legs_against}</td><td>${p.difference>0?'+':''}${p.difference}</td></tr>`).join('')}</tbody></table></div><p class="table-note">${t.played<t.total?`Zwischenstand · ${t.total-t.played} Ergebnisse fehlen. `:''}Sieg = 2 Punkte · Sortierung: Punkte → gewonnene Legs → Leg-Differenz. Gleiche Werte teilen sich den Platz.</p>`;
    return;
  }
  if(state.tab==='players') {
    const boards=['Rot','Blau','Schwarz'].slice(0,t.boards);
    content.innerHTML=`<div class="rule-note">Jeder spielt einmal gegen jeden. Die Scheiben und Anwürfe werden möglichst gleichmäßig verteilt. Spieler 1 wirft an. Bei ungerader Spielerzahl gibt es pro Runde eine Pause.</div><div class="table-wrap"><table><thead><tr><th>Spieler</th><th>Anwürfe</th>${boards.map(b=>`<th><i class="dot ${boardColor(b)}"></i>${b}</th>`).join('')}</tr></thead><tbody>${t.players.map(p=>`<tr><td>${esc(p)}</td><td>${t.matches.filter(m=>m.player1===p).length}</td>${boards.map(b=>`<td>${t.matches.filter(m=>m.board===b&&(m.player1===p||m.player2===p)).length}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="table-note">Die Verteilung zählt alle geplanten Begegnungen.</p>`;
    return;
  }
  const matches=t.matches.filter(m=>(!state.board||m.board===state.board)&&(!state.pending||m.score1===null));
  const waves=[...new Set(matches.map(m=>m.wave))];
  content.innerHTML=`<div class="match-toolbar"><div class="filters"><select id="board-filter" aria-label="Scheibe filtern"><option value="">Alle Scheiben</option>${['Rot','Blau','Schwarz'].slice(0,t.boards).map(b=>`<option ${state.board===b?'selected':''}>${b}</option>`).join('')}</select><select id="status-filter" aria-label="Spiele filtern"><option value="all">Alle Spiele</option><option value="pending" ${state.pending?'selected':''}>Nur offene Spiele</option></select></div><span class="help-text">${isArchived(t)?'Archivierter Spielplan':'Spieler 1 wirft an · Ergebnisse in Legs'}</span></div>${waves.map(w=>{
    const all=t.matches.filter(m=>m.wave===w);
    const round=all[0].round;
    const resting=t.players.filter(p=>!t.matches.some(m=>m.round===round&&(m.player1===p||m.player2===p)));
    return `<div class="wave"><div class="wave-heading"><h3>Durchgang ${w}</h3><span>Runde ${round}${resting.length?' · Pause: '+resting.map(esc).join(', '):''}</span></div><div class="matches ${t.boards===3?'three':''}">${matches.filter(m=>m.wave===w).map(matchCard).join('')}</div></div>`;
  }).join('')}${!waves.length?'<div class="empty"><span class="empty-symbol">✓</span><h3>Keine Spiele in dieser Ansicht.</h3><p>Ändere die Filter, um andere Begegnungen zu sehen.</p></div>':''}`;
  document.querySelector('#board-filter').onchange=e=>{state.board=e.target.value;renderDetailContent();};
  document.querySelector('#status-filter').onchange=e=>{state.pending=e.target.value==='pending';renderDetailContent();};
}
function matchCard(m) {
  const finished=isArchived(state.tournament);
  const played=m.score1!==null;
  return `<form class="match" data-match="${m.id}" data-revision="${m.revision}"><div class="match-top"><span class="board"><i class="dot ${boardColor(m.board)}"></i> Scheibe ${esc(m.board)}</span><span>Spiel ${m.number}</span></div>
  <div class="player-line"><label class="player-name" for="score1-${m.id}">${esc(m.player1)}<span class="starter">ANWURF</span></label><input class="score" id="score1-${m.id}" name="score1" type="number" min="0" max="999" step="1" inputmode="numeric" aria-label="Legs ${esc(m.player1)}" value="${m.score1??''}" ${finished?'disabled':'required'}></div>
  <div class="player-line"><label class="player-name" for="score2-${m.id}">${esc(m.player2)}</label><input class="score" id="score2-${m.id}" name="score2" type="number" min="0" max="999" step="1" inputmode="numeric" aria-label="Legs ${esc(m.player2)}" value="${m.score2??''}" ${finished?'disabled':'required'}></div>
  <div class="match-footer"><span class="${played?'winner-name':''}">${played?'✓ '+esc(m.score1>m.score2?m.player1:m.player2):'Noch offen'}</span>${finished?'':`<span>${played?'<button type="button" class="clear-score" data-clear>Zurücksetzen</button>':''}<button class="button small" type="submit">Speichern</button></span>`}</div><p class="match-error" role="alert"></p></form>`;
}
let selectedPlayers = [];
let shortcuts = [];
let createVersion = 0;
const playerKey = name => name.toLocaleLowerCase('de');
function renderPlayerPicker() {
  const selected = new Set(selectedPlayers.map(playerKey));
  document.querySelector('#player-shortcuts').innerHTML = shortcuts.map((name, index) => `<button type="button" class="player-shortcut ${selected.has(playerKey(name))?'chosen':''}" data-player-index="${index}" aria-label="${esc(name)} hinzufügen" ${selected.has(playerKey(name))?'disabled':''}>${selected.has(playerKey(name))?'✓':'＋'} ${esc(name)}</button>`).join('');
  document.querySelector('#selected-players').innerHTML = selectedPlayers.length ? selectedPlayers.map((name, index) => `<span class="player-chip"><span>${esc(name)}</span><button type="button" data-remove-player="${index}" aria-label="${esc(name)} entfernen" title="Entfernen">×</button></span>`).join('') : '<span class="no-players">Keine Spieler ausgewählt</span>';
  updatePlanSummary();
}
function addPlayer(name) {
  name = name.trim();
  const error = document.querySelector('#create-error');
  if (!name) { error.textContent='Bitte einen Spielernamen eingeben.'; return false; }
  if (selectedPlayers.some(p => playerKey(p) === playerKey(name))) { error.textContent='Dieser Spieler ist bereits ausgewählt.'; return false; }
  if (selectedPlayers.length >= 64) { error.textContent='Es sind maximal 64 Spieler möglich.'; return false; }
  if (name.length > 60 || playerKey(name) === 'pause') { error.textContent='Name: maximal 60 Zeichen. PAUSE ist für Freilose reserviert.'; return false; }
  selectedPlayers.push(shortcuts.find(p => playerKey(p) === playerKey(name)) || name);
  error.textContent=''; renderPlayerPicker(); return true;
}
function addTypedPlayer() {
  const input = document.querySelector('#player-name');
  if (addPlayer(input.value)) {input.value='';input.focus();}
}
async function showCreate() {
  const version = ++createVersion;
  document.querySelector('#create-form').reset();
  document.querySelector('#tournament-name').value='Turnier · '+new Date().toLocaleDateString('de-DE');
  document.querySelector('#create-error').textContent='';
  selectedPlayers=[]; shortcuts=[]; renderPlayerPicker();
  document.querySelector('#shortcut-status').textContent='Spieler werden geladen …';
  dialog.showModal();
  try {
    const names=await api('/api/players');
    if(version!==createVersion || !dialog.open)return;
    shortcuts=names;renderPlayerPicker();
    document.querySelector('#shortcut-status').textContent='';
  } catch(error) {
    if(version===createVersion && dialog.open)document.querySelector('#shortcut-status').textContent='Spielerauswahl nicht verfügbar. Namen können manuell hinzugefügt werden.';
  }
}
function updatePlanSummary() {
  document.querySelector('#player-count').textContent=`${selectedPlayers.length} Spieler`;
  const n=selectedPlayers.length, boards=Number(document.querySelector('[name=boards]:checked').value);
  document.querySelector('#plan-summary').textContent=n<2?'Mindestens zwei Spieler auswählen.':`${n*(n-1)/2} ${n===2?'Begegnung':'Begegnungen'} · ${n%2?n:n-1} ${n===2?'Runde':'Runden'} · ${(n%2?n:n-1)*Math.ceil(Math.floor(n/2)/boards)} ${n===2?'Durchgang':'Durchgänge'}${n%2?' · mit Spielpausen':''}`;
}
async function loadList() { state.list=await api('/api/tournaments');setNav(); }
let routeVersion=0;
async function route() {
  const version=++routeVersion;
  const match=location.hash.match(/^#tournament\/([a-z0-9-]+)$/);
  main.innerHTML='<div class="loading">Turniere werden geladen …</div>';
  try {
    await loadList();
    if(version!==routeVersion)return;
    if(match) {
      const t=await api(`/api/tournaments/${match[1]}`);
      if(version!==routeVersion)return;
      state.tournament=t;renderDetail();
    } else {
      state.tournament=null;state.page=location.hash==='#archive'?'archive':'active';renderList();
    }
  } catch(error) {
    if(version!==routeVersion)return;
    main.innerHTML=`<div class="load-error"><h3>Die Ansicht konnte nicht geladen werden.</h3><p>${esc(error.message)}</p><button class="button" data-retry>Erneut versuchen</button><a class="button" href="#">Zur Übersicht</a></div>`;
  }
}
document.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>{state.search='';location.hash=el.dataset.page==='archive'?'archive':'';});
document.querySelector('#close-dialog').onclick=()=>dialog.close();
document.querySelector('#add-player').onclick=addTypedPlayer;
document.querySelector('#player-name').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();addTypedPlayer();}};
document.querySelector('#player-shortcuts').onclick=e=>{
  const button=e.target.closest('[data-player-index]');
  if(button&&!button.disabled)addPlayer(shortcuts[Number(button.dataset.playerIndex)]);
};
document.querySelector('#selected-players').onclick=e=>{
  const button=e.target.closest('[data-remove-player]');
  if(button){selectedPlayers.splice(Number(button.dataset.removePlayer),1);document.querySelector('#create-error').textContent='';renderPlayerPicker();}
};
document.querySelectorAll('[name=boards]').forEach(el=>el.onchange=updatePlanSummary);
document.querySelector('#create-form').onsubmit=async e=>{
  e.preventDefault();
  const input=document.querySelector('#player-name');
  if(input.value.trim()){if(!addPlayer(input.value))return;input.value='';}
  if(selectedPlayers.length<2){document.querySelector('#create-error').textContent='Mindestens zwei Spieler auswählen.';return;}
  const button=document.querySelector('#create-submit');button.disabled=true;
  document.querySelector('#create-error').textContent='';
  try {
    const t=await api('/api/tournaments',{method:'POST',body:JSON.stringify({name:document.querySelector('#tournament-name').value,players:selectedPlayers,boards:Number(document.querySelector('[name=boards]:checked').value)})});
    dialog.close();state.tab='matches';state.board='';state.pending=false;location.hash=`tournament/${t.id}`;toast('Turnier erstellt.');
  } catch(error) {document.querySelector('#create-error').textContent=error.message;} finally {button.disabled=false;}
};
async function saveScore(form, clear=false) {
  const t=state.tournament;
  const m=t.matches.find(m=>m.id===Number(form.dataset.match));
  const fields=new FormData(form);
  const body={score1:clear?null:Number(fields.get('score1')),score2:clear?null:Number(fields.get('score2')),revision:Number(form.dataset.revision)};
  const button=clear?form.querySelector('[data-clear]'):form.querySelector('[type=submit]');
  button.disabled=true;form.querySelector('.match-error').textContent='';
  try {
    const updated=await api(`/api/tournaments/${t.id}/matches/${m.id}`,{method:'PUT',body:JSON.stringify(body)});
    // Keep other unsaved inputs intact while updating the saved card and table data.
    state.tournament=updated;
    const updatedMatch=updated.matches.find(x=>x.id===m.id);
    if(state.pending&&!clear)form.remove();else form.outerHTML=matchCard(updatedMatch);
    const progress=document.querySelector('.detail-progress');
    progress.querySelector('.progress>span').style.width=percent(updated)+'%';
    progress.lastElementChild.textContent=`${updated.played} / ${updated.total} Spiele abgeschlossen`;
    const finish=document.querySelector('[data-finish]');if(finish){finish.disabled=updated.played!==updated.total;finish.classList.toggle('primary',!finish.disabled);}
    toast(clear?'Ergebnis zurückgesetzt.':'Ergebnis gespeichert.');
  } catch(error) {form.querySelector('.match-error').textContent=error.message;button.disabled=false;}
}
main.addEventListener('submit',e=>{if(e.target.matches('[data-match]')){e.preventDefault();saveScore(e.target);}});
main.addEventListener('click',async e=>{
  const el=e.target.closest('button');if(!el)return;
  if(el.matches('[data-create]'))showCreate();
  if(el.matches('[data-retry]'))route();
  if(el.matches('[data-back]'))location.hash=state.page==='archive'?'archive':'';
  if(el.matches('[data-tab]')) {
    state.tab=el.dataset.tab;
    document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('selected',b.dataset.tab===state.tab);b.setAttribute('aria-selected',b.dataset.tab===state.tab);});
    renderDetailContent();
  }
  if(el.matches('[data-clear]'))saveScore(el.closest('form'),true);
  if(el.matches('[data-refresh]')){await route();toast('Ansicht aktualisiert.');}
  if(el.matches('[data-finish],[data-reopen]')) {
    el.disabled=true;
    try {
      state.tournament=await api(`/api/tournaments/${state.tournament.id}/${el.matches('[data-finish]')?'finish':'reopen'}`,{method:'POST'});
      await loadList();renderDetail();toast(state.tournamenisArchived(t)?'Turnier im Archiv gespeichert.':'Turnier für Korrekturen geöffnet.');
    } catch(error){toast(error.message);el.disabled=false;}
  }
});
window.addEventListener('hashchange',()=>{state.tab='matches';state.board='';state.pending=false;route();});
document.querySelector('#today').textContent=new Date().toLocaleDateString('de-DE',{weekday:'short',day:'2-digit',month:'long',year:'numeric'});
route();
