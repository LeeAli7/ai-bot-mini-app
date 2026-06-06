const Modal = {
    open(title, html) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = html;
        document.getElementById('modal-overlay').classList.remove('hidden');
    },
    close() {
        document.getElementById('modal-overlay').classList.add('hidden');
        document.getElementById('modal-body').innerHTML = '';
    },
    setBody(html) {
        document.getElementById('modal-body').innerHTML = html;
    }
};

const Toast = {
    _timer: null,

    show(msg, duration = 2500) {
        const el = document.getElementById('toast');
        el.textContent = msg;
        el.classList.remove('hidden');
        clearTimeout(this._timer);
        this._timer = setTimeout(() => el.classList.add('hidden'), duration);
    }
};

function renderFileTree(treeText) {
    if (!treeText) return '<div class="empty-state">Пустой проект</div>';
    return `<div class="file-tree">${escapeHtml(treeText)}</div>`;
}

function renderProviderCard(p) {
    const badge = p.is_active
        ? '<span class="badge badge-active">Активен</span>'
        : '<span class="badge badge-inactive">Не активен</span>';

    return `
    <div class="provider-card">
        <div class="provider-name">${escapeHtml(p.name)} ${badge}</div>
        <div class="provider-detail">${escapeHtml(p.model)} | ${escapeHtml(p.base_url)}</div>
        <div class="provider-detail">Temp: ${p.temperature} | Context: ${p.context_length}</div>
        <div class="provider-actions">
            ${!p.is_active ? `<button class="btn btn-sm btn-primary" onclick="ProvidersPage.activate(${p.id})">✓ Актив.</button>` : ''}
            <button class="btn btn-sm btn-outline" onclick="ProvidersPage.editForm(${p.id})">✎ Ред.</button>
            <button class="btn btn-sm btn-outline" onclick="ProvidersPage.clearHistory(${p.id})">🗑 Ист.</button>
            <button class="btn btn-sm btn-outline" onclick="ProvidersPage.test(${p.id})">🔍 Тест</button>
            <button class="btn btn-sm btn-danger" onclick="ProvidersPage.delete(${p.id})">✕ Удал.</button>
        </div>
    </div>`;
}

function renderProjectCard(p) {
    const activeClass = ProjectsPage._activeProjectId === p.id ? ' active-project' : '';
    return `
    <div class="project-card${activeClass}" onclick="ProjectsPage.open(${p.id})">
        <div>
            <div style="font-weight:600">📁 ${escapeHtml(p.name)}</div>
            <div style="font-size:12px;color:var(--tg-hint)">${formatDate(p.updated_at)}</div>
        </div>
        <div style="display:flex;gap:4px">
            <button class="btn btn-sm btn-outline" onclick="event.stopPropagation();ProjectsPage.downloadZip(${p.id})">📦</button>
            <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();ProjectsPage.delete(${p.id})">✕</button>
        </div>
    </div>`;
}

function renderChatMessage(msg) {
    const cls = msg.role === 'user' ? 'user' : 'assistant';
    const html = mdToHtml(msg.content || '');
    return `<div class="msg ${cls}">${html}</div>`;
}
