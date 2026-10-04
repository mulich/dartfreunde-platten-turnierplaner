let statisticsData;
let statisticsSort='medal_points';
let statisticsSearch='';
const statisticsNumber=value=>Number(value).toLocaleString('de-DE');
const statisticsRate=value=>value===null?'—':value.toLocaleString('de-DE',{maximumFractionDigits:1})+' %';
function sortStatistics(players,metric) {
  const value=p=>p[metric]===null?-1:p[metric];
  return [...players].sort((a,b)=>value(b)-value(a) || b.gold-a.gold || b.silver-a.silver || b.bronze-a.bronze || a.name.localeCompare(b.name,'de'));
}
function statisticsLeaders(title,metric,players) {
  const rows=sortStatistics(players,metric).filter(p=>p[metric]>0).slice(0,5);
  const max=rows[0]?.[metric] || 1;
  return `<section class="statistics-leaders"><h3>${title}</h3>${rows.length?`<ol>${rows.map(p=>`<li><div class="statistics-leader-label"><span>${esc(p.name)}</span><strong>${statisticsNumber(p[metric])}</strong></div><div class="statistics-bar"><span style="width:${p[metric]/max*100}%"></span></div>${metric==='medal_points'?`<p class="statistics-medals"><span aria-label="${p.gold} Goldmedaillen">🥇 ${p.gold}</span><span aria-label="${p.silver} Silbermedaillen">🥈 ${p.silver}</span><span aria-label="${p.bronze} Bronzemedaillen">🥉 ${p.bronze}</span></p>`:''}</li>`).join('')}</ol>`:'<p class="field-hint">Noch keine Ergebnisse.</p>'}</section>`;
}
async function renderStatistics() {
  const data=await api('/api/statistics');
  if(state.page!=='statistics')return;
  statisticsData=data;
  const s=data.summary;
  main.innerHTML=`<div class="page-heading"><div><span class="eyebrow">DARTFREUNDE PLATTEN</span><h1>Statistik</h1><p class="detail-meta">Alle vergangenen Turniere</p></div><button class="button" data-statistics-refresh>↻ Aktualisieren</button></div>
  <div class="stats statistics-totals">${[[s.tournaments,'Turniere im Archiv','◷'],[s.players,'Spieler','♙'],[s.matches,'Gespielte Begegnungen','◎'],[s.legs,'Gespielte Legs','▥']].map(([value,label,icon])=>`<div class="stat"><div><div class="stat-number">${statisticsNumber(value)}</div><div class="stat-label">${label}</div></div><span class="stat-icon">${icon}</span></div>`).join('')}</div>
  <p class="rule-note">Erfasste Ergebnisse aus dem Archiv. Gold = 3 Punkte · Silber = 2 Punkte · Bronze = 1 Punkt. Medaillen nur für vollständig gewertete Turniere; gleiche Platzierungen teilen sich die Medaille. Laufende und abgebrochene Turniere zählen nicht.${s.missing_results?` ${s.missing_results} Ergebnisse aus ${s.incomplete_tournaments} unvollständigen Turnieren fehlen.`:''}${s.excluded_aborted?` ${s.excluded_aborted} abgebrochene Turniere ausgeschlossen.`:''} Frühere Spielernamen werden dem aktuellen Spielerprofil zugeordnet.</p>
  ${data.players.length?`<div class="statistics-highlights">${statisticsLeaders('Medaillenspiegel','medal_points',data.players)}${statisticsLeaders('Meiste gewonnene Legs','legs_for',data.players)}${statisticsLeaders('Meiste Spielsiege','wins',data.players)}</div>
  <div class="section-heading statistics-table-heading"><h3>Spieler im Vergleich</h3><div class="statistics-controls"><label>Sortierung<select id="statistics-sort">${[['medal_points','Medaillenpunkte'],['medals','Medaillenanzahl'],['gold','Turniersiege'],['legs_for','Gewonnene Legs'],['difference','Leg-Differenz'],['wins','Spielsiege'],['win_rate','Siegquote'],['leg_win_rate','Legquote'],['tournaments','Teilnahmen']].map(([value,label])=>`<option value="${value}" ${statisticsSort===value?'selected':''}>${label}</option>`).join('')}</select></label><input class="search" id="statistics-search" type="search" aria-label="Spieler suchen" placeholder="Spieler suchen …" value="${esc(statisticsSearch)}"></div></div><div id="statistics-table"></div>`:'<div class="empty"><span class="empty-symbol">▥</span><h3>Noch keine Statistik</h3><p>Turniere abschließen oder vergangene Turniere importieren.</p><a class="button" href="#archive">Zum Archiv</a></div>'}`;
  if(data.players.length) {
    renderStatisticsTable();
    document.querySelector('#statistics-sort').onchange=e=>{statisticsSort=e.target.value;renderStatisticsTable();};
    document.querySelector('#statistics-search').oninput=e=>{statisticsSearch=e.target.value;renderStatisticsTable();};
  }
}
function renderStatisticsTable() {
  const sorted=sortStatistics(statisticsData.players,statisticsSort);
  let rank=0,previous;
  const ranked=sorted.map((p,index)=>{if(p[statisticsSort]!==previous){rank=index+1;previous=p[statisticsSort];}return {...p,rank};});
  const rows=ranked.filter(p=>p.name.toLocaleLowerCase('de').includes(statisticsSearch.toLocaleLowerCase('de').trim()));
  document.querySelector('#statistics-table').innerHTML=rows.length?`<div class="table-wrap standings-wrap"><table class="standings-table statistics-table" aria-label="Statistik aller vergangenen Turniere"><thead><tr><th scope="col">Platz</th><th scope="col">Spieler</th><th scope="col">Medaillenpunkte</th><th scope="col">Medaillen</th><th scope="col">🥇<span class="sr-only"> Gold / Turniersiege</span></th><th scope="col">🥈<span class="sr-only"> Silber</span></th><th scope="col">🥉<span class="sr-only"> Bronze</span></th><th scope="col">Turniere</th><th scope="col">Spiele</th><th scope="col">Siege</th><th scope="col">Niederlagen</th><th scope="col">Siegquote</th><th scope="col">Legs +</th><th scope="col">Legs −</th><th scope="col">Differenz</th><th scope="col">Legquote</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${p.rank}</td><th scope="row" class="standing-player">${esc(p.name)}</th><td><span class="points-pill">${p.medal_points}</span></td><td>${p.medals}</td><td>${p.gold}</td><td>${p.silver}</td><td>${p.bronze}</td><td>${p.tournaments}</td><td>${p.played}</td><td>${p.wins}</td><td>${p.losses}</td><td>${statisticsRate(p.win_rate)}</td><td>${p.legs_for}</td><td>${p.legs_against}</td><td class="${p.difference>0?'difference-positive':p.difference<0?'difference-negative':''}">${p.difference>0?'+':''}${p.difference}</td><td>${statisticsRate(p.leg_win_rate)}</td></tr>`).join('')}</tbody></table></div><p class="table-note">Siegquote = gewonnene Spiele / gespielte Spiele · Legquote = gewonnene Legs / gespielte Legs. Platzierung nach der gewählten Kennzahl; gleiche Werte teilen sich den Platz.</p>`:'<p class="field-hint">Kein passender Spieler.</p>';
}
main.addEventListener('click',async e=>{
  const button=e.target.closest('[data-statistics-refresh]');if(!button)return;
  button.disabled=true;
  try{await renderStatistics();}catch(error){toast(error.message);button.disabled=false;}
});
