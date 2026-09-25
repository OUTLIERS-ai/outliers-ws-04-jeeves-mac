// app.js - the Jeeves cockpit. Every ability is a panel you can drag, dock, tab,
// close, re-open (+ Panel) and pop out into its own window (the square button).
// Your layout is saved in this browser and comes back next time.
//
// One lesson from the original is built in: a panel's content is wired up when
// the panel MOUNTS, never at page load. The original's Status panel looked for
// its box before the layout had built it, and stayed empty.
import { createDockview } from '/static/vendor/dockview/dockview-core.esm.min.js';

const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (p) => { const r = await fetch(p); return r.json(); };
const fmt = n => { n = +n || 0; if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B'; if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'; if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k'; return '' + n; };
let CFG = { name: 'Jeeves', models: { best: 'claude-opus-5-5', deep: 'claude-sonnet-5', fast: 'claude-haiku-4-5' } };
let orbTop = null, orbBig = null;

// ------------------------------------------------------------------ markdown
// A small, safe renderer: everything is escaped first, so a note can never run code.
function inline(s) {
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>');
  s = s.replace(/(^|\s)_([^_\s][^_]*)_(?=\s|$|[.,;:!?])/g, '$1<i>$2</i>');
  s = s.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (m, a, b) => `<span class="wl" data-note="${a}">${b || a}</span>`);
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}
function md(text) {
  text = String(text || '').replace(/\r/g, '');
  if (text.startsWith('---\n')) { const e = text.indexOf('\n---', 4); if (e > 0) text = text.slice(text.indexOf('\n', e + 1) + 1); }
  const L = text.split('\n'), out = [];
  let i = 0;
  while (i < L.length) {
    let l = L[i];
    if (/^```/.test(l)) { const buf = []; i++; while (i < L.length && !/^```/.test(L[i])) buf.push(L[i++]); i++; out.push('<pre>' + esc(buf.join('\n')) + '</pre>'); continue; }
    let m = l.match(/^(#{1,4})\s+(.*)$/);
    if (m) { out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`); i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < L.length && /^\s*\|[\s:|-]+\|\s*$/.test(L[i + 1])) {
      const row = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const h = row(l); i += 2; const rows = [];
      while (i < L.length && /^\s*\|.*\|\s*$/.test(L[i])) rows.push(row(L[i++]));
      out.push('<table><tr>' + h.map(c => '<th>' + inline(c) + '</th>').join('') + '</tr>' + rows.map(r => '<tr>' + r.map(c => '<td>' + inline(c) + '</td>').join('') + '</tr>').join('') + '</table>');
      continue;
    }
    if (/^\s*[-*]\s+/.test(l)) {
      const items = [];
      while (i < L.length && /^\s*[-*]\s+/.test(L[i])) {
        let t = L[i].replace(/^\s*[-*]\s+/, ''); let cls = '';
        const tm = t.match(/^\[( |x|X)\]\s*(.*)$/);
        if (tm) { cls = ' class="task"'; t = (tm[1] === ' ' ? '☐ ' : '☑ ') + tm[2]; }
        items.push(`<li${cls}>` + inline(t) + '</li>'); i++;
      }
      out.push('<ul>' + items.join('') + '</ul>'); continue;
    }
    if (/^\s*\d+\.\s+/.test(l)) {
      const items = [];
      while (i < L.length && /^\s*\d+\.\s+/.test(L[i])) items.push('<li>' + inline(L[i++].replace(/^\s*\d+\.\s+/, '')) + '</li>');
      out.push('<ol>' + items.join('') + '</ol>'); continue;
    }
    if (/^>\s?/.test(l)) { const buf = []; while (i < L.length && /^>\s?/.test(L[i])) buf.push(L[i++].replace(/^>\s?/, '')); out.push('<blockquote>' + inline(buf.join(' ')) + '</blockquote>'); continue; }
    if (/^\s*(---|\*\*\*)\s*$/.test(l)) { out.push('<hr>'); i++; continue; }
    if (!l.trim()) { i++; continue; }
    const buf = [];
    while (i < L.length && L[i].trim() && !/^(#{1,4}\s|```|\s*[-*]\s|\s*\d+\.\s|>|\s*\|)/.test(L[i])) buf.push(L[i++]);
    if (!buf.length) buf.push(L[i++]);
    out.push('<p>' + inline(buf.join(' ')) + '</p>');
  }
  return '<div class="md">' + out.join('\n') + '</div>';
}

// ------------------------------------------------------------------ panel shell
function shell(hint, bodyClass = '') {
  const d = document.createElement('div');
  d.className = 'pane';
  d.innerHTML = `<div class="ptools"><span class="hint">${esc(hint)}</span><button class="refresh" title="Refresh">↻</button><button class="pop" title="Pop out into its own window">⧉</button></div><div class="pbody ${bodyClass}"></div>`;
  return d;
}
function wire(el, name, refresh) {
  el.querySelector('.refresh').onclick = refresh;
  el.querySelector('.pop').onclick = () => popout(name);
  el.__refresh = refresh;
  refresh();
}
function popout(name) {
  window.open(location.origin + '/?only=' + encodeURIComponent(name), 'jeeves-' + name, 'width=1100,height=800');
}
function setStatus(t) { const s = $('#status-line'); if (s) s.textContent = t; }

