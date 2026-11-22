document.documentElement.classList.add('js');
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* Split page-head titles into words for a masked rise */
document.querySelectorAll('[data-split]').forEach(el => {
  const words = el.textContent.trim().split(/\s+/);
  el.setAttribute('aria-label', el.textContent.trim());
  el.innerHTML = words.map((w, i) => `<span class="w" aria-hidden="true"><span style="--w:${i}">${w}</span></span>`).join(' ');
});

/* Scroll reveal */
const io = new IntersectionObserver((entries) => {
  entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
}, { threshold: .15, rootMargin: '0px 0px -6% 0px' });
document.querySelectorAll('[data-reveal], [data-split]').forEach(el => reduce ? el.classList.add('in') : io.observe(el));

/* Animated counters */
const cio = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (!e.isIntersecting) return;
    const el = e.target, end = +el.dataset.count, suffix = el.dataset.suffix || '';
    cio.unobserve(el);
    if (reduce) { el.textContent = end + suffix; return; }
    const t0 = performance.now(), dur = 1400;
    const tick = (t) => {
      const p = Math.min((t - t0) / dur, 1), eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(end * eased) + (p === 1 ? suffix : '');
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}, { threshold: .6 });
document.querySelectorAll('[data-count]').forEach(el => cio.observe(el));

/* Gentle parallax */
const par = [...document.querySelectorAll('[data-parallax]')];
if (par.length && !reduce) {
  let ticking = false;
  addEventListener('scroll', () => {
    if (ticking) return; ticking = true;
    requestAnimationFrame(() => {
      par.forEach(el => {
        const r = el.getBoundingClientRect(), k = parseFloat(el.dataset.parallax);
        el.style.translate = `0 ${((r.top + r.height / 2) - innerHeight / 2) * k * -1}px`;
      });
      ticking = false;
    });
  }, { passive: true });
}

/* Page transition: fade out on internal navigation */
document.addEventListener('click', (e) => {
  const a = e.target.closest('a[href]');
  if (!a || reduce || e.metaKey || e.ctrlKey || e.shiftKey || a.target === '_blank') return;
  const u = new URL(a.href, location.href);
  if (u.origin !== location.origin || (u.pathname === location.pathname && u.hash) || u.protocol.startsWith('tel')) return;
  e.preventDefault();
  document.body.classList.add('leaving');
  setTimeout(() => { location.href = a.href; }, 220);
});
addEventListener('pageshow', (e) => { if (e.persisted) document.body.classList.remove('leaving'); });

/* Before/after sliders */
function initBA(root) {
  const range = root.querySelector('.ba-range');
  const set = () => root.style.setProperty('--pos', range.value + '%');
  range.addEventListener('input', set); set();
}
document.querySelectorAll('[data-ba]').forEach(initBA);

/* Testimonials carousel */
document.querySelectorAll('[data-carousel]').forEach(c => {
  const slides = [...c.querySelectorAll('.quote')], dots = [...c.querySelectorAll('.quote-dots button')];
  let i = 0, timer;
  const show = (n) => {
    slides[i].classList.remove('is-active'); dots[i].classList.remove('on');
    i = (n + slides.length) % slides.length;
    slides[i].classList.add('is-active'); dots[i].classList.add('on');
    // keep container height stable: active slide is position:relative, others absolute
  };
  const start = () => { if (!reduce && slides.length > 1) timer = setInterval(() => show(i + 1), 6000); };
  dots.forEach((d, n) => d.addEventListener('click', () => { clearInterval(timer); show(n); start(); }));
  c.addEventListener('mouseenter', () => clearInterval(timer)); c.addEventListener('mouseleave', start);
  start();
});

/* Copy coupon code */
document.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(b.dataset.copy); } catch (_) {}
  const label = b.querySelector('em'), old = label.textContent;
  b.classList.add('done'); label.textContent = 'Copied'; setTimeout(() => { b.classList.remove('done'); label.textContent = old; }, 1800);
}));

/* Services: highlight the category tab in view */
const tabs = [...document.querySelectorAll('.cat-tabs a')];
if (tabs.length) {
  const tio = new IntersectionObserver((es) => es.forEach(e => {
    if (e.isIntersecting) tabs.forEach(t => t.classList.toggle('on', t.getAttribute('href') === '#' + e.target.id));
  }), { rootMargin: '-35% 0px -55% 0px' });
  document.querySelectorAll('.cat-block').forEach(s => tio.observe(s));
}

/* Gallery: filter with fade, and lightbox */
const grid = document.getElementById('masonry');
if (grid) {
  const items = [...grid.querySelectorAll('.m-item')];
  items.forEach(i => i.classList.add('in'));
  document.querySelectorAll('[data-filter]').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('on', b === btn));
    const f = btn.dataset.filter;
    items.forEach(it => it.classList.add('fade'));
    setTimeout(() => {
      items.forEach(it => { it.classList.toggle('hide', f !== 'all' && it.dataset.cat !== f); });
      requestAnimationFrame(() => items.forEach(it => it.classList.remove('fade')));
    }, reduce ? 0 : 280);
  }));
  const dlg = document.getElementById('lightbox'), stage = dlg.querySelector('.lb-stage'), title = dlg.querySelector('.lb-title');
  grid.addEventListener('click', (e) => {
    const b = e.target.closest('.m-open'); if (!b) return;
    title.textContent = b.dataset.title;
    if (b.dataset.before) {
      stage.innerHTML = `<div class="ba" data-ba><img src="${b.dataset.full}" alt="After"><div class="ba-before"><img src="${b.dataset.before}" alt="Before"></div><span class="ba-tag ba-tag-l">Before</span><span class="ba-tag ba-tag-r">After</span><input class="ba-range" type="range" min="0" max="100" value="50" aria-label="Compare before and after"><span class="ba-handle"></span></div>`;
      initBA(stage.querySelector('[data-ba]'));
    } else { stage.innerHTML = `<img src="${b.dataset.full}" alt="${b.dataset.title}">`; }
    dlg.showModal();
  });
  dlg.querySelector('.lb-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
}

/* Contact form: inline validation feedback without a page reload */
const form = document.getElementById('enquiry-form');
if (form) {
  const interest = new URLSearchParams(location.search).get('interest');
  if (interest && form.interested_in) form.interested_in.value = interest;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type=submit]');
    form.querySelectorAll('[data-err]').forEach(p => p.textContent = '');
    btn.disabled = true; btn.classList.add('sending');
    try {
      const r = await fetch(form.action || location.href, { method: 'POST', body: new FormData(form), headers: { 'x-requested-with': 'fetch' } });
      const data = await r.json();
      if (data.ok) { form.reset(); toast(data.message, 'success'); }
      else { Object.entries(data.errors).forEach(([k, v]) => { const p = form.querySelector(`[data-err="${k}"]`); if (p) p.textContent = v; }); toast('Please check the highlighted fields.', 'error'); }
    } catch (_) { toast('Could not send right now. Please try again or message us on WhatsApp.', 'error'); }
    btn.disabled = false; btn.classList.remove('sending');
  });
}
function toast(msg, kind) {
  let wrap = document.querySelector('.toasts');
  if (!wrap) { wrap = document.createElement('div'); wrap.className = 'toasts'; wrap.setAttribute('role', 'status'); document.body.appendChild(wrap); }
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.textContent = msg; wrap.appendChild(t);
  setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = 0; setTimeout(() => t.remove(), 450); }, 5000);
}
