function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function mdToHtml(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
    });

    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');

    // Italic
    html = html.replace(/\*([^*]+)\*/g, '<i>$1</i>');

    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

    // Line breaks
    html = html.replace(/\n/g, '<br>');

    return html;
}

function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    return d.toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function fileIcon(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    const icons = {
        py: '🐍', js: '🟨', ts: '🔷', jsx: '⚛️', tsx: '⚛️',
        html: '🌐', css: '🎨', json: '📋', yaml: '📋', yml: '📋',
        md: '📝', txt: '📄', sh: '💻', go: '🔵', rs: '🦀',
        java: '☕', c: '⚙️', cpp: '⚙️', h: '🔧', sql: '🗄️',
        php: '🐘', rb: '💎', swift: '🦅', kt: '🅱️',
        png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', webp: '🖼️', svg: '🖼️',
        zip: '📦', mp3: '🎵', wav: '🎵', ogg: '🎵', mp4: '🎬',
    };
    return icons[ext] || '📄';
}

function truncate(str, n) {
    return str.length > n ? str.slice(0, n) + '...' : str;
}
