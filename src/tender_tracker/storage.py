from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import shutil
import time
from typing import Any
from urllib.parse import quote

import requests

from tender_tracker.config import AppSettings
from tender_tracker.models import json_default


class StorageError(RuntimeError):
    """Raised when storage operations fail."""


class BaseStorage:
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        raise NotImplementedError

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        raise NotImplementedError

    def read_text(self, remote_path: str) -> str | None:
        raise NotImplementedError

    def write_text(self, remote_path: str, content: str) -> None:
        raise NotImplementedError

    def exists(self, remote_path: str) -> bool:
        raise NotImplementedError

    def write_json(self, remote_path: str, payload: Any) -> None:
        self.write_text(remote_path, json.dumps(payload, ensure_ascii=False, indent=2, default=json_default))

    def read_json(self, remote_path: str) -> Any | None:
        content = self.read_text(remote_path)
        if content is None:
            return None
        return json.loads(content)


class LocalStorage(BaseStorage):
    def __init__(self, root: Path) -> None:
        self.root = root

    def _resolve(self, remote_path: str) -> Path:
        return self.root / remote_path.lstrip("/").replace("/", os.sep)

    def download_file(self, remote_path: str, local_path: Path) -> bool:
        source = self._resolve(remote_path)
        if not source.exists():
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_path)
        return True

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        target = self._resolve(remote_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)

    def read_text(self, remote_path: str) -> str | None:
        path = self._resolve(remote_path)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_text(self, remote_path: str, content: str) -> None:
        path = self._resolve(remote_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def exists(self, remote_path: str) -> bool:
        return self._resolve(remote_path).exists()


class GraphOneDriveStorage(BaseStorage):
    def __init__(self, settings: AppSettings) -> None:
        if not settings.auth.tenant_id or not settings.auth.client_id or not settings.auth.client_secret:
            raise StorageError("Microsoft Graph credentials are missing from environment variables")
        self.settings = settings
        self._session = requests.Session()
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._base_url = "https://graph.microsoft.com/v1.0"
        self._user = settings.storage.onedrive.user_principal_name

    def _token(self, *, force_refresh: bool = False) -> str:
        if (
            not force_refresh
            and self._access_token
            and time.monotonic() < self._access_token_expires_at - 300
        ):
            return self._access_token
        response = self._session.post(
            f"https://login.microsoftonline.com/{self.settings.auth.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.settings.auth.client_id,
                "client_secret": self.settings.auth.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        self._access_token_expires_at = time.monotonic() + int(payload.get("expires_in", 3600))
        return self._access_token

    def _headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token(force_refresh=force_refresh)}"}

    def _normalize(self, remote_path: str) -> str:
        return "/" + remote_path.strip("/")

    def _path_url(self, remote_path: str) -> str:
        normalized = quote(self._normalize(remote_path), safe="/")
        return f"{self._base_url}/users/{quote(self._user)}/drive/root:{normalized}:"

    def _request(self, method: str, url: str, *, allow_404: bool = False, **kwargs: Any) -> requests.Response:
        base_headers = kwargs.pop("headers", {})
        for attempt in range(2):
            headers = dict(base_headers)
            headers.update(self._headers(force_refresh=attempt == 1))
            response = self._session.request(method, url, headers=headers, timeout=60, **kwargs)
            if allow_404 and response.status_code == 404:
                return response
            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                self._access_token_expires_at = 0.0
                continue
            if response.status_code >= 400:
                raise StorageError(f"Graph request failed: {method} {url} -> {response.status_code} {response.text[:400]}")
            return response
        raise StorageError(f"Graph request failed: {method} {url} -> unauthorized after token refresh")

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        normalized = self._normalize(remote_dir)
        if normalized == "/":
            return
        parts = [part for part in normalized.strip("/").split("/") if part]
        current = ""
        for part in parts:
            current = f"{current}/{part}"
            metadata = self._request("GET", self._path_url(current), allow_404=True)
            if metadata.status_code == 200:
                continue
            parent_segments = current.strip("/").split("/")[:-1]
            if parent_segments:
                parent = "/" + "/".join(parent_segments)
                create_url = self._path_url(parent) + "/children"
            else:
                create_url = f"{self._base_url}/users/{quote(self._user)}/drive/root/children"
            payload = {"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
            response = self._request("POST", create_url, allow_404=True, json=payload)
            if response.status_code not in {200, 201, 409}:
                raise StorageError(f"Could not create OneDrive directory {current}: {response.status_code} {response.text[:400]}")

    def download_file(self, remote_path: str, local_path: Path) -> bool:
        response = self._request("GET", self._path_url(remote_path) + "/content", allow_404=True, stream=True)
        if response.status_code == 404:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return True

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        remote_parent = str(Path(remote_path).parent).replace("\\", "/")
        self._ensure_remote_dir(remote_parent)

        size = local_path.stat().st_size
        if size <= 4 * 1024 * 1024:
            with local_path.open("rb") as handle:
                self._request("PUT", self._path_url(remote_path) + "/content", data=handle.read())
            return

        session_response = self._request(
            "POST",
            self._path_url(remote_path) + "/createUploadSession",
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        upload_url = session_response.json()["uploadUrl"]
        chunk_size = 320 * 1024
        with local_path.open("rb") as handle:
            start = 0
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                end = start + len(chunk) - 1
                headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                }
                response = requests.put(upload_url, headers=headers, data=chunk, timeout=120)
                if response.status_code not in {200, 201, 202}:
                    raise StorageError(f"Upload session failed for {remote_path}: {response.status_code} {response.text[:400]}")
                start = end + 1

    def read_text(self, remote_path: str) -> str | None:
        response = self._request("GET", self._path_url(remote_path) + "/content", allow_404=True)
        if response.status_code == 404:
            return None
        response.encoding = "utf-8"
        return response.text

    def write_text(self, remote_path: str, content: str) -> None:
        work_dir = Path("work")
        work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            prefix="graph_upload_",
            dir=work_dir,
            delete=False,
        ) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            self.upload_file(temp_path, remote_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def exists(self, remote_path: str) -> bool:
        response = self._request("GET", self._path_url(remote_path), allow_404=True)
        return response.status_code == 200


def build_storage(settings: AppSettings) -> BaseStorage:
    if settings.storage.backend == "local":
        return LocalStorage(Path(settings.storage.local_root))
    return GraphOneDriveStorage(settings)
