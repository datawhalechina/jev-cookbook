#!/usr/bin/env python3
"""TypeSafe 中文文档 — 静态站点生成器（仅用 Python 标准库）。

用法:
    python3 build.py            # 构建站点到 dist/
    python3 build.py --check    # 构建并校验内链/资源
之后:
    cd dist && python3 -m http.server 8000
"""
import html
import json
import os
import posixpath
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
ORIG = os.path.join(ROOT, "_orig")
DIST = os.path.join(ROOT, "dist")
ASSETS = os.path.join(ROOT, "assets")

SITE_TITLE = "TypeSafe 中文文档"
ORIGIN_URL = "https://docs.typesafe.ai"

# ---------------------------------------------------------------- 页面集合

def list_pages():
    pages = []
    for dirpath, _dirnames, filenames in os.walk(CONTENT):
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, CONTENT)[:-3].replace(os.sep, "/")
            pages.append(rel)
    pages.sort()
    return pages

ROOT_PAGE = "introduction"  # 站点首页同时生成到 /index.html

# ---------------------------------------------------------------- 导航（镜像原站结构）

COOKBOOKS = [
    ("cookbooks/consistency_noul_cookbook", "自一致性：Noul"),
    ("cookbooks/consistency_choice_cookbook", "自一致性：Choice"),
    ("cookbooks/parallel_questions", "并行提问"),
    ("cookbooks/rerank_typesafe", "重排序（Re-ranking）"),
    ("cookbooks/semantic_find", "逐行语义搜索"),
    ("cookbooks/autoformat", "结构恢复"),
    ("cookbooks/function_calling", "函数调用"),
    ("cookbooks/skill_suggestion", "技能推荐"),
    ("cookbooks/entity_alignment", "知识图谱实体对齐"),
    ("cookbooks/classifying_rag_passages", "RAG 段落分类"),
    ("cookbooks/citation_check", "引用核查"),
    ("cookbooks/llm_guardrails", "LLM 防护栏"),
    ("cookbooks/sde_cascade", "SDE 级联"),
    ("cookbooks/date_extraction_cookbook", "日期抽取"),
    ("cookbooks/pre_parsed_value_extraction_cookbook", "预解析值抽取"),
    ("cookbooks/hierarchical_classification", "层级分类"),
    ("cookbooks/autoresearch_feature_discovery", "自动研究特征发现"),
    ("cookbooks/classification_using_confidence", "基于置信度的分类"),
]

PY_SDK = [
    ("sdk/python", "TypeSafe Python SDK"),
    ("sdk/python/usage", "用法"),
    ("sdk/python/changelog", "更新日志"),
    ("sdk/python/api", "API 参考"),
    ("sdk/python/api/clients/async", "异步客户端 AsyncTypeSafeClient"),
    ("sdk/python/api/clients/sync", "同步客户端 TypeSafeClient"),
    ("sdk/python/api/types/questions", "类型：Questions（提问）"),
    ("sdk/python/api/types/responses", "类型：Answers 与响应"),
    ("sdk/python/api/types/common", "通用类型"),
    ("sdk/python/api/retries", "重试策略 RetryPolicy"),
    ("sdk/python/api/exceptions", "异常"),
    ("sdk/python/api/constants", "常量"),
]

JS_CLASSES = ["APIConnectionError", "APIError", "APIPromise", "APITimeoutError",
              "APIUserAbortError", "AuthenticationError", "BadRequestError",
              "InternalServerError", "NotFoundError", "PermissionDeniedError",
              "RateLimitError", "TypeSafeClient", "TypeSafeError", "UnprocessableEntityError"]
JS_INTERFACES = ["ChoiceQuestion", "ChoiceResponse", "Logger", "ModelCard", "Models",
                 "NoulQuestion", "NoulResponse", "Questions", "RequestOptions",
                 "RetryPolicy", "ScoreQuestion", "ScoreResponse", "SystemOneRequest",
                 "SystemOneRequestPayload", "SystemOneResult", "TypeSafeClientConfig",
                 "Usage", "WithResponse"]
JS_FUNCTIONS = ["choice", "noul", "score"]
JS_ALIASES = ["ChoiceCriteria", "Description", "EntryType", "EnvVar", "Fetch",
              "JsonValue", "LogLevel", "Question", "ResultFor", "ScoreCriteria",
              "ScoreLegend", "ScoreOf"]
JS_VARS = ["ENV", "LOG_LEVELS", "VERSION"]

JS_SDK = [("sdk/javascript", "TypeSafe JavaScript SDK"),
          ("sdk/javascript/changelog", "更新日志"),
          ("sdk/javascript/api", "API 参考")]
JS_SDK += [("sdk/javascript/api/classes/" + c, "类：" + c) for c in JS_CLASSES]
JS_SDK += [("sdk/javascript/api/interfaces/" + i, "接口：" + i) for i in JS_INTERFACES]
JS_SDK += [("sdk/javascript/api/functions/" + f, "函数：" + f + "()") for f in JS_FUNCTIONS]
JS_SDK += [("sdk/javascript/api/type-aliases/" + t, "类型：" + t) for t in JS_ALIASES]
JS_SDK += [("sdk/javascript/api/variables/" + v, "变量：" + v) for v in JS_VARS]

GH_BASE = "https://github.com/datawhalechina/jev-cookbook/blob/main/"

