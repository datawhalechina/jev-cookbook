/* TypeSafe 中文文档 — 交互实验室（本地演示 + 真实 API + Playground 深链） */
(function () {
  "use strict";

  var labRoot = document.querySelector(".lab");
  if (!labRoot) return;
  var cfg = JSON.parse(document.getElementById("lab-config").textContent);

  /* ---------- 工具 ---------- */
  function tokenize(text) {
    var out = new Set();
    var en = String(text || "").toLowerCase().match(/[a-z0-9]{2,}/g) || [];
    en.forEach(function (w) { out.add(w); });
    var cjk = String(text || "").match(/[\u4e00-\u9fff]/g) || [];
    cjk.forEach(function (c) { out.add(c); });
    for (var i = 0; i + 1 < cjk.length; i++) out.add(cjk[i] + cjk[i + 1]);
    return out;
  }
  function overlap(a, b) {
    if (!a.size || !b.size) return 0;
    var hit = 0;
    b.forEach(function (x) { if (a.has(x)) hit++; });
    return hit / Math.sqrt(a.size * b.size);
  }
  function softmax(xs, temp) {
    var t = temp || 0.12;
    var mx = Math.max.apply(null, xs);
    var es = xs.map(function (x) { return Math.exp((x - mx) / t); });
    var s = es.reduce(function (a, b) { return a + b; }, 0);
    return es.map(function (e) { return e / s; });
  }
  function entropyConfidence(probs) {
    var H = 0;
    probs.forEach(function (p) { if (p > 1e-9) H -= p * Math.log(p); });
    var Hmax = Math.log(probs.length);
    var c = 1 - (Hmax > 0 ? H / Hmax : 0);
    return Math.max(0.3, Math.min(0.98, 0.35 + c * 0.65));
  }
  function clamp01(x) { return Math.max(0.01, Math.min(0.99, x)); }

  /* ---------- 本地演示模拟器（非真实模型，仅演示答案形状） ---------- */
  function simulate(state, questions) {
    var st = tokenize(state);
    var answers = {};
    Object.keys(questions).forEach(function (id) {
      var q = questions[id];
      var ins = tokenize(q.instructions || "");
      if (q.type === "choice") {
        var keys = Object.keys(q.criteria);
        var scores = keys.map(function (k) {
          var d = tokenize(String(q.criteria[k] == null ? k : q.criteria[k]));
          return overlap(st, d) * 1.0 + overlap(ins, d) * 0.25 + overlap(st, tokenize(k)) * 0.4;
        });
        var flat = scores.every(function (s) { return s === 0; });
        var probsArr = flat ? keys.map(function () { return 1 / keys.length; })
                            : softmax(scores.map(function (s) { return s + 0.02; }));
        var probs = {};
        keys.forEach(function (k, i) { probs[k] = probsArr[i]; });
        var sorted = probsArr.slice().sort(function (a, b) { return b - a; });
        answers[id] = { type: "choice", choice: keys[probsArr.indexOf(sorted[0])],
                        probabilities: probs,
                        confidence: flat ? 0.3 : entropyConfidence(probsArr) };
      } else if (q.type === "score") {
        var levels = q.criteria;
        var ls = levels.map(function (d, i) {
          var dt = tokenize(String(d));
          return overlap(st, dt) * (1 + i * 0.25) + overlap(ins, dt) * 0.2;
        });
        var allZero = ls.every(function (s) { return s === 0; });
        var ps = allZero ? levels.map(function (_, i) { return i === 0 ? 0.5 : 0.5 / (levels.length - 1 || 1); })
                         : softmax(ls.map(function (s) { return s + 0.02; }));
        var exp = 0; ps.forEach(function (p, i) { exp += p * i; });
        var probs2 = {}; levels.forEach(function (_, i) { probs2[i] = ps[i]; });
        answers[id] = { type: "score", score: Math.round(exp * 100) / 100,
                        probabilities: probs2,
                        confidence: allZero ? 0.35 : entropyConfidence(ps) };
      } else { // noul
        var o = overlap(st, ins);
        var yes = clamp01(0.45 + o * 2.2);
        answers[id] = { type: "noul", noul: Math.round(yes * 100) / 100 };
      }
    });
    return { model: "本地演示（非真实模型）", answers: answers };
  }

  /* ---------- 真实 API ---------- */
  function callReal(state, questions, apiKey, cb, err) {
    fetch("https://api.typesafe.ai/v1/systemone", {
      method: "POST",
      headers: { "Authorization": "Bearer " + apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "jev-latest", state: state, questions: questions })
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      var answers = {};
      Object.keys(data.answers || {}).forEach(function (id) {
        var a = data.answers[id];
        if (a.type === "score") {
          var p = {}; Object.keys(a.probabilities || {}).forEach(function (k) { p[k] = a.probabilities[k]; });
          answers[id] = { type: "score", score: a.score, probabilities: p, confidence: a.confidence };
        } else if (a.type === "choice") {
          answers[id] = { type: "choice", choice: a.choice, probabilities: a.probabilities, confidence: a.confidence };
        } else {
          answers[id] = { type: "noul", noul: a.noul };
        }
      });
      cb({ model: data.model, answers: answers });
    }).catch(function (e) { err(e.message || String(e)); });
  }

  /* ---------- 浏览器直连受限时：给可复制的 Python 调用代码 ---------- */
  function renderCurlFallback(state, questions, key, msg) {
    var pyState = state.trim().startsWith("{") ? state : JSON.stringify(state);
    var py = "from typesafe_sdk import TypeSafeClient\n\n" +
      "client = TypeSafeClient(api_key=\"YOUR_KEY\")  # 也可用环境变量 TYPESAFE_API_KEY\n" +
      "result = client.system_one(\n" +
      "    " + pyState + ",\n" +
      "    " + JSON.stringify(questions, null, 4).replace(/\n/g, "\n    ").replace(/"/g, '"') + ",\n" +
      ")\n" +
      "print(result.answers)";
    document.getElementById("lab-results").innerHTML =
      '<div class="lab-error"><b>浏览器直连受限</b>：官方 API 未开放跨域（CORS），网页无法直接调用' +
      '（' + esc(msg) + '）。下面是等价的 Python 调用，复制到本地运行即可得到真实结果：' +
      '<button class="lab-copy-py" type="button" id="lab-copy-py">复制代码</button>' +
      '<pre class="lab-py"></pre></div>';
    document.querySelector(".lab-py").textContent = py;
    document.getElementById("lab-copy-py").addEventListener("click", function () {
      var b = this;
      (navigator.clipboard ? navigator.clipboard.writeText(py) : Promise.reject())
        .then(function () { b.textContent = "已复制"; },
              function () { b.textContent = "请手动选择复制"; });
    });
  }

  /* ---------- Playground 深链 ---------- */
  function playgroundHref(state, questions) {
    var payload = {
      apiVersion: "v1",
      documentText: state,
      promptsText: JSON.stringify(questions, null, 2),
      selectedModels: ["jev-latest"]
    };
    var share = window.LZStringUriSafe
      .compressToEncodedURIComponent(JSON.stringify(payload));
    return "https://console.typesafe.ai/decode#share/" + share;
  }

  /* ---------- 渲染 ---------- */
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function bar(label, p, isTop) {
    var pct = Math.round(p * 1000) / 10;
    return '<div class="lab-bar-row' + (isTop ? ' top' : '') + '">' +
      '<span class="lab-bar-label">' + esc(label) + '</span>' +
      '<div class="lab-bar-track"><div class="lab-bar-fill" style="width:' + pct + '%"></div></div>' +
      '<span class="lab-bar-val">' + pct.toFixed(1) + '%</span></div>';
  }
  function renderAnswers(resp) {
    var box = document.getElementById("lab-results");
    var html = '<div class="lab-model-tag">模型：' + esc(resp.model) + '</div>';
    Object.keys(resp.answers).forEach(function (id) {
      var a = resp.answers[id];
      if (a.type === "choice") {
        var entries = Object.keys(a.probabilities).map(function (k) { return [k, a.probabilities[k]]; });
        entries.sort(function (x, y) { return y[1] - x[1]; });
        html += '<div class="lab-card"><div class="lab-q-head"><span class="lab-q-id">' + esc(id) +
          '</span><span class="lab-type-tag choice">choice</span>' +
          '<span class="lab-conf">confidence ' + a.confidence.toFixed(2) + '</span></div>' +
          '<div class="lab-choice-pick">→ <b>' + esc(a.choice) + '</b></div>' +
          entries.map(function (e, i) { return bar(e[0], e[1], i === 0); }).join("") + '</div>';
      } else if (a.type === "score") {
        var lv = Object.keys(a.probabilities).map(function (k) { return [k, a.probabilities[k]]; });
        lv.sort(function (x, y) { return x[0] - y[0]; });
        var legend = cfg.questions[id] && cfg.questions[id].criteria;
        html += '<div class="lab-card"><div class="lab-q-head"><span class="lab-q-id">' + esc(id) +
          '</span><span class="lab-type-tag score">score</span>' +
          '<span class="lab-conf">confidence ' + a.confidence.toFixed(2) + '</span></div>' +
          '<div class="lab-score-big">score = <b>' + a.score.toFixed(2) + '</b>' +
          (legend ? ' <span class="lab-legend-note">（量表 0–' + (legend.length - 1) + '）</span>' : '') + '</div>' +
          lv.map(function (e, i) {
            var lbl = e[0] + (legend && legend[e[0]] ? ' · ' + String(legend[e[0]]).slice(0, 22) : '');
            return bar(lbl, e[1], false);
          }).join("") + '</div>';
      } else {
        var pct = Math.round(a.noul * 100);
        var verdict = a.noul >= 0.65 ? "倾向于「是」" : (a.noul <= 0.35 ? "倾向于「否」" : "不确定（≈0.5）");
        html += '<div class="lab-card"><div class="lab-q-head"><span class="lab-q-id">' + esc(id) +
          '</span><span class="lab-type-tag noul">noul</span></div>' +
          '<div class="lab-noul-meter"><div class="lab-noul-fill" style="width:' + pct + '%"></div>' +
          '<span class="lab-noul-num">' + a.noul.toFixed(2) + '</span></div>' +
          '<div class="lab-noul-verdict">' + verdict + ' — noul 值即「是」的概率</div></div>';
      }
    });
    box.innerHTML = html;
  }

  function currentQuestions() {
    var qs = {};
    Object.keys(cfg.questions).forEach(function (id) {
      var q = cfg.questions[id];
      var edited = document.getElementById("lab-ins-" + id);
      qs[id] = { type: q.type, instructions: edited ? edited.value : q.instructions, criteria: q.criteria };
    });
    return qs;
  }

  /* ---------- 初始化 ---------- */
  document.getElementById("lab-state").value = cfg.state;
  var qBox = document.getElementById("lab-questions");
  var qHtml = "";
  Object.keys(cfg.questions).forEach(function (id) {
    var q = cfg.questions[id];
    qHtml += '<div class="lab-q-edit"><span class="lab-q-id">' + esc(id) +
      ' <span class="lab-type-tag ' + q.type + '">' + q.type + '</span></span>' +
      '<input id="lab-ins-' + esc(id) + '" value="' + esc(q.instructions) + '" /></div>';
  });
  qBox.innerHTML = qHtml;

  var keyInput = document.getElementById("lab-key");
  try { keyInput.value = localStorage.getItem("tszh-lab-key") || ""; } catch (e) {}

  document.getElementById("lab-run").addEventListener("click", function () {
    var btn = this;
    var state = document.getElementById("lab-state").value;
    var questions = currentQuestions();
    var key = keyInput.value.trim();
    try { if (key) localStorage.setItem("tszh-lab-key", key); else localStorage.removeItem("tszh-lab-key"); } catch (e) {}
    if (key) {
      btn.disabled = true; btn.textContent = "调用中…";
      callReal(state, questions, key, function (resp) {
        btn.disabled = false; btn.textContent = "▶ 运行（真实 API）";
        renderAnswers(resp);
      }, function (msg) {
        btn.disabled = false; btn.textContent = "▶ 运行（真实 API）";
        renderCurlFallback(state, questions, key, msg);
      });
    } else {
      renderAnswers(simulate(state, questions));
    }
  });

  document.getElementById("lab-playground").addEventListener("click", function (e) {
    e.preventDefault();
    var url = playgroundHref(document.getElementById("lab-state").value, currentQuestions());
    window.open(url, "_blank", "noopener");
  });

  renderAnswers(simulate(cfg.state, cfg.questions));
})();
