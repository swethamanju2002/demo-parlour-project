/* Portal behaviours shared by every customer page: confirm-then-fetch for cancel/reschedule forms.
   Wrapped in a closure: motion.js declares top-level const/let names (form, grid, io...), so nothing here may be global. */
(function () {
  'use strict';
  const dlg = document.getElementById('confirm-dialog');
  const reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const notify = (msg, kind) => { if (typeof window.toast === 'function') window.toast(msg, kind); };

  function confirmDialog({ title, text, yes }) {
    if (!dlg || typeof dlg.showModal !== 'function') return Promise.resolve(window.confirm(title + '\n\n' + text));
    dlg.querySelector('#cd-title').textContent = title;
    dlg.querySelector('#cd-text').textContent = text;
    const yesBtn = dlg.querySelector('[data-cd="yes"]'), noBtn = dlg.querySelector('[data-cd="no"]');
    yesBtn.textContent = yes || 'Confirm';
    return new Promise((resolve) => {
      const finish = (value) => {
        yesBtn.removeEventListener('click', onYes); noBtn.removeEventListener('click', onNo);
        dlg.removeEventListener('cancel', onCancel); dlg.removeEventListener('click', onBackdrop);
        if (dlg.open) dlg.close();
        resolve(value);
      };
      const onYes = () => finish(true), onNo = () => finish(false);
      const onCancel = (e) => { e.preventDefault(); finish(false); };       // Esc
      const onBackdrop = (e) => { if (e.target === dlg) finish(false); };   // click outside the card
      yesBtn.addEventListener('click', onYes); noBtn.addEventListener('click', onNo);
      dlg.addEventListener('cancel', onCancel); dlg.addEventListener('click', onBackdrop);
      dlg.showModal();
      noBtn.focus();
    });
  }

  async function send(form) {
    const btn = form.querySelector('button[type="submit"]');
    if (btn) { btn.disabled = true; btn.classList.add('is-busy'); }
    let done = false;
    try {
      const res = await fetch(form.action, {
        method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'x-requested-with': 'fetch' },
      });
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
      if (res.ok && data && data.ok) {
        done = true;
        notify(data.message, 'success');
        setTimeout(() => location.reload(), reduce ? 0 : 900);   // the page re-renders with the new status
      } else {
        notify((data && data.error) || 'Something went wrong. Please try again.', 'error');
      }
    } catch (_) {
      notify('We could not reach the salon system. Please check your connection and try again.', 'error');
    }
    if (!done && btn) { btn.disabled = false; btn.classList.remove('is-busy'); }
  }

  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-action-form')) return;
    e.preventDefault();
    const d = form.dataset;
    if (d.confirmTitle && !(await confirmDialog({ title: d.confirmTitle, text: d.confirmText || '', yes: d.confirmYes }))) return;
    send(form);
  });
})();