# 每页注入的交互实验室预置（state + questions，均取自官方文档示例的中文化版本）
LABS = {
    "introduction/quickstart": {
        "state": "你好，我上周四下的订单（#98423）被重复扣了两次款，请尽快帮我处理。",
        "questions": {
            "billing": {"type": "noul", "instructions": "这条消息是否与账单或扣款问题有关？"},
            "tone": {"type": "choice", "instructions": "用户的语气如何？",
                     "criteria": {"calm": "平静、就事论事", "angry": "不满、着急"}},
            "urgency": {"type": "score", "instructions": "这条消息的紧急程度",
                        "criteria": ["可以等几天再处理", "本周内应处理", "需要立刻处理"]},
        },
    },
    "concepts/system-one": {
        "state": "客户消息：我的卡被重复扣款了，订单号 A-104，我要退款。",
        "questions": {
            "refund_requested": {"type": "noul", "instructions": "用户明确要求退款"},
            "route": {"type": "choice", "instructions": "这条工单应当路由到哪个团队",
                      "criteria": {"billing": "账单、扣款、退款", "technical": "产品故障、报错",
                                   "account": "账号、登录、资料"}},
        },
    },
    "concepts/state": {
        "state": "{\"message\": \"我的卡被重复扣款了。\", \"order_id\": \"A-104\", \"plan\": \"pro\"}",
        "questions": {
            "about_billing": {"type": "noul", "instructions": "这条消息是否关于账单问题？"},
            "mention_order": {"type": "noul", "instructions": "消息中是否提供了订单号"},
        },
    },
    "primitives": {
        "state": "我买的跑鞋尺码不对，能帮我换一双 10 码的吗？",
        "questions": {
            "department": {"type": "choice", "instructions": "哪个团队应当处理这条请求？",
                           "criteria": {"returns": "换货、错发或损坏", "shipping": "物流状态、延误、丢件",
                                        "billing": "扣款、发票、支付问题"}},
        },
    },
    "primitives/choice": {
        "state": "我买的跑鞋尺码不对，能帮我换一双 10 码的吗？另外发货也太慢了。",
        "questions": {
            "department": {"type": "choice", "instructions": "哪个团队应当处理这条请求？",
                           "criteria": {"returns": "换货、错发或损坏", "shipping": "物流状态、延误、丢件",
                                        "billing": "扣款、发票、支付问题"}},
        },
    },
    "primitives/score": {
        "state": "导出报告的功能坏了。用 Chrome 可以绕过，但只用 Safari 的用户没法使用导出。",
        "questions": {
            "bug_severity": {"type": "score", "instructions": "所报告问题的严重程度",
                             "criteria": ["外观问题；不影响功能", "功能受损或降级；存在变通方案",
                                          "阻塞性问题；没有任何变通方案"]},
        },
    },
    "primitives/noul": {
        "state": "我上周被重复扣款两次，要求全额退款并且补偿我的时间。",
        "questions": {
            "refund_requested": {"type": "noul", "instructions": "用户明确要求退款或补偿"},
        },
    },
    "confidence": {
        "state": "帮我查一下储蓄卡余额",
        "questions": {
            "intent": {"type": "choice", "instructions": "用户想执行什么操作？",
                       "criteria": {"check_balance": "查询账户余额", "approve_transfer": "批准待确认的转账",
                                    "other": "其他事情"}},
        },
    },
    "patterns/fan-out": {
        "state": "你好，我上周四的订单（#98423）被重复扣了两次款，网站更新后账号也登录不上，挺让人生气的。",
        "questions": {
            "category": {"type": "choice", "instructions": "判断这条支持工单的大类",
                         "criteria": {"bug_report": "报告产品损坏或错误", "billing": "扣款、发票、退款",
                                      "account": "登录、权限、资料"}},
            "refund_requested": {"type": "noul", "instructions": "用户明确要求退款或补偿"},
            "frustration": {"type": "score", "instructions": "用户表现出的挫败程度",
                            "criteria": ["平静、就事论事", "有些沮丧但礼貌", "非常愤怒"]},
        },
    },
    "patterns/confidence-routing": {
        "state": "请批准那笔待确认的转账",
        "questions": {
            "intent": {"type": "choice", "instructions": "用户想执行什么操作？",
                       "criteria": {"check_balance": "查询账户余额", "approve_transfer": "批准待确认的转账",
                                    "other": "其他事情"}},
        },
    },
    "patterns/composite-scoring": {
        "state": "资深后端工程师，某被广泛使用的 Python ORM 的核心贡献者；设计过跨区域支付平台的分片架构，偏好亲自写架构方案。",
        "questions": {
            "python_depth": {"type": "score", "instructions": "候选人的 Python 功底有多深？",
                             "criteria": ["未提及", "仅提到", "项目中使用过", "主力语言、多项目",
                                          "深厚功底：架构、性能、类库"]},
            "system_design": {"type": "score", "instructions": "候选人设计大规模系统的经验",
                              "criteria": ["未提及", "参与讨论", "设计过局部组件", "主导过重要系统架构",
                                           "跨领域设计过大规模系统"]},
        },
    },
    "patterns/intent-routing": {
        "state": "这是第三次坏了，客服一直互相推，我要全额退款，让经理给我回电话。",
        "questions": {
            "intent": {"type": "choice", "instructions": "这条客户消息的主要意图",
                       "criteria": {"order_status": "询问订单状态", "product_question": "购前咨询",
                                    "return_exchange": "退货换货", "complaint": "不满、要求解决"}},
            "complexity": {"type": "score", "instructions": "解决该请求的复杂程度",
                           "criteria": ["简单查询或标准流程", "需要判断或多步流程", "特殊情况或需升级"]},
        },
    },
}

# 页面 → 深入学习素材（badge: chapter/notebook/article）
_CH02 = "main/02_核心概念/"
_COOK_NB = {
    "consistency_noul_cookbook": "01_自一致性Noul", "consistency_choice_cookbook": "02_自一致性Choice",
    "parallel_questions": "03_并行提问", "rerank_typesafe": "04_重排序",
    "semantic_find": "05_逐行语义搜索", "autoformat": "06_结构恢复",
    "function_calling": "07_函数调用", "skill_suggestion": "08_技能推荐",
    "entity_alignment": "09_实体对齐", "classifying_rag_passages": "10_RAG段落分类",
    "citation_check": "11_引用核查", "llm_guardrails": "12_LLM防护栏",
    "sde_cascade": "13_SDE级联", "date_extraction_cookbook": "14_日期抽取",
    "pre_parsed_value_extraction_cookbook": "15_预解析值抽取",
    "hierarchical_classification": "16_层级分类",
    "autoresearch_feature_discovery": "17_自动研究特征发现",
    "classification_using_confidence": "18_基于置信度的分类",
}

def _related_map():
    R = {
        "introduction": [("chapter", "main/01_认识Jev/README.md", "第 1 章 · 认识 Jev（导读）"),
                          ("notebook", "main/01_认识Jev/01_认识Jev.ipynb", "第 1 章 · 配套笔记本")],
        "concepts/system-one": [("notebook", _CH02 + "01_SystemOne.ipynb", "第 2 章 · System One 实验笔记本")],
        "concepts/state": [("notebook", _CH02 + "02_状态.ipynb", "第 2 章 · 状态实验笔记本")],
        "confidence": [("notebook", _CH02 + "04_置信度.ipynb", "第 2 章 · 置信度实验笔记本")],
        "concepts/how-to-build-with-system-one": [("notebook", _CH02 + "05_应用构建.ipynb", "第 2 章 · 应用构建笔记本")],
    }
    for page, nb in (("primitives", "03_原语"), ("primitives/choice", "03_原语"),
                     ("primitives/score", "03_原语"), ("primitives/noul", "03_原语"),
                     ("primitives/advanced", "03_原语")):
        R[page] = [("notebook", _CH02 + nb + ".ipynb", "第 2 章 · 原语实验笔记本")]
    for page in ("patterns", "patterns/fan-out", "patterns/confidence-routing",
                 "patterns/composite-scoring", "patterns/intent-routing"):
        R[page] = [("notebook", "main/03_架构模式/01_架构模式.ipynb", "第 3 章 · 架构模式实验笔记本（四种模式全套可运行实验）")]
    for slug, nb in _COOK_NB.items():
        items = [("notebook", "main/04_实战指南/" + nb + ".ipynb", "第 4 章 · " + nb + " 实战笔记本")]
        if slug == "rerank_typesafe":
            items.append(("article", "main/11_知识库/jev-cookbook/18-wechat-rerank-experiment/article.md",
                          "拓展文章 · Jev 能替代 Rerank 模型吗（Milvus 实测）"))
        R["cookbooks/" + slug] = items
    R["demos/smart-home"] = [
        ("notebook", "main/05_智能家居实验/01_智能家居实验.ipynb", "第 5 章 · 智能家居实验笔记本"),
        ("chapter", "main/07_实战应用/README.md", "第 7 章 · 实战应用（start.py 一键启动真实管线）")]
    R["models"] = [
        ("notebook", "main/06_模型评测/01_模型评测.ipynb", "第 6 章 · 模型评测笔记本"),
        ("chapter", "main/10_本地模型/README.md", "第 10 章 · 本地模型（Laya）")]
    R["model-jaggedness/jev-1.13"] = [("notebook", "main/06_模型评测/01_模型评测.ipynb", "第 6 章 · 模型评测笔记本")]
    R["agent-skill"] = [("chapter", "main/09_Agent集成/README.md", "第 9 章 · Agent 集成（Pi / DSH 实验）")]
    R["sdk/python"] = [("chapter", "main/09_Agent集成/README.md", "第 9 章 · Agent 集成")]
    R["introduction/coding-agents"] = [("chapter", "main/09_Agent集成/README.md", "第 9 章 · Agent 集成")]
    R["introduction/machine-learning-primer"] = [("chapter", "main/08_前沿研究/README.md", "第 8 章 · 前沿研究（Jev-Mem 走读）")]
    return R

RELATED = _related_map()

# 拓展阅读：从第 11 章知识库挂载进站点的文章 (nav_slug, 源目录 slug, 标题, 说明)
MATERIALS = [
    ("clef", "23-clef-decision-models", "Clef：开源决策模型与 RL 微调平台",
     "Cloudflare 官方发布文 · Jev Decision Index 完整评测表"),
    ("polydao", "24-polydao-jev-engineering", "Jev 工程实战：账单砍掉 90%",
     "从业者手册 · 四桶分拣 / 置信度路由 / Kimi K3 兜底"),
    ("rerank-lab", "18-wechat-rerank-experiment", "Jev 能替代 Rerank 模型吗",
     "Milvus + SciFact 80 条实测对照"),
    ("laya-arch", "19-wechat-laya-architecture", "Laya 决策模型架构解析", "魔搭 ModelScope 社区"),
    ("laya-oss", "20-wechat-laya-oss-release", "Laya 开源发布", "PaperAgent"),
    ("laya-trend", "21-wechat-laya-hf-trending", "Laya 登上 HuggingFace 榜单", "机器之心报道"),
]

