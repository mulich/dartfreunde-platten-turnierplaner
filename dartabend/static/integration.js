let integrationKey = '';
function readGameSettings(root=document) {
  return {base_score:Number(root.querySelector('#base-score').value),length_mode:root.querySelector('#length-mode').value,length:Number(root.querySelector('#match-length').value),in_mode:root.querySelector('#in-mode').value,out_mode:root.querySelector('#out-mode').value,bull_mode:root.querySelector('#bull-mode').value,max_rounds:Number(root.querySelector('#max-rounds').value)};
}
function gameSummary(settings) {
  const g=settings || {base_score:501,length_mode:'best_of',length:3,in_mode:'Straight',out_mode:'Double'};
  return `${g.base_score} · ${g.length_mode==='best_of'?'Best of':'First to'} ${g.length} · ${g.in_mode} In / ${g.out_mode} Out · Bull-off aus`;
}
async function integrationApi(path, body) {
  if(!integrationKey) {
    await unlockIntegration();
  }
  try{return await api(path,{method:'POST',headers:{'X-Integration-Key':integrationKey},body:JSON.stringify(body)});}catch(error){if(error.status===401)integrationKey='';throw error;}
}
function unlockIntegration() {
  return new Promise((resolve,reject)=>{
    const modal=document.createElement('dialog');
    modal.innerHTML='<form><h2>Autodarts-Verwaltung</h2><label>Verwaltungsschlüssel<input type="password" name="key" autocomplete="off" required></label><p class="field-hint">TOURNAMENT_ADMIN_KEY aus der Docker-Konfiguration. Wird nur für diese geöffnete Seite verwendet.</p><div class="detail-actions"><button class="button primary">Entsperren</button><button class="button" type="button" data-cancel>Abbrechen</button></div></form>';
    document.body.append(modal);
    const cancel=()=>{modal.close();modal.remove();reject(new Error('Verwaltung nicht entsperrt.'));};
    modal.querySelector('[data-cancel]').onclick=cancel;
    modal.addEventListener('cancel',e=>{e.preventDefault();cancel();});
    modal.querySelector('form').onsubmit=e=>{e.preventDefault();integrationKey=modal.querySelector('input').value;modal.close();modal.remove();resolve();};
    modal.showModal();
  });
}
async function renderIntegration() {
  const data=await api('/api/integration');
  if(state.page!=='integration')return;
  main.innerHTML=`<div class="page-heading"><div><span class="eyebrow">AUTODARTS</span><h1>Scheiben verbinden</h1></div><button class="button" data-integration-refresh>↻ Aktualisieren</button></div>
  <p class="rule-note">Pro Board-PC das passende Tampermonkey-Script installieren und mit einem Board-Schlüssel verbinden. Alle Teilnehmer müssen im Board-Account als Freunde bestätigt sein. Die Accounts im Portal anmelden und Einladungen automatisch annehmen lassen. Im Turnier anschließend „Autodarts starten“ wählen.</p>
  <div class="bridge-grid">${data.boards.map(b=>`<section class="bridge-card"><h3><i class="dot ${boardColor(b.name)}"></i>${esc(b.name)} <span class="badge ${b.online?'active':''}">${b.online?'Online':'Offline'}</span></h3><p class="field-hint">${esc(b.status || (b.paired?'Script noch nicht verbunden':'Noch nicht eingerichtet'))}</p><p class="board-ident">${esc(b.board_id)}</p><div class="detail-actions"><a class="button small" href="https://dartportal.mulich.de/static/turnier-${b.name.toLowerCase()}.user.js">Script installieren</a><button class="button small" data-pair="${b.name}">${b.paired?'Neuer Schlüssel':'Schlüssel erzeugen'}</button></div><div data-pair-output="${b.name}"></div></section>`).join('')}</div>
  <h3>Verknüpfte Begegnungen</h3>${data.jobs.length?data.jobs.map(j=>`<div class="bridge-job"><div><strong>${esc(j.board)} · Spiel ${j.number}</strong><p>${esc(({queued:'Vorbereiten',creating:'Lobby-Erstellung',lobby:'Einladungen / Lobby',starting:'Matchstart',playing:'Match läuft'})[j.phase] || j.phase)}${j.error?' · '+esc(j.error):''}</p>${j.autodarts_match_id?`<a href="https://play.autodarts.com/matches/${encodeURIComponent(j.autodarts_match_id)}" target="_blank" rel="noopener">Autodarts-Match öffnen</a>`:j.lobby_id?`<a href="https://play.autodarts.com/lobby/${encodeURIComponent(j.lobby_id)}" target="_blank" rel="noopener">Autodarts-Lobby öffnen</a>`:''}</div><button class="button small" data-reset-job="${esc(j.id)}">Zuordnung zurücksetzen</button></div>`).join(''):'<p class="field-hint">Keine offenen Verknüpfungen.</p>'}
  <p class="field-hint">Bei unklarem Lobby-/Matchstart wird kein zweites Spiel erstellt. Automatik pausieren, bestehende Lobby bzw. Match in Autodarts beenden und erst dann die Zuordnung zurücksetzen. Abbrechen oder Löschen im Planer beendet kein Autodarts-Match.</p>`;
}
main.addEventListener('click',async e=>{
  const el=e.target.closest('button');if(!el)return;
  if(el.matches('[data-integration-refresh]')){try{await renderIntegration();}catch(error){toast(error.message);}}
  if(el.matches('[data-pair]')) {
    if(el.textContent==='Neuer Schlüssel'&&!confirm('Der bisherige Board-Schlüssel wird ungültig. Danach das Script neu verbinden?'))return;
    el.disabled=true;
    try {
      const result=await integrationApi(`/api/integration/boards/${encodeURIComponent(el.dataset.pair)}/pair`,{});
      const out=document.querySelector(`[data-pair-output="${el.dataset.pair}"]`);
      out.innerHTML='<label>Board-Schlüssel (jetzt kopieren)<input type="text" readonly autocomplete="off"></label><button class="button small" data-copy-key>Kopieren</button><p class="field-hint">Im Board-Script auf „Verbinden“ klicken. Der Schlüssel wird nur jetzt angezeigt.</p>';
      out.querySelector('input').value=result.key;
      out.querySelector('[data-copy-key]').onclick=async()=>{try{await navigator.clipboard.writeText(result.key);toast('Board-Schlüssel kopiert.');}catch{out.querySelector('input').select();toast('Schlüssel markieren und kopieren.');}};
    } catch(error){toast(error.message);}finally{el.disabled=false;}
  }
  if(el.matches('[data-reset-job]')) {
    if(!confirm('Zuerst die Turnier-Automatik pausieren und die zugehörige Lobby bzw. das Match in Autodarts beenden. Ist das erledigt?'))return;
    try{await integrationApi(`/api/integration/jobs/${el.dataset.resetJob}/reset`,{});await renderIntegration();toast('Zuordnung zurückgesetzt.');}catch(error){toast(error.message);}
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
