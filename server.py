#!/usr/bin/env python3
"""Simple logging HTTP server.

Starts an HTTP server on 0.0.0.0:6565 (configurable) that logs every
incoming request and responds with a fixed body loaded from a file at
startup.
"""

import argparse
import base64
import datetime as _dt
import logging
import mimetypes
import os
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 6565


# ---- helpers -------------------------------------------------------------

def _shell_quote(value: str) -> str:
    """Return a shell-safe single-quoted string."""
    return "'" + value.replace("'", "'\\''") + "'"


def build_curl(method: str, url: str, headers: Dict[str, str], body: bytes) -> str:
    parts = ["curl", "-i", "-X", method]
    for key, val in headers.items():
        parts.extend(["-H", _shell_quote(f"{key}: {val}")])
    if body:
        try:
            body_text = body.decode("utf-8")
            parts.extend(["--data-raw", _shell_quote(body_text)])
        except UnicodeDecodeError:
            parts.extend(["--data-binary", _shell_quote(body.decode("latin1"))])
    parts.append(_shell_quote(url))
    return " ".join(parts)


def build_httpie(method: str, url: str, headers: Dict[str, str], body: bytes) -> str:
    parts = ["http", "-v", method, _shell_quote(url)]
    for key, val in headers.items():
        parts.append(_shell_quote(f"{key}:{val}"))
    if body:
        try:
            body_text = body.decode("utf-8")
            parts.extend(["--raw", _shell_quote(body_text)])
        except UnicodeDecodeError:
            parts.extend(["--raw", _shell_quote(body.decode("latin1"))])
    return " ".join(parts)


def build_python_requests(method: str, url: str, headers: Dict[str, str], body: bytes) -> str:
    # Use latin1 to preserve byte-for-byte round‑trip if not valid UTF-8.
    body_literal = repr(body.decode("utf-8", errors="backslashreplace"))
    headers_literal = repr(headers)
    snippet = f"""
import requests

url = {repr(url)}
headers = {headers_literal}
data = {body_literal}

resp = requests.request({repr(method)}, url, headers=headers, data=data)
print(resp.status_code)
print(resp.text)
"""
    return textwrap.dedent(snippet).strip()


def ensure_log_dir(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


# ---- request handler -----------------------------------------------------

class LoggingHandler(BaseHTTPRequestHandler):
    server_version = "LogServer/1.0"

    def _read_body(self) -> bytes:
        length_str = self.headers.get("Content-Length")
        if not length_str:
            return b""
        try:
            length = int(length_str)
        except ValueError:
            length = 0
        return self.rfile.read(length) if length > 0 else b""

    def _respond(self):
        body = self._read_body()
        host_header = self.headers.get(
            "Host", f"{self.server.server_name}:{self.server.server_port}"
        )
        full_url = f"http://{host_header}{self.path}"
        self.server.log_request(  # type: ignore[attr-defined]
            method=self.command,
            path=self.path,
            url=full_url,
            headers={k: v for k, v in self.headers.items()},
            body=body,
            client=self.client_address[0],
        )

        self.send_response(200)
        self.send_header("Content-Type", self.server.response_content_type)  # type: ignore[attr-defined]
        self.send_header("Content-Length", str(len(self.server.response_body)))  # type: ignore[attr-defined]
        self.end_headers()
        self.wfile.write(self.server.response_body)  # type: ignore[attr-defined]

    # Map all methods to the same handler.
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _respond

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Silence BaseHTTPRequestHandler default logging; we handle logging ourselves.
        return


# ---- server wrapper ------------------------------------------------------

class LogServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_cls, response_body: bytes, content_type: str, logger: logging.Logger):
        super().__init__(server_address, handler_cls)
        self.response_body = response_body
        self.response_content_type = content_type
        self.logger = logger
        self.allow_reuse_address = True

    def log_request(self, method: str, path: str, url: str, headers: Dict[str, str], body: bytes, client: str):
        timestamp = _dt.datetime.now().isoformat(timespec="seconds")
        body_utf8 = body.decode("utf-8", errors="replace") if body else ""
        body_b64 = base64.b64encode(body).decode("ascii") if body else ""

        curl_cmd = build_curl(method, url, headers, body)
        httpie_cmd = build_httpie(method, url, headers, body)
        requests_snippet = build_python_requests(method, url, headers, body)

        headers_block = "\n".join(f"  - {k}: {v}" for k, v in headers.items()) or "  - (none)"

        lines = [
            f"----- REQUEST START {timestamp} -----",
            f"client: {client}",
            f"method: {method}",
            f"path: {path}",
            f"url: {url}",
            "headers:",
            headers_block,
            "body:",
            f"  length: {len(body)} bytes",
            f"  utf8: {body_utf8}",
            f"  base64: {body_b64}",
            "replay:",
            "  curl: |",
            textwrap.indent(curl_cmd, "    "),
            "  httpie: |",
            textwrap.indent(httpie_cmd, "    "),
            "  python_requests: |",
            textwrap.indent(requests_snippet, "    "),
            f"----- REQUEST END {timestamp} -----\n",
        ]
        self.logger.info("\n".join(lines))


# ---- cli entry -----------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple HTTP logger server")
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST})"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--response-file",
        required=True,
        help="File whose contents will be returned for every request (read once at startup)",
    )
    parser.add_argument(
        "--log-file",
        default="requests.log",
        help="Path to append request logs (default: requests.log)",
    )
    parser.add_argument(
        "--clear-log",
        action="store_true",
        help="Truncate the log file at startup before writing new entries",
    )
    parser.add_argument(
        "--content-type",
        default=None,
        help="Optional Content-Type for responses. If omitted, guessed from file or defaults to text/plain; charset=utf-8",
    )
    return parser.parse_args()


def configure_logger(log_path: str) -> logging.Logger:
    ensure_log_dir(log_path)
    logger = logging.getLogger("log_server")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if run repeatedly in same process.
    if logger.handlers:
        return logger

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    stream_handler = logging.StreamHandler()

    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def load_response_body(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def determine_content_type(path: str, override: str | None) -> str:
    if override:
        return override
    guessed, _ = mimetypes.guess_type(path)
    if not guessed:
        return "text/plain; charset=utf-8"
    if guessed.startswith("text/") and "charset" not in guessed:
        guessed += "; charset=utf-8"
    return guessed


def main():
    args = parse_args()
    response_body = load_response_body(args.response_file)
    content_type = determine_content_type(args.response_file, args.content_type)

    if args.clear_log:
        ensure_log_dir(args.log_file)
        open(args.log_file, "w").close()

    logger = configure_logger(args.log_file)

    server = LogServer((args.host, args.port), LoggingHandler, response_body, content_type, logger)

    logger.info(
        "Starting server on %s:%s, responding with contents of %s (Content-Type: %s)",
        args.host,
        args.port,
        os.path.abspath(args.response_file),
        content_type,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
