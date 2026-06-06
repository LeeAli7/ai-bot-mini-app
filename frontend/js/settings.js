const SettingsPage = {
    render() {
        const user = Auth.getUser() || {};
        return `
        <h3 style="font-size:18px;margin-bottom:12px">Настройки</h3>

        <div class="settings-item">
            <span>👤 ${escapeHtml(user.username || 'Пользователь')}</span>
            <span style="font-size:13px;color:var(--tg-hint)">ID: ${user.telegram_id || ''}</span>
        </div>

        <div class="settings-item">
            <span class="settings-label">💭 Показывать рассуждения AI</span>
            <label class="toggle">
                <input type="checkbox" id="toggle-reasoning" onchange="SettingsPage.setReasoning(this.checked)">
                <span class="slider"></span>
            </label>
        </div>

        <div class="section-title">О приложении</div>
        <div class="settings-item">
            <span>Версия</span>
            <span style="color:var(--tg-hint)">1.0.0</span>
        </div>
        `;
    },

    async init() {
        try {
            const s = await API.get('/api/settings');
            const toggle = document.getElementById('toggle-reasoning');
            if (toggle) toggle.checked = s.show_reasoning;
        } catch (e) { /* ok */ }
    },

    async setReasoning(val) {
        try {
            await API.patch('/api/settings', { show_reasoning: val });
        } catch (e) { Toast.show('Ошибка сохранения'); }
    }
};
