// base.js — shared theme utilities and safe rendering helpers

function getTheme() {
    return document.documentElement.getAttribute("data-theme") || "light";
}

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
        localStorage.setItem("theme", theme);
    } catch {
        /* storage unavailable */
    }
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
    // headers — order matters: ### before ## before #
    out = out.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    out = out.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    out = out.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    // images ![alt](url) — before links to avoid conflict
    out = out.replace(
        /!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g,
        '<img src="$2" alt="$1" loading="lazy">',
    );
    // links [text](url)
    out = out.replace(
        /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>',
    );
    // bold
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // italic
    out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    // unordered lists — consecutive lines starting with - or *
    out = out.replace(/(?:(?:^|\n)[-*]\s+[^\n]+)+/g, (block) => {
        const items = block.replace(/(?:^|\n)[-*]\s+([^\n]+)/g, "<li>$1</li>");
        return `<ul>${items}</ul>`;
    });
    // ordered lists — consecutive lines starting with digit(s).
    out = out.replace(/(?:(?:^|\n)\d+\.\s+[^\n]+)+/g, (block) => {
        const items = block.replace(/(?:^|\n)\d+\.\s+([^\n]+)/g, "<li>$1</li>");
        return `<ol>${items}</ol>`;
    });
    // tables — consecutive lines with pipe separators
    out = out.replace(/(?:(?:^|\n)\|[^\n]+\|[^\n]*)+/g, (block) => {
        const rows = block.trim().split("\n");
        let html = "<table>";
        const hasHeader = rows.length >= 2 && /^\|[\s\-:|]+\|$/.test(rows[1].trim());
        for (let i = 0; i < rows.length; i++) {
            const row = rows[i].trim();
            if (/^\|[\s\-:|]+\|$/.test(row)) continue;
            const cells = row.replace(/^\||\|$/g, "").split("|");
            const tag = hasHeader && i === 0 ? "th" : "td";
            html += "<tr>";
            for (let j = 0; j < cells.length; j++) {
                html += `<${tag}>${cells[j].trim()}</${tag}>`;
            }
            html += "</tr>";
        }
        html += "</table>";
        return html;
    });
    // blockquotes
    out = out.replace(/(?:^|\n)&gt;\s+([^\n]+)/g, "\n<blockquote>$1</blockquote>");
    return out;
}

// Expose globally — these are called from HTML templates
window.toggleTheme = toggleTheme;
window.initThemeIcon = initThemeIcon;
window.renderSafeMarkdown = renderSafeMarkdown;
window.escapeHtml = escapeHtml;

// ── Top Progress Loading Bar ──
var _progressBarTimer = null;
function startTopProgressBar() {
    var bar = document.getElementById('topProgressBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'topProgressBar';
        bar.style.position = 'fixed';
        bar.style.top = '0';
        bar.style.left = '0';
        bar.style.height = '3px';
        bar.style.background = 'linear-gradient(90deg, #00f2fe, #4facfe, #a18cd1)';
        bar.style.boxShadow = '0 0 8px #00f2fe';
        bar.style.zIndex = '99999';
        bar.style.width = '0%';
        bar.style.transition = 'width 0.4s ease, opacity 0.4s ease';
        document.body.appendChild(bar);
    }
    bar.style.opacity = '1';
    bar.style.width = '0%';
    
    if (_progressBarTimer) clearInterval(_progressBarTimer);
    
    var progress = 0;
    _progressBarTimer = setInterval(function() {
        if (progress < 85) {
            progress += Math.random() * 8;
            bar.style.width = progress + '%';
        }
    }, 250);
}

function completeTopProgressBar() {
    var bar = document.getElementById('topProgressBar');
    if (!bar) return;
    if (_progressBarTimer) clearInterval(_progressBarTimer);
    bar.style.width = '100%';
    setTimeout(function() {
        bar.style.opacity = '0';
        setTimeout(function() {
            bar.style.width = '0%';
        }, 400);
    }, 300);
}

window.startTopProgressBar = startTopProgressBar;
window.completeTopProgressBar = completeTopProgressBar;

document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('click', function(e) {
        var a = e.target.closest('a');
        if (a && a.href && !a.getAttribute('href').startsWith('#') && !a.getAttribute('href').startsWith('javascript:') && a.target !== '_blank' && !e.ctrlKey && !e.metaKey) {
            startTopProgressBar();
        }
    });
    document.addEventListener('submit', function(e) {
        if (!e.defaultPrevented) {
            startTopProgressBar();
        }
    });
    // Complete progress bar when page is fully loaded
    completeTopProgressBar();
});
