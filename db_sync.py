"""Persist the SQLite database through GitHub Contents API.

Streamlit Cloud runtime storage is temporary. This module lets the app keep the
latest refreshed SQLite file in the GitHub repo so restarts do not fall back to
the older bundled database.
"""

import base64
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import streamlit as st


@dataclass
class SyncResult:
    ok: bool
    message: str
    changed: bool = False


def _setting(name: str, default: str = "") -> str:
    try:
        value = st.secrets[name]
        return str(value)
    except Exception:
        return os.environ.get(name, default)


def _headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _parse_refresh_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    value = value.strip()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _read_refresh_time(db_path: Path) -> Optional[datetime]:
    if not db_path.exists():
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key='last_refresh'")
        row = cursor.fetchone()
        conn.close()
    except Exception:
        return None

    return _parse_refresh_time(row[0] if row else None)


def _is_valid_database(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM brands")
        brand_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM models")
        model_count = cursor.fetchone()[0]
        conn.close()
        return brand_count > 0 and model_count > 0
    except Exception:
        return False


def _get_config() -> dict:
    token = _setting("GITHUB_TOKEN")
    repo = _setting("GITHUB_REPO") or _setting("GITHUB_REPOSITORY")
    branch = _setting("GITHUB_BRANCH")
    db_path = _setting("GITHUB_DB_PATH", "vehicle_data.db")
    enabled_text = _setting("GITHUB_DB_SYNC_ENABLED")

    enabled = enabled_text.lower() in ("1", "true", "yes", "on") or bool(token and repo)
    return {
        "enabled": enabled,
        "token": token,
        "repo": repo,
        "branch": branch,
        "db_path": db_path,
    }


def is_configured() -> bool:
    config = _get_config()
    return bool(config["enabled"] and config["token"] and config["repo"])


def _default_branch(repo: str, token: str) -> str:
    response = requests.get(
        f"https://api.github.com/repos/{repo}",
        headers=_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("default_branch") or "main"


def _content_url(repo: str, db_path: str) -> str:
    return f"https://api.github.com/repos/{repo}/contents/{db_path}"


def _get_remote_file(repo: str, db_path: str, branch: str, token: str) -> Optional[dict]:
    response = requests.get(
        _content_url(repo, db_path),
        headers=_headers(token),
        params={"ref": branch},
        timeout=30,
    )

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()


def download_database_if_newer(local_path: Path) -> SyncResult:
    """Download the GitHub copy when it is newer than the local bundled file."""
    config = _get_config()
    if not config["enabled"]:
        return SyncResult(True, "GitHub DB sync is disabled.")
    if not config["token"] or not config["repo"]:
        return SyncResult(False, "Set GITHUB_TOKEN and GITHUB_REPO to enable DB sync.")

    try:
        branch = config["branch"] or _default_branch(config["repo"], config["token"])
        remote = _get_remote_file(config["repo"], config["db_path"], branch, config["token"])
        if not remote:
            return SyncResult(True, "No database found in GitHub sync yet.")

        content = base64.b64decode(remote["content"])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f"{local_path.stem}_remote_",
            suffix=".db",
            dir=local_path.parent,
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        if not _is_valid_database(temp_path):
            temp_path.unlink(missing_ok=True)
            return SyncResult(False, "GitHub database was downloaded but is not valid.")

        remote_refresh = _read_refresh_time(temp_path)
        local_refresh = _read_refresh_time(local_path)
        if local_refresh and remote_refresh and local_refresh >= remote_refresh:
            temp_path.unlink(missing_ok=True)
            return SyncResult(True, "Local database is already current.")

        os.replace(temp_path, local_path)
        label = remote_refresh.isoformat(sep=" ") if remote_refresh else "unknown time"
        return SyncResult(True, f"Loaded database from GitHub sync ({label}).", True)

    except Exception as exc:
        return SyncResult(False, f"GitHub DB download failed: {exc}")


def upload_database(local_path: Path) -> SyncResult:
    """Upload the latest local SQLite file to GitHub after a successful refresh."""
    config = _get_config()
    if not config["enabled"]:
        return SyncResult(True, "GitHub DB sync is disabled.")
    if not config["token"] or not config["repo"]:
        return SyncResult(False, "Set GITHUB_TOKEN and GITHUB_REPO to enable DB sync.")
    if not local_path.exists() or not _is_valid_database(local_path):
        return SyncResult(False, "Local database is missing or invalid; upload skipped.")

    try:
        branch = config["branch"] or _default_branch(config["repo"], config["token"])
        remote = _get_remote_file(config["repo"], config["db_path"], branch, config["token"])
        refresh_time = _read_refresh_time(local_path)
        refresh_label = refresh_time.isoformat(sep=" ") if refresh_time else "latest"

        payload = {
            "message": f"Update vehicle database ({refresh_label})",
            "content": base64.b64encode(local_path.read_bytes()).decode("ascii"),
            "branch": branch,
        }
        if remote and remote.get("sha"):
            payload["sha"] = remote["sha"]

        response = requests.put(
            _content_url(config["repo"], config["db_path"]),
            headers=_headers(config["token"]),
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return SyncResult(True, "Saved updated database to GitHub sync.", True)

    except Exception as exc:
        return SyncResult(False, f"GitHub DB upload failed: {exc}")