NAV = [
    ("开始", [
        ("introduction", "简介"),
        ("introduction/quickstart", "快速开始"),
        ("introduction/machine-learning-primer", "AI 入门"),
        ("introduction/coding-agents", "Jev 与编码智能体"),
    ]),
    ("核心概念", [
        ("concepts/system-one", "System One"),
        ("concepts/state", "状态（State）"),
        ("concepts/how-to-build-with-system-one", "如何用 TypeSafe 构建"),
        ("concepts/use-case-map", "应用场景地图"),
    ]),
    ("原语（问题类型）", [
        ("primitives", "原语概览"),
        ("primitives/choice", "Choice（选择）"),
        ("primitives/score", "Score（评分）"),
        ("primitives/noul", "Noul（是非判断）"),
        ("primitives/advanced", "进阶：结构化"),
    ]),
    ("置信度", [
        ("confidence", "置信度（Confidence）"),
    ]),
    ("架构模式", [
        ("patterns", "模式概览"),
        ("patterns/fan-out", "投机式扇出"),
        ("patterns/confidence-routing", "置信度门控路由"),
        ("patterns/composite-scoring", "组合评分"),
        ("patterns/intent-routing", "意图路由"),
    ]),
    ("实战指南", [("cookbooks", "实战指南概览")] + COOKBOOKS),
    ("示例", [
        ("demos", "示例概览"),
        ("demos/smart-home", "智能家居助手"),
    ]),
    ("参考", [
        ("api", "HTTP API 参考"),
        ("models", "模型"),
        ("model-jaggedness/jev-1.13", "Jev 1.13 已知短板"),
        ("agent-skill", "Agent 技能"),
        ("legal", "法律条款"),
    ]),
    ("客户端 SDK", [("sdk", "SDK 概览")] + PY_SDK + JS_SDK),
    ("拓展阅读", [("materials/" + m[0], m[2]) for m in MATERIALS]),
]

FLAT_NAV = [p for _g, items in NAV for p, _l in items]

# ---------------------------------------------------------------- 交互实验室与拓展素材

NAV_LABELS = dict(NAVItems := ((p, l) for _g, its in NAV for p, l in its))  # noqa

ICONS = {
    "arrow-up-down": "↕️", "badge-check": "✅", "binary": "🔢", "blocks": "🧩",
    "braces": "🧱", "brain-circuit": "🧠", "chart-no-axes-combined": "📈",
    "chart-spline": "📊", "circle-check": "✅", "clipboard-check": "📋",
    "code": "💻", "database-zap": "🗄️", "flask-conical": "🧪", "gauge": "⏱️",
    "headset": "🎧", "landmark": "🏛️", "list": "📋", "megaphone": "📣",
    "messages-square": "💬", "network": "🕸️", "route": "🧭", "scale": "⚖️",
    "search": "🔍", "shield": "🛡️", "shield-check": "🛡️", "split": "✂️",
    "store": "🏪", "triangle-alert": "⚠️", "user-round-search": "🔎",
    "users": "👥", "wrench": "🔧", "zap": "⚡",
}

CALLOUTS = {
    "Tip": ("提示", "💡", "tip"),
    "Note": ("注意", "📝", "note"),
    "Info": ("信息", "ℹ️", "info"),
    "Warning": ("警告", "⚠️", "warning"),
    "Check": ("检查", "✅", "check"),
}

# ---------------------------------------------------------------- 工具

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def slugify(text):
    """GitHub 风格锚点 slug（保留中日韩字符）。"""
    t = text.strip().lower()
    t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE)
    return t.replace(" ", "-")

def esc(t):
    return html.escape(str(t), quote=True)

def dedent_block(text, base_indent):
    out = []
    for line in text.split("\n"):
        if line.startswith(base_indent):
            out.append(line[len(base_indent):])
        elif line.strip() == "":
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)

def plain_text(md):
    t = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", md)
    t = re.sub(r"[*_`]", "", t)
    return t

# ---------------------------------------------------------------- LZ-String 移植

_URI_SAFE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-$"

def _lz_compress(uncompressed, bits_per_char, get_char_from_int):
    """逐句对应原站内嵌 JS（lz-string）的 _compress。"""
    if uncompressed is None:
        return ""
    context_dictionary = {}
    context_dictionary_to_create = {}
    context_w = ""
    context_enlarge_in = 2
    context_dict_size = 3
    context_num_bits = 2
    context_data = []
    ctx = {"val": 0, "pos": 0}

    def push(val):
        context_data.append(get_char_from_int(val))
        ctx["val"] = 0
        ctx["pos"] = 0

    def emit(out_val, mode, count):
        """mode: 'zero' 全 0；'lsb' 低位在前；'const' 首位 out_val 之后全 0。"""
        v = out_val
        for _ in range(count):
            if mode == "zero":
                ctx["val"] = ctx["val"] << 1
            elif mode == "lsb":
                ctx["val"] = (ctx["val"] << 1) | (v & 1)
                v >>= 1
            else:  # const
                ctx["val"] = (ctx["val"] << 1) | v
                v = 0
            if ctx["pos"] == bits_per_char - 1:
                push(ctx["val"])
            else:
                ctx["pos"] += 1

    def dec_enlarge():
        nonlocal context_enlarge_in, context_num_bits
        context_enlarge_in -= 1
        if context_enlarge_in == 0:
            context_enlarge_in = 2 ** context_num_bits
            context_num_bits += 1

    def emit_w(w):
        if ord(w[0]) < 256:
            emit(0, "zero", context_num_bits)
            emit(ord(w[0]), "lsb", 8)
        else:
            emit(1, "const", context_num_bits)
            emit(ord(w[0]), "lsb", 16)

    for context_c in uncompressed:
        if context_c not in context_dictionary:
            context_dictionary[context_c] = context_dict_size
            context_dict_size += 1
            context_dictionary_to_create[context_c] = True
        context_wc = context_w + context_c
        if context_wc in context_dictionary:
            context_w = context_wc
            continue
        if context_w in context_dictionary_to_create:
            emit_w(context_w)
            dec_enlarge()
            context_dictionary_to_create.pop(context_w, None)
        else:
            emit(context_dictionary[context_w], "lsb", context_num_bits)
        dec_enlarge()
        context_dictionary[context_wc] = context_dict_size
        context_dict_size += 1
        context_w = context_c

    if context_w != "":
        if context_w in context_dictionary_to_create:
            emit_w(context_w)
            dec_enlarge()
            context_dictionary_to_create.pop(context_w, None)
        else:
            emit(context_dictionary[context_w], "lsb", context_num_bits)
        dec_enlarge()

    emit(2, "lsb", context_num_bits)
    while True:
        ctx["val"] = ctx["val"] << 1
        if ctx["pos"] == bits_per_char - 1:
            push(ctx["val"])
            break
        ctx["pos"] += 1
    return "".join(context_data)


def lz_compress_to_encoded_uri_component(uncompressed):
    if uncompressed is None:
        return ""
    return _lz_compress(uncompressed, 6, lambda i: _URI_SAFE[i])

# ---------------------------------------------------------------- 宽容的 JS 对象字面量解析