// ------------------------------------------------------------------ Chat
// Rules learned the hard way (usability audit, 2026-09-22):
// - 1 message at a time. Enter while an answer is coming in does not send; the
//   server refuses a second run too, so 2 answers can never race.
// - The conversation you can see is kept in this browser, so a reload shows it
//   again. Claude remembers it anyway; now you can see what it remembers.
// - Stop is not a crash: it shows a grey "Stopped" line, never a red error.
// - A failure says what went wrong in plain words and offers Try again.
const SESSION = 'main';
const TKEY = 'jeeves.chat.' + SESSION;
const FRIENDLY = {
  login: 'Claude Code is not logged in. Open a terminal, type claude, log in, then press Try again.',
  lost: 'Claude no longer had the earlier conversation, so Jeeves has let it go. Press Try again to start a fresh one.',
  not_found: 'Claude Code was not found on this computer. Install it, log in once by typing claude in a terminal, then restart Jeeves.',
  timeout: 'No answer came in time, so Jeeves stopped it.',
  busy: 'Still answering your last message. Wait for it to finish, or press Stop first.',
};
function chatPanel() {
  const d = document.createElement('div');
  d.className = 'pane';
  const power = CFG.read_only === false
    ? 'It can read your notes and CRM, and you have allowed it to act (allow_actions in config.json).'
    : 'It is given 3 tools and no others: open a file, search inside files, find files by name. '
      + 'Running commands, changing files and the internet are switched off until you set '
      + '"allow_actions": true in config.json.';
  d.innerHTML = `
    <div class="ptools"><span class="hint">Answered by your own Claude Code, in your second brain</span>
      <button class="sugg" title="Show the suggested questions">Suggestions</button>
      <button class="newchat" title="Start a fresh conversation">New conversation</button><button class="pop" title="Pop out">⧉</button></div>
    <div class="chat">
      <div class="chat-head"><div class="orb-big"><svg class="orb-svg"></svg></div>
        <div><div class="who">${esc(CFG.name)}</div><div class="sub">${esc(power)}</div></div></div>
      <div class="chips"></div>
      <div class="banner" style="display:none"></div>
      <div class="log"></div>
      <div class="composer"><textarea rows="1" placeholder="Ask ${esc(CFG.name)}… (Enter to send, Shift+Enter for a new line)"></textarea>
        <button class="btn send">Send</button><button class="btn ghost stop" style="display:none">Stop</button></div>
    </div>`;
  return d;
}
// The saved conversation is shared by every window on this computer: the main
// cockpit, a popped-out Chat, a second tab. Each window used to write its own whole
// list over the other's, so a message sent in the pop-out was wiped the moment the
// main window sent its next one. Now each window ADDS its own new lines to what is
// already saved, and is told when another window adds one.
const WINDOW_ID = Math.random().toString(36).slice(2, 8) + Date.now().toString(36);
let lineNo = 0;
const stampLine = it => { if (!it.id) it.id = WINDOW_ID + '-' + (++lineNo); return it; };
function loadTranscript() { try { return JSON.parse(localStorage.getItem(TKEY) || '[]'); } catch (e) { return []; } }
function saveTranscript(mine) {
  const saved = loadTranscript();
  const seen = new Set(saved.map(x => x.id).filter(Boolean));
  const merged = saved.concat(mine.filter(x => x.id && !seen.has(x.id))).slice(-200);
  try { localStorage.setItem(TKEY, JSON.stringify(merged)); } catch (e) {}
  return merged;
}
function clearTranscript() { try { localStorage.setItem(TKEY, '[]'); } catch (e) {} }
function mountChat(el) {
  el.querySelector('.pop').onclick = () => popout('chat');
  const chat = $('.chat', el), log = $('.log', el), ta = $('textarea', el), send = $('.send', el), stopb = $('.stop', el), banner = $('.banner', el);
  if (window.JeevesOrb && !orbBig) orbBig = window.JeevesOrb($('.orb-svg', el), CFG.orb || {});
  const chips = ['What needs me today?', 'Who in my CRM should I speak to first, and why?', 'Summarise what moved in my second brain this week', 'Which of my agents should I use to write a follow-up?'];
  $('.chips', el).innerHTML = chips.map(c => `<span class="chip">${esc(c)}</span>`).join('');
  $('.chips', el).onclick = e => { if (e.target.classList.contains('chip')) { ta.value = e.target.textContent; ta.focus(); chat.classList.remove('show-chips'); } };
  $('.sugg', el).onclick = () => chat.classList.toggle('show-chips');
  let items = loadTranscript();
  let busy = false, stopping = false;
  const compact = () => chat.classList.toggle('compact', log.children.length > 0);
  const add = (cls, html) => { const m = document.createElement('div'); m.className = cls; m.innerHTML = html; log.appendChild(m); log.scrollTop = log.scrollHeight; compact(); return m; };
  const orbs = s => { [orbTop, orbBig].forEach(o => o && o.setState(s)); };
  const draw = it => {
    if (it.role === 'you') return add('msg you', esc(it.text));
    if (it.role === 'bot') return add('msg bot', md(it.text));
    if (it.role === 'act') { const a = add('act', ''); a.textContent = it.text; return a; }
    if (it.role === 'stopped') return add('msg note', esc(it.text));
    if (it.role === 'err') return add('msg err', esc(it.text));
    return add('msg note', esc(it.text));
  };
  // Redraw the whole conversation, including anything another window added.
  const redrawAll = () => {
    if (busy) return;                       // an answer is being written into this log
    items = loadTranscript();
    log.innerHTML = '';
    items.forEach(draw);
    compact();
  };
  window.addEventListener('storage', e => { if (e.key === TKEY) redrawAll(); });
  // Redraw what this browser remembers, and say honestly what Claude remembers.
  items.forEach(draw);
  if (CFG.chat_updated) {
    const when = new Date(CFG.chat_updated);
    const w = isNaN(when) ? CFG.chat_updated : when.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    add('msg note', esc(items.length
      ? `Carrying on the conversation from ${w}. New conversation starts fresh.`
      : `Claude is carrying on a conversation last answered ${w}, but its messages were not saved in this browser. New conversation starts fresh.`));
  }
  if (CFG.claude_found === false) {
    // The address is a real link, and the suggestion buttons go away: they used to put
    // their question into a text box that was switched off, with nothing said about why.
    banner.style.display = '';
    banner.innerHTML = `<b>Claude Code was not found on this computer, so Chat cannot answer.</b> Every other panel works.
      <ol><li>Install Claude Code: <a href="https://code.claude.com/docs/en/setup" target="_blank" rel="noopener">code.claude.com/docs/en/setup</a></li><li>Open a new terminal and type <code>claude</code> once to log in.</li><li>Stop Jeeves and start it again.</li></ol>
      If it is installed somewhere unusual, put its full path in <code>config.json</code> as <code>"claude_command"</code>.`;
    ta.disabled = true; send.disabled = true;
    ta.placeholder = 'Chat is switched off until Claude Code is installed.';
    $('.chips', el).innerHTML = '';
    $('.sugg', el).style.display = 'none';
  }
  $('.newchat', el).onclick = async () => {
    if (busy) { sayHere('Press Stop first, then New conversation.'); return; }
    await fetch('/api/chat/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session: SESSION }) });
    log.innerHTML = ''; items = []; clearTranscript(); CFG.chat_updated = null; compact(); setStatus('New conversation.');
  };
  // Why a key press did nothing, said where the member is looking. The status line in
  // the top bar was 921 px away from the text box on a 1000 px-tall screen.
  const sayHere = t => {
    const old = log.querySelector('.msg.note.live'); if (old) old.remove();
    const m = add('msg note live', esc(t));
    setStatus(t);
    return m;
  };
  async function go(again) {
    const text = (again || ta.value).trim(); if (!text) return;
    if (busy) { sayHere('Still answering. Wait for that answer to finish, or press Stop.'); return; }
    busy = true; stopping = false;
    const live = log.querySelector('.msg.note.live'); if (live) live.remove();
    if (!again) ta.value = '';
    ta.style.height = 'auto';
    add('msg you', esc(text)); items.push(stampLine({ role: 'you', text }));
    const bot = add('msg bot', '<span class="dim">Thinking…</span>');
    let acc = '', gotText = false, failed = null, stopped = false;
    const acts = [];
    orbs('thinking'); setStatus('Working on it…'); send.disabled = true; stopb.style.display = '';
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, model: $('#model') ? $('#model').value : 'best', session: SESSION }) });
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done } = await rd.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let k;
        while ((k = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, k); buf = buf.slice(k + 2);
          if (!chunk.startsWith('data: ')) continue;
          let ev; try { ev = JSON.parse(chunk.slice(6)); } catch (e) { continue; }
          if (ev.type === 'delta') { if (!gotText) { orbs('speaking'); gotText = true; } acc += ev.text; bot.innerHTML = md(acc); }
          else if (ev.type === 'activity') { const a = document.createElement('div'); a.className = 'act'; a.textContent = ev.text; log.insertBefore(a, bot); acts.push(ev.text); setStatus(ev.text); }
          else if (ev.type === 'done') { if (ev.text) { acc = ev.text; bot.innerHTML = md(acc); } }
          else if (ev.type === 'stopped') { stopped = true; }
          else if (ev.type === 'error') { failed = ev; }
          log.scrollTop = log.scrollHeight;
        }
      }
    } catch (e) { if (!stopping) failed = { code: 'connection', text: 'Lost the connection to Jeeves: ' + e }; else stopped = true; }
    acts.forEach(a => items.push(stampLine({ role: 'act', text: a })));
    if (stopped || (stopping && !acc && !failed)) {
      if (!acc) bot.remove(); else items.push(stampLine({ role: 'bot', text: acc }));
      const t = acc ? 'Stopped. The part above is what Claude had written.' : 'Stopped before Claude wrote anything.';
      add('msg note', esc(t)); items.push(stampLine({ role: 'stopped', text: t }));
      setStatus('Stopped.');
    } else if (failed) {
      // Claude sometimes writes the error as its answer too: show it once, not twice.
      if (!acc.trim() || acc.trim() === (failed.text || '').trim()) bot.remove(); else items.push(stampLine({ role: 'bot', text: acc }));
      const plain = FRIENDLY[failed.code] || 'The reply failed.';
      const e = add('msg err', `${esc(plain)}<details><summary>Details</summary>${esc(failed.text || '')}</details>`);
      if (failed.code !== 'busy' && failed.code !== 'not_found') {
        const b = document.createElement('button'); b.className = 'btn small again'; b.textContent = 'Try again';
        b.onclick = () => { b.disabled = true; go(text); };
        e.appendChild(b);
      }
      items.push(stampLine({ role: 'err', text: plain }));
      setStatus(failed.code === 'busy' ? 'Still answering your last message.' : 'Last reply failed. Details are in the chat.');
    } else {
      if (!acc) bot.innerHTML = '<span class="dim">(Claude finished without writing anything)</span>';
      else items.push(stampLine({ role: 'bot', text: acc }));
      CFG.chat_updated = new Date().toISOString();
      setStatus('Ready.');
    }
    const before = items.length;
    items = saveTranscript(items);
    orbs('idle'); busy = false; send.disabled = false; stopb.style.display = 'none';
    if (items.length !== before) redrawAll();   // another window added a message meanwhile
  }
  send.onclick = () => go();
  stopb.onclick = () => { stopping = true; setStatus('Stopping…'); fetch('/api/chat/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session: SESSION }) }); };
  ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(); } });
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(160, ta.scrollHeight) + 'px'; });
  window.__jeevesAsk = (t) => { ta.value = t; ta.focus(); };
  window.__jeevesBusy = () => busy;
}

