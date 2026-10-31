// Show the "options" box only for multiple-choice questions.
document.querySelectorAll('select[data-qtype]').forEach(function (select) {
  var form = select.closest('form');
  var box = form.querySelector('[data-options]');
  function sync() { box.hidden = select.value !== 'choice'; }
  select.addEventListener('change', sync);
  sync();
});

// Ask before destructive actions.
document.querySelectorAll('form[data-confirm]').forEach(function (form) {
  form.addEventListener('submit', function (event) {
    if (!window.confirm(form.dataset.confirm)) { event.preventDefault(); }
  });
});
