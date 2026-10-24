"""Where evidence photos live, behind one small interface.

local     files under UPLOAD_DIR, served through short-lived signed paths (GET /evidence/file/{token}); tested.
supabase  a PRIVATE Supabase Storage bucket over its REST API; reads go through short-lived signed URLs. This backend
          is exercised by unit tests with a mocked HTTP client only: it has not been run against a real project.
"""
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import httpx

from . import config
from .http_utils import api_error


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _signing_key() -> bytes:
    if config.REPLY_LINK_SECRET:
        return config.REPLY_LINK_SECRET.encode()
    if config.AUTH_REQUIRED:
        raise api_error(503, "storage_not_configured", "REPLY_LINK_SECRET is not set on the server.")
    return b"local-development-reply-secret"


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("storage key escapes the upload folder")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def signed_url(self, key: str, seconds: int) -> str:
        body = _b64(json.dumps({"k": key, "e": int(time.time()) + seconds}, separators=(",", ":")).encode())
        sig = _b64(hmac.new(_signing_key(), b"file:" + body.encode(), hashlib.sha256).digest())
        return f"/evidence/file/{body}.{sig}"

    def key_from_token(self, token: str) -> str:
        """Verify a signed path token and return the storage key. Tamper or expiry is a plain 404."""
        bad = api_error(404, "invalid_link", "This link is not valid or has expired.")
        try:
            body, sig = token.split(".", 1)
            good = _b64(hmac.new(_signing_key(), b"file:" + body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, good):
                raise bad
            data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if int(data["e"]) < time.time():
                raise bad
            return str(data["k"])
        except (ValueError, KeyError, TypeError):
            raise bad


class SupabaseStorage:
    def __init__(self, url: str, service_key: str, bucket: str, client: httpx.Client | None = None):
        self.url, self.bucket = url.rstrip("/"), bucket
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self.client = client or httpx.Client(timeout=20)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        r = self.client.post(f"{self.url}/storage/v1/object/{self.bucket}/{key}",
                             headers={**self.headers, "Content-Type": content_type, "x-upsert": "false"}, content=data)
        r.raise_for_status()

    def signed_url(self, key: str, seconds: int) -> str:
        r = self.client.post(f"{self.url}/storage/v1/object/sign/{self.bucket}/{key}", headers=self.headers,
                             json={"expiresIn": seconds})
        r.raise_for_status()
        return f"{self.url}/storage/v1{r.json()['signedURL']}"


def get_storage():
    if config.STORAGE_BACKEND == "supabase":
        if not (config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY):
            raise api_error(503, "storage_not_configured", "SUPABASE_URL and SUPABASE_SERVICE_KEY are needed for storage.")
        return SupabaseStorage(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.SUPABASE_BUCKET)
    return LocalStorage(config.UPLOAD_DIR)