// ------------------------------------------------------------------ Today
// A folder that is not there is never reported as a quiet day. The Today panel used
// to say "Nothing has moved and nothing is left open" while the Vaults panel 300 px
// below it said the folder did not exist, and the loudest of the two was the wrong one.
function missingFolder(path, setting, refused) {
  // macOS refused Jeeves the folder: say so, never that it is missing (the server's words).
  if (refused) return `<div class="empty gone">${esc(refused)}</div>`;
  return `<div class="empty gone">Your ${setting === 'crm_vault' ? 'CRM' : 'second brain'} folder is not there:
    <code class="sel">${esc(path || '(not set)')}</code><br>
    Nothing can be read from it, so no count below is a real answer. Check
    <code>"${setting}"</code> in <code>config.json</code>, or plug the drive back in.</div>`;
}
const noteName = p => esc(String(p).split('/').pop().replace(/\.md$/, ''));
const noteDir = p => String(p).includes('/') ? esc(String(p).slice(0, String(p).lastIndexOf('/'))) : '';
async function renderToday(body) {
  const d = await api('/api/today');
  let h = '';
  if (d.crm) {
    h += `<div class="card"><h3>From your CRM${d.crm.built ? ' · built ' + esc(d.crm.built) : ''}</h3>`;
    h += d.crm.found ? md(d.crm.text)
      : (d.crm.exists === false ? missingFolder(d.crm.vault, 'crm_vault', d.crm.refused)
        : `<div class="empty">${esc(d.crm.hint)}</div>`);
    h += '</div>';
  } else h += '<div class="empty">No CRM folder is set in config.json, so there is no ranked list of people here.</div>';
  const b = d.brain;
  if (b) {
    h += '<div class="card"><h3>From your second brain</h3>';
    if (b.found === false) return void (body.innerHTML = h + missingFolder(b.path, 'second_brain', b.refused) + '</div>');
    if (b.daily) h += `<div class="dim">${esc(b.daily.path)}</div>` + md(b.daily.text);
    if (b.moved.length) h += '<div class="muted" style="margin-top:6px">Moved in the last 3 days</div><ul class="links">' + b.moved.map(m => `<li><span class="dim">${esc(m.when)}</span> <span class="wl" data-note="${esc(m.path)}">${noteName(m.path)}</span> <span class="dim">${noteDir(m.path)}</span></li>`).join('') + '</ul>';
    if (b.open.length) h += '<div class="muted" style="margin-top:6px">Left unfinished</div><ul>' + b.open.map(o => `<li>☐ ${inline(o.text)} <span class="dim">·</span> <span class="wl" data-note="${esc(o.path)}">${noteName(o.path)}</span></li>`).join('') + '</ul>';
    if (!b.daily && !b.moved.length && !b.open.length) h += '<div class="empty">Nothing has moved and nothing is left open. That is a real answer, not an empty one.</div>';
    h += '</div>';
  }
  body.innerHTML = h;
}

