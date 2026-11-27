/* Purchase form: add/remove product rows and show a running total. The server recalculates the real total. */
(function () {
  'use strict';
  const rows = document.getElementById('item-rows');
  if (!rows) return;
  const counter = document.getElementById('id_items-TOTAL_FORMS');
  const template = document.getElementById('item-empty');
  const totalEl = document.getElementById('items-total');

  const live = () => Array.from(rows.querySelectorAll('.inv-item-row')).filter((r) => !r.hidden);
  function recalc() {
    let sum = 0;
    live().forEach((row) => {
      const q = parseFloat(row.querySelector('[name$="-quantity"]').value) || 0;
      const c = parseFloat(row.querySelector('[name$="-unit_cost"]').value) || 0;
      const line = q * c;
      row.querySelector('.inv-line').textContent = '\u20B9' + line.toFixed(2);
      sum += line;
    });
    totalEl.textContent = '\u20B9' + sum.toFixed(2);
  }
  document.getElementById('add-item').addEventListener('click', () => {
    const html = template.innerHTML.replace(/__prefix__/g, counter.value);
    rows.insertAdjacentHTML('beforeend', html);
    counter.value = String(parseInt(counter.value, 10) + 1);
    recalc();
  });
  rows.addEventListener('click', (e) => {
    const btn = e.target.closest('.inv-remove');
    if (!btn) return;
    const row = btn.closest('.inv-item-row');
    const del = row.querySelector('[name$="-DELETE"]');
    if (del) del.checked = true;
    row.hidden = true;
    recalc();
  });
  rows.addEventListener('input', recalc);
  recalc();
})();
