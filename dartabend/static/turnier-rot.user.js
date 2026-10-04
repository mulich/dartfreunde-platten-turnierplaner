// ==UserScript==
// @name         Dartfreunde Platten – Turnier-Board Rot
// @namespace    dartfreunde-platten-turnierplaner
// @version      2.1.2
// @description  Private Turnier-Lobbys, Einladungen und Ergebnisübernahme für Rot.
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
// @downloadURL  https://dartportal.mulich.de/static/turnier-rot.user.js
// @updateURL    https://dartportal.mulich.de/static/turnier-rot.user.js
// ==/UserScript==

(() => {
  'use strict';
  const BOARD = 'Rot';
  const BOARD_ID = 'ad381dc0-7e86-45a1-9fa8-61c8b18ec89b';
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
  function entries(job) {
    return job.participants || [job.match.player1,job.match.player2].map(name=>({name,account_name:name}));
  }
  function localKey(name) {return 'local:'+normalize(name);}
  function matchesPlayer(player,index,job,stats=false) {
    const entry=entries(job)[index];
    if(!entry.account_name)return !player.userId && !player.user?.id && normalize(player.name)===normalize(entry.name);
    const id=job.user_ids[index];
    const ident=player.userId || player.user?.id || (job.user_ids.includes(player.id)?player.id:null);
    return ident ? ident===id : stats && normalize(player.name)===normalize(entry.account_name);
  }
  function finalResult(state, stats, job) {
    if (state?.finished !== true || !Array.isArray(stats?.players) || stats.players.length !== 2 || !Array.isArray(stats.matchStats) || stats.matchStats.length !== 2) return null;
    const scores = job.user_ids.map((id, expectedIndex) => {
      const matches = stats.players.map((p, index) => ({p, index})).filter(({p})=>matchesPlayer(p,expectedIndex,job,true));
      if (matches.length !== 1) return null;
      const legs = stats.matchStats[matches[0].index]?.legsWon;
      return Number.isInteger(legs) && legs >= 0 ? legs : null;
    });
    if (scores.some(s => s === null) || Math.max(...scores) !== job.lobby_payload.legs || Math.min(...scores) >= job.lobby_payload.legs) return null;
    return {score1:scores[0], score2:scores[1], user_ids:job.user_ids, autodarts_match_id:job.autodarts_match_id};
  }
  function normalizeLobby(lobby, id) {
    if(!lobby || lobby.id!==id || !Object.hasOwn(lobby,'players'))throw new Error('Lobby-Antwort unvollständig. Wartet auf aktuellen Autodarts-Status.');
    // An empty Autodarts lobby may serialize its player list as null.
    const players=lobby.players===null?[]:lobby.players;
    if(!Array.isArray(players) || players.some(p=>!p || typeof p!=='object'))throw new Error('Lobby-Spielerliste nicht verfügbar. Wartet auf aktuellen Autodarts-Status.');
    return {...lobby,players};
  }
  function completePlayers(lobby,job) {
    return lobby.players.length===2 && !lobby.players.some(p=>p.isPending || p.cpuPPR)
      && job.user_ids.every((id,index)=>lobby.players.filter(p=>matchesPlayer(p,index,job)).length===1);
  }
  function correctLobby(lobby, job) {
    if (!lobby?.isPrivate || !Array.isArray(lobby.players)) return false;
    const expected=job.lobby_payload;
    if(lobby.variant!==expected.variant || lobby.legs!==expected.legs || lobby.bullOffMode!==expected.bullOffMode || Object.entries(expected.settings).some(([key,value])=>lobby.settings?.[key]!==value))return false;
    const players = lobby.players;
    return players.length === 2 && players.every(p => !p.isPending && !p.cpuPPR && p.boardId === BOARD_ID)
      && job.user_ids.every((id, index) => matchesPlayer(players[index],index,job));
  }
  function parseResponse(response, url) {
    const service = new URL(url).origin === SERVER ? 'planner' : 'autodarts';
    const label = service === 'planner' ? 'Turnierplaner' : 'Autodarts';
    const fail = text => { const error=new Error(`${label}: HTTP ${response.status} – ${text}`); error.status=response.status; error.service=service; throw error; };
    const successful=response.status>=200 && response.status<300;
    const text=typeof response.responseText==='string'?response.responseText.trim():'';
    if(response.status===401 && /(?:^|\r?\n)www-authenticate:\s*Basic\b/i.test(response.responseHeaders || '')) {
      fail(service==='planner'?'Website-Passwortschutz: turnier.mulich.de auf diesem PC im selben Browser öffnen und anmelden.':'Zusätzlicher Passwortschutz blockiert die API.');
    }
    let body;
    if(response.response && typeof response.response==='object')body=response.response;
    else if(!text && successful)return null;
    else {
      try{body=JSON.parse(text);}catch {
        fail(/^(?:<!doctype|<html|<head|<body)/i.test(text)?'HTML-Seite statt JSON. Passwortschutz, Weiterleitung und Proxy-Ziel prüfen.':'Keine JSON-Antwort. Proxy-Ziel und Serverstatus prüfen.');
      }
    }
    if(!successful)fail(typeof body?.detail==='string'?body.detail:body?.error?.message || 'Anfrage abgelehnt.');
    return body;
  }
  // Pure adapters are exercised using fixtures; requiring this file never enables automation.
  if (typeof module === 'object' && module.exports) {
    module.exports = {resolvePlayers, finalResult, correctLobby, parseResponse, matchesPlayer, localKey, normalizeLobby};
    return;
  }
  const instance = crypto.randomUUID();
  const storage = `dfp-turnier-${BOARD_ID}`;
  let config = {enabled:GM_getValue(storage, {enabled:true}).enabled!==false};
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
    return new Promise((resolve, reject) => GM_xmlhttpRequest({url, method, timeout:12000, anonymous:new URL(url).origin!==SERVER,
      headers:{'Content-Type':'application/json', ...headers}, data:data===undefined?undefined:JSON.stringify(data),
      onload:r=>{
        try{resolve(parseResponse(r,url));}catch(error){reject(error);}
      }, onerror:()=>reject(new Error('Verbindung fehlgeschlagen.')), ontimeout:()=>reject(new Error('Zeitüberschreitung.'))
    }));
  }
  const planner = (path, data) => request(SERVER+path, 'POST', {instance, ...data}, {'X-Board-ID':BOARD_ID});
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
    const planned=entries(job);
    let sub;
    try{sub=JSON.parse(atob(bearer.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sub;}catch{throw new Error('Account-Sitzung nicht erkannt.');}
    let friends=[],me=null;
    if(planned.some(p=>p.account_name)) {
      friends=await autodarts('/as/v0/friends');
      if(!Array.isArray(friends))throw new Error('Freundesliste nicht erkannt.');
      me=await autodarts(`/us/v0/users/${encodeURIComponent(sub)}`);
    }
    const users=planned.map(p=>p.account_name?resolvePlayers([p.account_name],friends,me)[0]:{id:localKey(p.name),name:p.name});
    if(users[0].id===users[1].id)throw new Error('Beide Spieler sind derselbe Teilnehmer.');
    // Commit the creation intent BEFORE the external write. An ambiguous failure cannot create a second lobby.
    job=await phase(job,'creating');
    GM_setValue(cacheKey,{job:job.id, stage:'creating'});
    const lobby=await autodarts('/gs/v0/lobbies','POST',job.lobby_payload);
    if(!lobby?.id)throw new Error('Lobby wurde nicht bestätigt. Automatik pausieren und in Autodarts prüfen.');
    GM_setValue(cacheKey,{job:job.id,lobby_id:lobby.id,user_ids:users.map(u=>u.id),host:sub});
    return phase(job,'lobby',{lobby_id:lobby.id,user_ids:users.map(u=>u.id)});
  }
  async function loadLobby(job) {
    return normalizeLobby(await autodarts(`/gs/v0/lobbies/${job.lobby_id}`),job.lobby_id);
  }
  async function arrange(job) {
    let lobby=await loadLobby(job);
    let account;try{account=JSON.parse(atob(bearer.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'))).sub;}catch{}
    if(!account||lobby.host?.id!==account||lobby.isPrivate!==true)throw new Error('Private Gastgeber-Lobby nicht bestätigt.');
    // Newly created lobbies may contain the board account. Keep it only if it is one of the scheduled players.
    const hostIndex=lobby.players.findIndex(p=>p.userId===lobby.host.id && !job.user_ids.includes(p.userId));
    if(hostIndex>=0) {
      await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players/by-index/${hostIndex}`,'DELETE');
      lobby=await loadLobby(job);
    }
    if(lobby.players.some(p=>!job.user_ids.some((id,index)=>matchesPlayer(p,index,job))))throw new Error('Unerwarteter Teilnehmer in der Lobby. Manuell prüfen.');
    const record=GM_getValue(cacheKey,{job:job.id});
    record.invited=record.invited || [];
    record.locals=record.locals || [];
    for(let index=0;index<job.user_ids.length;index++) {
      const id=job.user_ids[index],entry=entries(job)[index];
      if(lobby.players.some(p=>matchesPlayer(p,index,job)))continue;
      if(!entry.account_name) {
        if(record.locals.includes(id))throw new Error('Lokaler Spieler nicht bestätigt. Automatik pausieren und Lobby prüfen; Zuordnung ggf. zurücksetzen.');
        record.locals.push(id);GM_setValue(cacheKey,record);
        await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players`,'POST',{name:entry.name,boardId:BOARD_ID});
      }else if(!record.invited.includes(id)) {
        record.invited.push(id);GM_setValue(cacheKey,record);
        await autodarts(`/gs/v0/lobbies/${job.lobby_id}/invitations/${encodeURIComponent(id)}`,'POST');
      }
      lobby=await loadLobby(job);
    }
    lobby=await loadLobby(job);
    if(lobby.players.length!==2 || lobby.players.some(p=>p.isPending)) {show('Wartet auf die Annahme der Account-Einladungen');return job;}
    for(let index=0;index<lobby.players.length;index++) {
      if(lobby.players[index].boardId!==BOARD_ID)await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players/by-index/${index}/host`,'PUT',{boardId:BOARD_ID});
    }
    lobby=await loadLobby(job);
    if(!completePlayers(lobby,job)){show('Wartet auf vollständige Lobby-Spielerliste');return job;}
    for(let target=0;target<job.user_ids.length;target++) {
      const index=lobby.players.findIndex(p=>matchesPlayer(p,target,job));
      if(index<0){show('Wartet auf bestätigte Teilnehmer');return job;}
      if(index!==target) {
        await autodarts(`/gs/v0/lobbies/${job.lobby_id}/players/move/to-index`,'POST',{index,toIndex:target});
        lobby=await loadLobby(job);
        if(!completePlayers(lobby,job)){show('Wartet auf vollständige Lobby-Spielerliste');return job;}
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
    if(ticking||!config.enabled)return;
    ticking=true;
    try {
      let ready=false;
      try{ready=await boardReady();}catch(error){show(error.message);}
      const reply=await planner('/api/bridge/poll',{ready,status:bearer?message:'Wartet auf Autodarts-Anmeldung'});
      if(reply.completed_match_id)GM_setValue(storage+'-last-match',reply.completed_match_id);
      if(!reply || typeof reply!=='object' || !Object.hasOwn(reply,'job'))throw new Error('Turnierplaner: Board-Antwort unvollständig. Container-Version und Proxy-Ziel prüfen.');
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
      if(error.status===401 && error.service==='autodarts')bearer='';
      show(error.message);
      if(currentJob)try{await planner(`/api/bridge/jobs/${currentJob.id}/state`,{phase:currentJob.phase,error:error.message.slice(0,240)});}catch{}
    } finally {ticking=false;}
  }
  function configure() {
    unsafeWindow.open(SERVER+'/#integration','_blank','noopener');
    show('Turnierplaner im geöffneten Tab anmelden; danach Script fortsetzen.');
  }
  function toggle() {config.enabled=!config.enabled;GM_setValue(storage,config);show(config.enabled?'Automatik aktiv':'Board-Script pausiert');tick();}
  GM_registerMenuCommand(`Turnier-Board ${BOARD}: Website anmelden`,configure);
  GM_registerMenuCommand(`Turnier-Board ${BOARD}: starten/pausieren`,toggle);
  function mount() {
    if(!document.body)return;
    panel=document.createElement('div');
    panel.style.cssText='position:fixed;bottom:12px;right:12px;z-index:9999;background:#142a40;color:#cce6ff;border:1px solid #395f80;border-radius:8px;padding:12px;font:12px system-ui;max-width:340px;box-shadow:0 4px 18px #0005';
    let collapsed=GM_getValue(storage+'-collapsed',true);
    const title=document.createElement('button');title.type='button';
    title.style.cssText='display:block;background:transparent;color:#cce6ff;border:0;padding:0;cursor:pointer;font:600 12px system-ui;line-height:20px';
    const details=document.createElement('div');details.id='dfp-board-details-'+BOARD_ID;
    title.setAttribute('aria-controls',details.id);
    function renderFold() {
      title.textContent=collapsed?`Darts · ${BOARD} ▸`:`Turnierplaner · ${BOARD} ▾`;
      title.setAttribute('aria-label',collapsed?'Turnierfenster ausklappen':'Turnierfenster einklappen');
      title.setAttribute('aria-expanded',String(!collapsed));
      details.hidden=collapsed;details.style.display=collapsed?'none':'block';
      panel.style.padding=collapsed?'5px 8px':'12px';
    }
    title.onclick=()=>{collapsed=!collapsed;GM_setValue(storage+'-collapsed',collapsed);renderFold();};

    const status=document.createElement('p');status.dataset.status='';status.style.cssText='margin:6px 0;overflow-wrap:anywhere';status.textContent=message;
    const setup=document.createElement('button');setup.textContent='Website anmelden';setup.onclick=configure;
    const pause=document.createElement('button');pause.textContent='Start / Pause';pause.onclick=toggle;
    for(const button of [setup,pause])button.style.cssText='background:#254b6a;color:#fff;border:1px solid #527795;border-radius:4px;padding:5px 8px;margin-right:6px;cursor:pointer';
    details.append(status,setup,pause);panel.append(title,details);renderFold();document.body.append(panel);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
  setInterval(tick,4000);
})();