class _JSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def error(self, msg):
        raise ValueError(f"JS value parse error at {self.i}: {msg}")

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n,":
            self.i += 1

    def parse(self):
        self.ws()
        v = self.value()
        return v

    def value(self):
        self.ws()
        if self.i >= len(self.s):
            self.error("unexpected end")
        c = self.s[self.i]
        if c == "{":
            return self.object()
        if c == "[":
            return self.array()
        if c in "\"'`":
            return self.string()
        if self.s.startswith("true", self.i):
            self.i += 4
            return True
        if self.s.startswith("false", self.i):
            self.i += 5
            return False
        if self.s.startswith("null", self.i):
            self.i += 4
            return None
        return self.number()

    def object(self):
        obj = {}
        self.i += 1
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated object")
            if self.s[self.i] == "}":
                self.i += 1
                return obj
            if self.s[self.i] in "\"'`":
                key = self.string()
            else:
                m = re.match(r"[^:\s{}[\],]+", self.s[self.i:])
                if not m:
                    self.error("bad key")
                key = m.group(0)
                self.i += len(key)
            self.ws()
            if self.i >= len(self.s) or self.s[self.i] != ":":
                self.error("expected :")
            self.i += 1
            obj[key] = self.value()

    def array(self):
        arr = []
        self.i += 1
        while True:
            self.ws()
            if self.i >= len(self.s):
                self.error("unterminated array")
            if self.s[self.i] == "]":
                self.i += 1
                return arr
            arr.append(self.value())

    def string(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'",
                   "\\": "\\", "/": "/", "`": "`", "b": "\b", "f": "\f"}
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                self.i += 1
                if self.i >= len(self.s):
                    self.error("bad escape")
                out.append(escapes.get(self.s[self.i], self.s[self.i]))
                self.i += 1
                continue
            if c == q:
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        self.error("unterminated string")

    def number(self):
        m = re.match(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", self.s[self.i:])
        if not m:
            self.error("bad number")
        self.i += len(m.group(0))
        t = m.group(0)
        try:
            return int(t)
        except ValueError:
            return float(t)

def parse_js_value(s):
    return _JSParser(s).parse()

# ---------------------------------------------------------------- 代码围栏

FENCE_OPEN_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[ \t]*(.*)$")

def extract_fences(text):
    """把围栏代码块替换为占位符 \\x00N\\x00，返回 (text, fences)。"""
    lines = text.split("\n")
    out = []
    fences = []
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if m:
            indent, tick, info = m.group(1), m.group(2), m.group(3)
            close_re = re.compile(
                r"^" + re.escape(indent) + re.escape(tick[0]) + "{" + str(len(tick)) + ",}[ \t]*$")
            j = i + 1
            code_lines = []
            while j < len(lines) and not close_re.match(lines[j]):
                code_lines.append(lines[j])
                j += 1
            if j >= len(lines):
                out.append(lines[i])
                i += 1
                continue
            body = "\n".join(code_lines)
            if indent:
                body = dedent_block(body, indent)
            fences.append({"info": info.strip(), "code": body})
            out.append(f"\x00{len(fences)-1}\x00")
            i = j + 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), fences

def fence_meta(info):
    """解析围栏 info → (lang, label, title)。兼容 `json theme={null}`、`bash cURL theme={null}`。"""
    lang = label = title = ""
    tokens = info.split()
    if tokens:
        lang = tokens[0]
        for t in tokens[1:]:
            m = re.match(r'title="(.*)"$', t)
            if m:
                title = m.group(1)
            elif t.startswith(("theme=", "{")):
                continue
            else:
                label = t
    return lang, label, title

# ---------------------------------------------------------------- 属性解析（扫描器实现，支持任意嵌套 {}）

def parse_attrs(src):
    attrs = {}
    i = 0
    n = len(src)
    key_re = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_-]*)")
    val_re = re.compile(r"\s*=\s*")
    while i < n:
        m = key_re.match(src, i)
        if not m:
            break
        key = m.group(1)
        i = m.end()
        mv = val_re.match(src, i)
        if not mv:  # 裸布尔属性，如 <ParamField ... required>
            attrs[key] = True
            continue
        i = mv.end()
        if i >= n:
            break
        if src[i] == '"':
            j = i + 1
            buf = []
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j + 1])
                    j += 2
                    continue
                if src[j] == '"':
                    break
                buf.append(src[j])
                j += 1
            attrs[key] = "".join(buf)
            i = j + 1
        elif src[i] == "{":
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                c = src[j]
                if c in "\"'`":
                    q = c
                    j += 1
                    while j < n and src[j] != q:
                        if src[j] == "\\":
                            j += 1
                        j += 1
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                j += 1
            attrs[key] = parse_js_value(src[i + 1:j - 1])
            i = j
        else:
            break
    return attrs

# ---------------------------------------------------------------- MDX 组件

COMP_NAMES = ["TypesafeExample", "ScoreExplorer", "ConfidenceExplorer", "SdkSignature",
              "ParamField", "ResponseField", "Expandable", "AccordionGroup", "Accordion",
              "CardGroup", "Card", "Columns", "Tabs", "Tab", "Steps", "Step", "Frame",
              "CodeGroup", "CodeBlock", "Tip", "Note", "Info", "Warning", "Check"]
COMP_RE = re.compile(r"<(" + "|".join(COMP_NAMES) + r")(?=[\s/>])")

def find_closing(text, name, from_idx):
    depth = 1
    pos = from_idx
    open_re = re.compile(r"<" + name + r"(?=[\s/>])")
    close_re = re.compile(r"</" + name + r"\s*>")
    while True:
        om = open_re.search(text, pos)
        cm = close_re.search(text, pos)
        if not cm:
            return None
        if om and om.start() < cm.start():
            gt = text.find(">", om.start())
            seg = text[om.start():gt + 1] if gt != -1 else ""
            if not seg.rstrip().endswith("/>"):
                depth += 1
            pos = (gt + 1) if gt != -1 else om.end()
        else:
            depth -= 1
            pos = cm.end()
            if depth == 0:
                return cm

def strip_export_blocks(text):
    """去掉页面里内嵌的 `export function X(...) { ... }` 组件定义。"""
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if re.match(r"export (async )?function ", lines[i]):
            depth = lines[i].count("{") - lines[i].count("}")
            j = i
            while depth > 0 and j + 1 < len(lines):
                j += 1
                depth += lines[j].count("{") - lines[j].count("}")
            i = j + 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)

IMG_RE = re.compile(r"<img ([^>]*?)className=\"([^\"]*)\"([^>]*?)/?>")

def fix_img_tags(html_text):
    def fix(m):
        pre, cls, post = m.group(1), m.group(2), m.group(3)
        if "dark:hidden" in cls:
            klass = "only-light"
        elif "dark:block" in cls:
            klass = "only-dark"
        else:
            klass = ""
        attrs = pre + post
        attrs = re.sub(r'\s*(?:className|data-path)="[^"]*"', "", attrs)
        if klass:
            attrs += f' class="{klass}"'
        return f"<img {attrs.strip()} />"
    return IMG_RE.sub(fix, html_text)

# ---------------------------------------------------------------- 行内渲染

ALLOWED_TAGS = {"a", "abbr", "b", "blockquote", "br", "button", "code", "del",
                "details", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
                "i", "img", "kbd", "li", "mark", "ol", "p", "pre", "q", "s",
                "section", "small", "span", "strong", "sub", "summary", "sup",
                "table", "tbody", "td", "th", "thead", "tr", "u", "ul"}
TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)((?:\"[^\"]*\"|'[^']*'|[^>])*?)>")
# 已成形的 HTML 实体不再转义，避免组件内部已 esc 的内容被二次转义
_ENTITY_RE = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,20};|#[0-9]{1,7};|#[xX][0-9a-fA-F]{1,6};)")

def esc_keep_entities(t):
    parts = _ENTITY_RE.split(t)
    ents = _ENTITY_RE.findall(t)
    out = []
    for i, p in enumerate(parts):
        out.append(esc(p))
        if i < len(ents):
            out.append(ents[i])
    return "".join(out)

def escape_preserving_tags(text):
    pos = 0
    out = []
    for m in TAG_RE.finditer(text):
        out.append(esc_keep_entities(text[pos:m.start()]))
        if m.group(1).lower() in ALLOWED_TAGS:
            out.append(m.group(0))
        else:
            out.append(esc(m.group(0)))
        pos = m.end()
    out.append(esc_keep_entities(text[pos:]))
    return "".join(out)

def unesc_md(s):
    return re.sub(r"\\([_`\*\[\]\(\)#\!\-~\\])", r"\1", s)

