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

// Dark / Light mode toggle
(function () {
  var toggle = document.getElementById('theme-toggle');
  if (!toggle) return;

  function getActiveTheme() {
    var explicit = document.documentElement.getAttribute('data-theme');
    if (explicit === 'dark' || explicit === 'light') return explicit;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function updateAria(theme) {
    var next = theme === 'dark' ? 'light' : 'dark';
    toggle.setAttribute('aria-label', 'Switch to ' + next + ' mode');
    toggle.setAttribute('title', 'Switch to ' + next + ' mode');
  }

  updateAria(getActiveTheme());

  toggle.addEventListener('click', function () {
    var current = getActiveTheme();
    var next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('theme', next);
    } catch (e) {}
    updateAria(next);
  });

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!localStorage.getItem('theme')) {
        var next = e.matches ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', next);
        updateAria(next);
      }
    });
  }
})();
