"""Run in each Notebook kernel to activate the ready local service."""
import json
import os
from pathlib import Path


def activate(path=None):
    import requests
    path = Path(path) if path else Path(__file__).resolve().parent.parent / ".local-jev.json"
    if not path.is_file():
        raise RuntimeError("尚无本地服务连接配置。请先运行 LocalJev.ipynb 到“发布连接配置”。")
    config = json.loads(path.read_text(encoding="utf-8"))
    from urllib.parse import urlparse
    url = urlparse(config["base_url"])
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"} or url.path:
        raise ValueError("本地连接配置必须指向本机 HTTP 根地址。")
    try:
        response = requests.get(config["base_url"] + "/health",
                                headers={"Authorization": "Bearer " + config["api_key"]}, timeout=3)
        response.raise_for_status()
        health = response.json()
        if health.get("status") != "ok" or config["model"] not in health.get("loaded", []):
            raise RuntimeError("所选模型尚未就绪。")
    except (requests.RequestException, ValueError) as error:
        raise RuntimeError("本地服务不可用。请检查 LocalJev 的服务状态与日志，或删除 .local-jev.json 恢复远程配置。") from error
    os.environ.update(TYPESAFE_BASE_URL=config["base_url"], TYPESAFE_API_KEY=config["api_key"],
                      TYPESAFE_DEFAULT_MODEL=config["model"], JEV_RUN_MODE="live")
    print("本次调用本地模型：", config["model"], "｜", config["base_url"], "｜", health.get("device"))
    return config


if __name__ in {"__main__", "<run_path>"}:
    activate()
