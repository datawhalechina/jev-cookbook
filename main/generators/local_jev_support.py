"""Add optional local-service setup without replacing teaching examples or prior outputs."""
from pathlib import Path
import nbformat

LOCAL_SETUP = '''import os
import runpy
from pathlib import Path

if os.environ.get("JEV_RUN_MODE") != "offline":
    for _root in [Path.cwd(), *Path.cwd().parents]:
        _main = _root if (_root / "LocalJev" / "use_local_jev.py").is_file() else _root / "main"
        if (_main / "LocalJev" / "use_local_jev.py").is_file() and (_main / ".local-jev.json").is_file():
            runpy.run_path(str(_main / "LocalJev" / "use_local_jev.py"))
            break'''


def connect_local_service(nb):
    changed = False
    for cell in nb.cells:
        if cell.get("id") == "local-jev-setup" and cell.source != LOCAL_SETUP:
            cell.source = LOCAL_SETUP
            changed = True
        if cell.get("id") == "local-jev-note":
            source = cell.source.replace("main/LocalJev.ipynb", "main/LocalJev/LocalJev.ipynb")
            if source != cell.source:
                cell.source = source
                changed = True
    for cell in nb.cells:
        if cell.cell_type == "code" and cell.source.lstrip().startswith("%pip install") and "typesafe-sdk" in cell.source:
            cell.source = '''import importlib.util
if importlib.util.find_spec("typesafe_sdk") is None:
    %pip install -q "typesafe-sdk>=0.7,<0.8"
else:
    print("TypeSafe SDK 已安装，复用当前环境。")'''
            changed = True
    for i, cell in enumerate(nb.cells):
        if cell.cell_type == "code" and "TypeSafeClient(" in cell.source:
            if not any(c.get("id") == "local-jev-setup" for c in nb.cells):
                nb.cells[i:i] = [nbformat.v4.new_markdown_cell(
                    "### 可选：本地模型连接\n\n先运行仓库内 main/LocalJev/LocalJev.ipynb 到发布连接配置。"
                    "本格检测到配置后验证服务并使用本地模型，无需远程 API key；服务不可用直接报错。"
                    "没有本地配置时继续原有流程，JEV_RUN_MODE=offline 可强制离线。"
                    "LLaMA／LFM 的实验适配概率不等同于 Jev 的校准概率。", id="local-jev-note"),
                    nbformat.v4.new_code_cell(LOCAL_SETUP, id="local-jev-setup")]
                changed = True
            break
    for cell in nb.cells:
        if cell.cell_type == "code" and "TypeSafeClient(" in cell.source:
            source = cell.source.replace('model="jev-latest"',
                                         'model=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest")')
            if source != cell.source:
                cell.source = source
                changed = True
    return changed


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    count = 0
    for folder in root.iterdir():
        if folder.is_dir() and folder.name[:2] in {"01", "02", "03", "04"}:
            for path in folder.glob("*.ipynb"):
                nb = nbformat.read(path, as_version=4)
                if connect_local_service(nb):
                    nbformat.validate(nb)
                    nbformat.write(nb, path)
                    count += 1
    print(f"已连接 {count} 本 SDK Notebook；保留现有教学代码和其他单元格输出。")
