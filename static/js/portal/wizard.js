/* Booking wizard: services → date → time → beautician → review → confirmation.
   All availability, prices and totals come from the Django JSON endpoints; this file only presents them.
   Closure-wrapped so it cannot clash with motion.js globals. DOM is built with textContent (never innerHTML) for server data. */
(function () {
  'use strict';
  const root = document.getElementById('wizard');
  if (!root) return;

  const D = root.dataset;
  const API = { services: D.apiServices, dates: D.apiDates, slots: D.apiSlots, staff: D.apiStaff, summary: D.apiSummary, book: D.apiBook };
  const MAX = parseInt(D.max, 10) || 8;
  const CANCEL_HOURS = parseInt(D.cancelHours, 10) || 4;
  const reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  const $ = (sel) => root.querySelector(sel);
  const bodies = {};
  root.querySelectorAll('[data-body]').forEach((el) => { bodies[el.dataset.body] = el; });
  const panels = Array.from(root.querySelectorAll('[data-panel]'));
  const stepperEl = $('#stepper'), stepperItems = Array.from(root.querySelectorAll('#stepper li'));
  const btnNext = $('#wiz-next'), btnBack = $('#wiz-back'), errBox = $('#wiz-error'), mini = $('#wiz-mini'), rail = $('#wiz-rail'), actions = $('#wiz-actions');

  /* ── helpers ─────────────────────────────────────────────────────────────── */
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (v == null || v === false) return;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    });
    kids.flat().forEach((kid) => { if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid))); });
    return el;
  }
  const rupee = (v) => '₹' + Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  const dur = (m) => { const hh = Math.floor(m / 60), mm = m % 60; return hh && mm ? hh + ' h ' + mm + ' min' : hh ? hh + ' h' : mm + ' min'; };
  const parseKey = (k) => { const p = k.split('-').map(Number); return new Date(p[0], p[1] - 1, p[2]); };
  const keyOf = (y, m, d) => y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  const longDate = (k) => parseKey(k).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const shortDate = (k) => parseKey(k).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
  const label12 = (mins) => { const hh = Math.floor(mins / 60), mm = mins % 60; return (hh % 12 || 12) + ':' + String(mm).padStart(2, '0') + ' ' + (hh < 12 ? 'AM' : 'PM'); };
  // ISO strings from the server carry the salon's own offset, so read the clock from the text, not the browser's timezone.
  const isoMinutes = (iso) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));
  const clock = (iso) => label12(isoMinutes(iso));
  const clockPlus = (iso, mins) => label12(isoMinutes(iso) + mins);

  class ApiError extends Error { constructor(msg, code, status) { super(msg); this.code = code; this.status = status; } }
  async function request(url, opts) {
    let res, data = null;
    try { res = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts)); }
    catch (_) { throw new ApiError('We could not reach the salon system. Please check your connection and try again.', 'network', 0); }
    try { data = await res.json(); } catch (_) { /* leave null */ }
    if (res.status === 401) {
      location.href = D.loginUrl + '?next=' + encodeURIComponent(location.pathname + location.search);
      throw new ApiError('Please sign in to continue.', 'auth_required', 401);
    }
    if (!res.ok || !data || data.ok === false) throw new ApiError((data && data.error) || 'Something went wrong. Please try again.', (data && data.code) || 'error', res.status);
    return data;
  }
  const get = (url, params) => request(url + '?' + new URLSearchParams(params).toString());
  const csrf = () => { const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ''; };
  const post = (url, body) => request(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify(body) });
  const say = (msg, kind) => { if (typeof window.toast === 'function') window.toast(msg, kind || 'error'); };
  const showError = (msg) => { errBox.textContent = msg; errBox.hidden = false; };
  const clearError = () => { errBox.textContent = ''; errBox.hidden = true; };

  /* ── state ───────────────────────────────────────────────────────────────── */
  const S = {
    step: 1, cats: [], byId: new Map(), selected: [], activeCat: null,
    dates: [], datesKey: null, window: null, month: null, date: null,
    slots: [], slot: null, staff: [], staffId: 'any', summary: null, notes: '', booking: null,
    incompatible: null, checking: false, busy: false,
  };
  const chosen = () => S.selected.map((id) => S.byId.get(id)).filter(Boolean);
  const totalMin = () => chosen().reduce((a, s) => a + s.duration_minutes, 0);
  const totalPrice = () => chosen().reduce((a, s) => a + Number(s.price), 0);
  const idsParam = () => S.selected.join(',');
  const staffName = () => {
    if (S.staffId === 'any') return 'Best available';
    const p = S.staff.find((x) => String(x.id) === String(S.staffId));
    return p ? p.name : 'Best available';
  };
  function invalidate(from) {
    if (from <= 2) { S.dates = []; S.datesKey = null; S.date = null; }
    if (from <= 3) { S.slots = []; S.slot = null; }
    if (from <= 4) { S.staff = []; S.staffId = 'any'; }
    S.summary = null;
  }
  function canContinue() {
    if (S.busy) return false;
    switch (S.step) {
      case 1: return S.selected.length > 0 && !S.incompatible && !S.checking;
      case 2: return !!S.date;
      case 3: return !!S.slot;
      case 4: return true;
      case 5: return !!S.summary;
      default: return false;
    }
  }

  /* ── chrome: stepper, rail, buttons ──────────────────────────────────────── */
  function renderRail() {
    const items = chosen();
    const row = (k, v) => h('div', { class: 'rail-row' }, h('span', { text: k }), h('b', { text: v }));
    const kids = [h('h3', { text: 'Your visit' })];
    if (!items.length) kids.push(h('p', { class: 'rail-empty', text: 'Choose a treatment to begin.' }));
    else {
      kids.push(h('ul', { class: 'rail-list' }, items.map((s) => h('li', {}, h('span', { text: s.name }), h('b', { text: rupee(s.price) })))));
      kids.push(row('Duration', dur(totalMin())));
      if (S.date) kids.push(row('Date', shortDate(S.date)));
      if (S.slot) kids.push(row('Time', S.slot.label + ' – ' + clockPlus(S.slot.start, totalMin())));
      if (S.slot && S.step >= 4) kids.push(row('Beautician', staffName()));
      kids.push(h('div', { class: 'rail-total' }, h('small', { text: 'Estimated total' }), h('b', { text: rupee(totalPrice()) })));
    }
    rail.replaceChildren(...kids);
  }
  function update() {
    btnNext.disabled = !canContinue();
    const items = chosen();
    mini.textContent = items.length ? items.length + (items.length === 1 ? ' service' : ' services') + ' · ' + dur(totalMin()) + ' · ' + rupee(totalPrice()) : '';
    renderRail();
  }
  function setBusy(b) { S.busy = b; btnNext.classList.toggle('is-busy', b); btnBack.disabled = b; update(); }
  function go(n, back) {
    S.step = n; clearError();
    panels.forEach((p) => { const on = Number(p.dataset.panel) === n; p.hidden = !on; p.classList.toggle('is-active', on); p.classList.toggle('back', on && !!back); });
    stepperItems.forEach((li, i) => {
      li.classList.toggle('is-done', i + 1 < n || n === 6);
      li.classList.toggle('is-current', i + 1 === n && n < 6);
      if (i + 1 === n && n < 6) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    });
    stepperEl.style.setProperty('--p', String((n - 1) / 5));
    btnBack.hidden = n === 1 || n === 6;
    actions.hidden = n === 6;
    rail.hidden = n === 6;
    btnNext.querySelector('span').textContent = n === 5 ? 'Request booking' : 'Continue';
    update();
    const heading = panels[n - 1].querySelector('h2');
    if (heading) heading.focus({ preventScroll: true });
    if (root.scrollIntoView) root.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  }

  /* ── step 1: services ────────────────────────────────────────────────────── */
  let cardEls = new Map(), compatSeq = 0, compatTimer = null;
  function renderServices() {
    const body = bodies[1];
    if (!S.cats.length) {
      body.replaceChildren(h('div', { class: 'empty-state' }, h('span', { class: 'es-arch', 'aria-hidden': 'true' }), h('h2', { text: 'Online booking is not open yet.' }), h('p', { text: 'Please call or message us on WhatsApp to book.' })));
      return;
    }
    const chip = (id, name) => h('button', { type: 'button', 'aria-pressed': String(S.activeCat === id), onclick: () => { S.activeCat = id; renderServices(); }, text: name });
    const visible = S.cats.filter((c) => S.activeCat === null || c.id === S.activeCat);
    cardEls = new Map();
    let i = 0;
    const cards = [];
    visible.forEach((c) => c.services.forEach((s) => {
      const el = h('button', { type: 'button', class: 'svc-pick', style: '--i:' + (i++), 'aria-pressed': String(S.selected.includes(s.id)), onclick: () => toggle(s.id) },
        h('span', { class: 'sp-media' }, s.image ? h('img', { src: s.image, alt: '', loading: 'lazy' }) : null),
        h('span', { class: 'sp-body' }, h('b', { text: s.name }), h('p', { text: s.description }),
          h('span', { class: 'sp-meta' }, h('b', { text: rupee(s.price) }), h('span', { text: s.duration_label }))),
        h('span', { class: 'sp-tick', 'aria-hidden': 'true' }));
      cardEls.set(s.id, el); cards.push(el);
    }));
    body.replaceChildren(
      h('div', { class: 'cat-chips', role: 'group', 'aria-label': 'Service categories' }, chip(null, 'All'), S.cats.map((c) => chip(c.id, c.name))),
      h('div', { class: 'pick-grid' }, cards),
      h('div', { class: 'compat', id: 'compat', 'aria-live': 'polite' }));
    renderCompat();
  }
  function renderCompat() {
    const box = $('#compat'); if (!box) return;
    box.replaceChildren(S.incompatible ? h('p', { class: 'notice', text: S.incompatible }) : '');
  }
  function toggle(id) {
    const at = S.selected.indexOf(id);
    if (at >= 0) S.selected.splice(at, 1);
    else if (S.selected.length >= MAX) { say('You can choose up to ' + MAX + ' services in one visit.'); return; }
    else S.selected.push(id);
    const el = cardEls.get(id); if (el) el.setAttribute('aria-pressed', String(S.selected.includes(id)));
    invalidate(2); clearError(); scheduleCompat();
  }
  function scheduleCompat() {          // early warning when no single beautician can do the whole combination
    clearTimeout(compatTimer);
    const seq = ++compatSeq;
    S.incompatible = null; renderCompat();
    if (!S.selected.length) { S.checking = false; update(); return; }
    S.checking = true; update();
    compatTimer = setTimeout(async () => {
      let msg = null;
      try { await get(API.staff, { services: idsParam() }); } catch (e) { if (e.code === 'no_staff') msg = e.message; }
      if (seq !== compatSeq) return;
      S.incompatible = msg; S.checking = false; renderCompat(); update();
    }, 200);
  }

  /* ── step 2: calendar ────────────────────────────────────────────────────── */
  async function loadDates() {
    const r = await get(API.dates, { services: idsParam() });
    S.dates = r.dates; S.window = r.window; S.datesKey = idsParam();
    const first = parseKey(S.dates[0] || r.window.first);
    S.month = { y: first.getFullYear(), m: first.getMonth() };
    renderCalendar();
  }
  function renderCalendar() {
    const body = bodies[2], { y, m } = S.month, open = new Set(S.dates);
    if (!S.dates.length) {
      body.replaceChildren(h('div', { class: 'empty-state' }, h('span', { class: 'es-arch', 'aria-hidden': 'true' }), h('h2', { text: 'No free days just now.' }), h('p', { text: 'Try a shorter combination of services, or call us and we will find a time.' })));
      return;
    }
    const fw = parseKey(S.window.first), lw = parseKey(S.window.last);
    const idx = y * 12 + m, canPrev = idx > fw.getFullYear() * 12 + fw.getMonth(), canNext = idx < lw.getFullYear() * 12 + lw.getMonth();
    const lead = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
    const cells = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => h('div', { class: 'cal-dow', 'aria-hidden': 'true', text: d }));
    for (let i = 0; i < lead; i++) cells.push(h('span', { class: 'cal-blank' }));
    for (let d = 1; d <= days; d++) {
      const key = keyOf(y, m, d), isOpen = open.has(key);
      cells.push(h('button', {
        type: 'button', class: 'cal-day' + (isOpen ? ' is-open' : '') + (key === S.window.first ? ' is-today' : ''), 'data-date': key,
        disabled: !isOpen, 'aria-pressed': String(key === S.date), 'aria-label': longDate(key) + (isOpen ? '' : ' (unavailable)'),
        onclick: () => pickDate(key), text: String(d),
      }));
    }
    const shift = (delta) => () => { const t = new Date(y, m + delta, 1); S.month = { y: t.getFullYear(), m: t.getMonth() }; renderCalendar(); };
    body.replaceChildren(h('div', { class: 'cal' },
      h('div', { class: 'cal-head' },
        h('button', { type: 'button', class: 'cal-nav', 'aria-label': 'Previous month', disabled: !canPrev, onclick: shift(-1), text: '‹' }),
        h('h3', { 'aria-live': 'polite', text: new Date(y, m, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }) }),
        h('button', { type: 'button', class: 'cal-nav', 'aria-label': 'Next month', disabled: !canNext, onclick: shift(1), text: '›' })),
      h('div', { class: 'cal-grid' }, cells),
      h('div', { class: 'cal-legend' }, h('span', {}, h('i'), 'Available'), h('span', {}, h('i', { class: 'sel' }), 'Selected'), h('span', {}, h('i', { class: 'off' }), 'Unavailable'))));
  }
  function pickDate(key) {
    if (S.date !== key) { S.date = key; invalidate(3); }
    bodies[2].querySelectorAll('.cal-day').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.date === key)));
    clearError(); update();
  }

  /* ── step 3: time slots ──────────────────────────────────────────────────── */
  async function loadSlots() {
    const r = await get(API.slots, { services: idsParam(), date: S.date });
    S.slots = r.slots;
    if (S.slot && !r.slots.some((s) => s.start === S.slot.start && s.available)) S.slot = null;   // chosen time was taken meanwhile
    renderSlots();
  }
  function renderSlots() {
    $('#slot-lede').textContent = longDate(S.date) + ' · ' + dur(totalMin()) + ' visit. Crossed-out times are taken.';
    const body = bodies[3];
    if (!S.slots.some((s) => s.available)) {
      body.replaceChildren(h('div', { class: 'empty-state' }, h('span', { class: 'es-arch', 'aria-hidden': 'true' }), h('h2', { text: 'Fully booked that day.' }), h('p', { text: 'Please go back and choose another date.' })));
      return;
    }
    const groups = [['Morning', (t) => t < '12:00'], ['Afternoon', (t) => t >= '12:00' && t < '17:00'], ['Evening', (t) => t >= '17:00']];
    let i = 0;
    const kids = groups.map(([name, test]) => {
      const list = S.slots.filter((s) => test(s.time));
      if (!list.length) return null;
      return h('div', { class: 'slot-group' }, h('h3', { text: name }), h('div', { class: 'slot-grid' }, list.map((s) => h('button', {
        type: 'button', class: 'slot', style: '--i:' + (i++), 'data-start': s.start, disabled: !s.available,
        'aria-pressed': String(!!S.slot && S.slot.start === s.start), 'aria-label': s.label + (s.available ? '' : ' (unavailable)'),
        onclick: () => pickSlot(s), text: s.label }))));
    });
    kids.push(h('p', { class: 'slot-note', id: 'slot-note', 'aria-live': 'polite' }));
    body.replaceChildren(...kids);
    slotNote();
  }
  function slotNote() {
    const n = $('#slot-note'); if (!n) return;
    n.textContent = S.slot ? 'Your visit runs ' + S.slot.label + ' – ' + clockPlus(S.slot.start, totalMin()) + '.' : '';
  }
  function pickSlot(s) {
    if (!S.slot || S.slot.start !== s.start) { S.slot = s; invalidate(4); }
    bodies[3].querySelectorAll('.slot').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.start === s.start)));
    slotNote(); clearError(); update();
  }

  /* ── step 4: beautician ──────────────────────────────────────────────────── */
  async function loadStaff() {
    const r = await get(API.staff, { services: idsParam(), start: S.slot.start });
    if (!r.any_available) return false;
    S.staff = r.staff;
    const cur = S.staff.find((p) => String(p.id) === S.staffId);
    if (S.staffId !== 'any' && (!cur || !cur.available)) S.staffId = 'any';
    renderStaff();
    return true;
  }
  function renderStaff() {
    const pick = (id, cls, photo, name, line, disabled, busy) => h('button', {
      type: 'button', class: 'staff-pick' + (cls ? ' ' + cls : ''), 'data-staff': id, disabled, 'aria-pressed': String(S.staffId === String(id)), onclick: () => pickStaff(id),
    }, h('span', { class: 'sf-photo', 'aria-hidden': 'true' }, photo), h('b', { text: name }), h('span', { text: line }), busy ? h('small', { class: 'busy', text: busy }) : null);
    const initials = (n) => n.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
    const cards = [pick('any', 'any', '✦', 'Best available', 'We assign the right person', false, null)];
    S.staff.forEach((p) => cards.push(pick(p.id, '', p.photo ? h('img', { src: p.photo, alt: '' }) : initials(p.name), p.name,
      p.title + (p.years_experience ? ' · ' + p.years_experience + ' yrs' : ''), !p.available, p.available ? null : 'Busy at ' + S.slot.label)));
    bodies[4].replaceChildren(h('div', { class: 'staff-grid' }, cards));
  }
  function pickStaff(id) {
    S.staffId = String(id); S.summary = null;
    bodies[4].querySelectorAll('.staff-pick').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.staff === S.staffId)));
    update();
  }

  /* ── step 5: review ──────────────────────────────────────────────────────── */
  async function loadSummary() {
    S.summary = await get(API.summary, { services: idsParam(), staff: S.staffId, start: S.slot.start });
    renderSummary();
  }
  function renderSummary() {
    const r = S.summary, when = (k, v) => h('div', {}, h('small', { text: k }), h('b', { text: v }));
    bodies[5].replaceChildren(h('div', { class: 'review' },
      h('div', { class: 'rv-card' }, h('ul', { class: 'rail-list' }, r.services.map((s) => h('li', {}, h('span', { text: s.name + ' · ' + dur(s.duration_minutes) }), h('b', { text: rupee(s.price) })))),
        h('div', { class: 'rail-total' }, h('small', { text: 'Total (' + dur(r.total_minutes) + ')' }), h('b', { text: rupee(r.total_price) }))),
      h('div', { class: 'rv-card rv-when' }, when('Date', longDate(S.date)), when('Time', r.time_label + ' – ' + clock(r.end)),
        when('Beautician', r.staff ? r.staff.name : 'Best available (assigned on confirmation)')),
      h('div', { class: 'rv-card rv-notes' }, h('label', { for: 'rv-notes', text: 'Anything we should know? (optional)' }),
        h('textarea', { id: 'rv-notes', class: 'field-input', maxlength: '1000', placeholder: 'Allergies, preferences, occasion…', oninput: (e) => { S.notes = e.target.value; } }, S.notes)),
      h('p', { class: 'policy', text: 'We will confirm your request shortly. You can cancel or ask to reschedule up to ' + CANCEL_HOURS + ' hours before your appointment, from My bookings.' })));
  }

  /* ── step 6: confirmation ────────────────────────────────────────────────── */
  async function submit() {
    const r = await post(API.book, { services: S.selected, start: S.slot.start, staff: S.staffId === 'any' ? null : Number(S.staffId), notes: S.notes });
    S.booking = r.booking;
    renderDone(r.message);
    go(6);
  }
  function renderDone(message) {
    const b = S.booking, row = (k, v) => h('div', { class: 'rail-row' }, h('span', { text: k }), h('b', { text: v }));
    const mark = h('div', { class: 'wiz-done-mark-wrap', 'aria-hidden': 'true' });
    mark.innerHTML = '<svg class="wiz-done-mark" viewBox="0 0 64 64"><circle cx="32" cy="32" r="30"/><path d="M19 33l9 9 17-19"/></svg>';   // static markup only
    bodies[6].replaceChildren(h('div', { class: 'wiz-done' }, mark,
      h('h2', { tabindex: '-1', id: 'done-title' }, 'Request received.', h('em', { text: 'we will confirm shortly' })),
      h('p', { text: message }),
      h('span', { class: 'wiz-done-id', text: b.public_id }),
      h('div', { class: 'rv-card' },
        b.items.map((i) => row(i.name, rupee(i.price))),
        row('When', longDate(b.start.slice(0, 10)) + ', ' + b.time_label), row('Beautician', b.staff.name + (b.any_staff ? ' (assigned)' : '')),
        row('Duration', dur(b.total_minutes)), row('Status', b.status_label), row('Total', rupee(b.total_price))),
      h('div', { class: 'wiz-done-actions' },
        h('a', { class: 'btn btn-primary', href: b.url, text: 'View booking' }),
        h('a', { class: 'btn btn-ghost', href: D.dashboardUrl, text: 'Back to overview' }),
        h('button', { type: 'button', class: 'btn btn-ghost', onclick: restart, text: 'Book another' }))));
    const t = bodies[6].querySelector('#done-title'); if (t) setTimeout(() => t.focus({ preventScroll: true }), 50);
  }
  function restart() {
    S.selected = []; S.activeCat = null; S.notes = ''; S.booking = null; S.window = null; S.month = null;
    invalidate(2); S.checking = false; S.incompatible = null;
    renderServices(); go(1, true);
  }

  /* ── flow control ────────────────────────────────────────────────────────── */
  async function lostSlot(message) {          // someone else took the time (or it lapsed): refresh and return to step 3
    say(message); S.slot = null; S.summary = null; S.staff = []; S.staffId = 'any';
    try { await loadSlots(); } catch (_) { /* the banner below covers it */ }
    go(3, true); showError(message);
  }
  async function advance() {
    if (!canContinue()) return;
    clearError(); setBusy(true);
    try {
      if (S.step === 1) { if (S.datesKey !== idsParam()) await loadDates(); go(2); }
      else if (S.step === 2) { await loadSlots(); go(3); }
      else if (S.step === 3) {
        if (await loadStaff()) go(4);
        else await lostSlot('Sorry, that time has just been taken. Please choose another.');
      }
      else if (S.step === 4) { await loadSummary(); go(5); }
      else if (S.step === 5) await submit();
    } catch (e) {
      if (e.code === 'slot_unavailable' && S.step >= 3) await lostSlot(e.message);
      else {
        if (e.code === 'no_staff' && S.step === 1) { S.incompatible = e.message; renderCompat(); }
        showError(e.message);
      }
    } finally { setBusy(false); }
  }

  btnNext.addEventListener('click', advance);
  btnBack.addEventListener('click', () => { if (S.step > 1 && !S.busy) go(S.step - 1, true); });

  (async function init() {
    go(1); renderRail();
    try {
      const r = await get(API.services);
      S.cats = r.categories;
      S.cats.forEach((c) => c.services.forEach((s) => S.byId.set(s.id, s)));
      const pre = parseInt(D.preselect, 10);
      if (S.byId.has(pre)) { S.selected = [pre]; const c = S.cats.find((x) => x.services.some((s) => s.id === pre)); S.activeCat = c ? c.id : null; }
      renderServices();
      if (S.selected.length) scheduleCompat();
      update();
    } catch (e) {
      bodies[1].replaceChildren(h('p', { class: 'wiz-error', text: e.message }));
    }
  })();
})();