_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def render_inline(text):
    text = unesc_md(text)
    text = text.replace("<br>", "<br />").replace("<br/>", "<br />")
    text = _AUTOLINK_RE.sub(r'<a href="\1">\1</a>', text)

    def img_repl(m):
        src, alt = m.group(2), m.group(1)
        local = mintcdn_to_local(src)
        if local:
            src = local
        return f'<img src="{esc(src)}" alt="{esc(alt)}" loading="lazy" />'
    text = _IMG_RE.sub(img_repl, text)

    def link_repl(m):
        label, target = m.group(1), m.group(2).strip()
        t = target.split()[0] if target else ""
        if t.startswith(("http://", "https://", "mailto:")):
            return f'<a href="{esc(t)}" target="_blank" rel="noopener">{label}</a>'
        return f'<a href="{esc(t)}">{label}</a>'
    text = _LINK_RE.sub(link_repl, text)

    text = re.sub(r"\*\*\*([^*]+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+?)~~", r"<del>\1</del>", text)
    text = escape_preserving_tags(text)
    return text

# ---------------------------------------------------------------- Markdown 块渲染

LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
INDENT_UNIT = 4

def indent_of(s):
    n = 0
    for ch in s:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += INDENT_UNIT - n % INDENT_UNIT
        else:
            break
    return n

_CODE_TOKEN_RE = re.compile(r"\x00(\d+)\x00")

_call_counter = [0]

def render_markdown(text, R):
    """渲染 Markdown 为 HTML。R 为 Renderer（提供 fence/toc/组件）。"""
    token = f"\x01C{_call_counter[0]}\x01"
    _call_counter[0] += 1
    codes = []

    def protect_code(m):
        codes.append(m.group(1))
        return f"{token}{len(codes)-1}\x01"

    text = re.sub(r"`([^`\n]+)`", protect_code, text)

    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue

        m = re.fullmatch(r"\x00(\d+)\x00", line.strip())
        if m:
            out.append(R.fence_html(int(m.group(1))))
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            plain = plain_text(m.group(2).strip())
            slug = slugify(plain)
            base_slug = slug
            k = 1
            while slug in R.heading_ids:
                k += 1
                slug = f"{base_slug}-{k}"
            R.heading_ids[slug] = level
            out.append(f'<h{level} id="{esc(slug)}">{render_inline(plain)}</h{level}>')
            i += 1
            continue

        if re.fullmatch(r"\s*(\*\*\*|---|___)\s*", line):
            out.append("<hr />")
            i += 1
            continue

        if line.lstrip().startswith(">"):
            quote_lines = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            first = quote_lines[0].strip() if quote_lines else ""
            single_simple = (len(quote_lines) == 1 and first
                             and not first.startswith(("#", "-", "*", ">", "`", "|"))
                             and not _CODE_TOKEN_RE.fullmatch(first))
            if single_simple and out and out[-1].startswith("<h1"):
                out.append(f'<p class="page-desc">{render_inline(first)}</p>')
            else:
                inner_html = render_markdown("\n".join(quote_lines), R)
                out.append(f"<blockquote>{inner_html}</blockquote>")
            continue

        if ("|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1])
                and "-" in lines[i + 1]):
            header = split_row(line)
            aligns = parse_aligns(lines[i + 1])
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            out.append(render_table(header, aligns, rows))
            continue

        m = LIST_RE.match(line)
        if m:
            item_html, i = parse_list(lines, i, R)
            out.append(item_html)
            continue

        m = re.match(r"^\s*<([a-zA-Z][a-zA-Z0-9]*)", line)
        if m and m.group(1).lower() in {"h1", "h2", "h3", "h4", "h5", "h6", "a", "div",
                                        "section", "table", "thead", "tbody", "iframe",
                                        "details", "summary", "button", "svg", "pre", "p"}:
            tag = m.group(1).lower()
            close = f"</{tag}>"
            if f"<{tag}" in line and close not in line and not line.rstrip().endswith("/>"):
                block = [line]
                i += 1
                while i < n and close not in lines[i]:
                    block.append(lines[i])
                    i += 1
                if i < n:
                    block.append(lines[i])
                    i += 1
                out.append(unesc_md("\n".join(block)))
            else:
                out.append(unesc_md(line))
                i += 1
            continue

        para = [line]
        i += 1
        while (i < n and lines[i].strip() != ""
               and not re.match(r"^(#{1,6}\s|\s*>|\s*(\*\*\*|---|___)\s*$)", lines[i])
               and not LIST_RE.match(lines[i])
               and not _CODE_TOKEN_RE.fullmatch(lines[i].strip())
               and not ("|" in lines[i] and i + 1 < n
                        and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1])
                        and "-" in lines[i + 1])):
            para.append(lines[i])
            i += 1
        out.append("<p>" + render_inline(" ".join(p.strip() for p in para)) + "</p>")

    html_text = "\n".join(out)

    def restore(m2):
        idx = int(m2.group(1))
        if idx < len(codes):
            return "<code>" + esc(codes[idx]) + "</code>"
        return ""
    return re.sub(re.escape(token) + r"(\d+)\x01", restore, html_text)

def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [c.replace("\\|", "|").strip() for c in cells]

def parse_aligns(line):
    aligns = []
    for c in split_row(line):
        if c.startswith(":") and c.endswith(":"):
            aligns.append("center")
        elif c.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("")
    return aligns

def render_table(header, aligns, rows):
    def cell(c, idx, tag):
        style = (f' style="text-align:{aligns[idx]}"'
                 if idx < len(aligns) and aligns[idx] else "")
        return f"<{tag}{style}>{render_inline(c)}</{tag}>"
    th = "".join(cell(c, idx, "th") for idx, c in enumerate(header))
    trs = "".join("<tr>" + "".join(cell(c, idx, "td") for idx, c in enumerate(row)) + "</tr>"
                  for row in rows)
    return ('<div class="table-wrap"><table><thead><tr>' + th
            + "</tr></thead><tbody>" + trs + "</tbody></table></div>")

def parse_list(lines, i, R):
    m0 = LIST_RE.match(lines[i])
    base_indent = indent_of(m0.group(1))
    ordered = m0.group(2)[0].isdigit()
    items = []
    while i < len(lines):
        m = LIST_RE.match(lines[i])
        if (not m or indent_of(m.group(1)) != base_indent
                or m.group(2)[0].isdigit() != ordered):
            break
        marker = m.group(2)
        cont_col = indent_of(m.group(1)) + len(marker) + 1
        content = [m.group(3)]
        i += 1
        while i < len(lines):
            line = lines[i]
            if line.strip() == "":
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines):
                    nm = LIST_RE.match(lines[j])
                    if ((nm and indent_of(nm.group(1)) >= base_indent)
                            or indent_of(lines[j]) >= cont_col):
                        content.append("")
                        i += 1
                        continue
                break
            nm = LIST_RE.match(line)
            if nm and indent_of(nm.group(1)) == base_indent:
                break
            if nm or indent_of(line) >= cont_col:
                content.append(line)
                i += 1
            else:
                break
        block = dedent_block("\n".join(content), " " * cont_col)
        items.append(render_markdown(block, R))
    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) + f"</{tag}>", i

# ---------------------------------------------------------------- 渲染器

def mintcdn_to_local(url):
    m = re.search(r'https://mintcdn\.com/ts-docs/[^/"]+/([^"?]+)', url)
    if not m:
        return None
    return "assets/images/" + m.group(1)

