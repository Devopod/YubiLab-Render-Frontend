/**
 * YubiLab AI Agent v2.1 - Devin-style agent
 * Full autonomous with real-time streaming
 */

const AgentManager = {
    sessionId: null,
    isRunning: false,
    streamBuffer: '',

    async send(message) {
        if (!message.trim() || this.isRunning) return;
        this.isRunning = true;

        // Hide welcome, show messages
        const welcome = document.getElementById('chat-welcome');
        if (welcome) welcome.style.display = 'none';

        // Add user message
        this.addChatMessage('user', message);

        // Update status
        this.updateStatus('thinking', 'Thinking...');

        try {
            // Create session if needed
            if (!this.sessionId) {
                const sessResp = await fetch('/api/agent/sessions', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({task: message}),
                });
                const sessData = await sessResp.json();
                if (sessData.session) {
                    this.sessionId = sessData.session.session_id;
                    YubiLab.sessionId = this.sessionId;
                    if (YubiLab.socket) YubiLab.socket.emit('join_session', {session_id: this.sessionId});
                    document.getElementById('session-title').textContent = message.substring(0, 50);
                }
            }

            // Send to agent
            this.addChatMessage('agent', '', true); // streaming message
            const chatResp = await fetch(`/api/agent/sessions/${this.sessionId || 'direct'}/chat`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message}),
            });

            if (!chatResp.ok) {
                // Try direct AI
                const aiResp = await fetch('/api/ai/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message}),
                });
                const aiData = await aiResp.json();
                if (aiData.response) {
                    this.updateStreamingMessage(aiData.response);
                    this.addActivity('success', 'Response received');
                } else {
                    this.updateStreamingMessage(aiData.error || 'AI unavailable. Please try again.');
                }
            } else {
                const data = await chatResp.json();
                if (data.error) {
                    this.updateStreamingMessage('Error: ' + data.error);
                    this.addActivity('error', data.error);
                } else if (data.verification) {
                    const v = data.verification;
                    const pct = v.total_steps > 0 ? Math.round((v.completed / v.total_steps) * 100) : 100;
                    YubiLab.updateProgressBar(pct);
                    this.addActivity('success', `${v.completed}/${v.total_steps} steps completed`);
                }
            }
        } catch (e) {
            // Fallback: direct Groq API via WebSocket
            if (YubiLab.socket && this.sessionId) {
                YubiLab.socket.emit('agent_chat', {session_id: this.sessionId, message});
            } else {
                this.updateStreamingMessage('Connection error. Please check the backend is running.');
                this.addActivity('error', e.message);
            }
        } finally {
            this.isRunning = false;
            this.updateStatus('idle', 'Ready');
            this.finalizeStreamingMessage();
        }
    },

    // Chat UI
    addChatMessage(role, content, isStreaming = false) {
        const container = document.getElementById('chat-messages');
        if (!container) return;

        const msg = document.createElement('div');
        msg.className = `chat-msg ${role}`;
        msg.innerHTML = `
            <div class="msg-avatar">${role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>'}</div>
            <div class="msg-body">
                <div class="msg-sender">${role === 'user' ? 'You' : 'YubiLab Agent'}</div>
                <div class="msg-text">${isStreaming ? '<span class="streaming-cursor">▌</span>' : this.formatContent(content)}</div>
                <div class="msg-meta"><span>${new Date().toLocaleTimeString()}</span></div>
            </div>
        `;
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;

        if (isStreaming) this.streamingMsgEl = msg.querySelector('.msg-text');
    },

    updateStreamingMessage(content) {
        if (this.streamingMsgEl) {
            this.streamingMsgEl.innerHTML = this.formatContent(content);
            const container = document.getElementById('chat-messages');
            if (container) container.scrollTop = container.scrollHeight;
        }
    },

    finalizeStreamingMessage() {
        if (this.streamingMsgEl) {
            const cursor = this.streamingMsgEl.querySelector('.streaming-cursor');
            if (cursor) cursor.remove();
            this.streamingMsgEl = null;
        }
    },

    handleStreamChunk(chunk) {
        this.streamBuffer += chunk;
        this.updateStreamingMessage(this.streamBuffer);
    },

    handleStreamComplete(data) {
        if (data.response) this.updateStreamingMessage(data.response);
        this.streamBuffer = '';
        this.finalizeStreamingMessage();
        this.isRunning = false;
        this.updateStatus('idle', 'Ready');
    },

    // Activity feed (right panel)
    addActivity(type, content) {
        const feed = document.getElementById('activity-feed');
        if (!feed) return;
        const placeholder = feed.querySelector('.empty-state');
        if (placeholder) placeholder.remove();

        const item = document.createElement('div');
        item.className = `activity-item ${type}`;
        const icons = {thinking: '🧠', action: '⚡', error: '❌', success: '✅', message: '💬'};
        const labels = {thinking: 'Thinking', action: 'Action', error: 'Error', success: 'Done', message: 'Info'};
        item.innerHTML = `<div class="activity-label">${icons[type] || '📝'} ${labels[type] || 'Info'}</div><div class="activity-content">${this.escapeHtml(content)}</div>`;
        feed.appendChild(item);
        feed.scrollTop = feed.scrollHeight;
    },

    // Status
    updateStatus(status, text) {
        const el = document.getElementById('agent-status');
        if (el) el.innerHTML = `<span class="status-dot ${status}"></span><span id="agent-status-text">${text}</span>`;
    },

    // Helpers
    formatContent(text) {
        if (!text) return '';
        // Basic markdown-like formatting
        let html = this.escapeHtml(text);
        // Code blocks
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Line breaks
        html = html.replace(/\n/g, '<br>');
        return html;
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

// Global functions
function sendMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    input.style.height = 'auto';
    AgentManager.send(msg);
}

function handleChatKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function quickPrompt(text) {
    document.getElementById('chat-input').value = text;
    sendMessage();
}

function askAI() {
    const input = document.getElementById('ai-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    const container = document.getElementById('ai-messages');
    // Add user msg
    const userMsg = document.createElement('div');
    userMsg.className = 'ai-msg';
    userMsg.innerHTML = `<div class="ai-msg-avatar" style="background:var(--bg-tertiary);color:var(--text-secondary)"><i class="fas fa-user"></i></div><div class="ai-msg-content">${msg}</div>`;
    container.appendChild(userMsg);

    // Call API
    fetch('/api/ai/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: msg}),
    }).then(r => r.json()).then(data => {
        const aiMsg = document.createElement('div');
        aiMsg.className = 'ai-msg';
        aiMsg.innerHTML = `<div class="ai-msg-avatar"><i class="fas fa-robot"></i></div><div class="ai-msg-content">${data.response || 'No response'}</div>`;
        container.appendChild(aiMsg);
        container.scrollTop = container.scrollHeight;
    }).catch(e => {
        const errMsg = document.createElement('div');
        errMsg.className = 'ai-msg';
        errMsg.innerHTML = `<div class="ai-msg-avatar" style="background:var(--accent-red);color:#fff"><i class="fas fa-exclamation"></i></div><div class="ai-msg-content">Error: ${e.message}</div>`;
        container.appendChild(errMsg);
    });
}
