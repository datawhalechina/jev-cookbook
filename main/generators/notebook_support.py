"""共用生成器组件；生成后的每本 Notebook 均包含完整代码，可独立运行。"""
from __future__ import annotations

import hashlib
import json
import math
import textwrap
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = "https://docs.typesafe.ai/"
CHINESE = "https://datawhalechina.github.io/jev-cookbook/"

# 章节文件名：编号与官方文档（docs.typesafe.ai/llms.txt）导航顺序一致；
# 官方文档中没有对应章节的笔记本不编号（如 Pi_Jev、DSH_Jev）。
FILENAMES = {  # 五章文件夹结构：值含相对路径（不含 .ipynb）
    "introduction": "01_认识Jev/01_认识Jev",
    "system_one": "02_核心概念/01_SystemOne",
    "state": "02_核心概念/02_状态",
    "primitives": "02_核心概念/03_原语",
    "confidence": "02_核心概念/04_置信度",
    "build_with_typesafe": "02_核心概念/05_应用构建",
    "patterns": "03_架构模式/01_架构模式",
}
PENDING_STATUS = "**验证状态：真实 API 待验收。** 本文件尚未执行真实 API；离线检查仅验证代码路径。"


def sources(path):
    return f"[官方原文]({OFFICIAL}{path}) · [中文参考]({CHINESE}{path}/)"


