"""
GitHub release update checker with local cache.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from version import __version__


@dataclass
class UpdateInfo:
    available: bool
    current_version: str
    latest_version: str
    release_url: str
    published_at: Optional[str] = None
    changelog: str = ""


def _default_cache_path() -> Path:
    # Keep SEBlockExchanger so the update cache survives the MBX rename.
    appdata = os.getenv("APPDATA")
    if appdata:
        base = Path(appdata) / "SEBlockExchanger"
    else:
        base = Path.home() / ".se_block_exchanger"
    base.mkdir(parents=True, exist_ok=True)
    return base / "update_cache.json"


class UpdateChecker:
    """Checks GitHub Releases API for new versions."""

    # owner/repo — both segments restricted to GitHub-allowed characters.
    _REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

    def __init__(
        self,
        repo: str = "MerabyLabs/Meraby-Block-Exchanger",
        cache_path: Optional[Path] = None,
        cache_hours: int = 24,
    ):
        if not self._REPO_PATTERN.match(repo):
            raise ValueError(f"Invalid repo identifier: {repo!r}")
        self.repo = repo
        self.cache_path = Path(cache_path) if cache_path else _default_cache_path()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_hours = cache_hours

    @staticmethod
    def _normalize_version(raw: str) -> str:
        return raw.lstrip("vV").strip()

    @staticmethod
    def _version_tuple(version: str):
        parts = re.findall(r"\d+", version)
        if not parts:
            return (0, 0, 0)
        numeric = [int(value) for value in parts[:3]]
        while len(numeric) < 3:
            numeric.append(0)
        return tuple(numeric)

    def _load_cache(self) -> Optional[Dict]:
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.now(timezone.utc) - cached_at > timedelta(hours=self.cache_hours):
                return None
            return data
        except Exception:
            return None

    def _save_cache(self, payload: Dict) -> None:
        record = dict(payload)
        record["cached_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.cache_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)

    def _fetch_release(self) -> Dict:
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Meraby-Block-Exchanger",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        self._save_cache(data)
        return data

    def check_for_updates(self, force: bool = False) -> UpdateInfo:
        data = None if force else self._load_cache()
        if data is None:
            data = self._fetch_release()

        latest_version = self._normalize_version(data.get("tag_name", "0.0.0"))
        current_version = self._normalize_version(__version__)
        available = self._version_tuple(latest_version) > self._version_tuple(current_version)

        return UpdateInfo(
            available=available,
            current_version=current_version,
            latest_version=latest_version,
            release_url=data.get("html_url", ""),
            published_at=data.get("published_at"),
            changelog=data.get("body", ""),
        )
