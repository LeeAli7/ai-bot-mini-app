const TerminalPage = {
    _projectId: null,
    _active: false,

    init(projectId) {
        this._projectId = projectId;
        this._active = false;

        const el = document.getElementById('project-terminal');
        if (!el) return;

        el.innerHTML = `
        <div style="margin-top:12px">
            <div style="font-size:13px;color:var(--tg-hint);margin-bottom:6px">💻 Терминал:</div>
            <div class="terminal-input-row">
                <input id="terminal-cmd" placeholder="bash / python main.py / npm start"
                    onkeydown="if(event.key==='Enter')TerminalPage.start()">
                <button class="btn btn-sm btn-primary" onclick="TerminalPage.start()">▶</button>
                <button class="btn btn-sm btn-danger hidden" id="terminal-stop-btn" onclick="TerminalPage.stop()">■</button>
            </div>
            <div id="terminal-output" class="terminal-output hidden"></div>
        </div>`;
    },

    async start() {
        const cmdInput = document.getElementById('terminal-cmd');
        const cmd = cmdInput.value.trim() || 'bash';
        cmdInput.value = '';

        try {
            await API.post(`/api/projects/${this._projectId}/terminal/start`, { command: cmd });
        } catch (e) {
            Toast.show('PTY недоступен: ' + e.message);
            return;
        }

        const outputEl = document.getElementById('terminal-output');
        outputEl.classList.remove('hidden');
        outputEl.textContent = `$ ${cmd}\n`;
        document.getElementById('terminal-stop-btn').classList.remove('hidden');
        this._active = true;

        // Stream output
        API.stream(
            `/api/projects/${this._projectId}/terminal/output`,
            {},
            (data) => {
                if (data.type === 'output' && data.text) {
                    outputEl.textContent += data.text;
                    outputEl.scrollTop = outputEl.scrollHeight;
                }
                if (data.type === 'heartbeat') {
                    outputEl.textContent += `\n[${data.message}]`;
                    outputEl.scrollTop = outputEl.scrollHeight;
                }
                if (data.type === 'error') {
                    outputEl.textContent += `\n⚠️ ${data.message}`;
                }
            },
            (data) => {
                outputEl.textContent += `\n[Процесс завершён, код: ${data.exit_code}]`;
                outputEl.scrollTop = outputEl.scrollHeight;
                this._active = false;
                document.getElementById('terminal-stop-btn').classList.add('hidden');
            },
            (err) => {
                outputEl.textContent += `\n⚠️ ${err.message}`;
            }
        );
    },

    async stop() {
        try {
            await API.post(`/api/projects/${this._projectId}/terminal/kill`, { input: '' });
        } catch (e) { /* ok */ }
        this._active = false;
        document.getElementById('terminal-stop-btn').classList.add('hidden');
    }
};