// ------------------------------------------------------------------ Vault browser
function vaultPanel() {
  const d = shell('Read-only. Type to filter names · Enter searches inside notes', 'flush');
  d.querySelector('.pbody').innerHTML = `<div class="vb"><div class="vb-side"><div class="vb-tabs"></div>
    <input type="search" placeholder="Filter names…" title="Type to filter this vault by note name. Press Enter to search inside every note in both vaults."><div class="vb-list"></div></div><div class="vb-note"><div class="empty">Pick a note on the left.</div></div></div>`;
  return d;
}
// The tab that is lit, the list on the left and the vault a note is read from
// must always agree. The old code switched vaults silently on a [[link]] and
// every note clicked afterwards said "no such note".
const VB = { key: 'brain', files: [], el: null, load: null, search: null };
async function openNote(key, path) {
  const el = VB.el; if (!el) return;
  const d = await api(`/api/vault/file?v=${encodeURIComponent(key)}&p=${encodeURIComponent(path)}`);
  const note = $('.vb-note', el);
  if (d.error) { note.innerHTML = `<div class="empty">${esc(d.error)}</div>`; return; }
  note.innerHTML = `<div class="vb-path">${esc(key === 'crm' ? 'CRM' : 'Second brain')} / ${esc(path)}</div>` + md(d.text);
  el.querySelectorAll('.vb-file').forEach(f => f.classList.toggle('on', f.dataset.p === path));
  const on = el.querySelector('.vb-file.on'); if (on) on.scrollIntoView({ block: 'nearest' });
}
async function mountVault(el) {
  VB.el = el;
  const tabs = $('.vb-tabs', el), list = $('.vb-list', el), q = $('input', el);
  const vs = await api('/api/vaults');
  tabs.innerHTML = vs.map(v => `<button data-k="${esc(v.key)}" title="${esc(v.path)}">${esc(v.label)}${v.exists ? '' : ' (missing)'}</button>`).join('') || '<div class="empty">No vaults set in config.json.</div>';
  const draw = () => {
    const f = q.value.trim().toLowerCase();
    let last = null, h = '';
    VB.files.filter(x => !f || x.path.toLowerCase().includes(f)).slice(0, 1500).forEach(x => {
      const dir = x.path.includes('/') ? x.path.slice(0, x.path.lastIndexOf('/')) : '(top level)';
      if (dir !== last) { h += `<div class="vb-dir">${esc(dir)}</div>`; last = dir; }
      h += `<button class="vb-file" data-p="${esc(x.path)}">${esc(x.path.split('/').pop().replace(/\.md$/, ''))}</button>`;
    });
    list.innerHTML = h || `<div class="empty" style="margin:8px">No note names contain "${esc(q.value.trim())}". Press Enter to search inside every note in both vaults.</div>`;
  };
  const load = async (key) => {
    VB.key = key;
    tabs.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.k === key));
    const t = await api('/api/vault/tree?v=' + encodeURIComponent(key));
    VB.files = t.files || [];
    if (t.exists === false) list.innerHTML = t.refused ? `<div class="empty" style="margin:8px">${esc(t.refused)}</div>` : '<div class="empty" style="margin:8px">That folder does not exist. Check the path in config.json.</div>'; else draw();
  };
  const search = async (text) => {
    q.value = text;
    const r = await api('/api/vault/search?q=' + encodeURIComponent(text));
    list.innerHTML = (r.hits || []).map(x => `<div class="vb-hit" data-k="${esc(x.key)}" data-p="${esc(x.path)}"><b>${esc(x.path)}</b> <span class="pill">${esc(x.label)}</span><small>${esc(x.snippet)}</small></div>`).join('') || '<div class="empty" style="margin:8px">Nothing found in either vault.</div>';
  };
  VB.load = load; VB.search = search;
  tabs.onclick = e => { const b = e.target.closest('button'); if (b) load(b.dataset.k); };
  list.onclick = e => { const f = e.target.closest('.vb-file'); if (f) openNote(VB.key, f.dataset.p); const h = e.target.closest('.vb-hit'); if (h) { load(h.dataset.k).then(() => openNote(h.dataset.k, h.dataset.p)); } };
  q.oninput = draw;
  q.onkeydown = e => { if (e.key === 'Enter') search(q.value); };
  el.querySelector('.refresh').onclick = () => load(VB.key);
  el.querySelector('.pop').onclick = () => popout('vaults');
  if (vs.length) await load(vs[0].key);
}
// Clicking a [[link]] anywhere asks the server which vault has that note (the
// second brain first, then the CRM), switches the Vaults panel to that vault
// and opens it there.
async function followLink(name, prefer) {
  openPanel('vaults');
  for (let i = 0; i < 40 && !VB.load; i++) await new Promise(r => setTimeout(r, 50));
  if (!VB.load) return;
  const r = await api('/api/vault/resolve?name=' + encodeURIComponent(name) + (prefer ? '&prefer=' + encodeURIComponent(prefer) : ''));
  if (r.key) { await VB.load(r.key); await openNote(r.key, r.path); return; }
  const note = $('.vb-note', VB.el);
  const plain = String(name).split('/').pop().replace(/\.md$/, '');
  note.innerHTML = `<div class="empty">No note called "${esc(plain)}" in either vault.<br><br><button class="btn small" data-search="${esc(plain)}">Search both vaults for "${esc(plain)}"</button></div>`;
  note.querySelector('[data-search]').onclick = e => VB.search(e.target.dataset.search);
}
document.addEventListener('click', e => {
  const w = e.target.closest('.wl'); if (!w || !dock) return;
  followLink(w.dataset.note, w.dataset.vault);
});

