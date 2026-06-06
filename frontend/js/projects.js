const ProjectsPage = {
    _activeProjectId: null,
    _activeProjectName: null,

    async init() {
        await this.refresh();
    },

    render() {
        return `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="font-size:18px">Вайб-кодинг</h3>
            <div style="display:flex;gap:6px">
                <button class="btn btn-outline btn-sm" onclick="ProjectsPage.importZip()">📥 Импорт</button>
                <button class="btn btn-primary btn-sm" onclick="ProjectsPage.createForm()">+ Проект</button>
            </div>
        </div>
        <div id="projects-list"></div>
        <div id="project-detail" class="hidden">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
                <button class="btn btn-sm btn-outline" onclick="ProjectsPage.closeDetail()">← Назад</button>
                <span id="project-detail-name" style="font-weight:600;font-size:16px"></span>
                <button class="btn btn-sm btn-outline" onclick="ProjectsPage.downloadZip(ProjectsPage._activeProjectId)">📦 ZIP</button>
            </div>
            <div id="project-file-tree" style="margin-bottom:12px"></div>
            <div style="font-size:13px;color:var(--tg-hint);margin-bottom:8px">💬 Чат с AI в контексте проекта:</div>
            <div id="project-chat-messages" class="chat-messages" style="max-height:300px;overflow-y:auto;margin-bottom:8px"></div>
            <div class="chat-input-bar" style="position:static;border:none;padding:0 0 12px 0">
                <textarea id="project-chat-input" rows="1" placeholder="Опиши что создать..."
                    onkeydown="ProjectsPage.onChatKey(event)" oninput="ChatPage.autoResize(this)"></textarea>
                <button class="btn btn-primary btn-sm" onclick="ProjectsPage.sendChat()">▶</button>
            </div>
            <div id="project-terminal"></div>
        </div>
        <input type="file" id="zip-import-input" accept=".zip" style="display:none" onchange="ProjectsPage.onZipImport(event)">`;
    },

    async refresh() {
        try {
            const projects = await API.get('/api/projects');
            const el = document.getElementById('projects-list');
            if (!el) return;
            if (projects.length === 0) {
                el.innerHTML = '<div class="empty-state"><div class="empty-icon">📁</div><p>Нет проектов</p><p>Создай первый!</p></div>';
                return;
            }
            el.innerHTML = projects.map(renderProjectCard).join('');
        } catch (e) {
            const el = document.getElementById('projects-list');
            if (el) el.innerHTML = `<div class="empty-state">Ошибка: ${escapeHtml(e.message)}</div>`;
        }
    },

    createForm() {
        Modal.open('Новый проект', `
            <form onsubmit="ProjectsPage.saveNew(event)">
                <div class="form-group">
                    <label>Название проекта</label>
                    <input name="name" required placeholder="my-awesome-app">
                </div>
                <button class="btn btn-primary" style="width:100%">Создать</button>
            </form>`);
    },

    async saveNew(e) {
        e.preventDefault();
        const name = e.target.name.value;
        try {
            await API.post('/api/projects', { name });
            Modal.close();
            await this.refresh();
            Toast.show('Проект создан');
        } catch (e) { Toast.show('Ошибка: ' + e.message); }
    },

    async open(id) {
        try {
            const project = await API.get(`/api/projects/${id}`);
            this._activeProjectId = id;
            this._activeProjectName = project.name;

            document.getElementById('projects-list').classList.add('hidden');
            const detail = document.getElementById('project-detail');
            detail.classList.remove('hidden');
            document.getElementById('project-detail-name').textContent = project.name;
            document.getElementById('project-file-tree').innerHTML = renderFileTree(project.file_tree);

            document.getElementById('project-chat-messages').innerHTML =
                '<div class="empty-state"><p>Напиши AI чтобы создать код в проекте</p></div>';

            TerminalPage.init(id);
        } catch (e) { Toast.show('Ошибка: ' + e.message); }
    },

    closeDetail() {
        this._activeProjectId = null;
        this._activeProjectName = null;
        document.getElementById('projects-list').classList.remove('hidden');
        document.getElementById('project-detail').classList.add('hidden');
    },

    async delete(id) {
        if (!confirm('Удалить проект безвозвратно?')) return;
        await API.delete(`/api/projects/${id}`);
        if (this._activeProjectId === id) this.closeDetail();
        await this.refresh();
        Toast.show('Удалено');
    },

    async downloadZip(id) {
        window.open(`${API._base}/api/projects/${id}/zip?token=${API._token}`, '_blank');
    },

    importZip() {
        document.getElementById('zip-import-input').click();
    },

    async onZipImport(event) {
        const file = event.target.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('file', file);
        try {
            const res = await API.upload('/api/projects/import-zip', fd);
            Toast.show(`Импортировано: ${res.extracted_files} файлов`);
            await this.refresh();
        } catch (e) { Toast.show('Ошибка: ' + e.message); }
        event.target.value = '';
    },

    async sendChat() {
        const input = document.getElementById('project-chat-input');
        const message = input.value.trim();
        if (!message || !this._activeProjectId) return;
        input.value = '';
        ChatPage.autoResize(input);

        const msgsEl = document.getElementById('project-chat-messages');
        if (msgsEl.querySelector('.empty-state')) msgsEl.innerHTML = '';

        msgsEl.appendChild(ChatPage._msgEl('user', message));
        let streamEl = ChatPage._msgEl('assistant', '', true);
        msgsEl.appendChild(streamEl);
        msgsEl.scrollTop = msgsEl.scrollHeight;

        API.stream(
            `/api/projects/${this._activeProjectId}/chat/stream`,
            { message },
            (data) => {
                if (data.content) {
                    streamEl._fullContent = (streamEl._fullContent || '') + data.content;
                    streamEl.innerHTML = mdToHtml(streamEl._fullContent);
                }
                if (data.type === 'files' && data.display) {
                    streamEl.innerHTML = mdToHtml(data.display);
                    this.open(this._activeProjectId); // refresh file tree
                }
                msgsEl.scrollTop = msgsEl.scrollHeight;
            },
            () => {
                streamEl.classList.remove('streaming');
                this.open(this._activeProjectId);
            },
            (err) => {
                streamEl.innerHTML = `⚠️ ${escapeHtml(err.message || 'Ошибка')}`;
                streamEl.classList.remove('streaming');
            }
        );
    },

    onChatKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.sendChat();
        }
    }
};
