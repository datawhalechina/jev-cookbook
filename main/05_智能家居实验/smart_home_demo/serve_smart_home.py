"""智能家居 3D 演练场本地服务：静态页面 + 三个上游 API 代理。

浏览器页面为什么要经过这层本地代理，而不是直连：
1. api.typesafe.ai 与 api.stepfun.com 都不保证给浏览器 CORS 头，直连会被拦；
2. API key 不能暴露在页面里——放在这台本地服务的环境变量中。

代理端点：
- POST /api/jev   → https://api.typesafe.ai/v1/systemone   （单次投机提示调用）
- POST /api/asr   → https://api.stepfun.com/v1/audio/asr/sse（阶跃星辰流式语音识别，SSE 原样透传）
- POST /api/chat  → https://api.stepfun.com/v1/chat/completions（复合指令拆分 / 常识问答）
- GET  /api/health→ 报告哪些 key 已配置，页面据此决定「真实 Jev / 本地模拟」模式

运行：  python3 serve_smart_home.py --port 8810
然后打开 http://127.0.0.1:8810

环境变量：
- TYPESAFE_API_KEY   console.typesafe.ai 获取。不设则页面自动降级为本地模拟引擎。
- STEPFUN_API_KEY    platform.stepfun.com 获取。不设则用文件内 DEFAULT_STEPFUN_KEY。
- STEPFUN_ASR_MODEL  默认 stepaudio-2.5-asr（实测比 stepaudio-3-asr-max 快约 0.1s）。
- STEPFUN_CHAT_MODEL 默认 step-1o-turbo-vision（无推理开销，拆指令最快）。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML_PATH = Path(__file__).resolve().parent / "smart_home_playground.html"

JEV_HOST = "api.typesafe.ai"
JEV_PATH = "/v1/systemone"
STEP_HOST = "api.stepfun.com"
ASR_PATH = "/v1/audio/asr/sse"
CHAT_PATH = "/v1/chat/completions"

stepfun_key = os.environ.get("STEPFUN_API_KEY", "")  # platform.stepfun.com 获取，语音/拆分/问答需要
jev_key = os.environ.get("TYPESAFE_API_KEY", "")
# 与官方 SDK 同名约定：指向自建/代理上游（默认官方端点），用于联调与离线测试
jev_base = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/")
jev_model = os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest")
asr_model = os.environ.get("STEPFUN_ASR_MODEL", "stepaudio-2.5-asr")
chat_model = os.environ.get("STEPFUN_CHAT_MODEL", "step-1o-turbo-vision")        # 拆指令：求快
answer_model = os.environ.get("STEPFUN_ANSWER_MODEL", "step-3.5-flash")          # 知识问答：求准
compare_model = os.environ.get("STEPFUN_COMPARE_MODEL", "step-5-preview")        # 传统 LLM 对比场景

_SSL = ssl.create_default_context()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 简短日志：方法 路径 状态 耗时
        print(f"[{time.strftime('%H:%M:%S')}] {self.command} {self.path}")

    # ---------- 基础设施 ----------

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    # ---------- 路由 ----------

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html = HTML_PATH.read_bytes()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/api/health":
            self._send_json({
                "jev": bool(jev_key),
                "jev_model": jev_model,
                "asr": bool(stepfun_key),
                "chat": bool(stepfun_key),
                "asr_model": asr_model,
                "chat_model": chat_model,
                "answer_model": answer_model,
                "compare_model": compare_model,
            })
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path == "/api/jev":
            self._proxy_jev()
        elif self.path == "/api/asr":
            self._proxy_asr()
        elif self.path == "/api/chat":
            self._proxy_chat()
        else:
            self._send_json({"error": "not found"}, 404)

    # ---------- /api/jev：Jev systemone 单次调用 ----------

    def _proxy_jev(self) -> None:
        payload = self._read_json_body()
        if not jev_key:
            self._send_json({"ok": False, "status": 0,
                             "error": "未设置 TYPESAFE_API_KEY，服务端以模拟模式运行"}, 503)
            return
        if jev_base.startswith(("http://127.0.0.1:", "http://localhost:")):
            payload["model"] = jev_model
        body = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(
            f"{jev_base}{JEV_PATH}", data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {jev_key}",
                "User-Agent": "jev-cookbook-smart-home/1.0",
            })
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            raw = e.read()
            status = e.code
        except Exception as e:  # 连接类错误
            self._send_json({"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}"}, 502)
            return
        upstream_ms = round((time.monotonic() - t0) * 1000)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode(errors="replace")[:2000]}
        self._send_json({"ok": 200 <= status < 300, "status": status,
                         "upstream_ms": upstream_ms, "body": parsed})

    # ---------- /api/asr：阶跃星辰 ASR SSE 透传 ----------

    def _proxy_asr(self) -> None:
        payload = self._read_json_body()
        audio_b64 = payload.get("audio_b64") or ""
        if not audio_b64:
            self._send_json({"error": "audio_b64 缺失"}, 400)
            return
        fmt = payload.get("format") or {"type": "pcm", "codec": "pcm_s16le",
                                        "rate": 16000, "bits": 16, "channel": 1}
        transcription = {"model": asr_model, "enable_itn": True}
        # language 传 null 会被上游 400；整个字段省略 = 自动检测中英文
        if payload.get("language"):
            transcription["language"] = payload["language"]
        if payload.get("hotwords"):
            transcription["hotwords"] = payload["hotwords"]
        upstream = {"audio": {"data": audio_b64, "input": {"transcription": transcription, "format": fmt}}}
        data = json.dumps(upstream).encode()

        try:
            conn = http.client.HTTPSConnection(STEP_HOST, timeout=60, context=_SSL)
            conn.request("POST", ASR_PATH, body=data, headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {stepfun_key}",
            })
            resp = conn.getresponse()
        except Exception as e:
            self._send_json({"error": f"ASR 上游连接失败: {type(e).__name__}: {e}"}, 502)
            return

        if resp.status != 200:
            err = resp.read().decode(errors="replace")[:500]
            self._send_json({"error": f"ASR 上游 HTTP {resp.status}", "detail": err}, 502)
            return

        # SSE 逐块透传给浏览器，前端边收边把增量文字填进输入框
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                chunk = resp.read(512)
                if not chunk:
                    break
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass  # 浏览器提前断开（如用户取消）
        finally:
            conn.close()

    # ---------- /api/chat：复合指令拆分 / 常识问答 ----------

    def _proxy_chat(self) -> None:
        payload = self._read_json_body()
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            self._send_json({"error": "messages 缺失"}, 400)
            return
        purpose_model = {"answer": answer_model, "compare": compare_model}
        body = json.dumps({
            "model": purpose_model.get(payload.get("purpose"), chat_model),
            "messages": messages,
            "temperature": payload.get("temperature", 0),
            "max_tokens": payload.get("max_tokens", 500),
        }).encode()
        req = urllib.request.Request(
            f"https://{STEP_HOST}{CHAT_PATH}", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {stepfun_key}"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                parsed = json.loads(resp.read())
                status = resp.status
        except urllib.error.HTTPError as e:
            self._send_json({"ok": False, "status": e.code,
                             "error": e.read().decode(errors="replace")[:500]}, 200)
            return
        except Exception as e:
            self._send_json({"ok": False, "status": 0, "error": f"{type(e).__name__}: {e}"}, 502)
            return
        content = ""
        try:
            content = parsed["choices"][0]["message"].get("content") or ""
            if not content:
                # 推理型模型可能把正文放在 reasoning_content
                content = parsed["choices"][0]["message"].get("reasoning_content") or ""
        except (KeyError, IndexError, TypeError):
            pass
        self._send_json({"ok": 200 <= status < 300, "status": status, "content": content,
                         "upstream_ms": round((time.monotonic() - t0) * 1000),
                         "model": purpose_model.get(payload.get("purpose"), chat_model),
                         "usage": parsed.get("usage")})


def make_selfsigned_cert(cert_dir: Path) -> tuple[Path, Path]:
    """openssl 生成一年期自签证书，供局域网 https（手机测麦克风）使用。"""
    cert_dir.mkdir(exist_ok=True)
    cert, key = cert_dir / "cert.pem", cert_dir / "key.pem"
    if not (cert.exists() and key.exists()):
        import subprocess
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert), "-days", "365", "-nodes",
            "-subj", "/CN=smart-home-demo",
        ], check=True, capture_output=True)
    return cert, key


def main() -> None:
    parser = argparse.ArgumentParser(description="智能家居 3D 演练场本地服务")
    parser.add_argument("--port", type=int, default=8810)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--tls", action="store_true",
                        help="启用 HTTPS（openssl 自签证书）。局域网设备测语音输入时必须用，"
                             "浏览器里对证书警告点「高级 → 继续前往」即可")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    scheme = "http"
    if args.tls:
        cert, key = make_selfsigned_cert(Path(__file__).resolve().parent / "certs")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    host_disp = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = f"{scheme}://{host_disp}:{args.port}"
    print(f"智能家居演练场: {url}")
    if args.host == "0.0.0.0":
        import subprocess as _sp
        try:
            lan = _sp.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True).stdout.strip() \
                or _sp.run(["ipconfig", "getifaddr", "en1"], capture_output=True, text=True).stdout.strip()
        except Exception:
            lan = ""
        if lan:
            print(f"  局域网: {scheme}://{lan}:{args.port}")
    print(f"  Jev   真实调用: {'✅ 已配置 TYPESAFE_API_KEY' if jev_key else '⚠️ 未配置 → 页面自动用本地模拟引擎'}")
    print(f"  ASR   语音识别: {'✅ ' + asr_model if stepfun_key else '❌ 未配置 STEPFUN_API_KEY'}")
    print(f"  Chat  拆分/问答: {'✅ ' + chat_model if stepfun_key else '❌ 未配置 STEPFUN_API_KEY'}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
