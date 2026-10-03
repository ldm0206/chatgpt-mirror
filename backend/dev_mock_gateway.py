# -*- coding: utf-8 -*-
"""本地开发用的 mock 网关：只实现 Django 侧需要的最小 HTTP 面。

仅供无 Docker / 无闭源网关时本地联调使用，不要部署到生产。
- GET/POST /api/custom-scripts  : 真实读写（持久化到 dev_mock_state.json）
- 其他 /api/*                    : 返回空对象，避免管理台页面直接报错
启动: python dev_mock_gateway.py   (监听 127.0.0.1:9100)
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9100
SHARED_SECRET = "local-dev-secret"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev_mock_state.json")

DEFAULT_STATE = {
    "scripts": [
        {"id": 1, "enabled": True, "name": "示例：隐藏横幅", "language": "css",
         "position": "body_end", "content": "#banner{display:none}"},
    ],
    "trusted_cdn_sources": [],
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


class Handler(BaseHTTPRequestHandler):
    server_version = "MockGateway/1.0"

    def _json(self, payload, code=200, cookies=()):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        return self.headers.get("Authorization") == "Bearer " + SHARED_SECRET

    def do_GET(self):
        print(f"[mock-gateway] GET {self.path}", flush=True)
        if not self._authorized():
            self._json({"detail": "invalid gateway secret"}, 401)
            return
        state = load_state()
        if self.path == "/api/custom-scripts":
            self._json(state)
            return
        self._json({})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            data = {}
        print(f"[mock-gateway] POST {self.path}", flush=True)
        if not self._authorized():
            self._json({"detail": "invalid gateway secret"}, 401)
            return
        if self.path == "/api/custom-scripts":
            state = {
                "scripts": data.get("scripts") or [],
                "trusted_cdn_sources": data.get("trusted_cdn_sources") or [],
            }
            save_state(state)
            self._json(state)
            return
        if self.path == "/api/login":
            # 本地没有真实镜像页面，用演示页充当 login_url 的落点；附带一个演示会话
            # Cookie，用来验证 Django 会把网关在登录时签发的 Cookie 透传给浏览器。
            self._json(
                {"login_url": "/admin/egress-demo.html"},
                cookies=["mock_gateway_session=demo; Path=/; HttpOnly; SameSite=Strict"],
            )
            return
        if self.path == "/api/diagnose-chatgpt-auth":
            # 本地演示凭据是假的，但让诊断始终报告可用
            self._json({"access_token_valid": True, "session_token_valid": True,
                        "last_check_at": int(time.time())})
            return
        self._json({})

    def log_message(self, fmt, *args):
        pass  # 已在 do_* 里打印


if __name__ == "__main__":
    print(f"[mock-gateway] listening on http://127.0.0.1:{PORT}", flush=True)
    print(f"[mock-gateway] state file: {STATE_FILE}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
