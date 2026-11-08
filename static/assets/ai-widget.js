/* ============================================================
 * 看板内嵌「经营决策助手」对话浮窗
 * 复用 /api/llm/chat（ReAct + 工具调用 + 口径护栏），
 * 支持对话内出图（render_chart）与多轮追问（history）。
 * 与 assistant.html 独立页面共存：浮窗=随手问，独立页=完整分析。
 * ============================================================ */
(function () {
  if (document.getElementById("ai-widget")) return;
  if (typeof echarts === "undefined") return; // 看板页必须已加载 echarts

  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  };

  // 极简 markdown：加粗 + 标题 + 无序列表（与 assistant.html 同构）
  function render(text) {
    if (!text) return "";
    var h = esc(text).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    var out = [], inUl = false;
    h.split("\n").forEach(function (ln) {
      var t = ln.trim();
      if (!t) { if (inUl) { out.push("</ul>"); inUl = false; } return; }
      if (/^- /.test(t)) {
        if (!inUl) { out.push("<ul>"); inUl = true; }
        out.push("<li>" + t.slice(2) + "</li>");
      } else if (/^<b>.*<\/b>$/.test(t)) {
        if (inUl) { out.push("</ul>"); inUl = false; }
        out.push("<h4>" + t.replace(/<\/?b>/g, "") + "</h4>");
      } else {
        if (inUl) { out.push("</ul>"); inUl = false; }
        out.push("<div>" + t + "</div>");
      }
    });
    if (inUl) out.push("</ul>");
    return out.join("");
  }

  // ---------- DOM ----------
  var fab = document.createElement("button");
  fab.className = "aiw-fab";
  fab.title = "智能问答助手（对话式分析 · 可出图）";
  fab.innerHTML = '<span class="aiw-fab-ico">💬</span><span class="aiw-fab-dot"></span>';
  document.body.appendChild(fab);

  var panel = document.createElement("div");
  panel.id = "ai-widget";
  panel.className = "aiw-panel";
  panel.innerHTML =
    '<div class="aiw-head">' +
    '  <b>🧭 经营决策助手</b>' +
    '  <span class="aiw-sp"></span>' +
    '  <a class="aiw-full" href="/assistant.html" title="打开完整版">完整版 ⤢</a>' +
    '  <button class="aiw-close" title="收起">×</button>' +
    "</div>" +
    '<div class="aiw-chips">' +
    '  <button class="aiw-chip">各品类GMV画柱状图</button>' +
    '  <button class="aiw-chip">美妆未来4周能卖多少？</button>' +
    '  <button class="aiw-chip">哪些商品该降价？</button>' +
    "</div>" +
    '<div class="aiw-chat"></div>' +
    '<form class="aiw-composer">' +
    '  <input placeholder="边看图边问，可让它出图…" autocomplete="off" />' +
    '  <button type="submit">发送</button>' +
    "</form>";
  document.body.appendChild(panel);

  var chatEl = panel.querySelector(".aiw-chat");
  var inputEl = panel.querySelector(".aiw-composer input");
  var sendBtn = panel.querySelector(".aiw-composer button");
  var open = false;
  var history = []; // 最近 6 轮多轮上下文
  var chartsSeq = 0; // 图表实例，供 resize

  function toggle(force) {
    open = typeof force === "boolean" ? force : !open;
    panel.classList.toggle("on", open);
    fab.classList.toggle("on", open);
    if (open) {
      if (!chatEl.children.length) welcome();
      setTimeout(function () { inputEl.focus(); }, 60);
    }
  }
  fab.onclick = function () { toggle(); };
  panel.querySelector(".aiw-close").onclick = function () { toggle(false); };
  panel.querySelectorAll(".aiw-chip").forEach(function (c) {
    c.onclick = function () { ask(c.textContent); };
  });

  function scrollBottom() { chatEl.scrollTop = chatEl.scrollHeight; }

  function addMsg(role, text) {
    var el = document.createElement("div");
    el.className = "aiw-msg " + role;
    el.innerHTML =
      '<div class="aiw-bubble"><div class="aiw-text">' +
      render(text) + '</div><div class="aiw-meta"></div></div>';
    chatEl.appendChild(el);
    scrollBottom();
    return el;
  }

  function welcome() {
    addMsg("bot",
      "**【能做什么】** 边看图边问，我只用平台真实数据回答：\n" +
      "- 出图：「把各品类 GMV 画成柱状图」「月度趋势画折线」\n" +
      "- 追问：「那第二名呢」「再按月拆」\n" +
      "- 数字都带口径标注，图可导出 PNG / CSV");
  }

  function downloadCSV(opt) {
    var s0 = opt.series[0] || {};
    var xs = (opt.xAxis && opt.xAxis.data)
      || ((s0.data || []).map(function (d) { return (d && typeof d === "object") ? d.name : ""; }));
    var series = (opt.series || []).map(function (s) {
      return { name: s.name || "值",
               data: (s.data || []).map(function (d) { return (d && typeof d === "object") ? d.value : d; }) };
    });
    var csv = "维度," + series.map(function (s) { return s.name; }).join(",") + "\n";
    (xs || []).forEach(function (x, i) {
      csv += '"' + x + '",' + series.map(function (s) { return (s.data[i] == null ? "" : s.data[i]); }).join(",") + "\n";
    });
    var blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = ((opt.title && opt.title.text) || "data") + ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function renderCharts(msgEl, charts) {
    if (!charts || !charts.length) return;
    var bubble = msgEl.querySelector(".aiw-bubble");
    charts.forEach(function (opt) {
      var box = document.createElement("div");
      box.className = "aiw-chart";
      bubble.appendChild(box);
      var c = echarts.init(box, null, { renderer: "canvas" });
      c.setOption(opt);
      chartsSeq++;
      var tools = document.createElement("div");
      tools.className = "aiw-tools";
      tools.innerHTML = '<button data-a="png">PNG</button><button data-a="csv">CSV</button>';
      tools.querySelector('[data-a="png"]').onclick = function () {
        var a = document.createElement("a");
        a.href = c.getDataURL({ pixelRatio: 2, backgroundColor: "#1a2438" });
        a.download = ((opt.title && opt.title.text) || "chart") + ".png";
        a.click();
      };
      tools.querySelector('[data-a="csv"]').onclick = function () { downloadCSV(opt); };
      bubble.appendChild(tools);
      window.addEventListener("resize", function () { c.resize(); });
    });
    scrollBottom();
  }

  function ask(text) {
    text = (text || "").trim();
    if (!text) return;
    addMsg("user", text);
    inputEl.value = "";
    sendBtn.disabled = true;
    var el = addMsg("bot", "思考中…");
    el.classList.add("thinking");

    fetch("/api/llm/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, mode: "full", history: history }),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.code !== 0) throw new Error(j.message || "请求失败");
        var d = j.data;
        el.querySelector(".aiw-text").innerHTML = render(d.answer);
        renderCharts(el, d.charts);
        var bits = [];
        if (d.provider && d.provider !== "offline") bits.push(d.provider + "/" + d.model);
        if (d.tools_used && d.tools_used.length) bits.push("工具×" + d.tools_used.length);
        if (d.elapsed_ms != null) bits.push(d.elapsed_ms + "ms");
        if (d.refused) bits.push("已拒答");
        el.querySelector(".aiw-meta").innerHTML = bits.map(function (b) { return "<span>" + esc(b) + "</span>"; }).join("");
        // 维护多轮上下文（最多 6 轮）
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: d.answer || "" });
        while (history.length > 12) history.shift();
      })
      .catch(function (e) {
        el.querySelector(".aiw-text").innerHTML = "⚠️ " + esc(e.message || "网络异常");
      })
      .finally(function () {
        el.classList.remove("thinking");
        sendBtn.disabled = false;
        scrollBottom();
        inputEl.focus();
      });
  }

  panel.querySelector(".aiw-composer").addEventListener("submit", function (e) {
    e.preventDefault();
    ask(inputEl.value);
  });

  // Esc 收起
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && open) toggle(false);
  });
})();
