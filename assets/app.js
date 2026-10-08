/* Jev Cookbook — 课程与参考文档交互 */
(function () {
  "use strict";

  /* ---------- 深色模式 ---------- */
  var root = document.documentElement;
  var toggle = document.getElementById("theme-toggle");
  function applyTheme(dark) {
    root.classList.toggle("dark", dark);
    toggle.textContent = dark ? "☀️" : "🌙";
    toggle.setAttribute("aria-label", dark ? "切换浅色模式" : "切换深色模式");
    try { localStorage.setItem("tszh-theme", dark ? "dark" : "light"); } catch (e) {}
  }
  var saved = null;
  try { saved = localStorage.getItem("tszh-theme"); } catch (e) {}
  applyTheme(saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches);
  toggle.addEventListener("click", function () {
    applyTheme(!root.classList.contains("dark"));
  });

  /* ---------- 移动端侧栏 ---------- */
  var sidebar = document.getElementById("sidebar");
  var mask = document.getElementById("sidebar-mask");
  var menuBtn = document.getElementById("menu-btn");
  menuBtn.addEventListener("click", function () {
    var open = sidebar.classList.toggle("open");
    mask.classList.toggle("show", open);
    menuBtn.setAttribute("aria-expanded", String(open));
  });
  mask.addEventListener("click", function () {
    sidebar.classList.remove("open");
    mask.classList.remove("show");
    menuBtn.setAttribute("aria-expanded", "false");
  });

  /* ---------- 侧栏分组折叠 ---------- */
  document.querySelectorAll(".nav-group-title").forEach(function (btn) {
    btn.addEventListener("click", function () {
      btn.parentElement.classList.toggle("open");
    });
  });

  /* ---------- 代码复制 ---------- */
  document.querySelectorAll(".codeblock, .sdk-signature").forEach(function (block) {
    var btn = block.querySelector(".cb-copy");
    var code = block.querySelector("pre code");
    if (!btn || !code) return;
    btn.addEventListener("click", function () {
      var text = code.textContent;
      function done(ok) {
        btn.textContent = ok ? "已复制" : "复制失败";
        btn.classList.add("copied");
        setTimeout(function () {
          btn.textContent = "复制";
          btn.classList.remove("copied");
        }, 1600);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done(true); },
          function () { done(false); });
      } else {
        var ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        done(ok);
      }
    });
  });

  
  /* ---------- Mermaid 图 ---------- */
  var mermaidBlocks = document.querySelectorAll(".mermaid");
  if (mermaidBlocks.length) {
    var mermaidDone = false;
    var s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";
    s.onload = function () {
      try {
        window.mermaid.initialize({ startOnLoad: false, theme: root.classList.contains("dark") ? "dark" : "default" });
        window.mermaid.run({ nodes: mermaidBlocks }).then(function () { mermaidDone = true; }).catch(fallback);
      } catch (e) { fallback(); }
    };
    s.onerror = fallback;
    document.head.appendChild(s);
    // CDN 不可达时 4 秒后降级为源码显示
    setTimeout(function () {
      if (!mermaidDone && document.querySelector(".mermaid:not(svg)")) fallback();
    }, 4000);
  }
  function fallback() {
    mermaidBlocks.forEach(function (el) {
      var frame = el.closest(".mermaid-frame");
      var pre = frame && frame.querySelector(".mermaid-source");
      if (pre) {
        pre.hidden = false;
        el.remove();
      }
    });
  }

