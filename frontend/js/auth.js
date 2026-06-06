const Auth = {
    _token: null,
    _user: null,

    async init() {
        const saved = localStorage.getItem('jwt_token');
        if (saved) {
            this._token = saved;
            API.setToken(saved);
            try {
                const user = await API.get('/api/settings');
                this._user = user;
                return true;
            } catch (e) {
                this._token = null;
                localStorage.removeItem('jwt_token');
            }
        }
        return false;
    },

    async loginViaTelegram() {
        const tg = window.Telegram?.WebApp;
        if (!tg || !tg.initData) {
            Toast.show('Откройте приложение через Telegram');
            return false;
        }

        try {
            const res = await API.post('/api/auth/telegram', {
                initData: tg.initData,
            }, { headers: {} });

            this._token = res.token;
            this._user = res.user;
            API.setToken(res.token);
            localStorage.setItem('jwt_token', res.token);
            return true;
        } catch (e) {
            Toast.show('Ошибка авторизации: ' + e.message);
            return false;
        }
    },

    logout() {
        this._token = null;
        this._user = null;
        localStorage.removeItem('jwt_token');
    },

    isLoggedIn() {
        return !!this._token;
    },

    getUser() {
        return this._user;
    }
};
