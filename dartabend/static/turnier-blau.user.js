// ==UserScript==
// @name         Dartfreunde Platten – Turnier-Board Blau
// @namespace    dartfreunde-platten-turnierplaner
// @version      2.0.0
// @description  Private Turnier-Lobbys, Einladungen und Ergebnisübernahme für Blau.
// @match        https://play.autodarts.com/*
// @run-at       document-start
// @noframes
// @grant        unsafeWindow
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @connect      turnier.mulich.de
// @connect      api.autodarts.com
// @downloadURL  https://dartportal.mulich.de/static/turnier-blau.user.js
// @updateURL    https://dartportal.mulich.de/static/turnier-blau.user.js
// ==/UserScript==

(() => {
  'use strict';
  const BOARD = 'Blau';
  const BOARD_ID = 'faa2cd5f-5d19-4e68-9749-1b7b95c753d4';
  const SERVER = 'https://turnier.mulich.de';
  const API = 'https://api.autodarts.com';
  const normalize = value => String(value || '').trim().toLocaleLowerCase('de');
  function resolvePlayers(names, friends, me) {
    const users = [me, ...friends.filter(f => f.requestStatus === 'Accepted').map(f => f.user)].filter(Boolean);
    return names.map(name => {
      const found = [...new Map(users.filter(u => normalize(u.name) === normalize(name)).map(u => [u.id, u])).values()];
      if (found.length !== 1 || !found[0].id) throw new Error(`Account „${name}“ nicht eindeutig gefunden. Im Board-Account als Freund hinzufügen und Anfrage annehmen.`);
      return found[0];
    });
  }
  function finalResult(state, stats, job) {
    if (state?.finished !== true || !Array.isArray(stats?.players) || stats.players.length !== 2 || !Array.isArray(stats.matchStats) || stats.matchStats.length !== 2) return null;
    const scores = job.user_ids.map((id, expectedIndex) => {
      const matches = stats.players.map((p, index) => ({p, index})).filter(({p}) => {
        const ident = p.userId || p.user?.id || (job.user_ids.includes(p.id)?p.id:null);
        return ident ? ident === id : normalize(p.name) === normalize(expectedIndex === 0 ? job.match.player1 : job.match.player2);
      });
      if (matches.length !== 1) return null;
      const legs = stats.matchStats[matches[0].index]?.legsWon;
      return Number.isInteger(legs) && legs >= 0 ? legs : null;
    });
    if (scores.some(s => s === null) || Math.max(...scores) !== job.lobby_payload.legs || Math.min(...scores) >= job.lobby_payload.legs) return null;
    return {score1:scores[0], score2:scores[1], user_ids:job.user_ids, autodarts_match_id:job.autodarts_match_id};
  }
  function correctLobby(lobby, job) {
    if (!lobby?.isPrivate || !Array.isArray(lobby.players)) return false;
    const expected=job.lobby_payload;
    if(lobby.variant!==expected.variant || lobby.legs!==expected.legs || lobby.bullOffMode!==expected.bullOffMode || Object.entries(expected.settings).some(([key,value])=>lobby.settings?.[key]!==value))return false;
    const players = lobby.players;
    return players.length === 2 && players.every(p => !p.isPending && !p.cpuPPR && p.boardId === BOARD_ID)
      && job.user_ids.every((id, index) => players[index]?.userId === id);
  }
  // Pure adapters are exercised using fixtures; requiring this file never enables automation.
  if (typeof module === 'object' && module.exports) {
    module.exports = {resolvePlayers, finalResult, correctLobby};
    return;
  }
  const instance = crypto.randomUUID();
  const storage = `dfp-turnier-${BOARD_ID}`;
  let config = GM_getValue(storage, {key:'', enabled:false});
  let bearer = '';
  let message = 'Automatik aus';
  let ticking = false;
  let panel;
  let currentJob;
  const cacheKey = storage + '-pending';
  const acceptedUrl = url => {
    try { return new URL(url, location.href).origin === API; } catch { return false; }
  };
  function capture(value) {
    const match = typeof value === 'string' && value.match(/^Bearer\s+(.+)$/i);
    if (match) bearer = match[1];
  }
  // Observe only requests to the exact Autodarts API origin; never log or transmit credentials to the planner.
  const requests = new WeakMap();
  const xhr = unsafeWindow.XMLHttpRequest.prototype;
  const open = xhr.open, header = xhr.setRequestHeader;
  xhr.open = function(method, url, ...rest) { requests.set(this, acceptedUrl(url)); return open.call(this, method, url, ...rest); };
  xhr.setRequestHeader = function(name, value) { if(requests.get(this) && String(name).toLowerCase() === 'authorization')capture(value); return header.call(this, name, value); };
  const originalFetch = unsafeWindow.fetch;
  unsafeWindow.fetch = function(input, options) {
    const url = typeof input === 'string' ? input : input?.url;
    if(acceptedUrl(url)) {
      const headers = new Headers(options?.headers || input?.headers);
      capture(headers.get('authorization'));
    }
    return originalFetch.call(this, input, options);
  };
  function show(text) { message = text; if(panel)panel.querySelector('[data-status]').textContent=text; }
  function request(url, method='GET', data, headers={}) {
    return new Promise((resolve, reject) => GM_xmlhttpRequest({url, method, timeout:12000, anonymous:true,
      headers:{'Content-Type':'application/json', ...headers}, data:data===undefined?undefined:JSON.stringify(data),
      onload:r=>{
        let body;try{body=r.responseText?JSON.parse(r.responseText):null;}catch{return reject(new Error('Unbekanntes Antwortformat.'))}
        if(r.status>=200&&r.status<300)return resolve(body);
        const error=new Error(typeof body?.detail==='string'?body.detail:body?.error?.message || `HTTP ${r.status}`);
        error.status=r.status;reject(error);
      }, onerror:()=>reject(new Error('Verbindung fehlgeschlagen.')), ontimeout:()=>reject(new Error('Zeitüberschreitung.'))
    }));
  }
  const planner = (path, data) => request(SERVER+path, 'POST', {instance, ...data}, {Authorization:'Bearer '+config.key});
  const autodarts = (path, method='GET', data) => {
    if(!bearer)throw new Error('Autodarts anmelden und Seite neu laden.');
    return request(API+path, method, data, {Authorization:'Bearer '+bearer});
  };
  async function phase(job, next, extra={}) {
    const r=await planner(`/api/bridge/jobs/${job.id}/state`, {phase:next, ...extra});
    currentJob=r.job;
    return r.job;
  }
  async function boardReady() {
    if(!bearer)return false;
    const info=await autodarts(`/bs/v0/boards/${BOARD_ID}`);
    if(info.id!==BOARD_ID)throw new Error('Board-ID stimmt nicht.');
    if(!info.matchId)return true;
    // A completed match may still be displayed on the board. Never displace an unrelated game.
    const last=GM_getValue(storage+'-last-match', '');
    if(info.matchId!==last)return false;
    const state=await autodarts(`/gs/v0/matches/${info.matchId}/state`);
    return state?.finished===true;
  }
  async function prepare(job) {
    const friends=await autodarts('/as/v0/friends');
    if(!Array.isArray(friends))throw new Error('Freundesliste nicht erkannt.');
    let sub;
    try{sub=JSON.parse(atob(bearer.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sub;}catch{throw new Error('Account-Sitzung nicht erkannt.');}
    const me=await autodarts(`/us/v0/users/${encodeURIComponent(sub)}`);
    const users=resolvePlayers([job.match.player1,job.match.player2],friends,me);
    if(users[0].id===users[1].id)throw new Error('Beide Spieler sind derselbe Account.');
    // Commit the creation intent BEFORE the external write. An ambiguous failure cannot create a second lobby.
    job=await phase(job,'creating');
    GM_setValue(cacheKey,{job:job.id, stage:'creating'});
    const lobby=await autodarts('/gs/v0/lobbies','POST',job.lobby_payload);
    if(!lobby?.id)throw new Error('Lobby wurde nicht bestätigt. Automatik pausieren und in Autodarts prüfen.');
    GM_setValue(cacheKey,{job:job.id,lobby_id:lobby.id,user_ids:users.map(u=>u.id),host:sub});
    return phase(job,'lobby',{lobby_id:lobby.id,user_ids:users.map(u=>u.id)});
  }
  async function arrange(job) {
    let lobby=await autodarts(`/gs/v0/lobbies/${job.lobby_id}`);
    let account;try{account=JSON.parse(atob(bearer.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sub;}catch{}
    if(!account||lobby.host?.id!==account||lobby.isPrivate!==true)throw new Error('Private Gastgeber-Lobby nicht bestätigt.');
    // Newly created lobbies may contain the board account. Keep it only if it is one of the scheduled players.
    const hostIndex=lobby.players.findIndex(p=>p.userId===lobby.host.id && !job.user_ids.includes(p.userId));
    if(hostIndex>=0) {
      await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players/by-index/${hostIndex}`,'DELETE');
      lobby=await autodarts(`/gs/v0/lobbies/${job.lobby_id}`);
    }
    if(lobby.players.some(p=>!job.user_ids.includes(p.userId)))throw new Error('Unerwarteter Teilnehmer in der Lobby. Manuell prüfen.');
    const record=GM_getValue(cacheKey,{job:job.id});
    record.invited=record.invited || [];
    for(const id of job.user_ids) {
      if(!lobby.players.some(p=>p.userId===id)&&!record.invited.includes(id)) {
        record.invited.push(id);GM_setValue(cacheKey,record);
        await autodarts(`/gs/v0/lobbies/${job.lobby_id}/invitations/${encodeURIComponent(id)}`,'POST');
      }
    }
    lobby=await autodarts(`/gs/v0/lobbies/${job.lobby_id}`);
    if(lobby.players.length!==2 || lobby.players.some(p=>p.isPending)) {show('Wartet auf die Annahme beider Einladungen');return job;}
    for(let index=0;index<lobby.players.length;index++) {
      if(lobby.players[index].boardId!==BOARD_ID)await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players/by-index/${index}/host`,'PUT',{boardId:BOARD_ID});
    }
    lobby=await autodarts(`/gs/v0/lobbies/${job.lobby_id}`);
    for(let target=0;target<job.user_ids.length;target++) {
      const index=lobby.players.findIndex(p=>p.userId===job.user_ids[target]);
      if(index!==target) {
        await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players/move/to-index`,'POST',{index,toIndex:target});
        lobby=await autodarts(`/gs/v0/lobbies/${job.lobby_id}`);
      }
    }
    if(!await boardReady()){show('Scheibe inzwischen belegt · wartet');return job;}
    if(!correctLobby(lobby,job))throw new Error('Spieler, Scheibe oder Anwurf konnten nicht bestätigt werden.');
    job=await phase(job,'starting');
    const started=await autodarts(`/gs/v0/lobbies/${job.lobby_id}/start`,'POST');
    if(!started?.id)throw new Error('Matchstart nicht bestätigt. Manuell prüfen.');
    GM_setValue(cacheKey,{job:job.id,lobby_id:job.lobby_id,user_ids:job.user_ids,autodarts_match_id:started.id});
    job=await phase(job,'playing',{autodarts_match_id:started.id});
    unsafeWindow.location.assign(`https://play.autodarts.com/matches/${started.id}`);
    return job;
  }
  async function watch(job) {
    const state=await autodarts(`/gs/v0/matches/${job.autodarts_match_id}/state`);
    if(state?.finished!==true) {show('Match läuft · Ergebnisübernahme aktiv');return;}
    let stats;
    try{stats=await autodarts(`/as/v0/matches/${job.autodarts_match_id}/stats`);}catch(e){if(e.status===404){show('Wartet auf gespeicherte Match-Statistik');return;}throw e;}
    const result=finalResult(state,stats,job);
    if(!result){show('Kein eindeutiges Endergebnis. Bitte Spielstand prüfen.');return;}
    await planner(`/api/bridge/jobs/${job.id}/result`,result);
    GM_setValue(storage+'-last-match',job.autodarts_match_id);
    GM_setValue(cacheKey,null);
    show(`Ergebnis ${result.score1}:${result.score2} übernommen`);
  }
  async function tick() {
    if(ticking||!config.enabled||!config.key)return;
    ticking=true;
    try {
      let ready=false;
      try{ready=await boardReady();}catch(error){show(error.message);}
      const reply=await planner('/api/bridge/poll',{ready,status:bearer?message:'Wartet auf Autodarts-Anmeldung'});
      if(reply.completed_match_id)GM_setValue(storage+'-last-match',reply.completed_match_id);
      currentJob=reply.job;
      if(!currentJob){show(reply.message || (ready?'Wartet auf nächste Begegnung':bearer?'Scheibe belegt · bestehendes Spiel zuerst beenden':'Autodarts anmelden und Seite neu laden'));return;}
      if(currentJob.paused){show('Turnier-Automatik pausiert oder beendet');return;}
      let job=currentJob;
      if(['queued','lobby'].includes(job.phase)&&!ready){show('Scheibe belegt oder Autodarts nicht bereit · wartet');return;}
      if(job.phase==='queued')job=await prepare(job);
      const cached=GM_getValue(cacheKey,null);
      if(job.phase==='creating') {
        if(cached?.job===job.id&&cached.lobby_id)job=await phase(job,'lobby',{lobby_id:cached.lobby_id,user_ids:cached.user_ids});
        else throw new Error('Lobby-Erstellung unklar. Automatik pausieren, Autodarts prüfen und Auftrag im Planer zurücksetzen.');
      }
      if(job.phase==='lobby')job=await arrange(job);
      if(job.phase==='starting') {
        if(cached?.job===job.id&&cached.autodarts_match_id)job=await phase(job,'playing',{autodarts_match_id:cached.autodarts_match_id});
        else throw new Error('Matchstart unklar. Automatik pausieren und Match in Autodarts prüfen.');
      }
      if(job.phase==='playing')await watch(job);
      currentJob=job;
    } catch(error) {
      if(error.status===401 && !String(error.message).includes('Board-Schlüssel'))bearer='';
      show(error.message);
      if(currentJob)try{await planner(`/api/bridge/jobs/${currentJob.id}/state`,{phase:currentJob.phase,error:error.message.slice(0,240)});}catch{}
    } finally {ticking=false;}
  }
  function configure() {
    const key=prompt(`Board ${BOARD}: Verbindungsschlüssel aus Turnierplaner → Autodarts einfügen.`, '');
    if(key===null)return;
    if(!/^[A-Za-z0-9_-]{30,100}$/.test(key.trim())){show('Ungültiger Board-Schlüssel');return;}
    config={key:key.trim(),enabled:true};GM_setValue(storage,config);show('Verbindet mit Turnierplaner …');tick();
  }
  function toggle() {config.enabled=!config.enabled;GM_setValue(storage,config);show(config.enabled?'Automatik aktiv':'Board-Script pausiert');tick();}
  GM_registerMenuCommand(`Turnier-Board ${BOARD}: verbinden`,configure);
  GM_registerMenuCommand(`Turnier-Board ${BOARD}: starten/pausieren`,toggle);
  function mount() {
    if(!document.body)return;
    panel=document.createElement('div');
    panel.style.cssText='position:fixed;bottom:12px;right:12px;z-index:9999;background:#142a40;color:#cce6ff;border:1px solid #395f80;border-radius:8px;padding:12px;font:12px system-ui;max-width:340px;box-shadow:0 4px 18px #0005';
    const title=document.createElement('strong');title.textContent=`Turnierplaner · ${BOARD}`;
    const status=document.createElement('p');status.dataset.status='';status.style.cssText='margin:6px 0;overflow-wrap:anywhere';status.textContent=message;
    const setup=document.createElement('button');setup.textContent='Verbinden';setup.onclick=configure;
    const pause=document.createElement('button');pause.textContent='Start / Pause';pause.onclick=toggle;
    for(const button of [setup,pause])button.style.cssText='background:#254b6a;color:#fff;border:1px solid #527795;border-radius:4px;padding:5px 8px;margin-right:6px;cursor:pointer';
    panel.append(title,status,setup,pause);document.body.append(panel);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
  setInterval(tick,4000);
})();
