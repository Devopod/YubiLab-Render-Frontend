/**
 * YubiLab App v2.1 - Devin-inspired 3-panel layout
 * With resizable panels (left chat, center code, right sidebar)
 */

const YubiLab = {
    user: null,
    sessionId: null,
    terminalSessionId: null,
    socket: null,
    agentRunning: false,
    editor: null,
    xterm: null,
    openFiles: {},
    activeFile: null,
    uploadedFiles: [],
    contextTokens: 0,
    maxContextTokens: 4096,

    async init() {
        this.user = await this.fetchUser();
        this.initSocket();
        this.initFileUpload();
        this.initResizeHandles();
        this.initAutoResize();
        this.updatePlanBadge();
        EditorManager.init();
        TerminalManager.init();
        WorkspaceManager.refresh();
    },

    async fetchUser() {
        try {
            const resp = await fetch('/api/auth/me');
            if (resp.ok) return await resp.json();
        } catch (e) {}
        return null;
    },

    initSocket() {
        this.socket = io({ transports: ['websocket', 'polling'], reconnection: true, reconnectionAttempts: 10 });

        this.socket.on('agent_stream', (data) => {
            if (data.chunk) AgentManager.handleStreamChunk(data.chunk);
        });
        this.socket.on('agent_complete', (data) => {
            AgentManager.handleStreamComplete(data);
        });
        this.socket.on('terminal_output', (data) => {
            TerminalManager.handleWebSocketOutput(data);
        });
    },

    initFileUpload() {
        const input = document.getElementById('file-upload');
        if (!input) return;

        input.addEventListener('change', (e) => {
            for (const file of e.target.files) {
                this.uploadedFiles.push(file);
                this.addUploadedItemUI(file.name);
                this.uploadFile(file);
            }
            input.value = '';
        });

        // Drag & drop on chat input
        const chatArea = document.querySelector('.chat-input-area');
        if (chatArea) {
            chatArea.addEventListener('dragover', (e) => { e.preventDefault(); chatArea.style.borderColor = 'var(--accent-blue)'; });
            chatArea.addEventListener('dragleave', () => { chatArea.style.borderColor = ''; });
            chatArea.addEventListener('drop', (e) => {
                e.preventDefault();
                chatArea.style.borderColor = '';
                for (const file of e.dataTransfer.files) {
                    this.uploadedFiles.push(file);
                    this.addUploadedItemUI(file.name);
                    this.uploadFile(file);
                }
            });
        }
    },

    initResizeHandles() {
        // Left panel resize (vertical - adjust width)
        this.setupVerticalResize('resize-left', 'left-panel');
        // Right panel resize (vertical - adjust width)
        this.setupVerticalResizeRight('resize-right', 'right-panel');
        // Terminal resize (horizontal - adjust height)
        this.setupHorizontalResize('resize-terminal', 'terminal-section');
    },

    setupVerticalResize(handleId, panelId) {
        const handle = document.getElementById(handleId);
        const panel = document.getElementById(panelId);
        if (!handle || !panel) return;

        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            handle.classList.add('active');
            const startX = e.clientX;
            const startWidth = panel.offsetWidth;

            const onMove = (e) => {
                const delta = e.clientX - startX;
                const newWidth = Math.max(280, Math.min(600, startWidth + delta));
                panel.style.width = newWidth + 'px';
            };
            const onUp = () => {
                handle.classList.remove('active');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                if (this.editor) this.editor.layout();
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    },

    setupVerticalResizeRight(handleId, panelId) {
        const handle = document.getElementById(handleId);
        const panel = document.getElementById(panelId);
        if (!handle || !panel) return;

        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            handle.classList.add('active');
            const startX = e.clientX;
            const startWidth = panel.offsetWidth;

            const onMove = (e) => {
                const delta = startX - e.clientX;
                const newWidth = Math.max(200, Math.min(500, startWidth + delta));
                panel.style.width = newWidth + 'px';
            };
            const onUp = () => {
                handle.classList.remove('active');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                if (this.editor) this.editor.layout();
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    },

    setupHorizontalResize(handleId, panelId) {
        const handle = document.getElementById(handleId);
        const panel = document.getElementById(panelId);
        if (!handle || !panel) return;

        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            handle.classList.add('active');
            const startY = e.clientY;
            const startHeight = panel.offsetHeight;

            const onMove = (e) => {
                const delta = startY - e.clientY;
                const newHeight = Math.max(40, Math.min(window.innerHeight * 0.6, startHeight + delta));
                panel.style.height = newHeight + 'px';
            };
            const onUp = () => {
                handle.classList.remove('active');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                if (this.editor) this.editor.layout();
                if (TerminalManager.xterm) { try { TerminalManager.fitAddon.fit(); } catch(e) {} }
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    },

    initAutoResize() {
        // Auto-resize chat textarea
        const textarea = document.getElementById('chat-input');
        if (textarea) {
            textarea.addEventListener('input', () => {
                textarea.style.height = 'auto';
                textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
            });
        }
    },

    addUploadedItemUI(name) {
        const row = document.getElementById('upload-row');
        const items = document.getElementById('uploaded-items');
        if (!row || !items) return;
        row.style.display = 'block';
        const div = document.createElement('div');
        div.className = 'uploaded-item';
        div.innerHTML = `<i class="fas fa-file"></i> <span>${name}</span> <span class="remove" onclick="this.parentElement.remove(); YubiLab.removeUpload('${name}')">&times;</span>`;
        items.appendChild(div);
    },

    removeUpload(name) {
        this.uploadedFiles = this.uploadedFiles.filter(f => f.name !== name);
        if (this.uploadedFiles.length === 0) {
            const row = document.getElementById('upload-row');
            if (row) row.style.display = 'none';
        }
    },

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        if (this.sessionId) formData.append('session_id', this.sessionId);
        try {
            await fetch('/api/upload', { method: 'POST', body: formData });
        } catch (e) {
            console.error('Upload failed:', e);
        }
    },

    updatePlanBadge() {
        const badge = document.getElementById('plan-badge');
        if (badge && this.user) {
            badge.textContent = (this.user.plan || 'FREE').toUpperCase();
            if (this.user.plan === 'pro') badge.style.background = 'rgba(63,185,80,0.2)';
            if (this.user.plan === 'admin') badge.style.background = 'rgba(188,140,255,0.2)';
        }
    },

    updateContextTokens(tokens) {
        this.contextTokens = tokens;
        const el = document.getElementById('context-label');
        if (el) el.textContent = `Context: ${tokens}/${this.maxContextTokens}`;
    },

    showLoading(msg) {
        document.getElementById('loading-overlay').style.display = 'flex';
        document.getElementById('loading-message').textContent = msg || 'Agent is working...';
    },
    hideLoading() { document.getElementById('loading-overlay').style.display = 'none'; },
    updateProgressBar(pct) {
        document.getElementById('agent-progress-bar').style.width = pct + '%';
        const s = document.getElementById('agent-progress');
        if (s) s.textContent = pct > 0 ? `${pct}%` : '';
    }
};

// Global helpers
function switchTopTab(tab) {
    document.querySelectorAll('.topbar-tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
}
function switchRightTab(tab) {
    document.querySelectorAll('.right-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.right-content').forEach(c => c.style.display = 'none');
    event.currentTarget.classList.add('active');
    document.getElementById(`right-${tab}`).style.display = 'flex';
}
function switchTermTab(tab) {
    document.querySelectorAll('.term-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.term-pane').forEach(p => p.classList.remove('active'));
    if (tab === 'agent') {
        document.querySelector('.term-tab:nth-child(1)').classList.add('active');
        document.getElementById('agent-terminal').classList.add('active');
    } else {
        document.querySelector('.term-tab:nth-child(2)').classList.add('active');
        document.getElementById('user-terminal').classList.add('active');
        setTimeout(() => { try { TerminalManager.fitAddon?.fit(); } catch(e) {} }, 50);
    }
}
function newSession() {
    document.getElementById('chat-messages').innerHTML = '';
    document.getElementById('chat-welcome').style.display = 'block';
    document.getElementById('agent-term-output').innerHTML = '';
    AgentManager.sessionId = null;
    YubiLab.sessionId = null;
}

function toggleTerminal() {
    const section = document.getElementById('terminal-section');
    if (!section) return;
    if (section.style.display === 'none') {
        section.style.display = '';
        if (TerminalManager.fitAddon) { try { TerminalManager.fitAddon.fit(); } catch(e) {} }
    } else {
        section.style.display = 'none';
    }
    if (YubiLab.editor) YubiLab.editor.layout();
}

function clearTerminal() {
    TerminalManager.clear();
}

function runTerminalCmd() {
    const input = document.getElementById('terminal-input');
    if (!input) return;
    const cmd = input.value.trim();
    if (!cmd) return;
    input.value = '';
    TerminalManager.executeCommand(cmd);
}

document.addEventListener('DOMContentLoaded', () => YubiLab.init());