// ------------------------------------------------------------------ Agents
async function renderAgents(body) {
  const d = await api('/api/agents');
  const looked = d.folders.map(f => `<span class="pill ${f.exists ? 'up' : ''}" title="${esc(f.path)}">${esc(f.label)}${f.exists ? '' : ' · none'}</span>`).join('');
  if (!d.agents.length) { body.innerHTML = `<div class="empty">No agents found yet. An agent is a markdown file in one of these folders:<ul>${d.folders.map(f => `<li><code class="sel">${esc(f.path)}</code> <span class="dim">(${esc(f.label)}${f.exists ? '' : ', folder does not exist yet'})</span></li>`).join('')}</ul></div>`; return; }
  body.innerHTML = `<div class="dim" style="margin-bottom:8px">${d.agents.length} agents · looked in ${looked}</div><div class="agents">` + d.agents.map(a => `
    <div class="agent"><div class="an">${esc(a.name)}</div><div class="ad" title="Click to read it all">${esc(a.description || 'No description written.')}</div>
      <div class="foot"><span class="pill">${esc(a.where)}</span>${a.model ? `<span class="pill">${esc(a.model)}</span>` : ''}<span style="flex:1"></span><button class="btn small ask" data-n="${esc(a.name)}">Ask in chat</button></div></div>`).join('') + '</div>';
  body.onclick = e => {
    const ad = e.target.closest('.ad'); if (ad) ad.classList.toggle('open');
    const b = e.target.closest('.ask'); if (b) { openPanel('chat'); setTimeout(() => window.__jeevesAsk && window.__jeevesAsk(`Use the ${b.dataset.n} agent to `), 120); }
  };
}

// ------------------------------------------------------------------ Activity
async function renderActivity(body) {
  const d = await api('/api/activity');
  if (!d.sessions.length) { body.innerHTML = '<div class="empty">No Claude Code conversations in the last 7 days were found.</div>'; return; }
  body.innerHTML = `<div class="dim" style="margin-bottom:6px">${d.total_sessions} conversations in the last ${d.days} days · newest first</div>
    <table class="t"><tr><th>When</th><th>Folder</th><th>What it was</th><th>Turns</th><th>Tokens</th></tr>` +
    d.sessions.map(s => `<tr><td class="dim">${esc(s.last)}</td><td title="${esc(s.folder)}">${esc(s.folder_name)}</td><td>${esc(s.title || '(untitled)')}<div class="dim">${esc(s.models.join(', '))}${s.minutes ? ' · ' + s.minutes + ' min' : ''}</div></td><td class="n">${s.turns}</td><td class="n">${fmt(s.tokens)}</td></tr>`).join('') + '</table>';
}

// ------------------------------------------------------------------ Tokens
async function renderTokens(body) {
  const d = await api('/api/tokens');
  const t = d.today, tot = t.total || 1;
  const row = (label, n) => `<div class="kv"><span class="muted">${label}</span><b>${fmt(n)}</b></div><div class="bar"><i style="width:${(100 * n / tot).toFixed(1)}%"></i></div>`;
  let h = `<div class="card"><h3>Today · ${esc(d.date)}</h3><div class="big">${fmt(t.total)}</div><div class="dim" style="margin-bottom:8px">tokens across ${d.sessions_today} conversation${d.sessions_today === 1 ? '' : 's'}</div>
    ${row('Conversation re-read (cache read)', t.cache_read)}${row('Saved for the next re-read (cache write)', t.cache_write)}${row('Written by Claude (output)', t.output)}${row('New input', t.input)}</div>`;
  const bm = Object.entries(d.by_model || {});
  if (bm.length) h += '<div class="card"><h3>By model, today</h3><div class="kv">' + bm.map(([m, v]) => `<span class="muted">${esc(m)}</span><b>${fmt(v.total)}</b>`).join('') + '</div></div>';
  h += `<div class="card"><h3>Last 5 hours</h3><div class="kv"><span class="muted">All tokens</span><b>${fmt(d.last_5_hours.total)}</b></div></div>`;
  const c = d.ccusage || {};
  h += `<div class="card"><h3>How much of your Claude plan's 5-hour allowance is left (needs the free ccusage program)</h3>`;
  if (!c.available) h += `<div class="muted">${esc(c.reason || 'not available')}</div>`;
  else if (!c.active) h += '<div class="muted">No window is open right now.</div>';
  else h += `<div class="kv"><span class="muted">Tokens in this window</span><b>${fmt(c.tokens)}</b><span class="muted">Window ends</span><b>${esc(new Date(c.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}</b><span class="muted">Minutes left</span><b>${esc(c.remaining_minutes ?? '?')}</b></div>`;
  h += '</div><div class="dim">Most tokens are Claude re-reading the conversation so far, listed above as "Conversation re-read". They count towards the usage limits of your Claude plan but are the cheapest kind.</div>';
  body.innerHTML = h;
}

// ------------------------------------------------------------------ Inbox
async function renderInbox(body) {
  const d = await api('/api/inbox');
  body.innerHTML = d.found ? `<div class="dim">${esc(d.path)}</div>` + md(d.text)
    : `<div class="empty">${esc(d.hint || 'No recommendations file.')}</div>`;
}

// ------------------------------------------------------------------ Embedded apps
function appPanel(name) {
  const d = shell(name === 'board' ? 'Your work board (ProjectForge)' : 'FleetView: every agent session on one screen', 'flush');
  return d;
}
async function mountApp(el, name) {
  const key = name === 'board' ? 'projectforge' : 'fleetview';
  const title = name === 'board' ? 'ProjectForge' : 'FleetView';
  const body = el.querySelector('.pbody');
  const draw = async () => {
    body.innerHTML = '<div style="padding:14px" class="dim">Checking whether ' + esc(title) + ' is running…</div>';
    const st = (await api('/api/apps'))[key] || {};
    if (st.up) {
      // Load the page only once the panel has real height: an app that starts
      // inside a hidden, zero-size panel can paint blank and stay blank.
      body.innerHTML = '<iframe class="appframe"></iframe>';
      const fr = body.querySelector('iframe');
      const load = () => { if (fr.clientHeight > 0 && !fr.src) { fr.src = st.url; return true; } return false; };
      if (!load()) { const ro = new ResizeObserver(() => { if (load()) ro.disconnect(); }); ro.observe(fr); }
      el.querySelector('.hint').innerHTML = `${esc(title)} · <a href="${esc(st.url)}" target="_blank" rel="noopener">open in its own tab</a>`;
    } else {
      body.innerHTML = `<div style="padding:14px"><div class="empty"><b>${esc(title)} is not running on this computer.</b><br>
        Nothing answered at <code>${esc(st.url || '(no address set)')}</code>.<br><br>
        If you have not installed it yet, here is the link: <a href="${esc(st.repo)}" target="_blank" rel="noopener">${esc(st.repo)}</a><br>
        If you have, start it, then press ↻ above. The address lives in <code>config.json</code> under <code>apps</code>.</div></div>`;
    }
  };
  el.querySelector('.refresh').onclick = draw;
  el.querySelector('.pop').onclick = () => popout(name);
  draw();
}