class Renderer:
    def __init__(self, page):
        self.page = page
        self.fences = []
        self.used_fences = set()
        self.heading_ids = {}

    def render_md(self, text):
        text = self.render_components(text)
        return render_markdown(text, self)

    # ---------- 组件 ----------

    def render_components(self, text):
        pos = 0
        while True:
            m = COMP_RE.search(text, pos)
            if not m:
                return text
            name = m.group(1)
            gt = text.find(">", m.start())
            if gt == -1:
                pos = m.end()
                continue
            open_tag = text[m.start():gt + 1]
            self_closing = open_tag.rstrip().endswith("/>")
            attrs = parse_attrs(open_tag[len(name) + 1:-1])
            if self_closing:
                inner = ""
                end = gt + 1
            else:
                cm = find_closing(text, name, gt + 1)
                if cm is None:
                    pos = gt + 1
                    continue
                inner = text[gt + 1:cm.start()]
                end = cm.end()
            m_indent = re.match(r"[ \t]*", text[m.start():])
            rendered = self.render_component(name, attrs, inner, m_indent.group(0))
            text = text[:m.start()] + rendered + text[end:]
            pos = m.start() + len(rendered)

    def render_component(self, name, attrs, inner, base_indent):
        inner_md = dedent_block(inner.strip("\n"), base_indent)
        if name in CALLOUTS:
            label, icon, cls = CALLOUTS[name]
            body = self.render_md(inner_md)
            return (f'<div class="callout callout-{cls}"><div class="callout-title">'
                    f'<span class="callout-icon">{icon}</span>{label}</div>'
                    f'<div class="callout-body">{body}</div></div>')
        if name == "Tabs":
            tabs = []
            tpos = 0
            while True:
                tm = re.search(r"<Tab(?=[\s/>])", inner_md[tpos:])
                if not tm:
                    break
                s = tpos + tm.start()
                gt = inner_md.find(">", s)
                t_attrs = parse_attrs(inner_md[s + 4:gt])
                cm = find_closing(inner_md, "Tab", gt + 1)
                if cm is None:
                    break
                content = self.render_md(inner_md[gt + 1:cm.start()].strip("\n"))
                tabs.append((str(t_attrs.get("title", "")), content))
                tpos = cm.end()
            panes = "".join(f'<div class="tab-pane" data-title="{esc(t)}">{c}</div>'
                            for t, c in tabs)
            return f'<div class="tabs">{panes}</div>'
        if name == "CodeGroup":
            panes = []
            for tok in _CODE_TOKEN_RE.findall(inner_md):
                idx = int(tok)
                if idx in self.used_fences:
                    continue
                self.used_fences.add(idx)
                lang, label, title = fence_meta(self.fences[idx]["info"])
                panes.append((label or lang or "代码", self.fence_html(idx)))
            if not panes:
                return self.render_md(inner_md)
            return ('<div class="tabs codegroup">' +
                    "".join(f'<div class="tab-pane" data-title="{esc(t)}">{c}</div>'
                            for t, c in panes) + "</div>")
        if name == "TypesafeExample":
            return self.typesafe_example(attrs)
        if name in ("ScoreExplorer", "ConfidenceExplorer"):
            anchor = "confidence" if name == "ConfidenceExplorer" else "primitives/score"
            return (f'<div class="explorer-note">🔭 本页原本包含一个交互式组件（{name}），'
                    f'为动态应用；请移步<a href="{ORIGIN_URL}/{anchor}" target="_blank" '
                    f'rel="noopener">原站对应页面</a>体验。</div>')
        if name == "SdkSignature":
            sig = re.sub(r'\{"((?:[^"\\]|\\.)*)"\}',
                         lambda m2: json.loads('"' + m2.group(1) + '"'), inner)
            return f'<div class="sdk-signature"><pre><code>{sig}</code></pre></div>'
        if name in ("ParamField", "ResponseField"):
            pname = attrs.get("name") or attrs.get("body") or ""
            ptype = attrs.get("type", "")
            req = bool(attrs.get("required", False))
            head = f'<code class="param-name">{esc(pname)}</code>'
            if ptype:
                head += f'<span class="param-type">{esc(ptype)}</span>'
            if req:
                head += '<span class="param-required">必填</span>'
            body = self.render_md(inner_md)
            return (f'<div class="param"><div class="param-head">{head}</div>'
                    f'<div class="param-body">{body}</div></div>')
        if name in ("Expandable", "Accordion"):
            title = str(attrs.get("title", "详情"))
            icon = ICONS.get(str(attrs.get("icon", "")), "")
            ic = f'<span class="icon">{icon}</span> ' if icon else ""
            body = self.render_md(inner_md)
            cls = "accordion" if name == "Accordion" else "expandable"
            return (f'<details class="{cls}"><summary>{ic}{esc(title)}'
                    f'<span class="chev">▾</span></summary>'
                    f'<div class="details-body">{body}</div></details>')
        if name == "AccordionGroup":
            return f'<div class="accordion-group">{self.render_md(inner_md)}</div>'
        if name == "Card":
            title = str(attrs.get("title", ""))
            icon = ICONS.get(str(attrs.get("icon", "")), "")
            ic = f'<span class="icon">{icon}</span>' if icon else ""
            body = self.render_md(inner_md)
            return (f'<div class="card"><div class="card-title">{ic}{esc(title)}</div>'
                    f'<div class="card-body">{body}</div></div>')
        if name in ("CardGroup", "Columns"):
            cols = attrs.get("cols")
            cls = "card-group" if name == "CardGroup" else "columns"
            if isinstance(cols, int):
                cls += f" cols-{min(cols, 4)}"
            return f'<div class="{cls}">{self.render_md(inner_md)}</div>'
        if name == "Steps":
            steps = []
            spos = 0
            while True:
                sm = re.search(r"<Step(?=[\s/>])", inner_md[spos:])
                if not sm:
                    break
                s = spos + sm.start()
                gt = inner_md.find(">", s)
                st_attrs = parse_attrs(inner_md[s + 5:gt])
                cm = find_closing(inner_md, "Step", gt + 1)
                if cm is None:
                    break
                content = self.render_md(inner_md[gt + 1:cm.start()].strip("\n"))
                title = str(st_attrs.get("title", ""))
                th = f'<strong class="step-title">{esc(title)}</strong>' if title else ""
                steps.append(f"<li>{th}{content}</li>")
                spos = cm.end()
            return f'<ol class="steps">{"".join(steps)}</ol>'
        if name == "Frame":
            return f'<div class="frame">{fix_img_tags(inner)}</div>'
        if name == "CodeBlock":
            lang = str(attrs.get("language", ""))
            title = str(attrs.get("filename") or attrs.get("title") or "")
            code = re.sub(r"^\n+", "", inner).rstrip("\n")
            return self.codeblock_html(esc(code), lang, title)
        return self.render_md(inner_md)

    def typesafe_example(self, attrs):
        example = attrs.get("example", {})
        display = attrs.get("display")
        title = str(attrs.get("title") or "request")
        if not isinstance(example, dict):
            return ""
        questions = example.get("questions", {})
        state = example.get("state")
        selected = example.get("selectedModels")
        if display == "questions" or state is None:
            shown = {"questions": questions}
        else:
            shown = {"state": state, "questions": questions}
        pretty = json.dumps(shown, ensure_ascii=False, indent=2)
        payload = {"apiVersion": "v1"}
        if state is None:
            payload["documentText"] = ""
        elif isinstance(state, str):
            payload["documentText"] = state
        else:
            payload["documentText"] = json.dumps(state, ensure_ascii=False)
        payload["promptsText"] = json.dumps(questions, ensure_ascii=False, indent=2)
        if selected:
            payload["selectedModels"] = selected
        try:
            share = lz_compress_to_encoded_uri_component(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            href = "https://console.typesafe.ai/decode#share/" + share
        except Exception:
            href = "https://console.typesafe.ai/playground"
        return (self.codeblock_html(esc(pretty), "json", title)
                + f'<p class="playground-link"><a href="{esc(href)}" target="_blank" '
                  f'rel="noopener">在 Playground 中打开 →</a></p>')

    def fence_html(self, idx):
        f = self.fences[idx]
        lang, label, title = fence_meta(f["info"])
        if lang == "mermaid":
            return (f'<div class="mermaid-frame"><pre class="mermaid-source" hidden>'
                    f'{esc(f["code"])}</pre><div class="mermaid">{esc(f["code"])}</div></div>')
        return self.codeblock_html(esc(f["code"]), lang, title or label)

    def codeblock_html(self, code_escaped, lang, title):
        cls = f' class="language-{esc(lang)}"' if lang else ""
        head = f'<span class="cb-title">{esc(title or lang)}</span>' if (title or lang) else ""
        return (f'<div class="codeblock">{head}<button class="cb-copy" type="button" '
                f'aria-label="复制代码">复制</button>'
                f'<pre><code{cls}>{code_escaped}</code></pre></div>')

# ---------------------------------------------------------------- 标题与锚点

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.M)

