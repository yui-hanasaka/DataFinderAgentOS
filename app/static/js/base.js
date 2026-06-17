// base.js — shared theme utilities and safe rendering helpers

function getTheme() {
    return document.documentElement.getAttribute("data-theme") || "light";
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch { /* storage unavailable */ }
}

function toggleTheme() {
    var next = getTheme() === "dark" ? "light" : "dark";
    setTheme(next);
    updateThemeIcon(next);
}

function initThemeIcon(iconId) {
    updateThemeIcon(getTheme(), iconId);
}

function updateThemeIcon(theme, iconId) {
    var el = document.getElementById(iconId || "themeIcon");
    if (!el) return;
    el.textContent = theme === "dark" ? "☀" : "🌙";
    el.title = theme === "dark" ? "切换浅色主题" : "切换暗色主题";
}

/* ── Safe HTML helpers ── */
var _escapeMap = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => _escapeMap[c] || c);
}

function renderSafeMarkdown(text) {
    var out = escapeHtml(text);
    // fenced code blocks
    out = out.replace(
        /```(\w*)\n?([\s\S]*?)```/g,
        (_, _lang, code) => `<pre><code>${code.trim()}</code></pre>`,
    );
    // inline code
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
    // bold
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // italic
    out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // unordered lists — lines starting with - or *
    out = out.replace(/(?:^|\n)[-*]\s+([^\n]+)/g, "\n<li>$1</li>");
    out = out.replace(/((?:<li>[^<]*<\/li>\n?)+)/g, "<ul>$1</ul>");
    // blockquotes
    out = out.replace(/(?:^|\n)&gt;\s+([^\n]+)/g, "\n<blockquote>$1</blockquote>");
    // links [text](url)
    out = out.replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>',
    );
    return out;
}

// Expose globally — these are called from HTML templates
window.toggleTheme = toggleTheme;
window.initThemeIcon = initThemeIcon;
window.renderSafeMarkdown = renderSafeMarkdown;