// ------------------------------------------------------------------ Across everything
// Every card heading opens its panel, every person opens their CRM note, and
// each card is drawn as soon as its own data arrives: the check on your other
// apps can take half a second when they are off, and nothing waits for it.
function crmPeople(text) {
  const rows = [];
  String(text || '').split('\n').forEach(l => { const m = l.match(/^\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|/); if (m) rows.push({ who: m[2].trim(), why: m[3].trim() }); });
  return rows;
}
async function renderOverview(body) {
  const cards = [
    ['people', 'today', 'People to speak to'], ['decide', 'inbox', 'Waiting for your decision'],
    ['brain', 'vaults', 'Your second brain'], ['claude', 'activity', 'Claude today'], ['apps', 'board', 'Your other apps'],
  ];
  body.innerHTML = '<div class="ov">' + cards.map(([k, open, t]) => `<div class="card" data-card="${k}"><h3><button class="cardlink" data-open="${open}" title="Open the ${esc(PANELS[open].title)} panel">${esc(t)} ›</button></h3><div class="cbody dim">Reading…</div></div>`).join('') + '</div>';
  const fill = (k, html) => { const c = body.querySelector(`[data-card="${k}"] .cbody`); if (c) { c.className = 'cbody'; c.innerHTML = html; } };
  const safe = p => api(p).catch(() => ({}));
  const jobs = [];
  jobs.push(safe('/api/today').then(td => {
    let h;
    if (!td.crm) h = '<div class="muted">No CRM folder is set in config.json.</div>';
    else if (td.crm.exists === false) h = missingFolder(td.crm.vault, 'crm_vault', td.crm.refused);
    else if (!td.crm.found && td.crm.no_today_tool) h = '<div class="muted">' + esc(td.crm.hint) + '</div>';
    else if (!td.crm.found) h = '<div class="muted">Your CRM has no <code>Today.md</code> yet. Build it in your CRM folder with <code>' + esc(CFG.python || 'python') + ' _engine/today.py --write</code>.</div>';
    else {
      const rows = crmPeople(td.crm.text);
      if (rows.length) h = '<ul>' + rows.slice(0, 4).map(r => `<li><span class="wl" data-vault="crm" data-note="${esc(r.who)}">${esc(r.who)}</span> <span class="muted">· ${inline(r.why)}</span></li>`).join('') + '</ul>' + (rows.length > 4 ? `<button class="cardlink small" data-open="today">and ${rows.length - 4} more in Today ›</button>` : '');
      else if (/\|/.test(td.crm.text)) h = '<div class="muted"><code>Today.md</code> has no numbered rows (number, name, reason), so no names can be picked out. <button class="cardlink small" data-open="today">Read it in Today ›</button></div>';
      else h = '<div class="muted">Nobody is waiting on you today.</div>';
    }
    fill('people', h);
    fill('brain', !td.brain ? '<div class="muted">No second brain is set in config.json.</div>'
      : td.brain.found === false ? missingFolder(td.brain.path, 'second_brain', td.brain.refused)
        : `<div class="kv"><span class="muted">Notes moved (3 days)</span><b>${td.brain.moved.length}</b><span class="muted">Left unfinished</span><b>${td.brain.open.length}</b><span class="muted">Daily note today</span><b>${td.brain.daily ? 'yes' : 'no'}</b></div>`);
  }));
  jobs.push(safe('/api/inbox').then(ib => {
    if (!ib.found) { fill('decide', `<div class="muted">No Recommendations file yet. Create <code>${esc((ib.looked_for || ['Inbox/Recommendations.md'])[0])}</code> in your second brain.</div>`); return; }
    const all = ib.text.split('\n').filter(l => /^\s*[-*]\s+/.test(l) && !/^\s*[-*]\s+\[[xX]\]/.test(l)).map(l => l.replace(/^\s*[-*]\s+(\[.\]\s*)?/, ''));
    fill('decide', all.length ? '<ul>' + all.slice(0, 4).map(x => `<li><span class="cardlink plain" role="button" tabindex="0" data-open="inbox">${inline(x)}</span></li>`).join('') + '</ul>' + (all.length > 4 ? `<button class="cardlink small" data-open="inbox">and ${all.length - 4} more ›</button>` : '') : '<div class="muted">The Recommendations file is there, with nothing waiting in it.</div>');
  }));
  jobs.push(Promise.all([safe('/api/activity'), safe('/api/tokens'), safe('/api/agents')]).then(([act, tok, ag]) => {
    const today = (act.sessions || []).filter(s => new Date(s.last_ts * 1000).toDateString() === new Date().toDateString());
    fill('claude', `<div class="kv"><span class="muted">Conversations</span><b>${today.length}</b><span class="muted">Tokens</span><b>${fmt(tok.today && tok.today.total)}</b><span class="muted">Agents you have</span><b><button class="cardlink plain" data-open="agents">${(ag.agents || []).length}</button></b></div>` + (today[0] ? `<div class="dim" style="margin-top:6px">Latest: ${esc(today[0].title || today[0].folder_name)}</div>` : ''));
  }));
  fill('apps', '<div class="dim">Checking…</div>');
  jobs.push(safe('/api/apps').then(ap => {
    fill('apps', Object.entries(ap).map(([k, v]) => `<div><span class="pill ${v.up ? 'up' : 'down'}">${v.up ? 'running' : 'not running'}</span> <button class="cardlink plain" data-open="${k === 'fleetview' ? 'fleet' : 'board'}">${k === 'projectforge' ? 'Work board (ProjectForge)' : k === 'fleetview' ? 'FleetView' : esc(k)}</button></div>`).join('') || '<div class="muted">None set in config.json.</div>');
  }));
  await Promise.all(jobs);
}
document.addEventListener('click', e => {
  const b = e.target.closest('.ov [data-open], .dv-watermark-jeeves [data-open]'); if (!b) return;
  openPanel(b.dataset.open);
});

