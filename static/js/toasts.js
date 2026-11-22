// Auto-dismiss toast messages after a few seconds.
document.querySelectorAll('.toast').forEach((t, i) => {
  setTimeout(() => { t.style.transition = 'opacity .4s'; t.style.opacity = '0'; setTimeout(() => t.remove(), 450); }, 5000 + i * 600);
});
