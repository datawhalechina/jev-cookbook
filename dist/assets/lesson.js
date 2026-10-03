/* TypeSafe 中文文档 — 内嵌教程（notebook 逐步揭示的伪交互教学） */
(function () {
  "use strict";
  var root = document.getElementById("lesson");
  if (!root) return;
  var cfg = JSON.parse(document.getElementById("lesson-data").textContent);
  var cellsBox = document.getElementById("lesson-cells");
  var nextBtn = document.getElementById("lesson-next");
  var allBtn = document.getElementById("lesson-all");
  var resetBtn = document.getElementById("lesson-reset");
  var fill = document.getElementById("lesson-fill");
  var pos = document.getElementById("lesson-pos");

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function cellHtml(item, animate) {
    if (item.k === "md") {
      return '<div class="lc lc-md' + (animate ? ' lc-anim' : '') + '">' + item.h + '</div>';
    }
    var runBadge = item.o
      ? '<span class="lc-run">▶ 运行</span>'
      : '<span class="lc-run muted">▶ 运行（此格无附带输出）</span>';
    var html = '<div class="lc lc-code' + (animate ? ' lc-anim' : '') + '">' +
      '<div class="lc-head"><span class="lc-in">In [' + item.n + ']</span>' + runBadge + '</div>' +
      '<pre class="lc-src">' + esc(item.c) + '</pre>';
    if (item.o) {
      html += '<div class="lc-outwrap" data-out="1"><div class="lc-head">' +
        '<span class="lc-out-label">Out [' + item.n + ']</span></div>' +
        '<pre class="lc-out">' + esc(item.o) + '</pre></div>';
    }
    html += '</div>';
    return html;
  }

  var revealed = 0;
  var running = false;

  function updateMeta() {
    pos.textContent = revealed + " / " + cfg.cells.length;
    fill.style.width = (cfg.cells.length ? (revealed / cfg.cells.length) * 100 : 0) + "%";
    nextBtn.disabled = revealed >= cfg.cells.length || running;
    nextBtn.textContent = revealed >= cfg.cells.length ? "✔ 已到结尾" : "▶ 下一步";
  }

  function scrollToCell(el) {
    var y = el.getBoundingClientRect().top + window.scrollY - 90;
    window.scrollTo({ top: y, behavior: "smooth" });
  }

  function revealNext(cb) {
    if (revealed >= cfg.cells.length) return cb && cb();
    var item = cfg.cells[revealed];
    revealed++;
    var wrap = document.createElement("div");
    wrap.innerHTML = cellHtml(item, true);
    var node = wrap.firstChild;
    cellsBox.appendChild(node);
    updateMeta();
    scrollToCell(node);
    if (item.k === "code" && item.o) {
      running = true;
      nextBtn.disabled = true;
      var outwrap = node.querySelector(".lc-outwrap");
      var src = node.querySelector(".lc-src");
      outwrap.style.display = "none";
      var badge = node.querySelector(".lc-run");
      badge.textContent = "⏳ 运行中…";
      badge.classList.add("running");
      setTimeout(function () {
        outwrap.style.display = "";
        outwrap.classList.add("lc-out-anim");
        badge.textContent = "✔ 已运行";
        badge.classList.remove("running");
        badge.classList.add("done");
        src && src.classList.add("lc-src-done");
        running = false;
        updateMeta();
        cb && cb();
      }, 650);
    } else {
      cb && cb();
    }
  }

  nextBtn.addEventListener("click", function () { revealNext(); });
  allBtn.addEventListener("click", function () {
    (function loop() {
      if (revealed < cfg.cells.length) {
        revealNext(revealed < cfg.cells.length ? loop : null);
        if (running) { setTimeout(loop, 120); }
      }
    })();
  });
  resetBtn.addEventListener("click", function () {
    cellsBox.innerHTML = "";
    revealed = 0;
    updateMeta();
    window.scrollTo({ top: root.getBoundingClientRect().top + window.scrollY - 80, behavior: "smooth" });
  });

  updateMeta();
  /* 首格自动展示，让读者立刻看到形态 */
  revealNext();
})();
