"""MinerU precision API client. Never prints the token or signed URLs."""
import http.client
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from . import net

DEFAULT_BASE = "https://mineru.net/api/v4"
MODEL = "vlm"
DOWNLOAD_ATTEMPTS = 4


class MineruError(Exception):
    pass


def put_signed(url, path):
    """PUT a file to a signed OSS URL. Extra headers such as Content-Type break the signature."""
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(parts.hostname, timeout=300)
    try:
        conn.request("PUT", f"{parts.path}?{parts.query}", body=Path(path).read_bytes())
        status = conn.getresponse().status
    except OSError as e:
        raise MineruError(f"upload failed: {type(e).__name__}") from None
    finally:
        conn.close()
    if status != 200:
        raise MineruError(f"upload failed: HTTP {status}")


def unpack(data, assets):
    """Return full.md from a result zip, saving its images under the assets directory."""
    assets = Path(assets)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise MineruError("result is not a valid zip") from None
    with archive:
        names = archive.namelist()
        if "full.md" not in names:
            raise MineruError("result has no full.md")
        markdown = archive.read("full.md").decode("utf-8")
        for name in names:
            pure = PurePosixPath(name)
            if len(pure.parts) == 2 and pure.parts[0] == "images" and ".." not in pure.parts:
                assets.mkdir(parents=True, exist_ok=True)
                (assets / pure.name).write_bytes(archive.read(name))
    return re.sub(r"\]\(images/([^)\s/]+)\)", lambda m: f"]({assets.name}/{m.group(1)})", markdown)


class Client:
    def __init__(self, token, base=DEFAULT_BASE, language="en", poll_seconds=5, timeout_seconds=900):
        self.token = token
        self.base = base.rstrip("/")
        self.language = language
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def _api(self, path, body=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with net.urlopen(request, timeout=60) as resp:
                result = json.load(resp)
        except (OSError, ValueError) as e:
            raise MineruError(f"API request failed: {type(e).__name__}") from None
        if result.get("code") != 0:
            raise MineruError(f"API error {result.get('code')}: {result.get('msg')}")
        return result["data"]

    def _options(self):
        return {"model_version": MODEL, "language": self.language, "enable_formula": True, "enable_table": True}

    def _wait(self, read_state):
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            state = read_state()
            if state and state.get("state") == "done":
                return state["full_zip_url"]
            if state and state.get("state") == "failed":
                raise MineruError(f"parse failed: {state.get('err_msg', 'unknown')}")
            time.sleep(self.poll_seconds)
        raise MineruError("parse timed out")

    @staticmethod
    def _download(url):
        for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
            try:
                with net.urlopen(url, timeout=300) as resp:
                    return resp.read()
            except (OSError, http.client.HTTPException) as e:
                if attempt == DOWNLOAD_ATTEMPTS:
                    raise MineruError(f"result download failed: {type(e).__name__}") from None
                time.sleep(5 * attempt)

    def parse_url(self, url, assets):
        task = self._api("/extract/task", {"url": url, **self._options()})["task_id"]
        return unpack(self._download(self._wait(lambda: self._api(f"/extract/task/{task}"))), assets)

    def parse_file(self, path, assets):
        data = self._api("/file-urls/batch", {"files": [{"name": "paper.pdf"}], **self._options()})
        put_signed(data["file_urls"][0], path)
        batch = data["batch_id"]

        def read_state():
            results = self._api(f"/extract-results/batch/{batch}").get("extract_result") or []
            return results[0] if results else None

        return unpack(self._download(self._wait(read_state)), assets)
