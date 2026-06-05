/**
 * YubiLab Terminal Manager v2.1
 */

const TerminalManager = {
    xterm: null,
    fitAddon: null,
    sessionId: null,
    history: [],
    historyIndex: -1,
    currentLine: '',

    init() {
        this.initXterm();
        this.createSession();
    },

    initXterm() {
        const container = document.getElementById('xterm-container');
        if (!container) return;

        this.xterm = new Terminal({
            theme: {
                background: '#0d1117', foreground: '#e6edf3', cursor: '#58a6ff',
                selectionBackground: '#264f78', black: '#000', red: '#f85149',
                green: '#3fb950', yellow: '#d29922', blue: '#58a6ff',
                magenta: '#bc8cff', cyan: '#39d353', white: '#e6edf3',
            },
            fontFamily: "'JetBrains Mono', Consolas, monospace",
            fontSize: 12, lineHeight: 1.4, cursorBlink: true, scrollback: 5000,
        });

        this.fitAddon = new FitAddon.FitAddon();
        this.xterm.loadAddon(this.fitAddon);
        this.xterm.open(container);
        try { this.fitAddon.fit(); } catch(e) {}

        this.xterm.writeln('\x1b[36m  YubiLab Terminal v2.1\x1b[0m\r\n');

        this.xterm.onData((data) => {
            if (data === '\r') {
                this.xterm.write('\r\n');
                if (this.currentLine) { this.executeInXterm(this.currentLine); this.history.push(this.currentLine); this.historyIndex = this.history.length; this.currentLine = ''; }
            } else if (data === '\x7f') {
                if (this.currentLine.length > 0) { this.currentLine = this.currentLine.slice(0, -1); this.xterm.write('\b \b'); }
            } else if (data === '\x1b[A') {
                if (this.historyIndex > 0) { this.historyIndex--; this.clearLine(); this.currentLine = this.history[this.historyIndex] || ''; this.xterm.write(this.currentLine); }
            } else if (data === '\x1b[B') {
                if (this.historyIndex < this.history.length - 1) { this.historyIndex++; this.clearLine(); this.currentLine = this.history[this.historyIndex] || ''; this.xterm.write(this.currentLine); }
            } else if (data >= ' ') { this.currentLine += data; this.xterm.write(data); }
        });

        YubiLab.xterm = this.xterm;
    },

    clearLine() {
        for (let i = 0; i < this.currentLine.length; i++) this.xterm.write('\b \b');
    },

    async createSession() {
        try {
            const resp = await fetch('/api/terminal/sessions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({workspace_id: 'default'}) });
            const data = await resp.json();
            if (data.success) { this.sessionId = data.session_id; YubiLab.terminalSessionId = data.session_id; }
        } catch (e) { console.error('Terminal session error:', e); }
    },

    async executeInXterm(command) {
        if (!command.trim()) return;
        if (!this.sessionId) { this.xterm.writeln('\x1b[31mNo terminal session.\x1b[0m'); return; }
        try {
            const resp = await fetch(`/api/terminal/sessions/${this.sessionId}/execute`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command}) });
            const data = await resp.json();
            if (data.success && data.output) this.xterm.writeln(data.output);
            else if (data.error) this.xterm.writeln(`\x1b[31m${data.error}\x1b[0m`);
        } catch (e) { this.xterm.writeln(`\x1b[31mError: ${e.message}\x1b[0m`); }
        this.xterm.write('\x1b[32m$\x1b[0m ');
    },

    async executeCommand(command) {
        if (!command.trim()) return {success: false, error: 'Empty'};
        this.writeAgentTerminal(`$ ${command}`, 'cmd');
        try {
            const sid = this.sessionId || 'default';
            const resp = await fetch(`/api/terminal/sessions/${sid}/execute`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command}) });
            const data = await resp.json();
            if (data.success && data.output) this.writeAgentTerminal(data.output, 'info');
            else if (data.error) this.writeAgentTerminal(data.error, 'err');
            return data;
        } catch (e) { this.writeAgentTerminal(`Error: ${e.message}`, 'err'); return {success: false, error: e.message}; }
    },

    writeAgentTerminal(text, type) {
        const out = document.getElementById('agent-term-output');
        if (!out) return;
        const span = document.createElement('span');
        span.className = type || '';
        span.textContent = text + '\n';
        out.appendChild(span);
        out.scrollTop = out.scrollHeight;
    },

    handleWebSocketOutput(data) {
        if (data.output) this.writeAgentTerminal(data.output, 'info');
        if (data.error) this.writeAgentTerminal(data.error, 'err');
    },

    clear() { const out = document.getElementById('agent-term-output'); if (out) out.innerHTML = ''; if (this.xterm) this.xterm.clear(); },
};

function runTerminalCmd() {
    const input = document.getElementById('terminal-input');
    const cmd = input.value.trim(); if (!cmd) return;
    input.value = '';
    TerminalManager.executeCommand(cmd);
}
function clearTerminal() { TerminalManager.clear(); }
function toggleTerminal() {
    const panel = document.getElementById('terminal-section');
    if (panel) panel.classList.toggle('collapsed');
    if (YubiLab.editor) setTimeout(() => YubiLab.editor.layout(), 100);
}

document.addEventListener('DOMContentLoaded', () => TerminalManager.init());
