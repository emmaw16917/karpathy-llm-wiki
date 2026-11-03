#!/usr/bin/env python3
"""Diagnose local-file uploads to MinerU (signed PUT to Aliyun OSS).

Stdlib only. Never prints the token or the signed URL.

  python scripts/test_mineru_oss.py                 # network checks + real 1-page upload
  python scripts/test_mineru_oss.py --no-upload     # network checks only, no token used
  python scripts/test_mineru_oss.py --proxy http://127.0.0.1:21081
  python scripts/test_mineru_oss.py --file some.pdf # upload this file instead of the test PDF

A real upload starts a MinerU parse, so it uses a little quota.
"""
import argparse
import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://mineru.net/api/v4"
HOSTS = ["mineru.net", "oss-cn-shanghai.aliyuncs.com", "mineru.oss-cn-shanghai.aliyuncs.com"]
CONFIG = Path(__file__).resolve().parent.parent / "config.json"
TEST_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
    b"/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj\n"
    b"4 0 obj<</Length 41>>stream\nBT /F1 18 Tf 40 100 Td (OSS test) Tj ET\nendstream endobj\n"
    b"trailer<</Root 1 0 R>>\n"
)


def report(ok, label, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{' - ' + str(detail) if detail else ''}", flush=True)
    return ok


def check_host(host):
    try:
        ip = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)[0][4][0]
    except OSError as e:
        return report(False, f"{host} DNS", e)
    report(True, f"{host} DNS", ip)
    try:
        sock = socket.create_connection((ip, 443), timeout=10)
    except OSError as e:
        return report(False, f"{host} direct TCP", e)
    report(True, f"{host} direct TCP")
    try:
        with sock, ssl.create_default_context().wrap_socket(sock, server_hostname=host) as tls:
            return report(True, f"{host} direct TLS", f"{tls.version()} {tls.cipher()[0]}")
    except (OSError, ssl.SSLError) as e:
        return report(False, f"{host} direct TLS", e)


def request_upload_url(token, name):
    body = {"files": [{"name": name}], "model_version": "vlm", "language": "en"}
    req = urllib.request.Request(
        f"{API}/file-urls/batch",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.load(resp)
    if res.get("code") != 0:
        raise RuntimeError(f"API code={res.get('code')} msg={res.get('msg')}")
    return res["data"]["batch_id"], res["data"]["file_urls"][0]


def put_urllib(url, path, proxy):
    # urllib adds a default Content-Type, which breaks the OSS signature (403).
    parts = urllib.parse.urlsplit(url)
    if proxy:
        p = urllib.parse.urlsplit(proxy)
        conn = http.client.HTTPConnection(p.hostname, p.port, timeout=300)
        conn.set_tunnel(parts.hostname, 443)
        conn = _tls_over(conn, parts.hostname)
    else:
        conn = http.client.HTTPSConnection(parts.hostname, timeout=300)
    try:
        conn.request("PUT", f"{parts.path}?{parts.query}", body=Path(path).read_bytes())
        return conn.getresponse().status
    finally:
        conn.close()


def _tls_over(plain, host):
    plain.connect()
    wrapped = http.client.HTTPSConnection(host, timeout=300)
    wrapped.sock = ssl.create_default_context().wrap_socket(plain.sock, server_hostname=host)
    return wrapped


def put_curl(url, path, proxy):
    cmd = ["curl", "-sS", "-m", "280", "-o", os.devnull, "-w", "%{http_code}",
           "-T", str(path), "-H", "Content-Type:", url]
    if proxy:
        cmd += ["--proxy", proxy]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip() == "200":
        return 200
    raise RuntimeError(f"http={r.stdout.strip()} {r.stderr.split('?')[0].strip()}")


def safe_error(e):
    return str(e).split("?")[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--proxy", help="for example http://127.0.0.1:21081")
    ap.add_argument("--file", help="PDF to upload; defaults to a generated 1-page PDF")
    ap.add_argument("--config", default=str(CONFIG))
    args = ap.parse_args()

    print("Proxy env:", {k: "set" for k in os.environ if k.lower() in
                         ("http_proxy", "https_proxy", "all_proxy", "no_proxy")} or "none")
    print("System proxy seen by Python:", {k: "set" for k in urllib.request.getproxies()} or "none")
    print("OpenSSL:", ssl.OPENSSL_VERSION, "\n")

    for host in HOSTS:
        check_host(host)
    if args.no_upload:
        return 0

    token = json.loads(Path(args.config).read_text(encoding="utf-8"))["mineru"]["api_token"].strip()
    if not token:
        report(False, "token", "mineru.api_token is empty")
        return 1

    methods = [("python", put_urllib)]
    if shutil.which("curl"):
        methods.append(("curl", put_curl))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(args.file) if args.file else Path(tmp) / "oss_test.pdf"
        if not args.file:
            path.write_bytes(TEST_PDF)
        print(f"\nUpload file: {path.name} ({path.stat().st_size} bytes)")
        for name, put in methods:
            try:
                # A signed URL is single-purpose, so each method gets its own.
                batch, url = request_upload_url(token, path.name)
                report(True, "request signed URL", f"host={urllib.parse.urlparse(url).hostname}")
            except (OSError, RuntimeError, urllib.error.URLError) as e:
                report(False, "request signed URL", safe_error(e))
                return 1
            start = time.time()
            try:
                status = put(url, path, args.proxy)
                report(status == 200, f"{name} PUT", f"http={status} {time.time() - start:.1f}s batch={batch}")
                if status == 200:
                    print("\nUpload works. Use this network setup and method.")
                    return 0
            except Exception as e:  # report every failure type, then try the next method
                report(False, f"{name} PUT", f"{type(e).__name__}: {safe_error(e)[:200]}")
    print("\nAll upload methods failed. Retry with --proxy, or change the proxy/VPN rule for aliyuncs.com.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