// ------------------------------------------------------------------ the dock
const PANELS = {
  chat:     { title: 'Chat',               make: chatPanel, mount: el => mountChat(el) },
  overview: { title: 'Across everything',  make: () => shell('What is moving, everywhere. Click a heading to open its panel.'), render: renderOverview },
  today:    { title: 'Today',              make: () => shell('Your CRM’s Today.md and your second brain’s day'), render: renderToday },
  inbox:    { title: 'Recommendations',    make: () => shell('A markdown file in your second brain that you and your agents write to'), render: renderInbox },
  vaults:   { title: 'Vaults',             make: vaultPanel, mount: el => mountVault(el) },
  agents:   { title: 'Agents',             make: () => shell('Your Claude Code agents and what each one is for'), render: renderAgents },
  activity: { title: 'Activity',           make: () => shell('Recent Claude Code conversations, from its own log files'), render: renderActivity },
  tokens:   { title: 'Tokens',             make: () => shell('Tokens used today, read from Claude Code’s log files'), render: renderTokens },
  board:    { title: 'Work board',         make: () => appPanel('board'), mount: el => mountApp(el, 'board') },
  fleet:    { title: 'FleetView',          make: () => appPanel('fleet'), mount: el => mountApp(el, 'fleet') },
};
const CACHE = {};
function build(name) {
  if (!CACHE[name]) {
    const p = PANELS[name]; const el = p.make(); el.__mounted = false; CACHE[name] = el;
  }
  return CACHE[name];
}
function mount(name, el) {
  if (el.__mounted) return; el.__mounted = true;
  const p = PANELS[name];
  try {
    if (p.mount) p.mount(el);
    else wire(el, name, () => p.render(el.querySelector('.pbody')).catch(e => { el.querySelector('.pbody').innerHTML = '<div class="empty">Could not load: ' + esc(e) + '</div>'; }));
  } catch (e) { el.querySelector('.pbody') && (el.querySelector('.pbody').innerHTML = '<div class="empty">' + esc(e) + '</div>'); }
}

let dock = null;
// A closed panel comes back next to the panels it normally sits with, not in
// whichever group you clicked last.
const NEIGHBOURS = {
  chat: [], overview: ['tokens', 'today'], today: ['inbox', 'overview'], inbox: ['today', 'overview'],
  vaults: ['agents', 'board', 'fleet', 'today'], agents: ['vaults', 'board', 'fleet'], board: ['vaults', 'agents', 'fleet'],
  fleet: ['vaults', 'agents', 'board'], tokens: ['activity', 'overview'], activity: ['tokens', 'overview'],
};
function openPanel(name) {
  if (!dock || !PANELS[name]) return;
  const ex = dock.getPanel(name);
  if (ex) { if (dock.hasMaximizedGroup && dock.hasMaximizedGroup() && !(ex.api.isMaximized && ex.api.isMaximized())) dock.exitMaximizedGroup(); ex.api.setActive(); return; }
  const near = (NEIGHBOURS[name] || []).find(n => dock.getPanel(n));
  let position;
  if (near) position = { referencePanel: near, direction: 'within' };
  else if (name === 'chat' && dock.panels.length) position = { referencePanel: dock.panels[0].id, direction: 'left' };
  dock.addPanel(Object.assign({ id: name, component: name, title: PANELS[name].title }, position ? { position } : {}));
}

// ---- layouts. Every layout has all 10 panels; only where they sit changes.
const add = (id, ref, dir, inactive) => dock.addPanel(Object.assign({ id, component: id, title: PANELS[id].title }, ref ? { position: { referencePanel: ref, direction: dir } } : {}, inactive ? { inactive: true } : {}));
const size = (id, s) => { try { dock.getPanel(id).group.api.setSize(s); } catch (e) {} };
const activate = ids => ids.forEach(i => { try { dock.getPanel(i).api.setActive(); } catch (e) {} });
const LAYOUTS = {
  standard: {
    title: 'Big screen', note: 'Chat, Today, Across everything and Tokens side by side',
    build() {
      add('chat');
      add('today', 'chat', 'right'); add('inbox', 'today', 'within', true);
      add('overview', 'today', 'right');
      add('tokens', 'overview', 'below'); add('activity', 'tokens', 'within', true);
      add('vaults', 'today', 'below'); ['agents', 'board', 'fleet'].forEach(p => add(p, 'vaults', 'within', true));
      activate(['today', 'vaults', 'tokens']);
    },
  },
  laptop: {
    title: 'Laptop', note: 'Chat on the left; 1 tall stack of tabs on the right; a short row below',
    build() {
      add('chat');
      add('overview', 'chat', 'right'); ['today', 'inbox', 'vaults'].forEach(p => add(p, 'overview', 'within', true));
      add('tokens', 'overview', 'below'); ['activity', 'agents', 'board', 'fleet'].forEach(p => add(p, 'tokens', 'within', true));
      activate(['overview', 'tokens']);
      size('chat', { width: Math.round(innerWidth * 0.42) });
      size('tokens', { height: Math.round((innerHeight - 50) * 0.32) });
    },
  },
  chatfocus: {
    title: 'Chat focus', note: 'A wide Chat; every other panel as tabs beside it',
    build() {
      add('chat');
      add('overview', 'chat', 'right'); ['today', 'inbox', 'vaults', 'agents', 'activity', 'tokens', 'board', 'fleet'].forEach(p => add(p, 'overview', 'within', true));
      activate(['overview']);
      size('chat', { width: Math.round(innerWidth * 0.62) });
    },
  },
  morning: {
    title: 'Morning review', note: 'Across everything first, then Today, then Chat',
    build() {
      add('overview');
      add('today', 'overview', 'right'); add('inbox', 'today', 'within', true);
      add('chat', 'today', 'right');
      add('vaults', 'overview', 'below'); ['agents', 'tokens', 'activity', 'board', 'fleet'].forEach(p => add(p, 'vaults', 'within', true));
      activate(['today', 'vaults']);
    },
  },
};
const LKEY = 'jeeves.layout.v1', SKEY = 'jeeves.layouts.saved';
const defaultLayoutName = () => (innerWidth < 1440 ? 'laptop' : 'standard');
function applyLayout(name) {
  const saved = savedLayouts();
  try { if (dock.hasMaximizedGroup && dock.hasMaximizedGroup()) dock.exitMaximizedGroup(); } catch (e) {}
  try { dock.clear(); } catch (e) {}
  if (LAYOUTS[name]) LAYOUTS[name].build();
  else if (saved[name]) { try { dock.fromJSON(saved[name]); } catch (e) { LAYOUTS[defaultLayoutName()].build(); } }
  // A saved layout from an older copy may miss a panel: nothing is ever lost.
  Object.keys(PANELS).forEach(p => { if (!dock.getPanel(p)) openPanel(p); });
}
function savedLayouts() { try { return JSON.parse(localStorage.getItem(SKEY) || '{}'); } catch (e) { return {}; } }

