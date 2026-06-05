"""
Worker Client - Communicates with the YubiLab backend worker.
"""

import os
import json
import requests
from typing import Dict, Optional


class WorkerClient:
    """Client for communicating with the YubiLab backend worker."""

    def __init__(self):
        self.base_url = os.getenv("WORKER_URL", "http://localhost:8000")
        self.api_key = os.getenv("WORKER_API_KEY", "")

    def _headers(self, jwt_token: str = None) -> Dict:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"
        return headers

    def _request(self, method: str, path: str, data: Dict = None, token: str = None, timeout: int = 30) -> Dict:
        """Make a request to the worker."""
        url = f"{self.base_url}{path}"
        try:
            if method == "GET":
                resp = requests.get(url, headers=self._headers(token), timeout=timeout)
            elif method == "POST":
                resp = requests.post(url, headers=self._headers(token), json=data, timeout=timeout)
            elif method == "PUT":
                resp = requests.put(url, headers=self._headers(token), json=data, timeout=timeout)
            elif method == "DELETE":
                resp = requests.delete(url, headers=self._headers(token), timeout=timeout)
            else:
                return {"error": f"Unsupported method: {method}"}

            return resp.json() if resp.content else {"status": resp.status_code}
        except requests.exceptions.Timeout:
            return {"error": "Worker request timed out"}
        except requests.exceptions.ConnectionError:
            return {"error": "Cannot connect to worker"}
        except Exception as e:
            return {"error": str(e)}

    # Agent sessions
    def create_agent_session(self, task: str, token: str) -> Dict:
        return self._request("POST", "/api/agent/sessions", {"task": task}, token)

    def list_agent_sessions(self, token: str) -> Dict:
        return self._request("GET", "/api/agent/sessions", token=token)

    def get_agent_session(self, session_id: str, token: str) -> Dict:
        return self._request("GET", f"/api/agent/sessions/{session_id}", token=token)

    def agent_chat(self, session_id: str, message: str, token: str) -> Dict:
        return self._request("POST", f"/api/agent/sessions/{session_id}/chat", {"message": message}, token, timeout=120)

    def get_agent_activity(self, session_id: str, token: str) -> Dict:
        return self._request("GET", f"/api/agent/sessions/{session_id}/activity", token=token)

    def analyze_project(self, session_id: str, token: str) -> Dict:
        return self._request("POST", f"/api/agent/sessions/{session_id}/analyze", token=token)

    # Workspace
    def list_workspaces(self, token: str) -> Dict:
        return self._request("GET", "/api/workspaces", token=token)

    def list_files(self, workspace_id: str, path: str = "", token: str = None) -> Dict:
        return self._request("GET", f"/api/workspaces/{workspace_id}/files?path={path}", token=token)

    def read_file(self, workspace_id: str, file_path: str, token: str) -> Dict:
        return self._request("GET", f"/api/workspaces/{workspace_id}/files/{file_path}", token=token)

    def write_file(self, workspace_id: str, file_path: str, content: str, token: str) -> Dict:
        return self._request("PUT", f"/api/workspaces/{workspace_id}/files/{file_path}", {"content": content}, token)

    # Terminal
    def create_terminal(self, workspace_id: str, token: str) -> Dict:
        return self._request("POST", "/api/terminal/sessions", {"workspace_id": workspace_id}, token)

    def execute_command(self, session_id: str, command: str, token: str) -> Dict:
        return self._request("POST", f"/api/terminal/sessions/{session_id}/execute", {"command": command}, token, timeout=60)

    def terminal_history(self, session_id: str, token: str) -> Dict:
        return self._request("GET", f"/api/terminal/sessions/{session_id}/history", token=token)

    # Health
    def health_check(self) -> Dict:
        return self._request("GET", "/api/health")


# Singleton instance
worker_client = WorkerClient()
