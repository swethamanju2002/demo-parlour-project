/* DQ Aesthetic booking wizard.
   Django is the source of truth: this file only displays what the JSON endpoints return and sends
   service IDs, a start time and a beautician choice back. Prices, durations and availability are never computed here. */
(() => {
  'use strict';
  const root = document.getElementById('wizard');
  if (!root) return;
  const D = root.dataset;
  const URLS = { services: D.apiServices, dates: D.apiDates, slots: D.apiSlots, staff: D.apiStaff, summary: D.apiSummary, book: D.apiBook };
  const MAX = parseInt(D.max, 10) || 8;
  const STEPS = ['Services', 'Date', 'Time', 'Beautician', 'Review', 'Confirmed'];
  const rail = root.querySelector('#wz-rail'), pane = root.querySelector('#wz-pane'), side = root.querySelector('#wz-side'), grid = root.querySelector('.wz-grid');

  /* ---------- helpers ---------- */
  const h = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return n;
  };
  const money = (v) => '\u20B9' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const mins = (m) => { const a = Math.floor(m / 60), b = m % 60; return a && b ? `${a} h ${b} min` : a ? `${a} h` : `${b} min`; };
  const parseDay = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };
  const dayLabel = (iso) => parseDay(iso).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
  const monthOf = (iso) => { const d = parseDay(iso); return new Date(d.getFullYear(), d.getMonth(), 1); };
  const clock = (hhmm) => { const [H, M] = hhmm.split(':').map(Number); return `${H % 12 || 12}:${String(M).padStart(2, '0')} ${H < 12 ? 'AM' : 'PM'}`; };
  const csrf = () => { const i = root.querySelector('input[name=csrfmiddlewaretoken]'); return i ? i.value : ''; };
  const say = (msg, kind) => { if (typeof window.toast === 'function') window.toast(msg, kind); };

  async function api(url, params, opts) {
    const q = params ? '?' + new URLSearchParams(params) : '';
    let r;
    try { r = await fetch(url + q, opts || { headers: { Accept: 'application/json' }, credentials: 'same-origin' }); }
    catch (_) { return { ok: false, code: 'network', error: 'Could not reach the salon. Check your connection and try again.' }; }
    let data = {};
    try { data = await r.json(); } catch (_) { /* non-JSON error page */ }
    if (r.status === 401) { location.href = D.login + '?next=' + encodeURIComponent(location.pathname + location.search); return { ok: false, code: 'auth_required', error: 'Please sign in to continue.' }; }
    if (!data.ok) return { ok: false, code: data.code || 'error', error: data.error || 'Something went wrong. Please try again.' };
    return data;
  }

  /* ---------- state ---------- */
  const fresh = () => ({ step: 1, reached: 1, picked: [], tally: null, tallyErr: '', tallyBusy: false, dates: null, win: null, month: null, date: null,
    slots: null, slot: null, staffRes: null, staff: 'any', summary: null, notes: '', error: '', loading: false, busy: false, booking: null });
  const S = Object.assign(fresh(), { cats: [], svc: new Map() });
  let seq = 0, tallySeq = 0;
  const ids = () => S.picked.join(',');

  /* ---------- data loaders (one per step) ---------- */
  const LOADERS = {
    2: async () => {
      const r = await api(URLS.dates, { services: ids() });
      if (!r.ok) { S.dates = null; S.error = r.error; return; }
      S.dates = new Set(r.dates); S.win = r.window;
      if (S.date && !S.dates.has(S.date)) { S.date = null; S.slot = null; }
      S.month = monthOf(S.date || r.dates[0] || r.window.first);
    },
    3: async () => {
      const r = await api(URLS.slots, { services: ids(), date: S.date });
      if (!r.ok) { S.slots = null; S.error = r.error; return; }
      S.slots = r.slots;
      if (S.slot && !r.slots.some((s) => s.start === S.slot.start && s.available)) S.slot = null;
    },
    4: async () => {
      const r = await api(URLS.staff, { services: ids(), start: S.slot.start });
      if (!r.ok) { S.staffRes = null; S.error = r.error; return; }
      S.staffRes = r;
      if (S.staff !== 'any' && !r.staff.some((p) => p.id === S.staff && p.available)) S.staff = 'any';
    },
    5: async () => {
      const r = await api(URLS.summary, { services: ids(), staff: S.staff, start: S.slot.start });
      if (!r.ok) {
        if (r.code === 'slot_unavailable') { S.slot = null; await enter(3, r.error); return; }
        S.summary = null; S.error = r.error; return;
      }
      S.summary = r;
    },
  };

  async function enter(n, msg) {
    S.step = n; S.reached = Math.max(S.reached, n); S.error = msg || ''; S.loading = false;
    const mine = ++seq;
    if (LOADERS[n]) { S.loading = true; render(); await LOADERS[n](); if (mine !== seq) return; S.loading = false; }
    render();
  }

  async function refreshTally() {
    const mine = ++tallySeq;
    if (!S.picked.length) { S.tally = null; S.tallyErr = ''; S.tallyBusy = false; render(true); return; }
    S.tallyBusy = true; render(true);
    const r = await api(URLS.summary, { services: ids() });
    if (mine !== tallySeq) return;
    S.tallyBusy = false;
    if (r.ok) { S.tally = r; S.tallyErr = ''; } else { S.tally = null; S.tallyErr = r.error; }
    render(true);
  }

  function toggle(id) {
    const i = S.picked.indexOf(id);
    if (i >= 0) S.picked.splice(i, 1); else if (S.picked.length < MAX) S.picked.push(id); else return;
    Object.assign(S, { tally: null, tallyErr: '', dates: null, date: null, slot: null, staff: 'any', summary: null, reached: 1, error: '' });
    refreshTally();
  }

  async function confirm() {
    if (S.busy) return;
    S.busy = true; S.error = ''; render(true);
    const r = await api(URLS.book, null, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify({ services: S.picked, start: S.slot.start, staff: S.staff, notes: S.notes }),
    });
    S.busy = false;
    if (r.ok) { S.booking = r.booking; say(r.message, 'success'); return enter(6); }
    if (r.code === 'slot_unavailable') { S.slot = null; return enter(3, r.error); }
    S.error = r.error; render(true);
  }

  function reset() { const keep = { cats: S.cats, svc: S.svc }; Object.assign(S, fresh(), keep); enter(1); }

  /* ---------- views ---------- */
  const foot = (back, next) => h('div', { class: 'wz-foot' },
    back ? h('button', { type: 'button', class: 'btn btn-ghost', 'data-k': 'back', onclick: back }, 'Back') : h('span'),
    next && h('button', { type: 'button', class: 'btn btn-primary', 'data-k': 'next', disabled: !next.on, onclick: next.fn }, next.label));
  const errBox = () => S.error && h('p', { class: 'wz-error', role: 'alert' }, S.error);
  const loading = (t) => h('div', { class: 'wz-loading', 'aria-busy': 'true' }, h('span', { class: 'wz-spin' }), t);
  const retry = (fn) => h('button', { type: 'button', class: 'btn btn-ghost btn-small', onclick: fn }, 'Try again');

  const VIEWS = {
    1() {
      const w = h('div', {}, h('h2', {}, 'Choose your treatments'), h('p', { class: 'wz-lede' }, `Pick up to ${MAX}. Prices and times come straight from the salon.`), errBox());
      if (S.loading) return w.appendChild(loading('Loading treatments')), w;
      if (!S.cats.length) { w.append(h('p', { class: 'p-muted' }, 'No treatments can be booked online right now.'), retry(init)); return w; }
      for (const c of S.cats) {
        w.append(h('section', { class: 'wz-cat' }, h('h3', {}, c.name), c.tagline && h('p', { class: 'help' }, c.tagline),
          h('ul', { class: 'wz-list' }, c.services.map((s) => {
            const on = S.picked.includes(s.id);
            return h('li', {}, h('button', { type: 'button', class: 'wz-svc' + (on ? ' on' : ''), role: 'checkbox', 'aria-checked': String(on), 'data-k': 's' + s.id,
              disabled: !on && S.picked.length >= MAX, onclick: () => toggle(s.id) },
              h('span', { class: 'wz-check', 'aria-hidden': 'true' }, on ? '\u2713' : ''),
              h('span', {}, h('span', { class: 'wz-name' }, s.name), h('span', { class: 'wz-desc' }, s.description)),
              h('span', { class: 'wz-meta' }, h('b', {}, money(s.price)), s.duration_label)));
          }))));
      }
      const t = S.tallyBusy ? 'Checking\u2026' : S.tally ? `${S.picked.length} selected, ${mins(S.tally.total_minutes)}, ${money(S.tally.total_price)}` : '';
      w.append(h('div', { class: 'wz-tally', 'aria-live': 'polite' }, S.tallyErr ? h('span', { class: 'wz-error', role: 'alert' }, S.tallyErr) : t));
      w.append(foot(null, { label: 'Choose a date', on: !!S.tally && !S.tallyBusy, fn: () => enter(2) }));
      return w;
    },
    2() {
      const w = h('div', {}, h('h2', {}, 'Pick a day'), h('p', { class: 'wz-lede' }, 'Days with open times are highlighted.'), errBox());
      if (S.loading) return w.appendChild(loading('Checking the diary')), w;
      if (!S.dates) { w.append(retry(() => enter(2)), foot(() => enter(1))); return w; }
      if (!S.dates.size) { w.append(h('p', { class: 'p-muted' }, 'No days are open for this combination. Try fewer treatments or book them separately.'), foot(() => enter(1))); return w; }
      const m = S.month, y = m.getFullYear(), mo = m.getMonth(), f = parseDay(S.win.first), l = parseDay(S.win.last);
      const idx = (a, b) => a * 12 + b;
      const lead = (new Date(y, mo, 1).getDay() + 6) % 7, count = new Date(y, mo + 1, 0).getDate(), cells = [];
      for (let i = 0; i < lead; i++) cells.push(h('span', { 'aria-hidden': 'true' }));
      for (let d = 1; d <= count; d++) {
        const iso = `${y}-${String(mo + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`, ok = S.dates.has(iso), on = S.date === iso;
        cells.push(h('button', { type: 'button', class: 'wz-day' + (ok ? ' open' : '') + (on ? ' on' : ''), disabled: !ok, 'aria-pressed': ok ? String(on) : null,
          'aria-label': dayLabel(iso), 'data-k': 'd' + iso, onclick: () => { if (S.date !== iso) { S.date = iso; S.slot = null; S.staff = 'any'; } enter(3); } }, String(d)));
      }
      const go = (n) => { S.month = new Date(y, mo + n, 1); render(true); };
      w.append(h('div', { class: 'wz-cal' },
        h('div', { class: 'wz-cal-head' },
          h('button', { type: 'button', class: 'wz-nav', 'aria-label': 'Previous month', 'data-k': 'prev', disabled: idx(y, mo) <= idx(f.getFullYear(), f.getMonth()), onclick: () => go(-1) }, '\u2039'),
          h('h3', {}, m.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })),
          h('button', { type: 'button', class: 'wz-nav', 'aria-label': 'Next month', 'data-k': 'nextm', disabled: idx(y, mo) >= idx(l.getFullYear(), l.getMonth()), onclick: () => go(1) }, '\u203A')),
        h('div', { class: 'wz-dow', 'aria-hidden': 'true' }, ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((x) => h('span', {}, x))),
        h('div', { class: 'wz-days' }, cells)));
      w.append(foot(() => enter(1)));
      return w;
    },
    3() {
      const w = h('div', {}, h('h2', {}, 'Choose a time'), h('p', { class: 'wz-lede' }, S.date ? dayLabel(S.date) : ''), errBox());
      if (S.loading) return w.appendChild(loading('Checking the diary')), w;
      if (!S.slots) { w.append(retry(() => enter(3)), foot(() => enter(2))); return w; }
      if (!S.slots.some((s) => s.available)) { w.append(h('p', { class: 'p-muted' }, 'Every time is taken on this day. Please choose another day.'), foot(() => enter(2))); return w; }
      const groups = [['Morning', (n) => n < 12], ['Afternoon', (n) => n >= 12 && n < 17], ['Evening', (n) => n >= 17]];
      for (const [name, test] of groups) {
        const list = S.slots.filter((s) => test(Number(s.time.slice(0, 2))));
        if (!list.length) continue;
        w.append(h('h3', {}, name), h('div', { class: 'wz-slots' }, list.map((s) => h('button', { type: 'button', class: 'wz-slot' + (S.slot && S.slot.start === s.start ? ' on' : ''),
          disabled: !s.available, 'aria-pressed': String(!!(S.slot && S.slot.start === s.start)), 'data-k': 't' + s.time,
          onclick: () => { if (!S.slot || S.slot.start !== s.start) S.staff = 'any'; S.slot = s; render(true); } }, s.label))));
      }
      w.append(foot(() => enter(2), { label: 'Choose a beautician', on: !!S.slot, fn: () => enter(4) }));
      return w;
    },
    4() {
      const w = h('div', {}, h('h2', {}, 'Who would you like?'), h('p', { class: 'wz-lede' }, S.slot ? `${dayLabel(S.date)} at ${S.slot.label}` : ''), errBox());
      if (S.loading) return w.appendChild(loading('Checking who is free')), w;
      if (!S.staffRes) { w.append(retry(() => enter(4)), foot(() => enter(3))); return w; }
      const R = S.staffRes, pick = (v) => { S.staff = v; render(true); };
      const person = (key, avatar, name, sub, on, can) => h('button', { type: 'button', class: 'wz-person' + (on ? ' on' : ''), disabled: !can, 'aria-pressed': String(on), 'data-k': key, onclick: () => pick(key === 'any' ? 'any' : Number(key.slice(1))) },
        h('span', { class: 'wz-avatar', 'aria-hidden': 'true' }, avatar), h('span', {}, h('strong', {}, name), h('small', {}, sub)), h('span', { class: 'p-muted' }, can ? '' : 'Booked then'));
      w.append(h('div', { class: 'wz-staff' },
        person('any', '\u2726', 'Any available beautician', 'We assign the best match for your time', S.staff === 'any', R.any_available),
        R.staff.map((p) => person('p' + p.id, p.photo ? h('img', { src: p.photo, alt: '', loading: 'lazy' }) : p.name[0], p.name,
          p.title + (p.years_experience ? `, ${p.years_experience} years` : ''), S.staff === p.id, p.available))));
      if (!R.any_available) w.append(h('p', { class: 'wz-error', role: 'alert' }, 'Everyone is booked at this time. Go back and choose another.'));
      w.append(foot(() => enter(3), { label: 'Review booking', on: R.any_available, fn: () => enter(5) }));
      return w;
    },
    5() {
      const w = h('div', {}, h('h2', {}, 'Review your booking'), errBox());
      if (S.loading) return w.appendChild(loading('Confirming the details')), w;
      const s = S.summary;
      if (!s) { w.append(foot(() => enter(4))); return w; }
      const who = s.staff ? s.staff.name : 'Best available beautician';
      w.append(h('div', { class: 'wz-review' },
        s.services.map((x) => h('div', { class: 'row' }, h('span', {}, x.name, h('br'), h('small', { class: 'p-muted' }, mins(x.duration_minutes))), h('b', {}, money(x.price)))),
        h('div', { class: 'row' }, h('span', {}, 'When'), h('span', {}, `${dayLabel(S.date)}, ${s.time_label} to ${clock(s.end.slice(11, 16))}`)),
        h('div', { class: 'row' }, h('span', {}, 'Beautician'), h('span', {}, who)),
        h('div', { class: 'row' }, h('span', {}, `Total, ${mins(s.total_minutes)}`), h('b', {}, money(s.total_price)))));
      w.append(h('div', { class: 'field' }, h('label', { for: 'wz-notes' }, 'Anything we should know? (optional)'),
        h('textarea', { id: 'wz-notes', class: 'field-input wz-notes', maxlength: '1000', oninput: (e) => { S.notes = e.target.value; } }, S.notes)));
      w.append(h('p', { class: 'help' }, 'Your request is held for you now. We confirm it shortly. You can cancel or ask to reschedule from your account.'));
      w.append(foot(() => enter(4), { label: S.busy ? 'Confirming\u2026' : 'Confirm booking', on: !S.busy, fn: confirm }));
      return w;
    },
    6() {
      const b = S.booking;
      const copy = async (e) => { try { await navigator.clipboard.writeText(b.public_id); e.target.textContent = 'Copied'; } catch (_) { say('Select the ID to copy it.', 'error'); } };
      return h('div', { class: 'wz-done' },
        h('div', { class: 'p-arch', 'aria-hidden': 'true' }, '\u2713'),
        h('h2', {}, 'Your request is in'),
        h('p', {}, 'Your booking ID is'),
        h('p', { class: 'id', 'data-k': 'id' }, b.public_id),
        h('button', { type: 'button', class: 'btn btn-ghost btn-small', onclick: copy }, 'Copy ID'),
        h('p', {}, `${dayLabel(b.start.slice(0, 10))} at ${b.time_label} with ${b.staff.name}. ${b.status_label}: we will confirm it shortly.`),
        h('p', {}, b.items.map((i) => i.name).join(', '), ', ', h('b', {}, money(b.total_price))),
        h('div', { class: 'actions' },
          h('a', { class: 'btn btn-primary', href: b.url }, 'View booking'),
          h('a', { class: 'btn btn-ghost', href: D.dashboard }, 'Back to overview'),
          h('button', { type: 'button', class: 'btn btn-ghost', onclick: reset }, 'Book another')));
    },
  };

  /* ---------- rendering ---------- */
  function renderRail() {
    rail.replaceChildren(...STEPS.map((name, i) => {
      const n = i + 1, state = n < S.step ? 'done' : n === S.step ? 'cur' : 'todo';
      const inner = [h('span', { class: 'n' }, state === 'done' ? '\u2713' : String(n)), h('span', { class: 't' }, name)];
      const clickable = S.step < 6 && n < S.step;
      return h('li', { class: state }, clickable ? h('button', { type: 'button', class: 'st', onclick: () => enter(n) }, inner)
        : h('span', Object.assign({ class: 'st' }, n === S.step ? { 'aria-current': 'step' } : {}), inner));
    }));
  }

  function renderSide() {
    grid.classList.toggle('single', S.step === 6);
    side.hidden = S.step === 6;
    if (S.step === 6) return;
    const t = S.step === 5 && S.summary ? S.summary : S.tally;
    const staff = S.staff === 'any' ? 'Any available beautician' : (S.staffRes && S.staffRes.staff.find((p) => p.id === S.staff) || {}).name;
    side.replaceChildren(h('h3', {}, 'Your visit'),
      S.picked.length ? h('ul', {}, S.picked.map((id) => { const s = S.svc.get(id); return h('li', {}, h('span', {}, s.name), h('span', {}, money(s.price))); }))
        : h('p', { class: 'p-muted' }, 'Nothing selected yet.'),
      S.tallyBusy ? h('p', { class: 'p-muted' }, 'Updating\u2026')
        : t ? h('div', { class: 'wz-total' }, h('span', {}, mins(t.total_minutes)), h('b', {}, money(t.total_price))) : null,
      (S.date || S.slot || (S.step >= 4 && staff)) ? h('dl', {}, S.date && [h('dt', {}, 'Day'), h('dd', {}, dayLabel(S.date))],
        S.slot && [h('dt', {}, 'Time'), h('dd', {}, S.slot.label)], S.step >= 4 && staff && [h('dt', {}, 'Beautician'), h('dd', {}, staff)]) : null);
  }

  function render(keepFocus) {
    const key = keepFocus && document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.k : null;
    renderRail(); renderSide();
    pane.replaceChildren(VIEWS[S.step]());
    const target = key && pane.querySelector(`[data-k="${CSS.escape(key)}"]`);
    if (target && !target.disabled) target.focus({ preventScroll: true });
    else if (!keepFocus) { const hd = pane.querySelector('h2'); if (hd) { hd.tabIndex = -1; hd.focus(); } }
  }

  /* ---------- start ---------- */
  async function init() {
    S.loading = true; S.error = ''; render();
    const r = await api(URLS.services);
    S.loading = false;
    if (!r.ok) { S.error = r.error; S.cats = []; render(); return; }
    S.cats = r.categories;
    r.categories.forEach((c) => c.services.forEach((s) => S.svc.set(s.id, s)));
    const pre = parseInt(D.preselect, 10);
    if (S.svc.has(pre)) { S.picked = [pre]; render(); refreshTally(); } else render();
  }
  init();
})();