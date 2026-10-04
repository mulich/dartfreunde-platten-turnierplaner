let profiles=[];
const accountBadge=name=>(state.tournament?.player_accounts?.[name] || profiles.find(p=>playerKey(p.name)===playerKey(name))?.account_name)?'<span class="account-check" title="Autodarts-Account zugewiesen" aria-label="Autodarts-Account zugewiesen">✓</span>':'';
async function renderPlayers() {
  profiles=await api('/api/player-profiles');
  if(state.page!=='players')return;
  main.innerHTML=`<div class="page-heading"><div><span class="eyebrow">SPIELERVERWALTUNG</span><h1>Spieler</h1></div><button class="button" data-players-refresh>↻ Aktualisieren</button></div><p class="rule-note">Optional einen Autodarts-Account zuweisen. Ohne Account wird der Spieler als lokaler Gast an der Scheibe angelegt. Änderungen gelten für noch nicht verknüpfte Begegnungen; vergangene Ergebnisse behalten ihre Namen.</p><form id="new-profile" class="profile-row"><label>Spielername<input name="name" required maxlength="60" placeholder="Name im Turnier"></label><label>Autodarts-Account<input name="account_name" maxlength="60" placeholder="Optional · exakter Accountname"></label><button class="button primary">＋ Hinzufügen</button><p class="form-error" role="alert"></p></form><div class="profile-list">${profiles.map(p=>`<form class="profile-row" data-profile="${p.id}" data-revision="${p.revision}"><label>Spielername ${accountBadge(p.name)}<input name="name" value="${esc(p.name)}" required maxlength="60"></label><label>Autodarts-Account<input name="account_name" value="${esc(p.account_name || '')}" maxlength="60" placeholder="Lokaler Spieler"></label><div class="detail-actions"><button class="button small">Speichern</button><button type="button" class="button small danger" data-remove-profile>Entfernen</button></div><p class="form-error" role="alert"></p></form>`).join('')}</div>`;
}
main.addEventListener('submit',async e=>{
  const form=e.target;
  if(!form.matches('#new-profile,[data-profile]'))return;
  e.preventDefault();const button=form.querySelector('button');button.disabled=true;
  const data=new FormData(form),body={name:data.get('name'),account_name:data.get('account_name'),revision:Number(form.dataset.revision || 0)};
  try{await api('/api/player-profiles'+(form.dataset.profile?'/'+form.dataset.profile:''),{method:form.dataset.profile?'PUT':'POST',body:JSON.stringify(body)});if(state.page==='players')await renderPlayers();toast('Spieler gespeichert.');}catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
});
main.addEventListener('click',async e=>{
  if(e.target.closest('[data-players-refresh]')){try{await renderPlayers();}catch(error){toast(error.message);}return;}
  const button=e.target.closest('[data-remove-profile]');if(!button)return;
  if(!confirm('Spieler aus der Auswahlliste entfernen? Vergangene Turniere und laufende Begegnungen bleiben erhalten.'))return;
  const form=button.closest('form');button.disabled=true;
  try{await api(`/api/player-profiles/${form.dataset.profile}?revision=${form.dataset.revision}`,{method:'DELETE'});await renderPlayers();toast('Spieler aus der Liste entfernt.');}catch(error){form.querySelector('.form-error').textContent=error.message;button.disabled=false;}
});
