# YubiLab Frontend v2.1

Devin-style AI IDE frontend for YubiLab. 3-panel layout with chat, code editor, and workspace sidebar.

## Features

- **3-Panel IDE Layout** (Chat / Code Editor / Sidebar)
- **Monaco Editor** with syntax highlighting, themes, tabs
- **xterm.js Terminal** with command history
- **AI Agent Chat** with real-time streaming via WebSocket
- **Direct AI Chat** with Groq API fallback
- **File Explorer** with drag-and-drop upload
- **User Auth** (register, login, JWT)
- **Subscription System** with bKash payment verification
- **Admin Dashboard** for user management
- **Context Window**: 4096 tokens

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your secrets and worker URL
python app.py
```

Frontend starts on `http://localhost:5000`.

## Architecture

```
yubilab-frontend/
├── app.py                    # Main Flask + SocketIO application
├── services/
│   ├── groq_service.py       # Direct Groq API (4096 token limit)
│   ├── worker_client.py      # Worker backend HTTP client
│   └── auth_service.py       # JWT auth, user management, bKash payments
├── templates/
│   ├── ide.html              # Main 3-panel IDE
│   ├── index.html            # Landing page
│   ├── login.html / register.html
│   ├── dashboard.html        # User dashboard
│   └── ...
└── static/
    ├── js/
    │   ├── app.js            # Main app logic, panel resizing
    │   ├── agent.js          # AI agent chat manager
    │   ├── editor.js         # Monaco editor manager
    │   ├── terminal.js       # xterm.js terminal manager
    │   └── workspace.js      # File tree manager
    └── css/
        ├── main.css / ide.css / agent.css
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | Flask secret key |
| `JWT_SECRET` | (required) | JWT signing secret (must match worker) |
| `WORKER_URL` | `http://localhost:8000` | Worker backend URL |
| `WORKER_API_KEY` | (required) | Worker API key |
| `GROQ_API_KEY` | (required) | Groq API key (for direct AI chat) |
| `PORT` | `5000` | Server port |

## License

MIT
