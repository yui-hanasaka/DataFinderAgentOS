// base.js — shared theme utilities

function getTheme() {
  return document.documentElement.getAttribute('data-theme') || 'light';
}

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

function toggleTheme() {
  var next = getTheme() === 'dark' ? 'light' : 'dark';
  setTheme(next);
  updateThemeIcon(next);
}

function initThemeIcon(iconId) {
  updateThemeIcon(getTheme(), iconId);
}

function updateThemeIcon(theme, iconId) {
  var el = document.getElementById(iconId || 'themeIcon');
  if (!el) return;
  el.textContent = theme === 'dark' ? '☀' : '🌙';
  el.title = theme === 'dark' ? '切换浅色主题' : '切换暗色主题';
}
