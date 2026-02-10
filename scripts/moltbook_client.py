"""Moltbook API client library.

Wraps the Moltbook REST API (https://www.moltbook.com/api/v1) in a
Python class.  The client is intentionally decoupled from any UI layer
so it can be used by a CLI, a TUI (e.g. textual), or as a library.
"""

import json
import os
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://www.moltbook.com/api/v1"
CONFIG_PATH = Path(os.environ.get("MOLTBOOK_CONFIG", Path.home() / ".moltbook" / "config.json"))


class MoltbookError(Exception):
    """Raised when an API call returns a non-2xx status."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class MoltbookClient:
    """Thin wrapper around every Moltbook API endpoint."""

    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or self._load_api_key()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    # ── config persistence ──────────────────────────────────────────

    @staticmethod
    def _load_api_key() -> Optional[str]:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            return data.get("api_key")
        return None

    @staticmethod
    def save_api_key(api_key: str) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
        data["api_key"] = api_key
        CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n")

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    # ── HTTP helpers ────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, **kwargs)
        if not resp.ok:
            try:
                detail = resp.json()
            except (ValueError, requests.JSONDecodeError):
                detail = resp.text
            raise MoltbookError(resp.status_code, str(detail))
        if resp.status_code == 204 or not resp.text:
            return {}
        return resp.json()

    def _get(self, path: str, **params) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: Optional[dict] = None) -> dict:
        return self._request("POST", path, json=body)

    def _patch(self, path: str, body: dict) -> dict:
        return self._request("PATCH", path, json=body)

    def _delete(self, path: str, body: Optional[dict] = None) -> dict:
        if body is not None:
            return self._request("DELETE", path, json=body)
        return self._request("DELETE", path)

    def _upload(self, path: str, file_path: str, data: Optional[dict] = None) -> dict:
        with open(file_path, "rb") as f:
            return self._request("POST", path, files={"file": f}, data=data)

    # ── Agents ──────────────────────────────────────────────────────

    def register(self, name: str, description: str) -> dict:
        """Register a new agent. Returns agent info including api_key."""
        return self._post("/agents/register", {"name": name, "description": description})

    def me(self) -> dict:
        """Get the current agent's profile."""
        return self._get("/agents/me")

    def update_profile(self, description: str) -> dict:
        """Update the current agent's description."""
        return self._patch("/agents/me", {"description": description})

    def claim_status(self) -> dict:
        """Check the claim / verification status of the current agent."""
        return self._get("/agents/status")

    def view_agent(self, name: str) -> dict:
        """View another agent's public profile."""
        return self._get("/agents/profile", name=name)

    def follow(self, name: str) -> dict:
        """Follow an agent."""
        return self._post(f"/agents/{name}/follow")

    def unfollow(self, name: str) -> dict:
        """Unfollow an agent."""
        return self._delete(f"/agents/{name}/follow")

    def upload_avatar(self, file_path: str) -> dict:
        """Upload an avatar image (max 1 MB; JPEG, PNG, GIF, WebP)."""
        return self._upload("/agents/me/avatar", file_path)

    def remove_avatar(self) -> dict:
        """Remove the current agent's avatar."""
        return self._delete("/agents/me/avatar")

    def setup_owner_email(self, email: str) -> dict:
        """Send a setup link so the agent's human can access the owner dashboard."""
        return self._post("/agents/me/setup-owner-email", {"email": email})

    # ── Posts ───────────────────────────────────────────────────────

    def create_text_post(self, submolt: str, title: str, content: str) -> dict:
        return self._post("/posts", {"submolt": submolt, "title": title, "content": content})

    def create_link_post(self, submolt: str, title: str, url: str) -> dict:
        return self._post("/posts", {"submolt": submolt, "title": title, "url": url})

    def get_posts(self, sort: str = "hot", limit: int = 25,
                  submolt: Optional[str] = None) -> dict:
        params = {"sort": sort, "limit": limit}
        if submolt:
            params["submolt"] = submolt
        return self._get("/posts", **params)

    def get_post(self, post_id: str) -> dict:
        return self._get(f"/posts/{post_id}")

    def delete_post(self, post_id: str) -> dict:
        return self._delete(f"/posts/{post_id}")

    def pin_post(self, post_id: str) -> dict:
        """Pin a post in its submolt (mod/owner only, max 3)."""
        return self._post(f"/posts/{post_id}/pin")

    def unpin_post(self, post_id: str) -> dict:
        """Unpin a post (mod/owner only)."""
        return self._delete(f"/posts/{post_id}/pin")

    # ── Comments ────────────────────────────────────────────────────

    def add_comment(self, post_id: str, content: str, parent_id: Optional[str] = None) -> dict:
        body: dict = {"content": content}
        if parent_id:
            body["parent_id"] = parent_id
        return self._post(f"/posts/{post_id}/comments", body)

    def get_comments(self, post_id: str, sort: str = "top") -> dict:
        return self._get(f"/posts/{post_id}/comments", sort=sort)

    # ── Voting ──────────────────────────────────────────────────────

    def upvote_post(self, post_id: str) -> dict:
        return self._post(f"/posts/{post_id}/upvote")

    def downvote_post(self, post_id: str) -> dict:
        return self._post(f"/posts/{post_id}/downvote")

    def upvote_comment(self, comment_id: str) -> dict:
        return self._post(f"/comments/{comment_id}/upvote")

    # ── Submolts ────────────────────────────────────────────────────

    def create_submolt(self, name: str, display_name: str, description: str) -> dict:
        return self._post("/submolts", {
            "name": name,
            "display_name": display_name,
            "description": description,
        })

    def list_submolts(self) -> dict:
        return self._get("/submolts")

    def get_submolt(self, name: str) -> dict:
        return self._get(f"/submolts/{name}")

    def subscribe(self, name: str) -> dict:
        return self._post(f"/submolts/{name}/subscribe")

    def unsubscribe(self, name: str) -> dict:
        return self._delete(f"/submolts/{name}/subscribe")

    def get_submolt_feed(self, name: str, sort: str = "hot", limit: int = 25) -> dict:
        """Get posts from a specific submolt."""
        return self._get(f"/submolts/{name}/feed", sort=sort, limit=limit)

    def update_submolt_settings(self, name: str, **settings) -> dict:
        """Update submolt settings (description, banner_color, theme_color)."""
        return self._patch(f"/submolts/{name}/settings", settings)

    def upload_submolt_avatar(self, name: str, file_path: str) -> dict:
        """Upload a submolt avatar (max 500 KB)."""
        return self._upload(f"/submolts/{name}/settings", file_path, data={"type": "avatar"})

    def upload_submolt_banner(self, name: str, file_path: str) -> dict:
        """Upload a submolt banner (max 2 MB)."""
        return self._upload(f"/submolts/{name}/settings", file_path, data={"type": "banner"})

    def list_moderators(self, name: str) -> dict:
        """List moderators of a submolt."""
        return self._get(f"/submolts/{name}/moderators")

    def add_moderator(self, name: str, agent_name: str) -> dict:
        """Add a moderator to a submolt (owner only)."""
        return self._post(f"/submolts/{name}/moderators",
                          {"agent_name": agent_name, "role": "moderator"})

    def remove_moderator(self, name: str, agent_name: str) -> dict:
        """Remove a moderator from a submolt (owner only)."""
        return self._delete(f"/submolts/{name}/moderators",
                            body={"agent_name": agent_name})

    # ── Feed & Discovery ────────────────────────────────────────────

    def feed(self, sort: str = "hot", limit: int = 25) -> dict:
        return self._get("/feed", sort=sort, limit=limit)

    def search(self, query: str, limit: int = 25,
               type: Optional[str] = None) -> dict:
        params = {"q": query, "limit": limit}
        if type:
            params["type"] = type
        return self._get("/search", **params)

    # ── Direct Messages ────────────────────────────────────────────

    def dm_check(self) -> dict:
        """Quick poll for DM activity (pending requests, unread messages)."""
        return self._get("/agents/dm/check")

    def dm_request(self, message: str, to: Optional[str] = None,
                   to_owner: Optional[str] = None) -> dict:
        """Send a chat request to another agent by name or owner handle."""
        body: dict = {"message": message}
        if to:
            body["to"] = to
        if to_owner:
            body["to_owner"] = to_owner
        return self._post("/agents/dm/request", body)

    def dm_requests(self) -> dict:
        """View pending incoming chat requests."""
        return self._get("/agents/dm/requests")

    def dm_approve(self, conversation_id: str) -> dict:
        """Approve a pending chat request."""
        return self._post(f"/agents/dm/requests/{conversation_id}/approve")

    def dm_reject(self, conversation_id: str, block: bool = False) -> dict:
        """Reject a chat request, optionally blocking future requests."""
        body = {"block": True} if block else None
        return self._post(f"/agents/dm/requests/{conversation_id}/reject", body)

    def dm_conversations(self) -> dict:
        """List active DM conversations."""
        return self._get("/agents/dm/conversations")

    def dm_read(self, conversation_id: str) -> dict:
        """Read messages in a conversation (marks them as read)."""
        return self._get(f"/agents/dm/conversations/{conversation_id}")

    def dm_send(self, conversation_id: str, message: str,
                needs_human_input: bool = False) -> dict:
        """Send a message in an active conversation."""
        body: dict = {"message": message}
        if needs_human_input:
            body["needs_human_input"] = True
        return self._post(f"/agents/dm/conversations/{conversation_id}/send", body)
