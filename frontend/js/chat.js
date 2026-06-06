const ChatPage = {
    _providerId: null,
    _streaming: false,
    _abortController: null,

    async init() {
        await this.loadProviders();
    },

    async loadProviders() {
        try {
            const providers = await API.get('/api/providers');
            const active = providers.find(p => p.is_active);
            if (active) this._providerId = active.id;
            const sel = document.getElementById('chat-provider-select');
            if (sel) {
                sel.innerHTML = providers.map(p =>
                    `<option value="${p.id}" ${p.is_active ? 'selected' : ''}>${escapeHtml(p.name)} (${escapeHtml(p.model)})</option>`
                ).join('');
                sel.value = active?.id || '';
            }
        } catch (e) {
            // providers not loaded yet
        }
    },

    render() {
        return `
        <div class="chat-header">
            <div class="provider-select">
                <select id="chat-provider-select" onchange="ChatPage.switchProvider(this.value)">
                    <option value="">Нет провайдеров</option>
                </select>
            </div>
            <button class="btn btn-sm btn-outline" onclick="ChatPage.clearHistory()">🗑</button>
            <button class="btn btn-sm btn-outline" id="btn-reasoning" onclick="ChatPage.toggleReasoning()">💭</button>
        </div>
        <div id="chat-messages" class="chat-messages">
            <div class="empty-state">
                <div class="empty-icon">💬</div>
                <p>Выбери провайдера и начни общение</p>
            </div>
        </div>
        <div class="chat-input-bar">
            <textarea id="chat-input" rows="1" placeholder="Сообщение..."
                onkeydown="ChatPage.onInputKey(event)" oninput="ChatPage.autoResize(this)"></textarea>
            <input type="file" id="attach-file" accept="image/*,audio/*,.zip,.txt,.py,.js,.html,.css,.json,.md"
                style="display:none" onchange="ChatPage.onAttach(event)">
            <button class="btn-icon" onclick="document.getElementById('attach-file').click()" title="Прикрепить">📎</button>
            <button id="btn-send" class="btn btn-primary btn-sm" onclick="ChatPage.send()">▶</button>
            <button id="btn-cancel" class="btn btn-danger btn-sm hidden" onclick="ChatPage.cancel()">■</button>
        </div>`;
    },

    switchProvider(id) {
        this._providerId = parseInt(id);
    },

    async send() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        if (!message || this._streaming) return;
        if (!this._providerId) { Toast.show('Сначала добавь провайдера'); return; }

        input.value = '';
        this.autoResize(input);
        this._streaming = true;

        const msgsEl = document.getElementById('chat-messages');
        if (msgsEl.querySelector('.empty-state')) msgsEl.innerHTML = '';

        // Add user message
        msgsEl.appendChild(this._msgEl('user', message));
        this._scrollBottom();

        // Create streaming assistant message
        const streamEl = this._msgEl('assistant', '', true);
        msgsEl.appendChild(streamEl);
        this._scrollBottom();

        // Load history first
        let historyMessages = [];
        try {
            const hist = await API.get('/api/chat/history', { provider_id: this._providerId, limit: 20 });
            historyMessages = hist.messages || [];
        } catch (e) { /* ok */ }

        this._toggleSendBtn(false);

        API.stream(
            '/api/chat/stream',
            { message, provider_id: this._providerId },
            (data) => {
                if (data.content) {
                    streamEl._fullContent = (streamEl._fullContent || '') + data.content;
                    streamEl.innerHTML = mdToHtml(streamEl._fullContent);
                }
                if (data.reasoning && streamEl._fullContent === undefined) {
                    const rDiv = document.createElement('div');
                    rDiv.className = 'msg reasoning';
                    rDiv.textContent = data.reasoning;
                    msgsEl.insertBefore(rDiv, streamEl);
                }
                this._scrollBottom();
            },
            () => {
                streamEl.classList.remove('streaming');
                this._streaming = false;
                this._toggleSendBtn(true);
                this.loadProviders();
            },
            (err) => {
                streamEl.innerHTML = `⚠️ ${escapeHtml(err.message || 'Ошибка')}`;
                streamEl.classList.remove('streaming');
                this._streaming = false;
                this._toggleSendBtn(true);
            }
        );
    },

    cancel() {
        API.post('/api/chat/cancel');
    },

    async clearHistory() {
        if (!this._providerId) return;
        if (!confirm('Очистить историю чата с этим провайдером?')) return;
        await API.delete('/api/chat/history', { provider_id: this._providerId });
        document.getElementById('chat-messages').innerHTML =
            '<div class="empty-state"><div class="empty-icon">💬</div><p>История очищена</p></div>';
    },

    async toggleReasoning() {
        try {
            const s = await API.get('/api/settings');
            await API.patch('/api/settings', { show_reasoning: !s.show_reasoning });
            Toast.show('Настройки обновлены');
        } catch (e) { Toast.show('Ошибка'); }
    },

    async onAttach(event) {
        const file = event.target.files[0];
        if (!file) return;
        const fd = new FormData();

        try {
            if (file.type.startsWith('image/')) {
                fd.append('image', file);
                fd.append('caption', 'Опиши это изображение.');
                const res = await API.upload('/api/vision', fd);
                const msgsEl = document.getElementById('chat-messages');
                if (msgsEl.querySelector('.empty-state')) msgsEl.innerHTML = '';
                msgsEl.appendChild(this._msgEl('assistant', res.reply));
                this._scrollBottom();
            } else if (file.type.startsWith('audio/')) {
                fd.append('audio', file);
                const res = await API.upload('/api/transcribe', fd);
                document.getElementById('chat-input').value = res.text;
            } else {
                fd.append('document', file);
                const res = await API.upload('/api/document', fd);
                const msgsEl = document.getElementById('chat-messages');
                if (msgsEl.querySelector('.empty-state')) msgsEl.innerHTML = '';
                if (res.type === 'text') {
                    msgsEl.appendChild(this._msgEl('assistant', `📄 *${file.name}*\n\`\`\`\n${res.content}\n\`\`\``));
                } else {
                    msgsEl.appendChild(this._msgEl('assistant', `📎 Файл прочитан: ${res.type}`));
                }
                this._scrollBottom();
            }
        } catch (e) {
            Toast.show('Ошибка: ' + e.message);
        }
        event.target.value = '';
    },

    _msgEl(role, content, streaming = false) {
        const div = document.createElement('div');
        div.className = `msg ${role}${streaming ? ' streaming' : ''}`;
        div.innerHTML = mdToHtml(content);
        div._fullContent = content;
        return div;
    },

    _toggleSendBtn(send) {
        document.getElementById('btn-send').classList.toggle('hidden', !send);
        document.getElementById('btn-cancel').classList.toggle('hidden', send);
    },

    _scrollBottom() {
        const msgsEl = document.getElementById('chat-messages');
        setTimeout(() => { msgsEl.scrollTop = msgsEl.scrollHeight; }, 50);
    },

    onInputKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.send();
        }
    },

    autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
};
