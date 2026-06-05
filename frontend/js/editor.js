/**
 * YubiLab Editor Manager v2.1 - Monaco Editor integration
 */

const EditorManager = {
    editor: null,
    models: {},
    currentFile: null,

    init() {
        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' } });
        require(['vs/editor/editor.main'], () => {
            monaco.editor.defineTheme('yubilab-dark', {
                base: 'vs-dark', inherit: true,
                rules: [
                    { token: 'comment', foreground: '6A9955', fontStyle: 'italic' },
                    { token: 'keyword', foreground: '569CD6' },
                    { token: 'string', foreground: 'CE9178' },
                    { token: 'number', foreground: 'B5CEA8' },
                    { token: 'type', foreground: '4EC9B0' },
                    { token: 'function', foreground: 'DCDCAA' },
                ],
                colors: {
                    'editor.background': '#0d1117',
                    'editor.foreground': '#e6edf3',
                    'editor.lineHighlightBackground': '#161b2244',
                    'editor.selectionBackground': '#264f78',
                    'editorCursor.foreground': '#58a6ff',
                }
            });

            this.editor = monaco.editor.create(document.getElementById('monaco-editor'), {
                value: '', language: 'markdown', theme: 'yubilab-dark',
                fontSize: 13, fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
                fontLigatures: true, minimap: { enabled: true }, scrollBeyondLastLine: false,
                wordWrap: 'on', automaticLayout: true, tabSize: 4, insertSpaces: true,
                renderWhitespace: 'selection', bracketPairColorization: { enabled: true },
                padding: { top: 8 }, smoothScrolling: true, cursorBlinking: 'smooth',
            });

            YubiLab.editor = this.editor;

            this.editor.onDidChangeCursorPosition((e) => {
                const el = document.getElementById('status-cursor');
                if (el) el.textContent = `Ln ${e.position.lineNumber}, Col ${e.position.column}`;
            });

            this.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => this.saveCurrentFile());
        });
    },

    openFile(filePath, content, language) {
        if (!this.editor) return;
        document.getElementById('welcome-content').style.display = 'none';
        if (!this.models[filePath]) {
            this.models[filePath] = monaco.editor.createModel(content, language || this.detectLanguage(filePath));
        }
        this.editor.setModel(this.models[filePath]);
        this.currentFile = filePath;
        this.addTab(filePath);
        const el = document.getElementById('status-language');
        if (el) el.textContent = (language || this.detectLanguage(filePath)).toUpperCase();
        YubiLab.updateContextTokens(Math.floor(content.length / 4));
    },

    addTab(filePath) {
        const tabs = document.getElementById('editor-tabs');
        if (tabs.querySelector(`.editor-tab[data-file="${filePath}"]`)) {
            tabs.querySelectorAll('.editor-tab').forEach(t => t.classList.remove('active'));
            tabs.querySelector(`.editor-tab[data-file="${filePath}"]`).classList.add('active');
            return;
        }
        tabs.querySelectorAll('.editor-tab').forEach(t => t.classList.remove('active'));
        const tab = document.createElement('div');
        tab.className = 'editor-tab active';
        tab.dataset.file = filePath;
        tab.innerHTML = `<span>${filePath.split('/').pop()}</span><button class="tab-close" onclick="closeTab('${filePath}'); event.stopPropagation();">&times;</button>`;
        tab.addEventListener('click', () => this.openFile(filePath));
        tabs.appendChild(tab);
    },

    saveCurrentFile() { /* Future: save to workspace */ },

    setContent(content, language) {
        if (this.editor) {
            const model = this.editor.getModel();
            if (model) { monaco.editor.setModelLanguage(model, language || 'plaintext'); model.setValue(content); }
        }
    },

    detectLanguage(filePath) {
        const ext = filePath.split('.').pop().toLowerCase();
        const map = {
            'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'jsx': 'javascript', 'tsx': 'typescript',
            'html': 'html', 'css': 'css', 'scss': 'scss', 'json': 'json', 'yaml': 'yaml', 'yml': 'yaml',
            'md': 'markdown', 'sql': 'sql', 'sh': 'shell', 'java': 'java', 'c': 'c', 'cpp': 'cpp',
            'go': 'go', 'rs': 'rust', 'rb': 'ruby', 'php': 'php', 'swift': 'swift', 'xml': 'xml',
            'toml': 'ini', 'env': 'plaintext', 'txt': 'plaintext', 'dockerfile': 'dockerfile',
        };
        return map[ext] || 'plaintext';
    }
};

function closeTab(filePath) {
    if (EditorManager.models[filePath]) { EditorManager.models[filePath].dispose(); delete EditorManager.models[filePath]; }
    const tab = document.querySelector(`.editor-tab[data-file="${filePath}"]`);
    if (tab) tab.remove();
    const remaining = Object.keys(EditorManager.models);
    if (remaining.length > 0) EditorManager.openFile(remaining[0]);
    else { EditorManager.currentFile = null; document.getElementById('welcome-content').style.display = 'flex'; }
}

document.addEventListener('DOMContentLoaded', () => EditorManager.init());