/* ---------- Tabs / CodeGroup ---------- */
  document.querySelectorAll(".tabs").forEach(function (tabs) {
    var panes = Array.prototype.slice.call(tabs.querySelectorAll(":scope > .tab-pane"));
    if (!panes.length) return;
    var bar = document.createElement("div");
    bar.className = "tab-bar";
    panes.forEach(function (pane, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tab-btn" + (i === 0 ? " active" : "");
      btn.textContent = pane.getAttribute("data-title") || "标签 " + (i + 1);
      btn.addEventListener("click", function () {
        panes.forEach(function (p, j) { p.classList.toggle("active", i === j); });
        bar.querySelectorAll(".tab-btn").forEach(function (b, j) { b.classList.toggle("active", i === j); });
      });
      bar.appendChild(btn);
      pane.classList.toggle("active", i === 0);
    });
    tabs.insertBefore(bar, tabs.firstChild);
  });

  /* ---------- 目录高亮 ---------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".toc-item"));
  if (tocLinks.length && "IntersectionObserver" in window) {
    var map = {};
    tocLinks.forEach(function (a) {
      var id = decodeURIComponent(a.getAttribute("href").slice(1));
      map[id] = a;
    });
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && map[en.target.id]) {
          tocLinks.forEach(function (a) { a.classList.remove("active"); });
          map[en.target.id].classList.add("active");
        }
      });
    }, { rootMargin: "-70px 0px -70% 0px" });
    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) obs.observe(el);
    });
  }

  /* ---------- 搜索 ---------- */
  var input = document.getElementById("search-input");
  var box = document.getElementById("search-results");
  var index = null;
  var activeIdx = -1;
  var hits = [];

  function loadIndex(cb) {
    if (index) return cb();
    var s = document.createElement("script");
    s.src = (window.BASE || "./") + "assets/search-index.js";
    s.onload = function () { index = window.SEARCH_INDEX || []; cb(); };
    s.onerror = function () { index = []; cb(); };
    document.head.appendChild(s);
  }

  function score(entry, terms) {
    var total = 0;
    var body = entry.b.toLowerCase();
    for (var i = 0; i < terms.length; i++) {
      var t = terms[i].toLowerCase();
      var sc = 0;
      var ti = entry.t.toLowerCase().indexOf(t);
      if (ti >= 0) sc += 60 - Math.min(ti, 30);
      if (entry.g && entry.g.toLowerCase().indexOf(t) >= 0) sc += 15;
      var bi = body.indexOf(t);
      if (bi >= 0) {
        sc += 20;
        var count = 0, pos = 0;
        while ((pos = body.indexOf(t, pos)) >= 0 && count < 20) { count++; pos += t.length; }
        sc += Math.min(count, 10) * 2;
      }
      if (sc === 0) return 0;
      total += sc;
    }
    return total;
  }

  function highlight(text, terms) {
    var out = text;
    terms.forEach(function (t) {
      if (!t) return;
      var re = new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      out = out.replace(re, function (m) { return "<mark>" + m + "</mark>"; });
    });
    return out;
  }

  function search(q) {
    var terms = q.trim().split(/\s+/).filter(Boolean);
    if (!terms.length) { box.hidden = true; box.innerHTML = ""; return; }
    var scored = [];
    for (var i = 0; i < index.length; i++) {
      var s = score(index[i], terms);
      if (s > 0) scored.push([s, index[i]]);
    }
    scored.sort(function (a, b) { return b[0] - a[0]; });
    hits = scored.slice(0, 12).map(function (x) { return x[1]; });
    activeIdx = -1;
    if (!hits.length) {
      box.innerHTML = '<div class="search-empty">没有找到与「' + q.replace(/</g, "&lt;") + "」相关的结果</div>";
    } else {
      var base = window.BASE || "./";
      box.innerHTML = hits.map(function (h) {
        var excerpt = "";
        var low = h.b.toLowerCase();
        for (var j = 0; j < terms.length; j++) {
          var p = low.indexOf(terms[j].toLowerCase());
          if (p >= 0) { excerpt = h.b.slice(Math.max(0, p - 30), p + 90); break; }
        }
        if (!excerpt) excerpt = h.b.slice(0, 110);
        return '<a class="search-hit" href="' + base + h.p + '/">' +
          '<div class="hit-title">' + (h.g ? '<span class="hit-group">' + h.g + "</span>" : "") +
          highlight(h.t, terms) + "</div>" +
          '<div class="hit-body">' + highlight(excerpt, terms) + "…</div></a>";
      }).join("");
      box.querySelectorAll(".search-hit").forEach(function (a, i2) {
        a.addEventListener("mousedown", function (e) {
          e.preventDefault();
          window.location.href = a.getAttribute("href");
        });
      });
    }
    box.hidden = false;
  }

  if (input && box) {
    window.BASE = (function () {
      var m = location.pathname.replace(/\/[^/]*$/, "");
      var depth = (document.querySelector('link[rel="stylesheet"]') || {}).href || "";
      var css = new URL(depth);
      return css.href.replace(/assets\/style\.css.*$/, "");
    })();
    input.addEventListener("input", function () {
      loadIndex(function () { search(input.value); });
    });
    input.addEventListener("focus", function () {
      loadIndex(function () { if (input.value) search(input.value); });
    });
    document.addEventListener("click", function (e) {
      if (!box.contains(e.target) && e.target !== input) box.hidden = true;
    });
    input.addEventListener("keydown", function (e) {
      var items = box.querySelectorAll(".search-hit");
      if (e.key === "Escape") { box.hidden = true; input.blur(); return; }
      if (!items.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        activeIdx = e.key === "ArrowDown"
          ? (activeIdx + 1) % items.length
          : (activeIdx - 1 + items.length) % items.length;
        items.forEach(function (a, i2) { a.classList.toggle("active", i2 === activeIdx); });
        items[activeIdx].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && activeIdx >= 0) {
        window.location.href = items[activeIdx].getAttribute("href");
      }
    });
    document.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.focus();
        input.select();
      }
    });
  }
})();
