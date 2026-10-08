function readGameSettings(root=document) {
  return {base_score:Number(root.querySelector('#base-score').value),length_mode:root.querySelector('#length-mode').value,length:Number(root.querySelector('#match-length').value),in_mode:root.querySelector('#in-mode').value,out_mode:root.querySelector('#out-mode').value,bull_mode:root.querySelector('#bull-mode').value,max_rounds:Number(root.querySelector('#max-rounds').value)};
}
function gameSummary(settings) {
  const g=settings || {base_score:501,length_mode:'best_of',length:3,in_mode:'Straight',out_mode:'Double'};
  return `${g.base_score} · ${g.length_mode==='best_of'?'Best of':'First to'} ${g.length} · ${g.in_mode} In / ${g.out_mode} Out · Bull-off aus`;
}
async function integrationApi(path,body) {
  return api(path,{method:'POST',body:JSON.stringify(body)});
}
async function renderIntegration() {
  const data=await api('/api/integration');
  if(state.page!=='integration')return;
  main.innerHTML=`<div class="page-heading"><div><span class="eyebrow">AUTODARTS</span><h1>Scheiben verbinden</h1></div><button class="button" data-integration-refresh>↻ Aktualisieren</button></div>
  <p class="rule-note">Pro Board-PC das passende Tampermonkey-Script installieren und die geschützte Turnier-Website einmal im selben Browser anmelden. Zugewiesene Accounts müssen im Board-Account als Freunde bestätigt sein; andere Spieler werden als lokale Gäste angelegt. Die Accounts im Portal anmelden und Einladungen automatisch annehmen lassen. Im Turnier anschließend „Autodarts starten“ wählen.</p>
  <div class="detail-actions">${['Blau','Rot','Schwarz'].map(name=>`<a class="button" href="/static/turnier-${name.toLowerCase()}.user.js">${name}: Script installieren</a>`).join('')}</div>
  <p class="field-hint">Je PC nur das Script seiner Scheibe installieren. Das bisherige automatische Script deaktivieren. Vollbild über ⛶ oder F11 aktivieren, falls der Browser den automatischen Start blockiert.</p>
  <div class="bridge-grid">${data.boards.map(b=>`<section class="bridge-card"><h3><i class="dot ${boardColor(b.name)}"></i>${esc(b.name)} <span class="badge ${b.online?'active':''}">${b.online?'Online':'Offline'}</span></h3><p class="field-hint">${esc(b.status || 'Script noch nicht verbunden')}</p><p class="board-ident">${esc(b.board_id)}</p></section>`).join('')}</div>
  <h3>Verknüpfte Begegnungen</h3>${data.jobs.length?data.jobs.map(j=>`<div class="bridge-job"><div><strong>${esc(j.board)} · Spiel ${j.number}</strong><p>${esc(({queued:'Vorbereiten',creating:'Lobby-Erstellung',lobby:'Einladungen / Lobby',starting:'Matchstart',playing:'Match läuft',restarting:'Lobby-Neustart'})[j.phase] || j.phase)}${j.error?' · '+esc(j.error):''}</p>${j.autodarts_match_id?`<a href="https://play.autodarts.com/matches/${encodeURIComponent(j.autodarts_match_id)}" target="_blank" rel="noopener">Autodarts-Match öffnen</a>`:j.lobby_id?`<a href="https://play.autodarts.com/lobby/${encodeURIComponent(j.lobby_id)}" target="_blank" rel="noopener">Autodarts-Lobby öffnen</a>`:''}</div><div class="detail-actions">${j.phase==='lobby'?`<button class="button small danger" data-restart-lobby="${esc(j.id)}">Notfall: Lobby neu starten</button>`:''}${j.phase!=='restarting'?`<button class="button small" data-reset-job="${esc(j.id)}">Zuordnung zurücksetzen</button>`:''}</div></div>`).join(''):'<p class="field-hint">Keine offenen Verknüpfungen.</p>'}
  <p class="field-hint">Notfall-Neustart: alte Lobby löschen → 2 Sekunden warten → betroffene Accounts zur Startseite → 3 Sekunden warten → neue Lobby und Einladungen. Beide Websites und Board-Script benötigen Version 2.4.0. Accountzentrale auf dem Board-PC einmal anmelden (Tampermonkey-Menü). Laufende Matches können hier nicht neu gestartet werden.</p>
  <p class="field-hint">Bei unklarem Lobby-/Matchstart wird kein zweites Spiel erstellt. Automatik pausieren, bestehende Lobby bzw. Match in Autodarts beenden und erst dann die Zuordnung zurücksetzen. Abbrechen oder Löschen im Planer beendet kein Autodarts-Match.</p>`;
}
main.addEventListener('click',async e=>{
  const el=e.target.closest('button');if(!el)return;
  if(el.matches('[data-integration-refresh]')){try{await renderIntegration();}catch(error){toast(error.message);}}
  if(el.matches('[data-reset-job]')) {
    if(!confirm('Zuerst die Turnier-Automatik pausieren und die zugehörige Lobby bzw. das Match in Autodarts beenden. Ist das erledigt?'))return;
    try{await integrationApi(`/api/integration/jobs/${el.dataset.resetJob}/reset`,{});await renderIntegration();toast('Zuordnung zurückgesetzt.');}catch(error){toast(error.message);}
  }
  if(el.matches('[data-restart-lobby]')) {
    if(!confirm('Diese Lobby löschen und neu erstellen? Die betroffenen Spieler-Accounts werden in der Accountzentrale zur Autodarts-Startseite zurückgeführt und erneut eingeladen.'))return;
    el.disabled=true;
    try{await integrationApi(`/api/integration/jobs/${el.dataset.restartLobby}/restart`,{});await renderIntegration();toast('Lobby-Neustart angefordert.');}catch(error){el.disabled=false;toast(error.message);}
  }
});

