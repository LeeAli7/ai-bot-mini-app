const API = {
    _base: '',
    _token: null,

    init(baseUrl, token) {
        this._base = baseUrl || '';
        this._token = token;
    },

    setToken(token) {
        this._token = token;
    },

    headers(extra) {
        const h = { 'Content-Type': 'application/json' };
        if (this._token) h['Authorization'] = `Bearer ${this._token}`;
        return { ...h, ...extra };
    },

    async request(method, path, body, opts = {}) {
        const url = this._base + path;
        const fetchOpts = { method, headers: this.headers(opts.headers) };
        if (body && !opts.noJson) fetchOpts.body = JSON.stringify(body);
        else if (body && opts.noJson) fetchOpts.body = body;

        const res = await fetch(url, fetchOpts);
        if (res.status === 401) {
            Auth.logout();
            throw new Error('Unauthorized');
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        if (opts.raw) return res;
        return res.json();
    },

    get(path, params = {}) {
        const qs = new URLSearchParams(params).toString();
        return this.request('GET', path + (qs ? '?' + qs : ''));
    },

    post(path, body, opts) {
        return this.request('POST', path, body, opts);
    },

    patch(path, body) {
        return this.request('PATCH', path, body);
    },

    delete(path) {
        return this.request('DELETE', path);
    },

    upload(path, formData) {
        return this.request('POST', path, formData, { noJson: true,
            headers: { 'Authorization': `Bearer ${this._token}` } });
    },

    // SSE streaming
    stream(path, params, onChunk, onDone, onError) {
        const qs = new URLSearchParams(params).toString();
        const url = this._base + path + (qs ? '?' + qs : '');

        fetch(url, { headers: { 'Authorization': `Bearer ${this._token}` } })
            .then(async response => {
                if (!response.ok) throw new Error('Stream failed');
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'done') onDone && onDone(data);
                                else if (data.type === 'cancelled') onDone && onDone(data);
                                else if (data.type === 'files') onChunk && onChunk(data);
                                else if (data.type === 'error') onError && onError(data);
                                else onChunk && onChunk(data);
                            } catch (e) { /* skip malformed */ }
                        }
                    }
                }
            })
            .catch(e => onError && onError({ message: e.message }));
    }
};
