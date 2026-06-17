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
