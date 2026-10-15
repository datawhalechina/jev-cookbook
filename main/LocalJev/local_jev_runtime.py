"""Local model preparation and service lifecycle; importing this module has no side effects."""
import importlib.util
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path


MODELS = {
    "convaiinnovations/laya-multilingual": {"backend": "laya", "ram_gib": 4, "vram_gib": 2},
    "convaiinnovations/laya": {"backend": "laya", "ram_gib": 4, "vram_gib": 2},
    "LiquidAI/d1-omni-600M": {"backend": "d1", "ram_gib": 6, "vram_gib": 3, "transformers": "5.15"},
    "LiquidAI/d1-3B": {"backend": "d1", "ram_gib": 16, "vram_gib": 10, "transformers": "5.14"},
    "LiquidAI/LFM2.5-350M": {"backend": "causal", "ram_gib": 4, "vram_gib": 2, "transformers": "5.0"},
    "LiquidAI/LFM2.5-2.6B": {"backend": "causal", "ram_gib": 14, "vram_gib": 8, "transformers": "5.0"},
    "meta-llama/Llama-3.2-1B-Instruct": {"backend": "causal", "ram_gib": 8, "vram_gib": 4},
    "meta-llama/Llama-3.2-3B-Instruct": {"backend": "causal", "ram_gib": 16, "vram_gib": 10},
    "meta-llama/Llama-3.1-8B-Instruct": {"backend": "causal", "ram_gib": 40, "vram_gib": 24},
}


def model_spec(model_id):
    if model_id not in MODELS:
        raise ValueError(f"未配置模型 {model_id}。请先用硬件评估 Prompt 核对架构和加载方式，再加入 MODELS。")
    return MODELS[model_id]


def model_paths(model_id, main_dir):
    """Portable cache, with an explicit override or reuse of a previous local model."""
    main_dir = Path(main_dir).resolve()
    override = os.environ.get("JEV_MODEL_CACHE")
    cache = Path(override).expanduser() if override else main_dir / ".models"
    if not cache.is_absolute():
        cache = main_dir / cache
    model = cache / model_id.replace("/", "--")
    # Existing users keep their downloaded files; fresh clones have no ignored config.
    config = main_dir / ".local-jev.json"
    if not override and config.is_file():
        try:
            previous = json.loads(config.read_text(encoding="utf-8"))
            old_dir = Path(previous.get("model_dir", ""))
            if previous.get("repo_id") == model_id and old_dir.is_absolute() and old_dir.is_dir():
                model = old_dir
        except (OSError, ValueError, TypeError):
            pass
    return cache, model


def check_dependencies(model_id):
    spec = model_spec(model_id)
    if spec["backend"] != "laya" and not Path(__file__).with_name("local_jev_server.py").is_file():
        raise RuntimeError("当前交付只提供 Laya 服务。D1／LFM／LLaMA 适配暂未随仓库提交；请改用 Laya，或仅在硬件评估 Prompt 中填写这些模型。")
    packages = {"torch": "torch", "transformers": "transformers", "safetensors": "safetensors",
                "requests": "requests", "huggingface_hub": "huggingface-hub", "psutil": "psutil",
                "fastapi": "fastapi", "uvicorn": "uvicorn", "typesafe_sdk": "typesafe-sdk"}
    if spec["backend"] == "laya":
        packages.update({"laya": "laya", "multipart": "python-multipart"})
    if spec["backend"] == "d1":
        packages.update({"torchvision": "torchvision", "PIL": "pillow", "soundfile": "soundfile"})
    missing = [package for module, package in packages.items() if importlib.util.find_spec(module) is None]
    if missing:
        raise RuntimeError("缺少依赖，请在当前内核运行：%pip install " + " ".join(missing))
    if "transformers" in spec:
        from importlib.metadata import version
        from packaging.version import Version
        if Version(version("transformers")) < Version(spec["transformers"]):
            raise RuntimeError(f"该模型需要 transformers>={spec['transformers']}。建议新建内核安装，避免影响现有 Laya 环境。")


def hardware_report():
    import psutil
    import torch
    memory = psutil.virtual_memory()
    report = {"os": platform.platform(), "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"), "cpu_threads": os.cpu_count(),
              "ram_total_gib": round(memory.total / 2**30, 2),
              "ram_available_gib": round(memory.available / 2**30, 2),
              "python": sys.version.split()[0], "torch": torch.__version__,
              "torch_cuda_build": torch.version.cuda, "cuda_available": torch.cuda.is_available()}
    report["device"] = ("cuda" if report["cuda_available"] else "mps" if
                        hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu")
    if report["cuda_available"]:
        report["gpu"] = torch.cuda.get_device_name(0)
        free, total = torch.cuda.mem_get_info(0)
        report.update(vram_free_gib=round(free / 2**30, 2), vram_total_gib=round(total / 2**30, 2))
    else:
        try:
            detected = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                                       "--format=csv,noheader"], capture_output=True, text=True, timeout=10,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if detected.returncode == 0:
                report["nvidia_smi"] = detected.stdout.strip()
                report["gpu_note"] = "检测到 NVIDIA 显卡，但当前 PyTorch 无法使用 CUDA；本次使用 CPU。"
        except (OSError, subprocess.TimeoutExpired):
            pass
    return report


