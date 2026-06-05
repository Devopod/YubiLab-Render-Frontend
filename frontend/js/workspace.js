/**
 * YubiLab Workspace Manager v2.1 - Integrated into right panel
 */

const WorkspaceManager = {
    currentPath: '',

    async refresh() {
        const tree = document.getElementById('file-tree');
        if (!tree) return;
        tree.innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-spin"></i><p>Loading...</p></div>';
        try {
            const resp = await fetch(`/api/workspace/files?workspace_id=default&path=${this.currentPath}`);
            const data = await resp.json();
            if (data.entries) this.renderTree(data.entries);
            else tree.innerHTML = '<div class="empty-state"><i class="fas fa-folder-open"></i><p>No project loaded</p></div>';
        } catch (e) {
            tree.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-circle"></i><p>Error loading files</p></div>';
        }
    },

    renderTree(entries) {
        const tree = document.getElementById('file-tree');
        tree.innerHTML = '';
        const sorted = [...entries].sort((a, b) => {
            if (a.is_directory && !b.is_directory) return -1;
            if (!a.is_directory && b.is_directory) return 1;
            return a.name.localeCompare(b.name);
        });
        if (this.currentPath) {
            const back = document.createElement('div');
            back.className = 'tree-item';
            back.innerHTML = '<span class="tree-icon">📁</span><span>..</span>';
            back.onclick = () => { this.currentPath = this.currentPath.split('/').slice(0, -1).join('/'); this.refresh(); };
            tree.appendChild(back);
        }
        for (const entry of sorted) {
            const item = document.createElement('div');
            item.className = 'tree-item';
            const icon = entry.is_directory ? '📁' : this.getIcon(entry.name);
            item.innerHTML = `<span class="tree-icon">${icon}</span><span>${entry.name}</span>`;
            item.onclick = () => { if (entry.is_directory) { this.currentPath = entry.path; this.refresh(); } else this.openFile(entry.path); };
            tree.appendChild(item);
        }
    },

    async openFile(path) {
        try {
            const resp = await fetch(`/api/workspace/files/${path}?workspace_id=default`);
            const data = await resp.json();
            if (data.success) EditorManager.openFile(path, data.content, EditorManager.detectLanguage(path));
        } catch (e) { console.error('Open file error:', e); }
    },

    getIcon(name) {
        const ext = name.split('.').pop().toLowerCase();
        const map = {py:'🐍',js:'📜',ts:'📘',html:'🌐',css:'🎨',json:'📋',md:'📝',sh:'🖥️',sql:'🗃️',env:'🔐'};
        return map[ext] || '📄';
    }
};
