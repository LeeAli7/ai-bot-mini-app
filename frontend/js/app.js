const App = {
    _pages: {
        chat: ChatPage,
        providers: ProvidersPage,
        projects: ProjectsPage,
        settings: SettingsPage,
    },
    _currentPage: 'chat',
    _history: [],
    _initialized: false,

    async boot() {
        // Init Telegram WebApp
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
            // Apply theme
            document.documentElement.style.setProperty('--tg-theme-bg-color', tg.backgroundColor || '#ffffff');
            document.documentElement.style.setProperty('--tg-theme-text-color', tg.textColor || '#000000');
            document.documentElement.style.setProperty('--tg-theme-hint-color', tg.hintColor || '#999999');
            document.documentElement.style.setProperty('--tg-theme-link-color', tg.linkColor || '#2481cc');
            document.documentElement.style.setProperty('--tg-theme-button-color', tg.buttonColor || '#2481cc');
            document.documentElement.style.setProperty('--tg-theme-button-text-color', tg.buttonTextColor || '#ffffff');
            document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', tg.secondaryBackgroundColor || '#f0f0f0');
            document.documentElement.style.setProperty('--tg-theme-section-bg-color', tg.sectionBackgroundColor || '#ffffff');
            document.documentElement.style.setProperty('--tg-theme-section-header-text-color', tg.sectionHeaderTextColor || '#6d6d71');

            tg.MainButton?.hide();
            tg.BackButton?.hide();
            tg.BackButton?.onClick(() => this.goBack());
        }

        // Init API with current origin
        API.init('', null);

        // Auth
        const loggedIn = await Auth.init();
        if (!loggedIn) {
            const ok = await Auth.loginViaTelegram();
            if (!ok) {
                document.getElementById('app-content').innerHTML =
                    '<div class="empty-state" style="padding-top:60px"><div class="empty-icon">🔒</div><p>Откройте Mini App через Telegram</p><button class="btn btn-primary" style="margin-top:16px" onclick="App.boot()">🔄 Попробовать снова</button></div>';
                return;
            }
        }

        this._initialized = true;
        this.navigate('chat');
    },

    navigate(page) {
        if (!this._initialized) return;
        if (page === this._currentPage) return;

        const tg = window.Telegram?.WebApp;

        // Hide current page
        const oldPage = this._pages[this._currentPage];
        if (oldPage && oldPage.hide) oldPage.hide();

        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        const navBtn = document.querySelector(`.nav-btn[data-page="${page}"]`);
        if (navBtn) navBtn.classList.add('active');

        // Push history
        if (this._currentPage && page !== this._currentPage) {
            this._history.push(this._currentPage);
        }

        this._currentPage = page;

        const content = document.getElementById('app-content');
        content.innerHTML = '';

        // Render page
        const pageObj = this._pages[page];
        let html = '';
        if (pageObj && pageObj.render) {
            html = pageObj.render();
        }
        content.innerHTML = `<div class="page active" id="page-${page}">${html}</div>`;

        document.getElementById('header-title').textContent =
            { chat: 'AI Чат', providers: 'Провайдеры', projects: 'Вайб-кодинг', settings: 'Настройки' }[page] || 'AI Bot';

        // Show/hide back button
        const backBtn = document.getElementById('btn-back');
        if (this._history.length > 0) {
            backBtn.classList.remove('hidden');
        } else {
            backBtn.classList.add('hidden');
        }

        // Init page
        if (pageObj && pageObj.init) {
            setTimeout(() => pageObj.init(), 50);
        }

        // Update back button
        if (tg && tg.BackButton) {
            if (this._history.length > 0) {
                tg.BackButton.show();
            } else {
                tg.BackButton.hide();
            }
        }
    },

    goBack() {
        if (this._history.length === 0) return;
        const prev = this._history.pop();
        this._currentPage = prev; // Prevent history push

        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        const navBtn = document.querySelector(`.nav-btn[data-page="${prev}"]`);
        if (navBtn) navBtn.classList.add('active');

        const content = document.getElementById('app-content');
        content.innerHTML = '';
        const pageObj = this._pages[prev];
        let html = '';
        if (pageObj && pageObj.render) {
            html = pageObj.render();
        }
        content.innerHTML = `<div class="page active" id="page-${prev}">${html}</div>`;

        document.getElementById('header-title').textContent =
            { chat: 'AI Чат', providers: 'Провайдеры', projects: 'Вайб-кодинг', settings: 'Настройки' }[prev] || 'AI Bot';

        if (this._history.length === 0) {
            document.getElementById('btn-back').classList.add('hidden');
            const tg = window.Telegram?.WebApp;
            if (tg?.BackButton) tg.BackButton.hide();
        }

        if (pageObj && pageObj.init) {
            setTimeout(() => pageObj.init(), 50);
        }
    }
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.boot());