function watermark() {
  const el = document.createElement('div');
  el.className = 'dv-watermark-jeeves';
  el.innerHTML = `<div><b>No panels open.</b> Bring one back, or put every panel back where it started.</div>
    <div class="wm-row">${Object.entries(PANELS).map(([k, p]) => `<button class="btn small" data-open="${k}">${esc(p.title)}</button>`).join('')}</div>
    <div><button class="btn" data-reset="1">Reset layout</button></div>`;
  el.querySelector('[data-reset]').onclick = () => applyLayout(defaultLayoutName());
  return { element: el, init() {}, dispose() {} };
}
function maxButton() {
  const el = document.createElement('div');
  el.className = 'grp-actions';
  el.innerHTML = '<button class="maxb" title="Make this group fill the screen (or double-click a tab). Esc puts it back.">⤢</button>';
  let group = null;
  el.querySelector('.maxb').onclick = e => {
    e.stopPropagation(); if (!group) return;
    if (group.api.isMaximized()) group.api.exitMaximized(); else group.api.maximize();
  };
  return { element: el, init(params) { group = params.group; }, dispose() {} };
}

async function start() {
  try { CFG = Object.assign(CFG, await api('/api/config')); } catch (e) {}
  document.title = CFG.name;
  $('#brand-name').textContent = CFG.name;
  $('#today-date').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
  const sel = $('#model');
  sel.innerHTML = Object.entries(CFG.models || {}).map(([k, v]) => `<option value="${esc(k)}">${esc(k)} · ${esc(v)}</option>`).join('');
  sel.value = CFG.default_model || 'best';
  try { const m = localStorage.getItem('jeeves.model'); if (m && CFG.models[m]) sel.value = m; } catch (e) {}
  sel.onchange = () => { try { localStorage.setItem('jeeves.model', sel.value); } catch (e) {} };
  if (window.JeevesOrb) orbTop = window.JeevesOrb($('#orb-top'), CFG.orb || {});
  if (CFG.claude_found === false) setStatus('Claude Code was not found on this computer, so Chat cannot answer. Every other panel works.');

  const solo = new URLSearchParams(location.search).get('only');
  dock = createDockview($('#dock'), Object.assign({
    createComponent: (o) => { const element = build(o.name); return { element, init: () => mount(o.name, element) }; },
    createWatermarkComponent: watermark,
  }, solo ? {} : { createRightHeaderActionComponent: maxButton }));
  if (solo && PANELS[solo]) {
    document.body.classList.add('solo');
    document.title = CFG.name + ' · ' + PANELS[solo].title;
    dock.addPanel({ id: solo, component: solo, title: PANELS[solo].title });
  } else {
    let restored = false;
    try { const saved = localStorage.getItem(LKEY); if (saved) { dock.fromJSON(JSON.parse(saved)); restored = dock.panels.length > 0; } } catch (e) { restored = false; }
    if (!restored) applyLayout(defaultLayoutName());
    dock.onDidLayoutChange(() => { try { localStorage.setItem(LKEY, JSON.stringify(dock.toJSON())); } catch (e) {} });
    // Double-click a tab to make its group fill the screen; again (or Esc) to put it back.
    $('#dock').addEventListener('dblclick', e => {
      if (!e.target.closest('.dv-tab')) return;
      const g = dock.activeGroup; if (!g) return;
      if (g.api.isMaximized()) g.api.exitMaximized(); else g.api.maximize();
    });
  }

  // + Panel: nothing is ever gone for good. Open panels are marked "(open)".
  const menu = $('#add-menu');
  const drawMenu = () => {
    menu.innerHTML = Object.entries(PANELS).map(([k, p]) => `<div class="row"><button data-open="${k}">+ ${esc(p.title)}${dock.getPanel(k) ? ' <span class="dim">(open)</span>' : ''}</button><button class="pop" data-pop="${k}" title="Pop out into its own window">⧉</button></div>`).join('');
  };
  menu.onclick = e => { const b = e.target.closest('button'); if (!b) return; const o = b.dataset.open, p = b.dataset.pop; if (o) openPanel(o); if (p) popout(p); menu.classList.remove('open'); e.stopPropagation(); };
  $('#add-btn').onclick = e => { e.stopPropagation(); lmenu.classList.remove('open'); drawMenu(); menu.classList.toggle('open'); };

  // Layouts: 4 ready-made arrangements plus any you save. All keep all 10 panels.
  const lmenu = $('#layout-menu');
  const drawLayouts = () => {
    const saved = Object.keys(savedLayouts());
    lmenu.innerHTML = Object.entries(LAYOUTS).map(([k, l]) => `<div class="row"><button data-layout="${k}"><b>${esc(l.title)}</b><br><span class="dim">${esc(l.note)}</span></button></div>`).join('') +
      (saved.length ? '<div class="sep">Saved by you</div>' + saved.map(n => `<div class="row"><button data-layout="${esc(n)}">${esc(n)}</button><button class="pop" data-forget="${esc(n)}" title="Forget this saved layout">×</button></div>`).join('') : '') +
      '<div class="sep"></div><div class="row"><button data-save="1">Save this layout as…</button></div>';
  };
  lmenu.onclick = e => {
    const b = e.target.closest('button'); if (!b) return; e.stopPropagation();
    if (b.dataset.layout) applyLayout(b.dataset.layout);
    if (b.dataset.forget) { const s = savedLayouts(); delete s[b.dataset.forget]; try { localStorage.setItem(SKEY, JSON.stringify(s)); } catch (x) {} drawLayouts(); return; }
    if (b.dataset.save) {
      const n = (prompt('Name for this layout, for example "Client prep":') || '').trim();
      if (n && !LAYOUTS[n]) { const s = savedLayouts(); s[n] = dock.toJSON(); try { localStorage.setItem(SKEY, JSON.stringify(s)); } catch (x) {} setStatus('Saved the layout "' + n + '".'); }
    }
    lmenu.classList.remove('open');
  };
  $('#layout-btn').onclick = e => { e.stopPropagation(); menu.classList.remove('open'); drawLayouts(); lmenu.classList.toggle('open'); };
  document.addEventListener('click', () => { menu.classList.remove('open'); lmenu.classList.remove('open'); });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    menu.classList.remove('open'); lmenu.classList.remove('open');
    try { if (dock.hasMaximizedGroup()) dock.exitMaximizedGroup(); } catch (x) {}
  });
  $('#reset-btn').onclick = () => applyLayout(defaultLayoutName());

  // Reading local files costs no tokens, so the reading panels refresh once a
  // minute while this tab is visible. Nothing here ever starts Claude on a timer.
  setInterval(() => {
    if (document.hidden) return;
    ['today', 'tokens', 'activity', 'overview'].forEach(n => { const el = CACHE[n]; if (el && el.__refresh && el.offsetParent) el.__refresh(); });
  }, 60000);
  window.__jeevesReady = true;
}
start();
