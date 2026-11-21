"""本地网页工具的服务端骨架片段。

取自已验证实现 <project-root>/watermark-remover/server.py（净印），去掉业务逻辑，只留交付骨架。
用前替换占位：APP_ID（实例标识）、NO_BROWSER_ENV 变量名、错误文案里的工具名。
"""

import atexit
import json
import os
import secrets
import socket
import sys
import threading
import traceback
import uuid
from pathlib import Path
from urllib.request import urlopen

from flask import Flask, jsonify, render_template, request, session
from werkzeug.serving import make_server

APP_ID = "jingyin"
NO_BROWSER_ENV = "JINGYIN_NO_BROWSER"

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "work"
UPLOAD_ROOT = WORK_DIR / "uploads"
ZIP_DIR = WORK_DIR / "zips"
OUTPUT_ROOT = BASE_DIR / "成品"
RUNTIME_FILE = WORK_DIR / "runtime.json"
LOG_FILE = WORK_DIR / "tool.log"
SERVER_HOLDER: dict = {}

APP_TOKEN = secrets.token_urlsafe(32)


def find_existing_instance():
    if not RUNTIME_FILE.exists():
        return None
    try:
        data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
        port = int(data["port"])
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("app") == APP_ID:
            return port
    except Exception:
        return None
    return None


def choose_port():
    for port in range(8765, 8786):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("端口 8765-8785 都被占用，请关闭其他程序后重试")


def remove_runtime_file():
    try:
        if RUNTIME_FILE.exists():
            data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
            if int(data.get("pid", -1)) == os.getpid():
                RUNTIME_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def build_app():
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        template_folder=str(BASE_DIR / "templates"),
    )

    @app.before_request
    def prepare_request():
        if "sid" not in session:
            session["sid"] = uuid.uuid4().hex
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token = request.headers.get("X-App-Token", "")
            if not secrets.compare_digest(token, APP_TOKEN):
                return jsonify({"error": "页面校验失败，请刷新后重试"}), 403
        return None

    @app.after_request
    def set_security_headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return render_template("index.html", app_token=APP_TOKEN)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "app": APP_ID, "version": 1})

    return app


def main():
    app = build_app()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    existing_port = find_existing_instance()
    if existing_port:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{existing_port}/")
        return

    port = choose_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    SERVER_HOLDER["server"] = server
    RUNTIME_FILE.write_text(
        json.dumps({"port": port, "pid": os.getpid()}, ensure_ascii=False),
        encoding="utf-8",
    )
    atexit.register(remove_runtime_file)
    app.logger.info("%s server listening on http://127.0.0.1:%s", APP_ID, port)
    if os.environ.get(NO_BROWSER_ENV) != "1":
        import webbrowser

        threading.Timer(0.7, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    try:
        server.serve_forever()
    finally:
        remove_runtime_file()
        app.logger.info("%s server stopped", APP_ID)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write("\n启动失败：\n")
            log.write(traceback.format_exc())
        if sys.stderr is not None:
            traceback.print_exc()
        raise