def headings_of(md_text):
    return [slugify(plain_text(m.group(2).strip())) for m in HEADING_RE.finditer(md_text)]

def build_anchor_maps(pages):
    """锚点映射优先从 _orig 现算；仓库发布版无 _orig 时回退到 anchor_maps.json。"""
    if not os.path.isdir(ORIG):
        cache = os.path.join(ROOT, "anchor_maps.json")
        if os.path.exists(cache):
            data = json.loads(read(cache))
            return {k: v for k, v in data.items() if k in set(pages)}
        print("警告: 缺少 _orig/ 与 anchor_maps.json，跨页锚点将不做改写")
        return {}
    maps = {}
    for p in pages:
        orig = os.path.join(ORIG, p.replace("/", "_") + ".md")
        zh = os.path.join(CONTENT, p + ".md")
        if not (os.path.exists(orig) and os.path.exists(zh)):
            continue
        o = headings_of(read(orig))
        z = headings_of(read(zh))
        mapping = {}
        for oslug, zslug in zip(o, z):
            if oslug and oslug not in mapping and zslug:
                mapping[oslug] = zslug
        maps[p] = mapping
    return maps

# ---------------------------------------------------------------- 链接与资源后处理

def rewrite_links(html_text, page, pages, anchor_maps, from_root=False):
    def href_repl(m):
        prefix, target = m.group(1), m.group(2)
        base_dir = "" if (from_root or page == "@root") else page
        if target.startswith("/"):
            frag = ""
            path = target
            if "#" in target:
                path, frag = target.split("#", 1)
            path = path.rstrip("/")
            dest = path.lstrip("/") or ROOT_PAGE
            if dest not in pages:
                return m.group(0)
            if frag:
                frag = anchor_maps.get(dest, {}).get(frag, frag)
            rel = posixpath.relpath(dest, base_dir) if base_dir else dest
            new = f"{prefix}{rel}/"
            if frag:
                new += f"#{frag}"
            return new + '"'  # 补回正则消费掉的闭合引号
        if target.startswith("#"):
            frag = target[1:]
            frag = anchor_maps.get(page, {}).get(frag, frag)
            return f'{prefix}#{frag}"'
        return m.group(0)
    html_text = re.sub(r'(href=")([^"]*)"', href_repl, html_text)

    def src_repl(m):
        local = mintcdn_to_local(m.group(1))
        return f'src="{local}"' if local else m.group(0)
    html_text = re.sub(r'src="(https://mintcdn[^"]*)"', src_repl, html_text)

    def ext_repl(m):
        href = m.group(1)
        host = href.split("/")[2] if href.count("/") >= 2 else ""
        if "typesafe.ai" not in host and "loom.com" not in host:
            return f'<a href="{href}" target="_blank" rel="noopener"'
        return m.group(0)
    html_text = re.sub(r'<a href="(https?://[^"]+)"', ext_repl, html_text)
    return html_text

# ---------------------------------------------------------------- 页面渲染

BOILER_RE = re.compile(r"^> ## Documentation Index\n.*?\n\n", re.S)
TOC_SCAN_RE = re.compile(r'<h([23]) id="([^"]*)">(.*?)</h[23]>', re.S)

def render_page(page, pages, anchor_maps, from_root=False):
    src = read(os.path.join(CONTENT, page + ".md"))
    src = BOILER_RE.sub("", src)
    src = strip_export_blocks(src)
    R = Renderer(page)
    src, fences = extract_fences(src)
    R.fences = fences
    body = R.render_md(src)

    def leftover(m2):
        idx = int(m2.group(1))
        if idx in R.used_fences:
            return ""
        return R.fence_html(idx)
    body = _CODE_TOKEN_RE.sub(leftover, body)
    body = fix_img_tags(body)
    body = rewrite_links(body, page, pages, anchor_maps, from_root=from_root)
    # 图片等资源是站点根相对路径，按页面深度补上相对前缀
    base_prefix = "" if (from_root or page == "@root") else "../" * (page.count("/") + 1)
    body = body.replace('src="assets/images/', f'src="{base_prefix}assets/images/')

    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else page

    toc = []
    seen = set()
    for m in TOC_SCAN_RE.finditer(body):
        lv, hid, text = int(m.group(1)), m.group(2), m.group(3)
        if hid in seen:
            continue
        seen.add(hid)
        toc.append((lv, re.sub(r"<[^>]+>", "", text).strip(), hid))
    return title, body, toc

# ---------------------------------------------------------------- 实验室 / 素材区块

def lab_html(page):
    cfg = LABS[page]
    payload = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<section class="lab">
  <div class="lab-title">🔬 交互实验室</div>
  <div class="lab-hint">改一改 state 或问题再运行，观察概率与置信度如何变化。默认运行<b>本地演示</b>（离线可用、
  非真实模型输出，仅演示答案形状）；填入 API Key 可尝试直连真实 API（官方暂未开放跨域时会给出一键复制的本地调用代码）；也可一键到官方 Playground 在线试跑。
  配套讲解见本页上方内容与「深入学习」素材。</div>
  <div class="lab-grid">
    <div class="lab-left">
      <label>state · 要判断的内容（可以是普通文本，或 JSON 字符串）</label>
      <textarea id="lab-state" spellcheck="false"></textarea>
      <div id="lab-questions"></div>
    </div>
    <div class="lab-right">
      <div class="lab-actions">
        <button id="lab-run" type="button">▶ 运行</button>
        <button id="lab-playground" type="button">在 Playground 打开 ↗</button>
      </div>
      <div class="lab-key-row">
        <input id="lab-key" placeholder="TYPESAFE_API_KEY（可选：调用真实 API）" autocomplete="off" spellcheck="false" />
        <div class="lab-key-note">Key 仅保存在本浏览器（localStorage），不会上传到本站。留空 = 本地演示。</div>
      </div>
      <div class="lab-results" id="lab-results"></div>
    </div>
  </div>
