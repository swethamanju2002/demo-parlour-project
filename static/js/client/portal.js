/* Portal chrome: modal dialogs on the booking detail page. Self-contained; no globals. */
(() => {
  'use strict';
  document.querySelectorAll('[data-open-dialog]').forEach((b) => b.addEventListener('click', () => {
    const d = document.getElementById(b.dataset.openDialog);
    if (d && d.showModal) d.showModal();
  }));
  document.querySelectorAll('dialog.p-dialog').forEach((d) => {
    d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
    d.querySelectorAll('[data-close-dialog]').forEach((b) => b.addEventListener('click', () => d.close()));
    const f = d.querySelector('form');
    if (f) f.addEventListener('submit', () => { const s = f.querySelector('button[type=submit]'); if (s) s.disabled = true; });
  });
})();