def model_problems(model_dir, backend):
    """Check local artifacts, including truncated safetensors, without loading tensors."""
    from safetensors import safe_open
    root = Path(model_dir)
    required = (["rl_agent_config.json", "model.safetensors", "encoder/config.json",
                 "tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json"] if backend == "laya"
                else ["config.json", "tokenizer.json", "tokenizer_config.json"])
    if backend == "d1":
        required.append("modeling_d1.py")
    if backend != "laya":
        index = root / "model.safetensors.index.json"
        if index.is_file():
            try:
                required.extend(set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values()))
            except (ValueError, KeyError):
                required.append("model.safetensors.index.json")
        else:
            required.append("model.safetensors")
    problems = []
    for name in required:
        path = root / name
        try:
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError("缺失或空文件")
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            if path.suffix == ".safetensors":
                with safe_open(str(path), framework="pt") as weights:
                    if not list(weights.keys()):
                        raise ValueError("无权重")
        except Exception as error:
            problems.append(f"{name}: {error}")
    # For D1, local custom code imports helper modules named in config / source.
    if backend == "d1" and (root / "config.json").is_file():
        import ast
        for code in root.glob("*.py"):
            try:
                tree = ast.parse(code.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.level and node.module:
                        helper = root / (node.module.split(".")[0] + ".py")
                        if not helper.is_file():
                            problems.append(f"{helper.name}: 缺失")
            except (SyntaxError, OSError) as error:
                problems.append(f"{code.name}: {error}")
    return problems


def ensure_model(model_id, model_dir):
    from huggingface_hub import snapshot_download
    backend = model_spec(model_id)["backend"]
    problems = model_problems(model_dir, backend)
    if not problems:
        print("本地模型完整，跳过下载：", model_dir)
        return Path(model_dir)
    print("需要补齐模型文件：\n" + "\n".join(problems))
    # Missing files resume normally; a file present but invalid must be refreshed.
    corrupt = any((Path(model_dir) / item.split(":", 1)[0]).is_file() for item in problems)
    snapshot_download(repo_id=model_id, local_dir=str(model_dir), force_download=corrupt,
                      allow_patterns=["*.json", "*.safetensors", "*.py", "*.model", "*.txt", "*.jinja"])
    remaining = model_problems(model_dir, backend)
    if remaining:
        raise RuntimeError("模型下载后仍不完整：\n" + "\n".join(remaining))
    print("模型已准备好：", model_dir)
    return Path(model_dir)


def read_health(base_url, api_key):
    import requests
    response = requests.get(base_url + "/health", headers={"Authorization": "Bearer " + api_key}, timeout=3)
    response.raise_for_status()
    return response.json()


def start_service(model_id, model_dir, device, port, config_path, log_path, process=None):
    """Reuse a healthy matching service; never kill an unrelated process."""
    import requests
    spec = model_spec(model_id)
    model_dir = Path(model_dir).resolve()
    config_path, log_path = Path(config_path), Path(log_path)
    base_url = f"http://127.0.0.1:{port}"
    previous = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    model_name = "local-" + model_id.rsplit("/", 1)[-1].lower() if spec["backend"] == "laya" else model_id
    config = {"base_url": base_url, "model": model_name, "repo_id": model_id, "model_dir": str(model_dir),
              "device": device, "backend": spec["backend"]}
    with socket.socket() as probe:
        occupied = probe.connect_ex(("127.0.0.1", port)) == 0
    if occupied:
        if all(previous.get(k) == v for k, v in config.items()):
            try:
                health = read_health(base_url, previous["api_key"])
                if health.get("status") == "ok" and model_name in health.get("loaded", []):
                    print("复用已运行的本地服务：", base_url)
                    return process, previous
            except (requests.RequestException, KeyError, ValueError):
                pass
        raise RuntimeError(f"端口 {port} 已被占用，且不是当前模型的就绪服务。请停止旧服务或更换 PORT。")
    if process is not None and process.poll() is None:
        raise RuntimeError("上一次服务仍在加载，请先重新检查状态，或停止后再修改模型配置。")
    problems = model_problems(model_dir, spec["backend"])
    if problems:
        raise RuntimeError("请先执行准备模型：\n" + "\n".join(problems))
    config["api_key"] = secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", USE_TF="0",
               PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    if spec["backend"] == "laya":
        env.update(LAYA_HOST="127.0.0.1", LAYA_PORT=str(port), LAYA_DEVICE=device,
                   LAYA_EXTRA_MODELS=json.dumps({model_name: str(model_dir)}), LAYA_MODELS=model_name,
                   LAYA_DEFAULT_MODEL=model_name, LAYA_PRELOAD="1", LAYA_JEV_STRICT="1",
                   LAYA_API_KEY=config["api_key"])
        command = [sys.executable, "-m", "laya.serve"]
    else:
        env["LOCAL_JEV_CONFIG"] = json.dumps(config)
        command = [sys.executable, str(Path(__file__).with_name("local_jev_server.py"))]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n--- Starting {model_id} on {device} ---\n")
        log.flush()
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    config["pid"] = process.pid
    print("服务正在加载，PID：", process.pid, "日志：", log_path)
    return process, config


def wait_service(process, config, timeout=180):
    import requests
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"服务退出，退出码 {process.returncode}；请查看服务日志。")
        try:
            health = read_health(config["base_url"], config["api_key"])
            if health.get("status") == "ok" and config["model"] in health.get("loaded", []):
                return health
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1)
    raise TimeoutError("模型仍未就绪，请查看日志，再重新运行本格；不会自动终止加载进程。")


def publish_connection(config, path):
    """Only publish after readiness, so other kernels cannot silently use a mock."""
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def stop_service(process, config, path):
    if process is None:
        print("本格未持有服务进程。请回到启动服务的内核停止；关闭连接配置可删除 .local-jev.json。")
        return False
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    path = Path(path)
    if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("pid") == process.pid:
        path.unlink()
    print("本 Notebook 启动的服务已停止。")
    return True