</section>
<script type="application/json" id="lab-config">{payload}</script>"""


def related_html(page):
    items = RELATED.get(page)
    if not items:
        return ""
    rows = []
    for badge, path, label in items:
        icon = {"notebook": "📓 笔记本", "article": "📰 拓展文章", "chapter": "📘 教程章节"}[badge]
        rows.append(f'<div class="related-item"><span class="related-badge {badge}">{icon}</span>'
                    f'<a href="{GH_BASE}{esc(path)}" target="_blank" rel="noopener">{esc(label)}</a></div>')
    return (f'<div class="related"><div class="related-title">深入学习 · 教程与素材</div>'
            f'<div class="related-list">{"".join(rows)}</div>'
            f'<div class="related-note">链接跳转到 GitHub 仓库（datawhalechina/jev-cookbook）对应文件；'
            f'notebook 在 GitHub 上可直接阅读渲染结果。</div></div>')


KB_ROOT = os.path.join(ROOT, "main", "11_知识库", "jev-cookbook")

def render_material(nav_slug, src_slug, title, desc):
    """把知识库文章渲染成站点页面（含 media 资源）。"""
    src_dir = os.path.join(KB_ROOT, src_slug)
    md_path = os.path.join(src_dir, "article.md")
    if not os.path.exists(md_path):
        print(f"警告: 素材缺失 {md_path}")
        return
    page = "materials/" + nav_slug
    text = read(md_path)
    R = Renderer(page)
    text, fences = extract_fences(text)
    R.fences = fences
    body = R.render_md(text)
    body = _CODE_TOKEN_RE.sub(lambda m: R.fence_html(int(m.group(1))), body)
    body = rewrite_links(body, page, list_pages() + [page], {}, from_root=False)
    head = (f'<p class="page-desc">{esc(desc)} · 收录自第 11 章知识库，'
            f'<a href="{GH_BASE}main/11_知识库/jev-cookbook/{src_slug}/article.md" '
            f'target="_blank" rel="noopener">查看来源与登记信息 ↗</a></p>')
    body = head + body
    toc = []
    for m in TOC_SCAN_RE.finditer(body):
        lv, hid, t = int(m.group(1)), m.group(2), m.group(3)
        toc.append((lv, re.sub(r"<[^>]+>", "", t).strip(), hid))
    base = "../" * (page.count("/") + 1)
    write(os.path.join(DIST, page, "index.html"), render_shell(page, title, body, toc, base))
    media_src = os.path.join(src_dir, "media")
    if os.path.isdir(media_src):
        dist_media = os.path.join(DIST, page, "media")
        if os.path.isdir(dist_media):
            shutil.rmtree(dist_media)
        shutil.copytree(media_src, dist_media)


# ---------------------------------------------------------------- 外壳

def render_shell(page, title, body, toc, base):
    if page == "@root":
        page = ROOT_PAGE
    if page in FLAT_NAV:
        p = FLAT_NAV.index(page)
        prev_page = FLAT_NAV[p - 1] if p > 0 else None
        next_page = FLAT_NAV[p + 1] if p < len(FLAT_NAV) - 1 else None
    else:
        prev_page = next_page = None

    nav_parts = ['<nav class="sidebar-nav" id="sidebar-nav">']
    for gi, (group, items) in enumerate(NAV):
        has_current = any(ip == page for ip, _ in items)
        nav_parts.append(f'<div class="nav-group{" open" if has_current else ""}" data-group="{gi}">')
        nav_parts.append(f'<button class="nav-group-title" type="button">{esc(group)}'
                         f'<span class="chev">▾</span></button>')
        nav_parts.append('<div class="nav-items">')
        for ip, label in items:
            cur = " current" if ip == page else ""
            nav_parts.append(f'<a class="nav-item{cur}" href="{base}{ip}/">{esc(label)}</a>')
        nav_parts.append("</div></div>")
    nav_parts.append("</nav>")
    nav_html = "".join(nav_parts)

    toc_html = ""
    if toc:
        items = "".join(f'<a class="toc-item toc-l{lv}" href="#{esc(slug)}">{esc(t)}</a>'
                        for lv, t, slug in toc)
        toc_html = f'<aside class="toc"><div class="toc-title">本页内容</div>{items}</aside>'

    pager = ['<nav class="pager">']
    if prev_page:
        pager.append(f'<a class="pager-prev" href="{base}{prev_page}/"><span>上一篇</span>'
                     f"<strong>{esc(NAV_LABELS[prev_page])}</strong></a>")
    if next_page:
        pager.append(f'<a class="pager-next" href="{base}{next_page}/"><span>下一篇</span>'
                     f"<strong>{esc(NAV_LABELS[next_page])}</strong></a>")
    pager.append("</nav>")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)} · {SITE_TITLE}</title>
<link rel="stylesheet" href="{base}assets/style.css" />
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🛡️%3C/text%3E%3C/svg%3E" />
</head>
<body>
<header class="topbar">
  <button class="menu-btn" id="menu-btn" aria-label="打开导航">☰</button>
  <a class="brand" href="{base}"><span class="brand-mark">🛡️</span>{SITE_TITLE}</a>
  <div class="searchbox">
    <input id="search-input" type="search" placeholder="搜索文档…（Ctrl / ⌘ + K）" autocomplete="off" />
    <div class="search-results" id="search-results" hidden></div>
  </div>
  <div class="top-actions">
    <button id="theme-toggle" class="theme-toggle" aria-label="切换深色模式">🌙</button>
    <a class="origin-link" href="{ORIGIN_URL}" target="_blank" rel="noopener">原文档 ↗</a>
  </div>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar">{nav_html}</aside>
  <div class="sidebar-mask" id="sidebar-mask"></div>
  <main class="content"><article class="doc">
{body}
  </article>
  {"".join(pager)}
  <footer class="site-footer">本站为 <a href="{ORIGIN_URL}" target="_blank" rel="noopener">docs.typesafe.ai</a> 的中文翻译，仅供学习参考；内容版权归原作者所有。</footer>
  </main>
{toc_html}
</div>
<script src="{base}assets/search-index.js"></script>
<script src="{base}assets/lz-string.js"></script>
<script src="{base}assets/app.js"></script>
<script src="{base}assets/lab.js"></script>
</body>
</html>"""

# ---------------------------------------------------------------- 搜索索引

def build_search_index(pages):
    entries = []
    for p in pages:
        title, body, _toc = render_page(p, pages, {}, from_root=False)
        text = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()[:12000]
        entries.append({"p": p, "t": title, "g": NAV_LABELS.get(p, ""), "b": text})
    return entries

# ---------------------------------------------------------------- 校验

def validate(pages):
    problems = []
    for dirpath, _d, files in os.walk(DIST):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, DIST)
            text = read(full)
            cur_dir = posixpath.dirname(rel)
            for m in re.finditer(r'href="([^"]+)"', text):
                href = m.group(1)
                if href.startswith(("http", "mailto:", "data:")):
                    continue
                target = href.split("#")[0]
                if not target:
                    continue
                resolved = posixpath.normpath(posixpath.join(cur_dir, target))
                if not os.path.exists(os.path.join(DIST, resolved, "index.html")) \
                        and not os.path.isfile(os.path.join(DIST, resolved)):
                    problems.append(f"{rel}: 内链失效 {href}")
            for m in re.finditer(r'src="([^"]+)"', text):
                src = m.group(1)
                if src.startswith("data:"):
                    continue
                if src.startswith("http"):
                    if "loom.com" not in src:  # demo 页的视频嵌入是有意保留的
                        problems.append(f"{rel}: 残留外部资源 {src}")
                    continue
                resolved = posixpath.normpath(posixpath.join(cur_dir, src))
                if not os.path.exists(os.path.join(DIST, resolved)):
                    problems.append(f"{rel}: 资源缺失 {src}")
    return problems

# ---------------------------------------------------------------- 主流程

def main():
    pages = list_pages()
    print(f"内容页面: {len(pages)}")
    missing = [p for p in pages if p not in NAV_LABELS]
    if missing:
        print("警告: 以下页面不在导航中:", *("  " + m for m in missing), sep="\n")
    anchor_maps = build_anchor_maps(pages)
    if os.path.isdir(ORIG):
        write(os.path.join(ROOT, "anchor_maps.json"),
              json.dumps(anchor_maps, ensure_ascii=False, indent=0))

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    if os.path.isdir(os.path.join(ASSETS, "images")):
        shutil.copytree(os.path.join(ASSETS, "images"), os.path.join(DIST, "assets", "images"))
    for fname in ("style.css", "app.js", "lab.js", "lz-string.js"):
        shutil.copy2(os.path.join(ASSETS, fname), os.path.join(DIST, "assets", fname))

    entries = build_search_index(pages)
    write(os.path.join(DIST, "assets", "search-index.js"),
          "window.SEARCH_INDEX=" + json.dumps(entries, ensure_ascii=False) + ";")

    total = len(pages)
    for i, p in enumerate(pages, 1):
        title, body, toc = render_page(p, pages, anchor_maps, from_root=False)
        if p in LABS:
            body += lab_html(p)
        rel = related_html(p)
        if rel:
            body += rel
        base = "../" * (p.count("/") + 1)
        write(os.path.join(DIST, p, "index.html"),
              render_shell(p, title, body, toc, base))
        print(f"[{i}/{total}] {p}")

    # 拓展阅读（第 11 章知识库文章挂载）
    for nav_slug, src_slug, m_title, m_desc in MATERIALS:
        render_material(nav_slug, src_slug, m_title, m_desc)
        print(f"[素材] materials/{nav_slug}")

    title, body, toc = render_page(ROOT_PAGE, pages, anchor_maps, from_root=True)
    write(os.path.join(DIST, "index.html"), render_shell("@root", title, body, toc, ""))
    print("根页面: /index.html")

    problems = validate(pages)
    if problems:
        print(f"\n校验发现 {len(problems)} 个问题:")
        for pr in problems[:40]:
            print("  " + pr)
    else:
        print("\n校验通过：全部内链与资源有效。")

if __name__ == "__main__":
    main()