class Chapter:
    def __init__(self, slug, title, path, objective, outline):
        self.slug = slug
        self.path = path
        self.nb = nbf.from_dict(json.loads((Path(__file__).resolve().parent / "templates/tutorial.ipynb").read_text()))
        self.nb.cells = []
        self.md(f"""# {title}

针对官方文档对应章节的可运行实验笔记，全部实验使用**中文场景与中文提示词**。
面向会基础 Python、刚接触 AI Agent 的读者。

**学习目标：** {objective}

{sources(path)}。本章以中文重述理论、复刻对应场景；扩展实验会单独说明。
所有客户、订单及消息均为教学合成数据。

## 笔记本结构

| 章节 | 内容 |
|---|---|
| 0. 准备 | 安装库、配置客户端、连通性测试与离线示例 |
{outline}
| 练习与小结 | 练习、自查、总结与本次执行记录 |

实验按**原理 → 理论根基 → 定义数据 → 定义问题 → 调用 → 解读结果**展开，每个代码单元格只做一件事。

## 运行要求

- Python ≥ 3.10；本章使用 `typesafe-sdk==0.7.0`。
- 真实实验需要启动进程的 `TYPESAFE_API_KEY` 环境变量，密钥不要写进 Notebook。

在本仓库 `main/` 目录创建环境并打开本文件：

```bash
./setup_env.sh
.venv/bin/python -m pip install -r requirements.txt -c generators/constraints-foundations.txt
.venv/bin/jupyter lab {FILENAMES.get(slug, slug + '_experiments')}.ipynb
```

产品名、字段名和选项 key 保持英文，state、提示词与解说使用中文。
默认 `JEV_RUN_MODE=auto`（在线优先）：检测到 `TYPESAFE_API_KEY` 即调用真实模型；未检测到才回退离线替身，每格输出都标注来源。
正式验收设置 `JEV_RUN_MODE=live`（无密钥直接报错、不回退）；强制纯离线学习设置 `JEV_RUN_MODE=offline`。

{PENDING_STATUS}
批量执行、离线预览和验收记录见本目录 `MAINTENANCE.md`。
""")

    def md(self, text):
        self.nb.cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(text).strip()))

    def code(self, text, tags=None):
        source = textwrap.dedent(text).strip()
        if len(source.splitlines()) > 30:
            raise ValueError(f"{self.slug}: 代码格超过 30 行：{source[:90]}")
        self.nb.cells.append(nbf.v4.new_code_cell(source, metadata={"tags": tags or []}))

    def step(self, explanation, source, observation=None):
        self.md(explanation)
        self.code(source)
        if observation:
            self.md(f"**观察与理解：** {observation}")

    def prepare(self):
        self.md("## 0. 准备\n\n本节可折叠阅读，但独立运行时不能跳过。客户端、辅助对象和示例数据都在本文件中定义。")
        self.step("### 0.1 安装依赖\n\n推荐先运行 `setup_env.sh`。只有当前内核缺少 SDK 时，本格才安装依赖。",
                  '''import importlib.util
if importlib.util.find_spec("typesafe_sdk") is None:
    %pip install -q typesafe-sdk==0.7.0''',
                  "安装包的名字是 typesafe-sdk，Python 导入名是 typesafe_sdk。安装成功不代表 API 已连通。")
        self.step("### 0.2 导入与配置\n\n默认模型固定版本，便于记录实验条件；可通过环境变量更换。不要从 Notebook 输入密钥。",
                  '''import os
import json
import time
import math
from datetime import datetime, timezone
from importlib.metadata import version
from typesafe_sdk import (
    Choice, Score, Noul, NoulCriteria, TypeSafeClient,
    TypeSafeAuthenticationError, RetryPolicy,
)

MODEL = os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-1.13.0")
RUN_MODE = os.environ.get("JEV_RUN_MODE", "auto")
API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
if RUN_MODE not in {"live", "offline", "auto"}:
    raise ValueError("JEV_RUN_MODE 只能是 live、offline 或 auto")
if RUN_MODE == "live" and not API_KEY:
    raise RuntimeError("JEV_RUN_MODE=live 需要真实密钥：请配置 TYPESAFE_API_KEY；仅学习可改用默认 auto（无密钥自动离线）")
client = None if (RUN_MODE == "offline" or not API_KEY) else TypeSafeClient(
    api_key=API_KEY, model=MODEL, timeout=30, retry=RetryPolicy(max_retries=0))
mode_note = ("在线优先：本次会话调用真实模型" if client is not None else
             ("强制离线（JEV_RUN_MODE=offline）" if RUN_MODE == "offline" else
              "未检测到 TYPESAFE_API_KEY → 离线替身；配置密钥后重跑本格即切在线实测"))
print("模式：", RUN_MODE, "｜", mode_note, "｜SDK：", version("typesafe-sdk"), "｜模型配置：", MODEL)''')
        self.md("默认在线优先：有密钥即走真实模型，每次调用的来源（live/offline）都记录在 `CALL_LOG` 与输出中；`auto` 仅在未配置密钥或 401 时回退离线替身。正式验收设 `JEV_RUN_MODE=live`（禁用回退、不自动重试，请求数量有界）。")
        self.step("### 0.3 连通性测试\n\n用一条 Noul 检查真实响应能否返回。网络、限流与输入错误直接抛出，不伪装成不确定判断。",
                  '''PING = {"source": "offline", "reason": "未发起连通性请求（无 client：未配置密钥或强制离线）"}
if client is not None:
    try:
        ping = client.system_one("你好", {"greeting": Noul(
            instructions="这段文字是否在打招呼？")})
        PING = {"source": "live", "model": ping.model,
                "input_tokens": ping.usage.input_tokens,
                "output_tokens": ping.usage.output_tokens}
    except TypeSafeAuthenticationError:
        if RUN_MODE == "live":
            raise
        client.close()
        client = None
        PING["reason"] = "401 鉴权失败，仅教学模式允许回退"
print(json.dumps(PING, ensure_ascii=False))''',
                  "source=live 表示这一次连通性请求成功；仍要查看后续实验记录，不能用它代替整章验收。")
        self.step("### 0.4 离线替身\n\n沿用参考模板的 `_FakeAnswer` 与 `_FakeResponse` 访问方式。人工数字仅用来检验读取字段和代码分支。",
                  '''class _FakeAnswer:
    def __init__(self, type_, **values):
        self.type = type_
        for name, value in values.items():
            setattr(self, name, value)


class _FakeResponse:
    def __init__(self, answers):
        self.answers = answers
        self.choices = {k: v for k, v in answers.items() if v.type == "choice"}
        self.scores = {k: v for k, v in answers.items() if v.type == "score"}
        self.nouls = {k: v for k, v in answers.items() if v.type == "noul"}
        self.model = "人工示例，非模型预测"
        self.usage = _FakeAnswer("usage", input_tokens=0, output_tokens=0)''')
        self.md("人工 Score 由概率计算期望，避免模板中的分数与分布不一致。人工 confidence 只是指定的演示字段，不是在复现服务端的计算公式。")
        self.step("定义两种示例答案构造器；Noul 可直接用 `_FakeAnswer`。所有具体答案集中在下一节。",
                  '''def fake_choice(probabilities, confidence):
    return _FakeAnswer("choice", choice=max(probabilities, key=probabilities.get),
                       probabilities=probabilities, confidence=confidence)


def fake_score(probabilities, legend, confidence):
    return _FakeAnswer("score", score=sum(k * p for k, p in probabilities.items()),
                       probabilities=probabilities, legend=dict(enumerate(legend)),
                       confidence=confidence)''',
                  "例如概率 {0:0.05, 1:0.26, 2:0.69} 对应 1.64。不能把另一个数与该分布配在一起。")
        self.step("### 0.5 统一调用入口\n\n每次调用记录来源、模型与 token 用量。离线耗时记为 None，不把本地字典访问当成模型速度。",
                  '''CALL_LOG = []


class TS:
    def call(self, state, questions, offline_answers, label):
        start = time.perf_counter()
        source = "live"
        if client is None:
            response, source = _FakeResponse(offline_answers), "offline"
        else:
            try:
                response = client.system_one(state, questions)
            except TypeSafeAuthenticationError:
                if RUN_MODE != "auto":
                    raise
                response, source = _FakeResponse(offline_answers), "offline"
        validate_response(response, questions)
        CALL_LOG.append({"case": label, "source": source, "model": response.model,
                         "seconds": time.perf_counter() - start if source == "live" else None,
                         "input_tokens": response.usage.input_tokens,
                         "output_tokens": response.usage.output_tokens})
        if source == "offline":
            print("离线替身（未调用真实模型）：", label, "；人工答案，仅演示代码路径")
        return response


ts = TS()''')
        self.md("与参考模板相比，这里增加了严格 live 模式和逐次记录。保留 401 教学回退，但超时、429 等错误继续失败，防止验收被回退掩盖。")
        self.step("校验结构与数值契约；只断言接口应满足的性质，不断言真实模型必须预测某个标签。",
                  '''def validate_response(response, questions):
    if set(response.answers) != set(questions):
        raise ValueError("答案 ID 与问题 ID 不一致")
    for key, question in questions.items():
        answer = response.answers[key]
        if isinstance(question, Noul):
            if not 0 <= answer.noul <= 1:
                raise ValueError("Noul 超出概率范围")
            continue
        probabilities = answer.probabilities
        if not all(math.isfinite(p) and 0 <= p <= 1 for p in probabilities.values()):
            raise ValueError("概率值无效")
        if not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02):
            raise ValueError("概率之和偏离 1")
        if not 0 <= answer.confidence <= 1:
            raise ValueError("confidence 超出范围")
        if isinstance(question, Choice):
            if set(probabilities) != set(question.criteria):
                raise ValueError("Choice 选项集合不一致")
            if answer.choice not in probabilities:
                raise ValueError("Choice 标签不在选项中")
        else:
            expected = sum(int(k) * p for k, p in probabilities.items())
            if not math.isclose(answer.score, expected, abs_tol=0.03):
                raise ValueError("Score 与概率加权期望不一致")''',
                  "容差用于服务端数值舍入。结构检查通过只说明响应可读取，不证明语义判断正确。")
        self.step("显示结果时统一列出类型、概率和置信度；Noul 不额外制造 confidence 字段。",
                  '''def show(response):
    rows = {}
    for key, answer in response.answers.items():
        rows[key] = {name: getattr(answer, name) for name in
                     ("type", "choice", "score", "noul", "confidence", "probabilities", "legend")
                     if hasattr(answer, name)}
    print(json.dumps(rows, ensure_ascii=False, indent=2))''')
        self.md("### 0.6 本章离线示例数据\n\n以下数值全部人工构造，专门测试分支；不来自 Jev，也不能用于估计中文准确率或校准情况。正式 live 运行不会使用这些答案。")

    def finish(self, recap, exercise, answer, readings=""):
        self.md(f"## 练习与自查\n\n{exercise}")
        self.md(f"<details><summary>参考思路：先完成练习再展开</summary>\n\n{answer}\n\n</details>")
        self.md(f"## 小结\n\n{recap}\n\n{readings}\n\n离线运行只说明教材代码能执行。正式交付必须实际运行 live，并阅读每条输出；缺失的分支应记为未观察到。")
        self.step("## 本次执行记录\n\n先关闭连接，再生成记录。下面的 JSON 由实际运行计算，批量执行器会据此检查来源。",
                  '''if client is not None:
    client.close()''')
        self.md("本章拿几句话试了试真实模型，看它给的概率怎么反应——这只说明模型对这类输入的反应方式，不构成准确率评测。特别提醒：如果哪句答得合心意就专门挑出来当考题，再拿这些挑过的句子去算准确率，数字必然虚高。输出里的耗时也只是当时网络的快照，每次都会不一样。")
        self.code('''AUDIT = {
    "kind": "jev_execution_audit",
    "executed_at_utc": datetime.now(timezone.utc).isoformat(),
    "sdk": version("typesafe-sdk"), "requested_model": MODEL,
    "mode": RUN_MODE, "ping": PING,
    "real_calls": sum(x["source"] == "live" for x in CALL_LOG),
    "offline_calls": sum(x["source"] == "offline" for x in CALL_LOG),
    "cases": CALL_LOG,
    "coverage": globals().get("COVERAGE", {}),
    "validation_status": "live_executed_requires_review" if (
        PING["source"] == "live" and CALL_LOG
        and all(x["source"] == "live" for x in CALL_LOG)
    ) else "offline_only_not_model_evidence",
}
print(json.dumps(AUDIT, ensure_ascii=False, indent=2))''', tags=["execution-audit"])
        self.md("读完输出后，在本仓库 `main/MAINTENANCE.md` 的验收表中记录日期、真实模型、观察到的分支和偏离预期之处。不要把人工演示数值抄进实测记录。")

    def save(self):
        # 合并相邻说明，保留完整叙事，并将单元格密度调整到约 3:2。
        code_count = sum(cell.cell_type == "code" for cell in self.nb.cells)
        target_md_count = math.ceil(code_count * 1.5)
        while sum(cell.cell_type == "markdown" for cell in self.nb.cells) > target_md_count:
            for i in range(len(self.nb.cells) - 1):
                first, second = self.nb.cells[i:i + 2]
                if first.cell_type == second.cell_type == "markdown":
                    first.source += "\n\n" + second.source
                    del self.nb.cells[i + 1]
                    break
            else:
                break
        for i, cell in enumerate(self.nb.cells):
            cell.id = hashlib.sha256(f"{self.slug}:{i}:{cell.source}".encode()).hexdigest()[:12]
        self.nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
        self.nb.metadata["jev_cookbook"] = {"chapter": self.slug, "source_path": self.path,
                                          "live_validation": "pending"}
        from local_jev_support import connect_local_service
        connect_local_service(self.nb)
        nbf.validate(self.nb)
        path = ROOT / f"{FILENAMES.get(self.slug, self.slug + '_experiments')}.ipynb"
        nbf.write(self.nb, path)
        return path
