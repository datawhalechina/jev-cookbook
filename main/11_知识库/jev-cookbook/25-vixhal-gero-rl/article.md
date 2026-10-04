# 搭建一个 RL 微调平台，训练 JEV 式决策模型

> 原文：[Building an RL fine-tuning platform to train JEV-like decision models](https://x.com/TheVixhal/status/2106439792800198966) · X 长文 · @TheVixhal（vixhaℓ）· 2026-10-03
>
> 译文为社区学习用途的非官方中文翻译，版权归原作者所有。

这篇文章讲的是我们如何搭建一个小型训练平台，把一个普通的开放 LLM（Qwen3-4B）变成决策模型。

最终成果是 [Gero-4B](https://huggingface.co/vixhal-baraiya/Gero-4B)，下面写的全部是我们实际用过的代码，只是稍作简化，方便跟着读。

我们在 MacBook（M5 Pro，24 GB）上使用 Apple 的 MLX 完成训练，但这些思路在 PyTorch 里同样行得通。

---

## 我们想让模型做什么

决策模型回答的是这类问题：

- **Choice：**「这个工单应该交给哪个团队处理？」选项为 billing、technical、account、shipping。
- **Score：**「这个问题有多严重？」答案是从 "cosmetic"（外观小问题）到 "everyone is blocked"（所有人都被阻塞）的有序等级。
- **Yes/no：**「客户满意吗？」
它不会写「我觉得是 billing」，而是返回类似这样的东西：

```json
{"billing": 0.974, "technical": 0.011, "account": 0.010, "shipping": 0.005}
```

这里有两点很关键：

1. **输出是数字**，你的代码可以直接拿来用。不用做解析，也不会出现「模型回复了错误格式」的情况。
1. **数字应该是诚实的。**如果模型说 0.9，那它应该大约每 10 次对 9 次。这就叫「校准」（calibrated），也是做这一切的根本原因。校准过的置信度让你可以说「0.95 以上的自动处理，其余转人工」。
普通聊天 LLM 恰恰在第 2 点上很糟糕。问它们有多确定，它们会开心地对那些一半时间都会答错的东西说出 95%。

---

## 计划：三个阶段

我们把工作拆成三个阶段，每个阶段只做一件事：

| 阶段 | 任务 | 不该做的事 |
|---|---|---|
| 1. 架构改造 | 把模型改造成给选项打分，而不是写文本 | |
| 2. 结构训练 | 教它读懂问题格式 | 教真实世界知识 |
| 3. RL 训练 | 教它做出校准的决策 | 重新教格式 |

把各阶段的职责分开听起来是件小事，但它救过我们很多次。出了问题，我们清楚地知道该去查哪个阶段。

---

## 环境准备

```bash
pip install mlx mlx-lm
```

```python
import json
import mlx.core as mx
import mlx.nn as nn
from mlx_lm import load
from mlx_lm.tuner import linear_to_lora_layers

model, tok = load("mlx-community/Qwen3-4B-4bit")   # 4-bit so it fits in 24 GB
model.freeze()                                        # base weights stay frozen
linear_to_lora_layers(model, 8, {"rank": 16, "scale": 8.0, "dropout": 0.0})
```

我们只训练最后 8 层上的小型 LoRA 适配器。基座模型对语言已经知道得够多了。我们只想改变它作答的方式，而不是它知道的内容。

---

## 第 1 步：提示词格式

每个问题都渲染成一个 *prefix*（前缀，即上下文）加上每个选项各一条 *branch*（分支）：

```python
SYSTEM = "Judge how well the Option answers the Question, given the State."

def render(state, question, options):
    if not isinstance(state, str):
        state = json.dumps(state, ensure_ascii=False)
    prefix = ("<|im_start|>system\n" + SYSTEM + "<|im_end|>\n"
              "<|im_start|>user\n<State>: " + state + "\n<Question>: " + question + "\n")
    branches = [f"<Option>: {o}<|im_end|>" for o in options]
    return prefix, branches
```

注意，选项列表**没有**写进 prefix。每个选项只存在于自己的 branch 里。这是刻意为之，也是下一步的关键想法。

对于是非题，两个选项就是「no」文本和「yes」文本，按此顺序。对带描述的选择题选项，我们写成 "billing - payments, invoices and refunds" 这样的形式。

---

## 第 2 步：把 LLM 变成打分器（branch 读出）

### **我们的第一次尝试，以及它为什么失败**

我们最初的想法很简单：把所有选项编号放进提示词，再加一个带 256 个输出的分类头，每个选项槽位对应一个输出。选项 1 是槽位 0，选项 2 是槽位 1，依此类推。

在测试超过 6 个选项之前，它看起来一切正常。选项一多，准确率就崩了。查看分类头的权重后，我们找到了原因：第 6 到 255 行基本还停在随机初始值上。我们的训练数据几乎从来没有超过 6 个选项，所以这些槽位从未被训练过。一个有 256 个槽位的模型，只学过其中 6 个。

它还有第二个问题：按顺序列出选项，意味着模型可以学到「答案通常靠前」。这就是位置偏差（position bias），会毁掉校准。

### 修复方案：一个共享打分器，每个选项一条 branch

不用槽位，我们改为：

1. 彻底移除 LM head。
1. 加一个小小的线性层 Linear(2560, 1)，把隐藏状态变成一个分数。
1. 前向跑一次 prefix，然后把每个选项当作独立的 branch 来跑——branch 可以看 prefix，但**不能**看其他选项。
1. 从每条 branch 的最后一个 token 读出分数，再对 branches 做 softmax。

```python
class Gero(nn.Module):
    def __init__(self, backbone, hidden=2560):
        super().__init__()
        self.backbone = backbone
        self.scorer = nn.Linear(hidden, 1, bias=False)
        # Hidden states have a norm around 300, so 1e-3 gives scores spread
        # around 0.3: close to uniform at the start, but not so tiny that
        # gradients die.
        self.scorer.weight = mx.random.normal(self.scorer.weight.shape) * 1e-3

m = Gero(model)
```

接下来是高效运行 branch 的诀窍。MLX 的层接收一个带有 update_and_fetch(k, v) 方法的 cache 对象。我们写了两个小 cache 类。第一个负责前向前缀过程，记录该层的 prefix keys 和 values。第二个把同一份 prefix 提供给每条 branch。

```python
class Record:
    """Prefix pass: remember this layer's keys and values."""
    def __init__(self):
        self.offset = 0
    def update_and_fetch(self, k, v):
        self.k, self.v = k, v
        self.offset += k.shape[2]
        return k, v

class SharePrefix:
    """Branch pass: every branch sees the same prefix keys and values."""
    def __init__(self, rec):
        self.pk, self.pv, self.offset = rec.k, rec.v, rec.offset
    def update_and_fetch(self, k, v):
        B = k.shape[0]                      # number of branches
        pk = mx.broadcast_to(self.pk, (B,) + self.pk.shape[1:])
        pv = mx.broadcast_to(self.pv, (B,) + self.pv.shape[1:])
        return mx.concatenate([pk, k], 2), mx.concatenate([pv, v], 2)

def run(backbone, ids, mask, caches):
    t = backbone.model
    h = t.embed_tokens(ids)
    for layer, c in zip(t.layers, caches):
        h = layer(h, mask, c)
    return t.norm(h)

def branch_logits(m, pre_ids, opt_ids):
    recs = [Record() for _ in m.backbone.model.layers]
    run(m.backbone, mx.array([pre_ids]), "causal", recs)      # prefix, once

    P, Lb = len(pre_ids), max(len(o) for o in opt_ids)
    ids = mx.array([o + [0] * (Lb - len(o)) for o in opt_ids])  # pad branches
    r = mx.arange(Lb)
    mask = mx.concatenate([mx.ones((Lb, P), dtype=mx.bool_),   # see all of the prefix
                           r[:, None] >= r[None, :]], axis=1)  # causal inside the branch
    h = run(m.backbone, ids, mask, [SharePrefix(x) for x in recs])

    last = mx.array([len(o) - 1 for o in opt_ids])
    return m.scorer(h[mx.arange(len(opt_ids)), last].astype(mx.float32)).squeeze(-1)
```

mask 是其中的关键部分。每条 branch 的那一行能看到：

```markdown
            prefix tokens        its own tokens
branch A:   [1 1 1 1 1 1 1 1]    [causal]
branch B:   [1 1 1 1 1 1 1 1]    [causal]      <- but never A's tokens
```

由于各 branch 是 batch 里各自独立的行，选项 B 在物理上根本看不到选项 A。短 branch 末尾的 padding 也无所谓，因为我们从最后一个真实 token 读分数，而且 mask 是因果的（causal）。

这个设计带来的好处：

- **从构造上就没有位置偏差。**打乱选项顺序，每个分数分毫不差。我们测过：最大差异是 0.0。
- **任意数量的选项。**一个共享打分器意味着 2 个选项和 256 个选项用的是同一套权重。不存在没训练过的槽位。
- **便宜。**prefix（通常是比较长的那部分）只计算一次，不管有多少个选项。
选项之间仍然存在竞争，通过 softmax 实现。它们各自单独打分，但放在一起训练。

一个你应该永远跑一下的快速健全性测试：

```python
pre, brs = render("Charged twice for my invoice.", "Which team?", ["billing", "technical", "shipping"])
enc = lambda s: tok.encode(s, add_special_tokens=False)
a = mx.softmax(branch_logits(m, enc(pre), [enc(b) for b in brs]))
b = mx.softmax(branch_logits(m, enc(pre), [enc(b) for b in reversed(brs)]))
print(a, b[::-1])   # should be identical
```

---

## 第 3 步：阶段 2 的数据，教格式而不教内容

阶段 2 只有一件事：教模型正确读懂问题格式。大量选项、有序等级、不同措辞的是非题、否定句。

阶段 2 的第一版用的是真实数据集（新闻主题、情感等等）。能用，但模型在同时学两样东西：格式和内容。出了问题，我们分不清是哪一部分坏了。

于是我们换成了**无内容**（content-free）数据。虚构的货箱、货架和像 QX-417A 这种毫无意义的编码。想答对，唯一的办法就是真正去读状态和问题。

下面是我们是非题生成器的简化版：

```python
import random

NOUL_OPTS = [("no", "yes"), ("false", "true"), ("incorrect", "correct")]

def make_yes_no(R, i):
    n = R.randint(2, 8)
    shelves = R.sample(range(1, 100), n)
    items = [f"{R.choice(['QX','FJ','RT','ZP'])}-{R.randint(100,999)}{R.choice('ABCDEFG')}" for _ in range(n)]
    ask = R.randrange(n)

    truth = (i % 2 == 0)                         # exactly 50/50 on the fact
    # the wrong item is taken from ANOTHER shelf in the same state,
    # so "is this code in the text?" never gives away the answer
    probe = items[ask] if truth else items[(ask + 1) % n]
    negated = (i // 2) % 2 == 1                  # exactly 50/50 on negation

    if negated:
        q = f"Is it false that shelf {shelves[ask]} holds {probe}?"
    else:
        q = f"Does shelf {shelves[ask]} hold {probe}?"
    state = "Manifest: " + "; ".join(f"shelf {s} holds {it}" for s, it in zip(shelves, items)) + "."
    no, yes = R.choice(NOUL_OPTS)
    return dict(state=state, question=q, options=[no, yes], target=int(truth != negated))
```

留意这些小细节，因为每一个都修掉了一个我们真踩过的 bug：

- **事实恰好 50/50**，否定也恰好 50/50。如果「yes」在 60% 的情况下是对的，模型就只会学成无脑说 yes。
- **错误答案来自同一个状态。**早期版本里错误编码是随机生成的，于是「这个编码在文本里出现过吗？」不用读题就能解出问题。模型立刻就找到了这条捷径。
- **是非题的措辞会变**（no/yes、false/true、incorrect/correct），这样模型就没法死记一个词。
我们还为其他题型写了类似的生成器：选择题（1 到 256 个选项，按对数均匀采样，这样大列表真的会出现）、评分题（2 到 10 个有序等级，各等级均衡），以及一些阅读技能：否定、「原文真的这么说了吗？」、把正确的属性绑定到正确的事物上。

### 否定捷径（一个值得了解的失误）

有一阵子，为了修否定的问题，我们加了大量否定问句。训练准确率上去了，我们很高兴。结果一个真实蕴含（entailment）任务上的准确率从 0.775 掉到了 0.617。

事情是这样的：在我们的数据里，「not」「false」这类否定词只出现在否定问句里。于是模型学到了「看到否定词就把答案反过来」。而在真实文本里，否定词到处都是——在状态里、在普通问题里——模型开始翻转那些不该翻转的答案。

修复办法是*去相关*（decorrelate）：在状态和普通问题里也放否定词，让这个词本身不携带任何信息。

---

## 第 4 步：训练之前先检查数据

这是整个项目里最大的一课。我们在坏数据上浪费的时间比其他任何事情都多。所以我们写了一个检查器，在每次训练前运行，一旦发现不对劲就拒绝继续。

下面是其中一些检查：

```python
from collections import Counter

def check_leak(train, holdout):
    """Train and holdout must not share a state, not just an index."""
    seen = {json.dumps(e["state"], sort_keys=True) for e in train}
    leaked = [e for e in holdout if json.dumps(e["state"], sort_keys=True) in seen]
    assert not leaked, f"{len(leaked)} holdout states also appear in train"

def check_position(data):
    """The right answer should not prefer one position."""
    for k in {e_k for e_k in (len(e["options"]) for e in data) if e_k <= 6}:
        rows = [e for e in data if len(e["options"]) == k]
        top = Counter(e["target"] for e in rows).most_common(1)[0][1] / len(rows)
        assert top < 1 / k + 0.10, f"k={k}: one slot holds {top:.0%} of answers"

def check_majority_text(data):
    """If always picking the same option TEXT scores well, the item can be solved without reading."""
    gold = Counter(e["options"][e["target"]] for e in data)
    worst = gold.most_common(1)[0][1] / len(data)
    assert worst < 0.6, f"answer text '{gold.most_common(1)[0][0]}' is right {worst:.0%} of the time"

def check_string_presence(data):
    """'Pick whichever option appears in the state' must not work."""
    solved = 0
    for e in data:
        hits = [i for i, o in enumerate(e["options"]) if o in json.dumps(e["state"])]
        solved += hits == [e["target"]]
    assert solved / len(data) < 0.05, f"string presence solves {solved/len(data):.0%}"
```

最后一条特别阴险。在我们的选择题数据里，正确项总是写在状态里，而错误项是随机编码。「选那个在文本里出现过的选项」几乎能解掉所有题。从同一个状态里取干扰项之后，这个问题才修好。

另外，永远要主动测试你的检查器：造一个已知有泄漏的数据集，确认检查器能抓住它。一个从不失败的检查器，可能只是它自己坏了。

---

## 第 5 步：阶段 2 训练

损失就是针对目标分布的普通交叉熵。我们用软目标（完整的概率列表）而不是单个索引，反正阶段 3 也需要它。

```python
def stage2_loss(model, batch):
    total = 0.0
    for e in batch:
        logits = branch_logits(model, e["pre_ids"], e["opt_ids"])
        logp = logits - mx.logsumexp(logits)
        target = mx.array(e["soft"])            # one-hot for normal items
        total = total - (target * logp).sum()
    return total / len(batch)
```

### **两个优化器，以及为什么放大梯度行不通**

打分器是全新初始化的，需要比 LoRA 权重更大的学习率。我们最初的尝试是把打分器的梯度乘以 20。在 Adam 下这毫无作用。

Adam 会把每个梯度除以一个对其自身大小的滑动估计。你把梯度乘以 20，这个估计也跟着放大 20 倍，两者正好抵消。于是我们的「20 倍学习率」整整一轮训练都是无效操作。真正的解决办法是用两个优化器：

```python
import mlx.optimizers as optim

opt_scorer = optim.AdamW(learning_rate=5e-4)
opt_lora = optim.AdamW(learning_rate=3e-5)
step_fn = nn.value_and_grad(m, stage2_loss)

for step in range(steps):
    batch = rng.sample(train, 8)
    loss, g = step_fn(m, batch)
    g, _ = optim.clip_grad_norm(g, 1.0)
    p = m.trainable_parameters()
    m.update(opt_scorer.apply_gradients({"scorer": g["scorer"]}, {"scorer": p["scorer"]}))
    m.update(opt_lora.apply_gradients({"backbone": g["backbone"]}, {"backbone": p["backbone"]}))
    mx.eval(m.parameters(), opt_scorer.state, opt_lora.state)
```

### **阶段 2 什么时候算完成？**

我们定了一条退出规则：每个结构族都要在留出条目上达到 0.98 的准确率，**并且**真实任务上的准确率不能下降。后半句很重要。在虚构的货箱上刷到满分、同时悄悄弄坏真实阅读能力，是太容易发生的事。

还有，要经常保存 checkpoint。我们有一次杀掉了一个没有进展的训练，把它仅有的一份 checkpoint 也弄丢了。现在我们每 150 步保存一次。

---

## 第 6 步：阶段 3，RL 奖励

正是这一部分让它成为决策模型。目标是：**模型的概率应当与它实际答对的频率相符。**

### 什么是正规评分规则（proper scoring rule）？

想象一枚 70% 概率正面朝上的硬币。你必须报出一个概率，然后按实际抛掷的结果拿奖励。如果一个奖励让你报出真值 0.7 成为最优策略，它就是 *proper*（正规的）。不是报 1.0 显得自信，也不是报 0.5 求稳。

log 分数（对实际发生的结果取 log p）是 proper 的，Brier 分数（Brier score）也是。如果你的奖励不 proper，RL 会兴高采烈地找到作弊的办法。

### 那个显而易见的奖励是坏的

我们最先想到的奖励听起来很合理：

> 让模型选一个答案。再根据它对这个答案的置信度对「答对与否」预测得有多好来给它奖励。

把这个想法写成代码，并且写成精确的期望值形式，这样我们能看到训练最终停在哪里：

```python
truth = mx.array([0.174, 0.261, 0.005, 0.001, 0.141, 0.418])   # true answer odds

def naive_loss(z):
    p = mx.softmax(z)
    c = mx.clip(p, 1e-6, 1 - 1e-6)
    # choose option a with prob p(a), score how well p(a) predicts "a is right"
    per_choice = truth * mx.log(c) + (1 - truth) * mx.log1p(-c)
    return -(p * per_choice).sum()
```

对它跑梯度下降，看看它停在哪：

```markdown
truth  [0.174, 0.261, 0.005, 0.001, 0.141, 0.418]
naive  [0.200, 0.181, 0.208, 0.208, 0.202, 0.001]
```

正确答案（0.418）被压到了 0.001。模型找到了一个作弊方式：挑一个几乎肯定错的选项，说「我不太确定」，校准得分就很好看。它「校准」得完美无缺，却完全没用。

### **我们的奖励**

我们把它拆成都 proper 的两部分：

1. **完整分布：**从条目的真实答案分布中采样真实结果，奖励 log p(outcome)。这会把整个分布推向真值。
1. **决策校准：**看模型的首选答案和它的置信度 c。采到的结果与它一致时奖励 log c，不一致时奖励 log(1 - c)。这让实际决策的置信度变得诚实。

```python
def rl_loss(logits, soft, G, rng, lam=1.0):
    logp = logits - mx.logsumexp(logits)
    k = len(soft)
    outcomes = rng.choices(range(k), weights=soft, k=G)   # G sampled outcomes

    top = int(mx.argmax(logp).item())
    c = mx.clip(mx.exp(logp[top]), 1e-6, 1 - 1e-6)

    full = mx.stack([logp[y] for y in outcomes]).mean()
    hit_rate = sum(1 for y in outcomes if y == top) / G
    calib = hit_rate * mx.log(c) + (1 - hit_rate) * mx.log1p(-c)
    return -(full + lam * calib)
```

和之前一样的测试：

```markdown
truth  [0.174, 0.261, 0.005, 0.001, 0.141, 0.418]
ours   [0.174, 0.261, 0.005, 0.001, 0.141, 0.418]
```

它正好落在真值上。**对你发明的任何奖励，永远要跑这个测试。**只花一分钟，却本可以为我们省下好几天。

我们每个条目用 G = 8 个结果，结果从数据中采样，而不是从模型中采。模型永远不会被直接告知真实概率。它只看得到发生了什么。

### 「真实概率」从哪里来？

对普通的标注数据，目标是 one-hot（该标签以概率 1 发生）。但校准模型也需要见到真正不确定的样本，否则它学到的永远只有「要 100% 确定」。

所以我们生成带软标签的*模糊*条目。比如一段简短日志，两个选项与证据契合得同样好，目标就是 [0.5, 0.5]，正确行为是输出 0.5。我们把确定条目和模糊条目混在一起（最终训练中确定条目约占 40%），并在损失里给模糊条目更高的权重，免得占多数的确定条目把它们淹没。

### KL 锚定的失误

很多 RL 配方都会加一个 KL 惩罚，让模型保持在出发点附近。我们也加了一个。结果更糟了。

原因是：KL 惩罚是把模型往*旧*模型的答案方向拉。这等于多了一个与真值竞争的目标，于是最优答案不再是真值，而是落在真值和旧模型之间的某处。我们的模型变得不那么锐利：它不再区分简单样本和困难样本。

对于任何要加进损失里的东西，我们最终遵守的规则是：**在模型概率等于真值的那一点上，附加项的梯度必须为零。**不为零，它就会挪动最优点。KL 锚定过不了这个测试，所以我们把它的权重设成了 0。

### 另外两个坑过我们的小问题

- **Brier 对比 log 分数。**在用 RL 奖励之前，我们训练阶段 3 用的是直接对软标签算的损失，而且一开始用的是 Brier。Brier 是 proper 的，但模型非常自信时它的梯度会变得极小。在 0.999 的置信度下，它比 log 分数的梯度小大约 250 倍，所以过度自信的模型几乎得不到纠正。我们的 RL 奖励建立在 log 分数之上，避开了这个问题。
- **裁剪梯度。**log 分数恰恰在你正想修复的过度自信样本上会产生很大的梯度。一次没裁剪的尖峰就能毁掉一整轮训练。

---

## 第 7 步：正确地度量校准

度量错了，就无从改进。而我们有一段时间就度量错了。

### 可靠性与分辨力

只看准确率是不够的。我们把 Brier 分数拆成两部分（这叫 Murphy 分解）：

- **可靠性（Reliability）：**置信度离实际准确率有多远。越低越好。这就是校准。
- **分辨力（Resolution）：**置信度能把答对和答错的答案区分得多好。越高越好。
为什么两个都要？一个在答对率 70% 的任务上永远说「70%」的模型，可靠性是完美的。但它毫无用处，因为它分不清简单样本和困难样本。分辨力能抓住这一点。

```python
def murphy(rows, bins=10):
    """rows: list of (confidence, correct) pairs."""
    n = len(rows)
    base = sum(o for _, o in rows) / n
    groups = [[] for _ in range(bins)]
    for c, o in rows:
        groups[min(bins - 1, int(c * bins))].append((c, o))
    rel = res = 0.0
    for g in groups:
        if not g:
            continue
        conf = sum(c for c, _ in g) / len(g)
        acc = sum(o for _, o in g) / len(g)
        rel += len(g) / n * (conf - acc) ** 2
        res += len(g) / n * (acc - base) ** 2
    return rel, res
```

### 选择性准确率

这才是实践中真正要紧的数字：如果我只在模型置信度不低于 0.9 时才行动，这部分有多准，又能覆盖我多少数据？

```python
def selective(rows, thr=0.9):
    hi = [(c, o) for c, o in rows if c >= thr]
    return dict(coverage=len(hi) / len(rows),
                accuracy=sum(o for _, o in hi) / len(hi),
                promised=sum(c for c, _ in hi) / len(hi))
```

如果 accuracy 接近 promised，你就可以信任这个阈值。

### 指标的 bug

对模糊条目，我们最初的做法是：答案与最可能的标签一致就算「正确」。听起来没问题，但想想一个概率为 [0.55, 0.45] 的条目。诚实的模型说 0.55。它选了第一个选项，按我们的指标 100%「正确」，于是它 0.55 的置信度看起来严重*欠*自信。而一个说 0.99 的过度自信模型看起来完美。

我们的指标奖励的恰恰是我们想消除的行为。用数字说：诚实模型的可靠性误差是 0.1019，过度自信的模型是 0.0001。

修复办法：对模糊条目，「正确」取所选选项的真实概率 soft[pred]，而不是 0/1 匹配。

```markdown
correct = soft[pred]          # not: 1.0 if pred == argmax(soft) else 0.0
```

修好之后，我们不得不重新度量每一个 checkpoint，一些已经写下的结论也随之翻转。

---

## 第 8 步：守护各个阶段

阶段 3 该教的是决策，不是格式。但 RL 更新的是同一批 LoRA 权重，所以它可能慢慢抹掉阶段 2 教会的东西。

所以在阶段 3 期间，我们持续运行一个结构探针：从未训练过的全新无内容问题。如果它的准确率朝任一方向变动超过 0.01，就说明出问题了：

- 如果**下降**，是阶段 3 在覆盖阶段 2。
- 如果**上升**，说明阶段 2 其实没做完。
我们还在训练脚本里放了一个硬检查：只要有任何纯结构数据混进阶段 3 的训练集，脚本就直接崩溃。本该分开的阶段，在代码里也应该是分开的，而不只是在我们脑子里。

---

## 第 9 步：导出为普通的 Hugging Face 模型

训练是在 4-bit 基座加 LoRA 上完成的，这只能在 MLX 里运行。要发布，我们：

1. 把每个 LoRA 合并进对应的层。你不能把浮点更新直接加到打包好的 4-bit 权重上，所以先反量化：W = dequantize(W_q) + scale * B @ A。
1. 把其余所有层反量化为 bf16。
1. 把我们的打分器改名为 score.weight，保存为带一个 label 的 **Qwen3ForSequenceClassification**。
最后一步之所以可行，是因为我们的 branch 读出在数学上等价于：把每个选项当作独立完整的序列跑一遍，再从它的最后一个 token 读出分数。这恰好就是 Hugging Face 序列分类头所做的事。我们的技巧只是通过共享 prefix 让它更快。

```python
from mlx_lm.utils import dequantize_model
from mlx.utils import tree_flatten, tree_unflatten

fused = [(n, mod.fuse(dequantize=True)) for n, mod in m.backbone.named_modules() if hasattr(mod, "fuse")]
m.backbone.update_modules(tree_unflatten(fused))
bb = dequantize_model(m.backbone)

weights = {k: v.astype(mx.bfloat16) for k, v in tree_flatten(bb.parameters())}
weights.pop("lm_head.weight", None)               # tied embeddings, no LM head needed
weights["score.weight"] = m.scorer.weight.astype(mx.bfloat16)
mx.save_safetensors("gero-4b/model.safetensors", weights, metadata={"format": "pt"})
# plus config.json with architectures=["Qwen3ForSequenceClassification"], num_labels=1
```

然后做验证。我们只加载导出的文件，在 1,866 个留出条目上与训练 checkpoint 对比。首选答案在 98.8% 的条目上一致，而那些微小的差异与正常的数值噪声处于同一量级。

---

## 我们犯过的错（你就不用再犯了）

1. 一个 256 槽位的分类头，其中只有 6 个槽位被训练过。
1. 否定词只出现在否定问句里，于是模型学会了「翻转」捷径。
1. 错误答案不在状态里，于是「提到了吗？」就能解题。
1. 在 Adam 下靠放大梯度来获得更高学习率。会相互抵消。
1. 一个不 proper 的天真 RL 奖励，把正确答案压到了 0.001。
1. 一个把最优点推离真值的 KL 锚定。
1. 一个在模糊条目上奖励过度自信的校准指标。
---

模型在 Hugging Face 上：[vixhal-baraiya/Gero-4B](https://huggingface.co/vixhal-baraiya/Gero-4B)，想试的话可以去试试。

**继续构建，继续学习。**
