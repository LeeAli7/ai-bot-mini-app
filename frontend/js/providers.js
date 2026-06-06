const ProvidersPage = {
    async init() {
        await this.refresh();
    },

    render() {
        return `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="font-size:18px">Провайдеры</h3>
            <button class="btn btn-primary btn-sm" onclick="ProvidersPage.addForm()">+ Добавить</button>
        </div>
        <div id="providers-list"></div>`;
    },

    async refresh() {
        try {
            const providers = await API.get('/api/providers');
            const el = document.getElementById('providers-list');
            if (!el) return;
            if (providers.length === 0) {
                el.innerHTML = '<div class="empty-state"><div class="empty-icon">📡</div><p>Нет провайдеров</p><p>Добавь первого!</p></div>';
                return;
            }
            el.innerHTML = providers.map(renderProviderCard).join('');
            ChatPage.loadProviders();
        } catch (e) {
            const el = document.getElementById('providers-list');
            if (el) el.innerHTML = `<div class="empty-state">Ошибка загрузки: ${escapeHtml(e.message)}</div>`;
        }
    },

    addForm() {
        Modal.open('Добавить провайдера', this._formHtml({}));
    },

    async editForm(id) {
        try {
            const p = await API.get(`/api/providers/${id}`);
            Modal.open('Редактировать', this._formHtml(p, id));
        } catch (e) { Toast.show('Ошибка: ' + e.message); }
    },

    async save(e) {
        e.preventDefault();
        const form = e.target;
        const data = {
            name: form.name.value,
            base_url: form.base_url.value,
            api_key: form.api_key.value,
            model: form.model.value,
            system_prompt: form.system_prompt.value,
            temperature: parseInt(form.temperature.value) || 7,
            context_length: parseInt(form.context_length.value) || 10,
        };

        const id = form.dataset.id;
        try {
            if (id) {
                await API.patch(`/api/providers/${id}`, data);
            } else {
                await API.post('/api/providers', data);
            }
            Modal.close();
            await this.refresh();
            Toast.show(id ? 'Обновлено' : 'Добавлено');
        } catch (e) { Toast.show('Ошибка: ' + e.message); }
    },

    async activate(id) {
        await API.post(`/api/providers/${id}/activate`);
        await this.refresh();
        Toast.show('Провайдер активирован');
    },

    async delete(id) {
        if (!confirm('Удалить провайдера и его историю?')) return;
        await API.delete(`/api/providers/${id}`);
        await this.refresh();
        Toast.show('Удалено');
    },

    async clearHistory(id) {
        if (!confirm('Очистить историю чата для этого провайдера?')) return;
        await API.post(`/api/providers/${id}/clear-history`);
        Toast.show('История очищена');
    },

    async test(id) {
        Toast.show('Проверяю подключение...');
        try {
            const res = await API.post(`/api/providers/${id}/test`);
            if (res.status === 'ok') {
                Toast.show('✓ Подключение успешно: ' + truncate(res.message, 80));
            } else {
                Toast.show('✗ Ошибка: ' + truncate(res.message, 80));
            }
        } catch (e) { Toast.show('Ошибка: ' + e.message); }
    },

    _formHtml(p, id) {
        const isEdit = !!id;
        return `
        <form onsubmit="ProvidersPage.save(event)" data-id="${id || ''}">
            <div class="form-group">
                <label>Название *</label>
                <input name="name" value="${escapeHtml(p.name || '')}" required placeholder="OpenAI / Groq / Ollama...">
            </div>
            <div class="form-group">
                <label>Base URL *</label>
                <input name="base_url" value="${escapeHtml(p.base_url || '')}" required placeholder="https://api.openai.com">
            </div>
            <div class="form-group">
                <label>API Key * ${isEdit ? '(оставь пустым чтоб не менять)' : ''}</label>
                <input name="api_key" value="" ${!isEdit ? 'required' : ''} placeholder="${isEdit ? '••••••••' : 'sk-...'}" type="password">
            </div>
            <div class="form-group">
                <label>Модель</label>
                <input name="model" value="${escapeHtml(p.model || 'gpt-3.5-turbo')}">
            </div>
            <div class="form-group">
                <label>System Prompt</label>
                <textarea name="system_prompt" rows="2">${escapeHtml(p.system_prompt || '')}</textarea>
            </div>
            <div class="form-group" style="display:flex;gap:12px">
                <div style="flex:1">
                    <label>Temperature (0-20)</label>
                    <input name="temperature" type="number" min="0" max="20" value="${p.temperature || 7}">
                </div>
                <div style="flex:1">
                    <label>Контекст (1-200)</label>
                    <input name="context_length" type="number" min="1" max="200" value="${p.context_length || 10}">
                </div>
            </div>
            <button class="btn btn-primary" style="width:100%;margin-top:8px">${isEdit ? 'Сохранить' : 'Добавить'}</button>
        </form>`;
    }
};