main.addEventListener('click',e=>{
  if(!e.target.closest('[data-game-settings]'))return;
  const t=state.tournament;
  const modal=document.createElement('dialog');
  const fields=dialog.querySelector('.game-options').cloneNode(true);
  fields.querySelectorAll('[id]').forEach(el=>{el.dataset.setting=el.id;el.removeAttribute('id');});
  modal.innerHTML='<form><h2>Spielregeln</h2><p class="field-hint">Gelten für kommende Begegnungen. Bereits gespeicherte Ergebnisse bleiben erhalten.</p><p class="form-error" role="alert"></p><div class="detail-actions"><button class="button primary">Speichern</button><button class="button" type="button" data-cancel>Abbrechen</button></div></form>';
  const form=modal.querySelector('form');form.insertBefore(fields,form.querySelector('.form-error'));
  const keys={'base-score':'base_score','length-mode':'length_mode','match-length':'length','in-mode':'in_mode','out-mode':'out_mode','bull-mode':'bull_mode','max-rounds':'max_rounds'};
  fields.querySelectorAll('[data-setting]').forEach(el=>{el.value=t.game_settings[keys[el.dataset.setting]];});
  const close=()=>{modal.close();modal.remove();};modal.querySelector('[data-cancel]').onclick=close;
  modal.addEventListener('cancel',e=>{e.preventDefault();close();});
  form.onsubmit=async e=>{
    e.preventDefault();const settings={};
    fields.querySelectorAll('[data-setting]').forEach(el=>{const key=keys[el.dataset.setting];settings[key]=['base_score','length','max_rounds'].includes(key)?Number(el.value):el.value;});
    const button=form.querySelector('[type=submit]') || form.querySelector('.primary');button.disabled=true;
    try{const updated=await integrationApi(`/api/tournaments/${t.id}/game-settings`,settings);close();if(state.tournament?.id===t.id){state.tournament=updated;renderDetail();}toast('Spielregeln gespeichert.');}catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
  };
  document.body.append(modal);modal.showModal();
});
