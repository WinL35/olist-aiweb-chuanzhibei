/* Olist 经营分析与智能选品平台 - 前端 (Vue3 + ECharts CDN) */
const { createApp } = Vue;

const API = "/api";
// 支持 ?view=xxx 直达某个页面（演示录屏、截图、深链分享用）
const VIEW_KEYS = ["dashboard", "rfm", "conversion", "prediction", "recommend", "pricing", "experiment"];
const _qView = new URLSearchParams(location.search).get("view");
const fmt = (n, dp = 0) => n == null ? "-" : Number(n).toLocaleString("zh-CN",
  { maximumFractionDigits: dp, minimumFractionDigits: dp });
const money = (n) => "R$ " + fmt(n, 0);
const pct = (n, dp = 1) => (n == null ? "-" : (Number(n) * 100).toFixed(dp) + "%");
const pctRaw = (n, dp = 1) => (n == null ? "-" : Number(n).toFixed(dp) + "%");

// 图表渲染辅助
function render(el, opt) {
  if (!el) return null;
  let c = echarts.getInstanceByDom(el) || echarts.init(el);
  c.setOption(opt, true);
  return c;
}
const disposeMixin = {
  beforeUnmount() {
    this.$el && this.$el.querySelectorAll(".chart").forEach(el => {
      let c = echarts.getInstanceByDom(el); if (c) c.dispose();
    });
  }
};
window.addEventListener("resize", () => {
  document.querySelectorAll(".chart").forEach(el => {
    let c = echarts.getInstanceByDom(el); if (c) c.resize();
  });
});
const PAL = ["#2f9bff", "#25d4a4", "#ffb547", "#ff6b6b", "#a866ff", "#36cfc7", "#ff85a2", "#ffc107"];
const axisColor = "#8ea0bd";
const baseGrid = { left: 84, right: 26, top: 34, bottom: 48 };
const tooltip = { backgroundColor: "#1a2438", borderColor: "#2a3650", textStyle: { color: "#e8eef7" } };

async function get(path) {
  let r;
  try {
    r = await fetch(API + path);
  } catch (e) {
    throw new Error(`网络请求失败：${e.message}`);
  }
  if (!r.ok) throw new Error(`接口 HTTP ${r.status}`);
  let j;
  try {
    j = await r.json();
  } catch (e) {
    throw new Error(`接口返回的不是 JSON（HTTP ${r.status}）`);
  }
  // 后端业务错误统一返回 {code, message, data}，HTTP 状态仍是 200
  if (j && typeof j.code === "number" && j.code !== 0) {
    throw new Error(j.message || `接口错误 code=${j.code}`);
  }
  return j;
}

/* ============ 经营看板 ============ */
const Dashboard = {
  mixins: [disposeMixin],
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
    <div class="kpi-grid">
      <div class="kpi b"><div class="label">GMV 商品总额</div><div class="val">{{ money(s.gmv) }}</div></div>
      <div class="kpi o"><div class="label">客单价(每单)</div><div class="val">{{ money(s.avg_order_value) }}</div></div>
      <div class="kpi"><div class="label">订单数</div><div class="val">{{ fmt(s.order_cnt) }}</div></div>
      <div class="kpi"><div class="label">客户数(去重)</div><div class="val">{{ fmt(s.customer_cnt) }}</div></div>
      <div class="kpi g"><div class="label">送达率</div><div class="val">{{ pct(s.delivery_rate) }}</div></div>
      <div class="kpi o"><div class="label">复购率</div><div class="val">{{ pct(s.repurchase_rate) }}</div></div>
      <div class="kpi b"><div class="label">支付转化率</div><div class="val">{{ pct(s.conversion_rate) }}</div></div>
    </div>
    <div class="card" style="margin-bottom:16px"><div class="metric-pills">
      <span class="pill">商品数 <b>{{ fmt(s.product_cnt) }}</b></span>
      <span class="pill">品类数 <b>{{ fmt(s.category_cnt) }}</b></span>
      <span class="pill">平均评分 <b>{{ fmt(s.avg_review,2) }}</b></span>
      <span class="pill">平均物流时效 <b>{{ fmt(s.avg_delivery_days,1) }} 天</b></span>
      <span class="pill">复购客户 <b>{{ fmt(s.repurchase_customers) }}</b></span>
    </div></div>

    <div class="grid g2">
      <div class="card"><h3>GMV 与订单趋势(月)</h3><div class="chart lg" ref="trend"></div></div>
      <div class="card"><h3>支付方式分布</h3><div class="chart lg" ref="payment"></div></div>
    </div>
    <div class="grid g3" style="margin-top:16px">
      <div class="card"><h3>品类 GMV Top15</h3><div class="chart" ref="cat"></div></div>
      <div class="card"><h3>各州销售额 Top12</h3><div class="chart" ref="region"></div></div>
      <div class="card"><h3>订单状态分布</h3><div class="chart" ref="status"></div></div>
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><h3>下单时段分布</h3><div class="chart sm" ref="hour"></div></div>
      <div class="card"><h3>下单星期分布</h3><div class="chart sm" ref="weekday"></div></div>
    </div>
    <div class="grid g2" style="margin-top:16px">
      <div class="card"><h3>评价星级分布</h3><div class="chart sm" ref="review"></div></div>
      <div class="card"><h3>热销商品 Top10</h3>
        <table><thead><tr><th>商品ID</th><th>品类</th><th class="num">GMV</th><th class="num">件数</th></tr></thead>
        <tbody><tr v-for="p in top" :key="p.product_id"><td class="muted">{{p.product_id.slice(0,10)}}…</td><td>{{p.category}}</td><td class="num">{{money(p.gmv)}}</td><td class="num">{{fmt(p.items)}}</td></tr></tbody></table>
      </div>
    </div>
  </div>
  </div>`,
  data: () => ({ s: {}, top: [] }),
  async mounted() {
    try {
    const [s, tr, cat, reg, pay, hr, wd, st, rv, tp] = await Promise.all([
      get("/dashboard/summary"), get("/dashboard/trend"),
      get("/dashboard/category"), get("/dashboard/region"),
      get("/dashboard/payment"), get("/dashboard/hour"),
      get("/dashboard/weekday"), get("/dashboard/order_status"),
      get("/dashboard/review"), get("/dashboard/top_products"),
    ]);
    this.s = s; this.top = tp.data;
    await this.$nextTick();
    // 趋势
    render(this.$refs.trend, {
      tooltip: { ...tooltip, trigger: "axis" },
      legend: { data: ["GMV", "订单数"], textStyle: { color: axisColor } },
      grid: baseGrid,
      xAxis: { type: "category", data: tr.data.map(d => d.t), axisLine: { lineStyle: { color: axisColor } } },
      yAxis: [{ type: "value", name: "GMV", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
              { type: "value", name: "订单数", axisLine: { lineStyle: { color: axisColor } }, splitLine: { show: false } }],
      series: [
        { name: "GMV", type: "line", smooth: true, areaStyle: { opacity: .15 }, itemStyle: { color: PAL[0] }, data: tr.data.map(d => +d.gmv) },
        { name: "订单数", type: "line", yAxisIndex: 1, smooth: true, itemStyle: { color: PAL[1] }, data: tr.data.map(d => d.orders) },
      ]
    });
    // 支付
    render(this.$refs.payment, {
      tooltip: { ...tooltip, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: axisColor } },
      series: [{ type: "pie", radius: ["38%", "65%"], color: PAL,
        label: { color: axisColor }, data: pay.data.map(d => ({ name: d.type, value: +d.amount })) }]
    });
    // 品类（横向条形图：类目名较长，单独给左侧留 150px，否则会被裁掉首字母）
    const cats = cat.data.slice().reverse();
    render(this.$refs.cat, {
      tooltip: { ...tooltip, trigger: "axis" }, grid: { ...baseGrid, left: 150 },
      xAxis: { type: "value", axisLine: { lineStyle: { color: axisColor } },
               splitNumber: 3,
               axisLabel: { color: axisColor,
                 formatter: v => v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "k" : v },
               splitLine: { lineStyle: { color: "#22304a" } } },
      yAxis: { type: "category", data: cats.map(d => d.category), axisLine: { lineStyle: { color: axisColor } } },
      series: [{ type: "bar", data: cats.map(d => +d.gmv), itemStyle: { color: PAL[0] } }]
    });
    // 区域
    const regTop = reg.data.slice().sort((a, b) => +b.gmv - +a.gmv).slice(0, 12);
    render(this.$refs.region, {
      tooltip: { ...tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { ...baseGrid, bottom: 46 },
      xAxis: { type: "category", data: regTop.map(d => d.state),
               axisLine: { lineStyle: { color: axisColor } },
               axisLabel: { rotate: 38, interval: 0, fontSize: 10, color: axisColor } },
      yAxis: { type: "value", axisLine: { lineStyle: { color: axisColor } },
               axisLabel: { color: axisColor, formatter: v => v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : (v / 1e3).toFixed(0) + "k" },
               splitLine: { lineStyle: { color: "#22304a" } } },
      series: [{ type: "bar", data: regTop.map(d => +d.gmv), itemStyle: { color: PAL[2] }, barMaxWidth: 22 }]
    });
    // 状态
    render(this.$refs.status, {
      tooltip: { ...tooltip, trigger: "item" },
      series: [{ type: "pie", radius: "62%", color: PAL,
        label: { color: axisColor }, data: st.data.map(d => ({ name: d.status, value: d.cnt })) }]
    });
    // 时段
    render(this.$refs.hour, {
      tooltip: { ...tooltip, trigger: "axis" }, grid: baseGrid,
      xAxis: { type: "category", data: hr.data.map(d => d.hour + "时"), axisLine: { lineStyle: { color: axisColor } } },
      yAxis: [{ type: "value", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
              { type: "value", name: "GMV", axisLine: { lineStyle: { color: axisColor } }, splitLine: { show: false } }],
      series: [{ name: "订单数", type: "bar", itemStyle: { color: PAL[0] }, data: hr.data.map(d => d.orders) },
               { name: "GMV", type: "line", yAxisIndex: 1, itemStyle: { color: PAL[2] }, data: hr.data.map(d => +d.gmv) }]
    });
    // 星期
    render(this.$refs.weekday, {
      tooltip: { ...tooltip, trigger: "axis" }, grid: baseGrid,
      xAxis: { type: "category", data: wd.data.map(d => d.name), axisLine: { lineStyle: { color: axisColor } } },
      yAxis: { type: "value", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
      series: [{ type: "bar", data: wd.data.map(d => d.orders), itemStyle: { color: PAL[1] } }]
    });
    // 评价
    render(this.$refs.review, {
      tooltip: { ...tooltip, trigger: "axis" }, grid: baseGrid,
      xAxis: { type: "category", data: rv.data.map(d => d.score + "星"), axisLine: { lineStyle: { color: axisColor } } },
      yAxis: { type: "value", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
      series: [{ type: "bar", data: rv.data.map(d => d.cnt),
        itemStyle: { color: (p) => ["#ff6b6b","#ff9f43","#ffd43b","#a9e34b","#25d4a4"][p.dataIndex % 5] } }]
    });
  
    } catch (e) {
      console.error(e);
      this.err = e.message || String(e);
    } finally {
      this.loading = false;
    }
  },
  methods: { fmt, money, pct }
};

/* ============ 用户分群 RFM ============ */
const Rfm = {
  mixins: [disposeMixin],
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
    <div class="ctrl">
      <span class="muted">分群口径：</span>
      <button class="tab" :class="{on: scheme==='rule8'}" @click="switchScheme('rule8')">业务规则 8 类</button>
      <button class="tab" :class="{on: scheme==='kmeans4'}" @click="switchScheme('kmeans4')">K-Means 聚类 4 类</button>
      <span class="muted">{{ schemeHint }}</span>
    </div>
    <div class="grid g3" style="margin-bottom:16px">
      <div class="card" v-for="seg in segs" :key="seg.segment">
        <h3>{{ seg.segment }}</h3>
        <div style="font-size:26px;font-weight:700;color:var(--accent)">{{ fmt(seg.cnt) }} <small style="font-size:13px;color:var(--txt2)">({{ pctRaw(seg.pct) }})</small></div>
        <div class="muted" style="margin-top:6px">平均R {{ fmt(seg.avg_recency) }}天 · 平均F {{ fmt(seg.avg_frequency,1) }} · 平均M {{ money(seg.avg_monetary) }}</div>
      </div>
    </div>
    <div class="grid g2">
      <div class="card"><h3>分群人数占比</h3><div class="chart lg" ref="pie"></div></div>
      <div class="card"><h3>各分群金额贡献</h3><div class="chart lg" ref="bar"></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>用户 RFM 散点(Recency × Frequency, 颜色=分群, 采样2000)</h3><div class="chart lg" ref="scatter"></div></div>
  </div>
  </div>`,
  data: () => ({ segs: [], scheme: "rule8" }),
  computed: {
    schemeHint() {
      return this.scheme === "rule8"
        ? "规则 8 类：按 R/F/M 五分位打分落档，业务含义直观"
        : "K-Means 4 类：R/F/M 三维聚类，题目要求的聚类分群";
    }
  },
  async mounted() {
    try {
      await this.load();
    } catch (e) {
      console.error(e);
      this.err = e.message || String(e);
    } finally {
      this.loading = false;
    }
  },
  methods: {
    fmt, money, pctRaw,
    async switchScheme(v) {
      if (v === this.scheme) return;
      this.scheme = v;
      this.loading = true;
      this.err = "";
      try {
        await this.load();
      } catch (e) {
        console.error(e);
        this.err = e.message || String(e);
      } finally {
        this.loading = false;
      }
    },
    async load() {
      const [sg, sc] = await Promise.all([
        get(`/rfm/segments?scheme=${this.scheme}`),
        get(`/rfm/scatter?scheme=${this.scheme}`)
      ]);
      this.segs = sg.data;
      await this.$nextTick();
      render(this.$refs.pie, {
        tooltip: { ...tooltip, trigger: "item" },
        legend: { bottom: 0, textStyle: { color: axisColor } },
        series: [{ type: "pie", radius: ["35%", "65%"], color: PAL,
          label: { color: axisColor }, data: sg.data.map(d => ({ name: d.segment, value: d.cnt })) }]
      });
      render(this.$refs.bar, {
        tooltip: { ...tooltip, trigger: "axis" }, grid: baseGrid,
        xAxis: { type: "category", data: sg.data.map(d => d.segment), axisLine: { lineStyle: { color: axisColor } } },
        yAxis: { type: "value", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
        series: [{ type: "bar", data: sg.data.map(d => +d.total_monetary), itemStyle: { color: PAL[2] } }]
      });
      const segNames = [...new Set(sc.data.map(d => d.segment))];
      render(this.$refs.scatter, {
        tooltip: { ...tooltip, formatter: p => `分群:${p.data[2]}<br/>R=${p.data[0]} F=${p.data[1]}` },
        legend: { data: segNames, textStyle: { color: axisColor }, top: 0 },
        grid: baseGrid,
        xAxis: { name: "Recency(天)", type: "value", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
        yAxis: { name: "Frequency", type: "value", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
        series: segNames.map((n, i) => ({
          name: n, type: "scatter", symbolSize: 6, itemStyle: { color: PAL[i % PAL.length], opacity: .7 },
          data: sc.data.filter(d => d.segment === n).map(d => [d.recency, d.frequency, n])
        }))
      });
    }
  }
};

/* ============ 转化分析 ============ */
const Conversion = {
  mixins: [disposeMixin],
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
    <div class="grid g2">
      <div class="card"><h3>订单转化漏斗(下单→已批准→已发货→已送达→已评价)</h3><div class="chart lg" ref="funnel"></div></div>
      <div class="card"><h3>单次 vs 复购客户</h3><div class="chart lg" ref="rep"></div></div>
    </div>
    <div class="card" style="margin-top:16px"><h3>复购客户金额贡献对比</h3><div class="chart" ref="repMoney"></div></div>
  </div>
  </div>`,
  async mounted() {
    try {
    const [fn, rp] = await Promise.all([get("/conversion/funnel"), get("/conversion/repurchase")]);
    await this.$nextTick();
    render(this.$refs.funnel, {
      tooltip: { ...tooltip, trigger: "item", formatter: "{b}: {c} ({d}%)" },
      series: [{ type: "funnel", left: "10%", width: "80%", sort: "none",
        label: { color: axisColor, formatter: "{b}\n{c}" },
        itemStyle: { borderColor: "#1a2438" },
        data: fn.data.map(d => ({ name: d.stage, value: d.cnt })) }]
    });
    render(this.$refs.rep, {
      tooltip: { ...tooltip, trigger: "item" },
      legend: { bottom: 0, textStyle: { color: axisColor } },
      series: [{ type: "pie", radius: ["38%", "65%"], color: [PAL[1], PAL[0]],
        label: { formatter: "{b}\n{d}%", color: axisColor },
        data: rp.data.map(d => ({ name: d.type, value: d.customers })) }]
    });
    render(this.$refs.repMoney, {
      tooltip: { ...tooltip, trigger: "axis" }, grid: baseGrid,
      xAxis: { type: "category", data: rp.data.map(d => d.type), axisLine: { lineStyle: { color: axisColor } } },
      yAxis: [{ type: "value", name: "金额", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
              { type: "value", name: "占比%", axisLine: { lineStyle: { color: axisColor } }, splitLine: { show: false } }],
      series: [
        { name: "金额贡献", type: "bar", data: rp.data.map(d => +d.monetary), itemStyle: { color: PAL[0] } },
        { name: "客户占比%", type: "line", yAxisIndex: 1, data: rp.data.map(d => +d.customer_pct), itemStyle: { color: PAL[2] } },
      ]
    });
  
    } catch (e) {
      console.error(e);
      this.err = e.message || String(e);
    } finally {
      this.loading = false;
    }
  }
};

/* ============ 销量预测 ============ */
const Prediction = {
  mixins: [disposeMixin],
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
    <div class="ctrl">
      <span class="muted">选择品类：</span>
      <select v-model="cat" @change="load">
        <option v-for="c in cats" :key="c.category" :value="c.category">{{ c.category }} (GMV {{ money(c.gmv) }})</option>
      </select>
      <span class="muted">预测周数：</span>
      <select v-model="weeks" @change="load"><option v-for="w in [4,6,8,12]" :key="w" :value="w">{{w}} 周</option></select>
    </div>
    <div class="metric-pills" style="margin-bottom:16px" v-if="r.metrics">
      <span class="pill">模型 <b>{{ r.metrics.model }}</b></span>
      <span class="pill">基线 <b>{{ r.metrics.baseline_model }}</b></span>
      <span class="pill">MAPE(模型) <b :style="{color: r.metrics.mape_model<=15?'var(--green)':'var(--orange)'}">{{ pctRaw(r.metrics.mape_model) }}</b></span>
      <span class="pill">MAPE(基线) <b>{{ pctRaw(r.metrics.mape_baseline) }}</b></span>
      <span class="pill">较基线提升 <b :style="{color: r.metrics.improvement_pct>=0?'var(--green)':'var(--red)'}">{{ (r.metrics.improvement_pct>=0?'+':'') + pctRaw(r.metrics.improvement_pct) }}</b></span>
      <span class="pill">验证窗口 <b>{{ r.metrics.holdout_weeks }} 周</b></span>
    </div>
    <div class="card"><h3>{{ cat }} 周销量预测(含95%置信区间)</h3><div class="chart lg" ref="chart"></div></div>
    <p class="muted" style="margin-top:10px">说明：模型采用 Holt-Winters/Holt 阻尼趋势；MAPE 在最近若干周留存窗口上计算，基线为移动平均(近4周)。单品类周销量波动较大，15% 为参考指标(非硬性)。</p>
  </div>
  </div>`,
  data: () => ({ cats: [], cat: "bed_bath_table", weeks: 8, r: {} }),
  async mounted() {
    try {
    const c = await get("/prediction/categories");
    this.cats = c.data;
    if (!this.cats.find(x => x.category === this.cat)) this.cat = this.cats[0].category;
    await this.load();
  
    } catch (e) {
      console.error(e);
      this.err = e.message || String(e);
    } finally {
      this.loading = false;
    }
  },
  methods: {
    async load() {
      try {
        this.r = await get(`/prediction/sales?category=${encodeURIComponent(this.cat)}&weeks=${this.weeks}`);
      } catch (e) {
        console.error(e);
        this.err = e.message || String(e);
        return;
      }
      this.err = "";
      await this.$nextTick();
      const hist = this.r.history || [], fut = this.r.future || [];
      const xAll = hist.map(d => d.week).concat(fut.map(d => d.week));
      const histLen = hist.length;
      // 修复：histLen=0 时 new Array(-1) 会抛 RangeError；先判空再拼接衔接点
      const bridge = histLen > 0 ? new Array(histLen - 1).concat([hist[histLen - 1]?.qty]) : [];
      const fcSeries = bridge.concat(fut.map(d => +d.forecast));
      const lower = new Array(histLen).concat(fut.map(d => +d.lower));
      const upper = new Array(histLen).concat(fut.map(d => +d.upper));
      const base = new Array(histLen).concat(fut.map(d => +d.baseline));
      render(this.$refs.chart, {
        tooltip: { ...tooltip, trigger: "axis" },
        legend: { data: ["历史销量", "模型预测", "基线(移动平均)", "95%下限", "95%上限"], textStyle: { color: axisColor }, top: 0 },
        grid: { ...baseGrid, top: 50 },
        xAxis: { type: "category", data: xAll, axisLine: { lineStyle: { color: axisColor } }, axisLabel: { rotate: 40 } },
        yAxis: { type: "value", name: "周销量(件)", axisLine: { lineStyle: { color: axisColor } }, splitLine: { lineStyle: { color: "#22304a" } } },
        series: [
          { name: "历史销量", type: "line", data: hist.map(d => d.qty).concat(new Array(fut.length).fill(null)),
            itemStyle: { color: PAL[0] }, areaStyle: { opacity: .1 } },
          { name: "模型预测", type: "line", data: fcSeries, itemStyle: { color: PAL[1] }, lineStyle: { type: "dashed" } },
          { name: "基线(移动平均)", type: "line", data: base, itemStyle: { color: PAL[2] }, lineStyle: { type: "dotted" } },
          { name: "95%下限", type: "line", data: lower, lineStyle: { opacity: 0 }, areaStyle: { color: "transparent" }, symbol: "none" },
          { name: "95%上限", type: "line", data: upper, lineStyle: { opacity: 0 }, areaStyle: { color: PAL[1], opacity: .15 }, symbol: "none" },
        ]
      });
    },
    fmt, money, pctRaw
  }
};

/* ============ 选品建议 ============ */
const Recommend = {
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
    <div class="metric-pills" style="margin-bottom:16px">
      <span class="pill">选品条目 <b>{{ fmt(sel.total) }}</b></span>
      <span class="pill" v-for="t in (sel.by_type||[])" :key="t.selection_type">
        {{ t.selection_type }} <b>{{ fmt(t.cnt) }}</b>
      </span>
      <span class="pill">评估窗口 <b>{{ winText }}</b></span>
    </div>

    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><h3>品类：规模 × 增长率（气泡大小=综合分）</h3><div class="chart lg" ref="scatter"></div></div>
      <div class="card"><h3>商品增长榜 Top10（近期 GMV）</h3><div class="chart lg" ref="prodBar"></div></div>
    </div>

    <div class="card" style="margin-bottom:16px"><h3>智能选品推荐 Top10 品类</h3>
      <p class="muted">综合分 = 规模(近期GMV归一)×0.5 + 增长率(归一)×0.5</p>
      <table><thead><tr><th>排名</th><th>品类</th><th class="num">近期GMV</th><th class="num">前期GMV</th><th class="num">增长率</th><th class="num">近期销量</th><th class="num">均价</th><th class="num">综合分</th></tr></thead>
      <tbody><tr v-for="d in rec" :key="d.category"><td>{{d.rank}}</td><td>{{d.category}}</td><td class="num">{{money(d.recent_gmv)}}</td><td class="num">{{money(d.prev_gmv)}}</td>
      <td class="num"><span class="tag" :class="d.growth_rate>=0?'up':'down'">{{(d.growth_rate>=0?'+':'')+(d.growth_rate*100).toFixed(1)+'%'}}</span></td>
      <td class="num">{{fmt(d.recent_qty)}}</td><td class="num">{{money(d.avg_price)}}</td><td class="num">{{d.score}}</td></tr></tbody></table>
    </div>

    <div class="card" style="margin-bottom:16px"><h3>商品级选品榜 Top10（算法2 交付，含推荐等级）</h3>
      <table><thead><tr><th>排名</th><th>商品ID</th><th>品类</th><th class="num">近期GMV</th><th class="num">增长率</th><th class="num">均价</th><th class="num">综合分</th><th>建议</th></tr></thead>
      <tbody><tr v-for="d in prods" :key="d.product_id"><td>{{d.rank}}</td><td class="muted">{{ d.product_id.slice(0,8) }}…</td><td>{{d.category}}</td>
      <td class="num">{{money(d.gmv_recent)}}</td><td class="num"><span class="tag" :class="(d.growth_pct||0)>=0?'up':'down'">{{ (d.growth_pct==null?'-':((d.growth_pct>=0?'+':'')+d.growth_pct.toFixed(1)+'%')) }}</span></td>
      <td class="num">{{money(d.avg_price)}}</td><td class="num">{{d.score_total}}</td>
      <td><span class="tag" :class="d.recommendation==='强推'?'up':'down'">{{d.recommendation}}</span></td></tr></tbody></table>
    </div>

    <div class="card"><h3>离线策略对照评估(验证期 Top-10 命中前20%)</h3>
      <div v-if="cmp.strategy_A" class="grid g2">
        <div>
          <p class="muted">{{ cmp.strategy_A.name }} → 命中率 <b style="color:var(--accent)">{{ pctRaw(cmp.strategy_A.hit_rate) }}</b></p>
          <table style="margin-top:8px"><thead><tr><th>品类</th><th class="num">训练期GMV</th><th class="num">增长率</th></tr></thead>
          <tbody><tr v-for="d in cmp.strategy_A.recommended" :key="d.category"><td>{{d.category}}</td><td class="num">{{money(d.train_gmv)}}</td><td class="num">{{(d.growth*100).toFixed(1)}}%</td></tr></tbody></table>
        </div>
        <div>
          <p class="muted">{{ cmp.strategy_B.name }} → 命中率 <b style="color:var(--green)">{{ pctRaw(cmp.strategy_B.hit_rate) }}</b></p>
          <table style="margin-top:8px"><thead><tr><th>品类</th><th class="num">训练期GMV</th><th class="num">增长率</th></tr></thead>
          <tbody><tr v-for="d in cmp.strategy_B.recommended" :key="d.category"><td>{{d.category}}</td><td class="num">{{money(d.train_gmv)}}</td><td class="num">{{(d.growth*100).toFixed(1)}}%</td></tr></tbody></table>
        </div>
      </div>
      <p class="muted" style="margin-top:12px">结论：{{ cmp.conclusion }}（验证期{{cmp.validation_window}}，前20%品类数={{cmp.top20_count}}）</p>
    </div>
  </div>
  </div>`,
  data: () => ({ rec: [], cmp: {}, win: null, sel: {}, prods: [] }),
  computed: {
    // 修复：win 是 {recent, end} 对象，直接插值会渲染成 JSON 串，这里格式化为日期区间
    winText() {
      return this.win ? `${this.win.recent} ~ ${this.win.end}` : "近90天 vs 前90天";
    }
  },
  async mounted() {
    try {
      const [r, c, s, pr] = await Promise.all([
        get("/recommendation/products"),
        get("/recommendation/strategy_compare"),
        get("/selection/summary"),
        get("/selection/products?limit=10")
      ]);
      this.rec = r.data; this.cmp = c; this.win = r.window || null;
      this.sel = s; this.prods = pr.data;
      await this.$nextTick();
      render(this.$refs.scatter, {
        tooltip: { ...tooltip, formatter: p =>
          `${p.data[3]}<br/>近期GMV ${money(p.data[0])}<br/>增长率 ${p.data[1].toFixed(1)}%<br/>综合分 ${p.data[2]}` },
        grid: { ...baseGrid, bottom: 44 },
        xAxis: { name: "近期GMV", type: "value", axisLine: { lineStyle: { color: axisColor } },
                 axisLabel: { color: axisColor, formatter: v => v >= 1e3 ? (v / 1e3).toFixed(0) + "k" : v },
                 splitLine: { lineStyle: { color: "#22304a" } } },
        yAxis: { name: "增长率(%)", type: "value", axisLine: { lineStyle: { color: axisColor } },
                 axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: "#22304a" } } },
        series: [{ type: "scatter", itemStyle: { color: PAL[0], opacity: .75 },
          symbolSize: d => 8 + Math.max(0, Math.min(100, d[2])) / 5,
          data: this.rec.map(d => [d.recent_gmv, +(d.growth_rate * 100).toFixed(1), d.score, d.category])
        }]
      });
      const top = this.prods.slice().reverse();
      render(this.$refs.prodBar, {
        tooltip: { ...tooltip, trigger: "axis", formatter: ps => {
          const d = top[ps[0].dataIndex];
          return `${d.category}<br/>近期GMV ${money(d.gmv_recent)}<br/>增长率 ${(d.growth_pct>=0?'+':'')+(d.growth_pct||0).toFixed(1)}%`; } },
        grid: { ...baseGrid, left: 120, bottom: 40 },
        xAxis: { type: "value", axisLabel: { color: axisColor, formatter: v => v >= 1e3 ? (v / 1e3).toFixed(0) + "k" : v },
                 splitLine: { lineStyle: { color: "#22304a" } } },
        yAxis: { type: "category", data: top.map(d => "#" + d.rank + " " + d.category),
                 axisLine: { lineStyle: { color: axisColor } }, axisLabel: { color: axisColor } },
        series: [{ type: "bar", data: top.map(d => +d.gmv_recent), itemStyle: { color: PAL[1] } }]
      });
    } catch (e) {
      console.error(e);
      this.err = e.message || String(e);
    } finally {
      this.loading = false;
    }
  },
  methods: { fmt, money, pctRaw }
};

/* ============ 定价建议 ============ */
const Pricing = {
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
      <div class="metric-pills" style="margin-bottom:16px">
        <span class="pill">分析商品 <b>{{ fmt(summary.total) }}</b></span>
        <span class="pill">可给建议价 <b style="color:var(--green)">{{ fmt(summary.has_suggestion) }}</b></span>
        <span class="pill">样本不足 <b style="color:var(--orange)">{{ fmt(summary.no_suggestion) }}</b></span>
        <span class="pill">高置信建议 <b>{{ fmt(summary.confidence && summary.confidence['高']) }}</b></span>
        <span class="pill">平均预期营收变化 <b>{{ pctRaw(summary.avg_expected_revenue_change_pct) }}</b></span>
      </div>

      <div class="grid g2" style="margin-bottom:16px">
        <div class="card"><h3>各品类可给建议价商品数</h3><div class="chart lg" ref="catBar"></div></div>
        <div class="card"><h3>价格弹性 × 预期营收变化</h3><div class="chart lg" ref="elast"></div></div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <h3>商品定价建议</h3>
        <p class="muted">建议价仅供经营决策参考。无建议价表示数据不足，不会被误显示为 0。</p>
        <table><thead><tr><th>商品ID</th><th>品类</th><th>置信度</th><th class="num">当前价</th><th class="num">建议价</th><th class="num">调价幅度</th><th class="num">预期营收变化</th><th>依据</th></tr></thead>
        <tbody><tr v-for="d in rows" :key="d.product_id"><td class="muted">{{ d.product_id.slice(0,10) }}…</td><td>{{ d.category }}</td><td><span class="tag" :class="d.confidence==='高'?'up':'down'">{{ d.confidence }}</span></td><td class="num">{{ money(d.current_price) }}</td><td class="num">{{ d.has_suggestion ? money(d.suggested_price) : '数据不足' }}</td><td class="num">{{ d.has_suggestion ? pctRaw(d.price_change_pct) : '-' }}</td><td class="num">{{ d.has_suggestion ? pctRaw(d.expected_revenue_change_pct) : '-' }}</td><td>{{ d.elasticity_source || d.note }}</td></tr></tbody></table>
      </div>

      <div class="grid g2">
        <div class="card"><h3>按品类汇总</h3>
          <table><thead><tr><th>品类</th><th class="num">商品数</th><th class="num">有建议价</th><th class="num">平均当前价</th><th class="num">平均调价幅度</th></tr></thead>
          <tbody><tr v-for="d in cats" :key="d.category"><td>{{ d.category }}</td><td class="num">{{ fmt(d.product_cnt) }}</td><td class="num">{{ fmt(d.has_suggestion) }}</td><td class="num">{{ money(d.avg_current_price) }}</td><td class="num">{{ pctRaw(d.avg_change_pct) }}</td></tr></tbody></table>
        </div>
        <div class="card"><h3>未给建议价的商品（样本不足）</h3>
          <p class="muted">共 {{ fmt(skipped.length) }} 个，均为月度观测不足或价格变异太小，无法估计弹性。</p>
          <table><thead><tr><th>商品ID</th><th>品类</th><th class="num">观测月</th><th class="num">价格CV</th></tr></thead>
          <tbody><tr v-for="d in skipped.slice(0,10)" :key="d.product_id"><td class="muted">{{ d.product_id.slice(0,8) }}…</td><td>{{ d.category }}</td><td class="num">{{ d.months_observed }}</td><td class="num">{{ fmt(d.price_cv_pct,2) }}%</td></tr></tbody></table>
        </div>
      </div>
    </div>
  </div>`,
  data: () => ({ summary: { confidence: {} }, rows: [], cats: [], skipped: [] }),
  async mounted() {
    try {
      const [summary, suggestions, cats, skipped] = await Promise.all([
        get('/pricing/summary'), get('/pricing/suggestions?limit=50'),
        get('/pricing/by-category'), get('/pricing/skipped')
      ]);
      this.summary = summary; this.rows = suggestions.data;
      this.cats = cats.data; this.skipped = skipped.data;
      await this.$nextTick();
      const cs = this.cats.slice().sort((a, b) => b.product_cnt - a.product_cnt).slice(0, 10).reverse();
      render(this.$refs.catBar, {
        tooltip: { ...tooltip, trigger: "axis" },
        legend: { data: ["可给建议价", "样本不足"], textStyle: { color: axisColor }, top: 0 },
        grid: { ...baseGrid, left: 130, top: 40, bottom: 36 },
        xAxis: { type: "value", axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: "#22304a" } } },
        yAxis: { type: "category", data: cs.map(d => d.category),
                 axisLine: { lineStyle: { color: axisColor } }, axisLabel: { color: axisColor } },
        series: [
          { name: "可给建议价", type: "bar", stack: "t", data: cs.map(d => +d.has_suggestion), itemStyle: { color: PAL[1] } },
          { name: "样本不足", type: "bar", stack: "t", data: cs.map(d => d.product_cnt - d.has_suggestion), itemStyle: { color: PAL[2] } }
        ]
      });
      const pts = this.rows.filter(d => d.has_suggestion);
      render(this.$refs.elast, {
        tooltip: { ...tooltip, formatter: p =>
          `${p.data[3]}<br/>弹性 ${p.data[0]}<br/>调价 ${p.data[1]}%<br/>预期营收变化 ${p.data[2]}%` },
        grid: { ...baseGrid, bottom: 44 },
        xAxis: { name: "价格弹性", type: "value", axisLine: { lineStyle: { color: axisColor } },
                 axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: "#22304a" } } },
        yAxis: { name: "预期营收变化(%)", type: "value", axisLine: { lineStyle: { color: axisColor } },
                 axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: "#22304a" } } },
        series: [{ type: "scatter", symbolSize: 9, itemStyle: { color: PAL[0], opacity: .8 },
          data: pts.map(d => [+d.elasticity, +d.price_change_pct, +d.expected_revenue_change_pct, d.category]) }]
      });
    } catch (e) {
      console.error(e); this.err = e.message || String(e);
    } finally { this.loading = false; }
  },
  methods: { fmt, money, pctRaw }
};

/* ============ 模型实验 ============ */
const Experiment = {
  template: `
  <div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-if="err" class="state err">接口加载失败：{{ err }}<button class="retry" @click="retry">重试</button></div>
    <div v-show="!err" :style="{opacity: loading ? 0.35 : 1}">
      <div class="grid g2" style="margin-bottom:16px">
        <div class="card"><h3>各模型误差对比（74 品类均值）</h3><div class="chart lg" ref="mbar"></div></div>
        <div class="card"><h3>稳健口径：MAPE 中位数</h3><div class="chart lg" ref="med"></div></div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <h3>预测模型离线对照（74 个品类，留出 6 周）</h3>
        <table><thead><tr><th>模型</th><th class="num">品类数</th><th class="num">MAPE 均值</th><th class="num">WAPE 均值</th><th class="num">MAE 均值</th><th class="num">RMSE 均值</th><th class="num">较基线 MAPE</th></tr></thead>
        <tbody><tr v-for="d in models" :key="d.model"><td>{{ d.model }} <span v-if="d.is_baseline" class="tag">基线</span></td><td class="num">{{ fmt(d.category_cnt) }}</td><td class="num">{{ pctRaw(d.avg_mape) }}</td><td class="num">{{ pctRaw(d.avg_wape) }}</td><td class="num">{{ fmt(d.avg_mae,2) }}</td><td class="num">{{ fmt(d.avg_rmse,2) }}</td><td class="num">{{ d.is_baseline ? '-' : pctRaw(d.avg_mape_improve_pct) }}</td></tr></tbody></table>
      </div>

      <div class="grid g2" style="margin-bottom:16px">
        <div class="card"><h3>主模型优于基线的品类</h3>
          <p class="metric-big">{{ fmt(better.better) }}/{{ fmt(better.total) }}</p>
          <p class="muted">占比 {{ pctRaw(better.pct) }}。结论应如实表述为“部分品类优于基线”。</p>
        </div>
        <div class="card"><h3>数据集与实验概览</h3>
          <table><tbody><tr v-for="d in stats" :key="d.name"><td>{{ d.name }}</td><td class="num">{{ d.value_text }}</td></tr></tbody></table>
        </div>
      </div>
      <p class="muted">{{ note }}</p>
    </div>
  </div>`,
  data: () => ({ models: [], median: {}, better: {}, note: '', stats: [] }),
  async mounted() {
    try {
      const [comparison, overview, st] = await Promise.all([
        get('/experiment/compare'), get('/experiment/median'), get('/experiment/summary-stats')
      ]);
      this.models = comparison.data; this.median = overview.median || {};
      this.better = overview.main_model_better_categories || {};
      this.note = overview.note || '';
      this.stats = (st.data || []).slice(0, 8);
      await this.$nextTick();
      const ms = this.models.slice().sort((a, b) => a.avg_mape - b.avg_mape);
      render(this.$refs.mbar, {
        tooltip: { ...tooltip, trigger: "axis" },
        legend: { data: ["MAPE 均值", "WAPE 均值"], textStyle: { color: axisColor }, top: 0 },
        grid: { ...baseGrid, left: 130, top: 40, bottom: 40 },
        xAxis: { type: "value", axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: "#22304a" } } },
        yAxis: { type: "category", data: ms.map(d => d.model.length > 14 ? d.model.slice(0, 14) + "…" : d.model),
                 axisLine: { lineStyle: { color: axisColor } }, axisLabel: { color: axisColor, fontSize: 11 } },
        series: [
          { name: "MAPE 均值", type: "bar", data: ms.map(d => +d.avg_mape),
            itemStyle: { color: p => ms[p.dataIndex].is_baseline ? PAL[3] : PAL[0] } },
          { name: "WAPE 均值", type: "bar", data: ms.map(d => +d.avg_wape), itemStyle: { color: PAL[2] } }
        ]
      });
      render(this.$refs.med, {
        tooltip: { ...tooltip, trigger: "axis" },
        grid: { ...baseGrid, top: 40, bottom: 36 },
        xAxis: { type: "category", data: ["主模型", "基线(MA4)"], axisLine: { lineStyle: { color: axisColor } },
                 axisLabel: { color: axisColor } },
        yAxis: { type: "value", name: "MAPE 中位数(%)", axisLine: { lineStyle: { color: axisColor } },
                 axisLabel: { color: axisColor }, splitLine: { lineStyle: { color: "#22304a" } } },
        series: [{ type: "bar", barWidth: 70,
          data: [{ value: +(this.median.main_model_mape || 0), itemStyle: { color: PAL[1] } },
                 { value: +(this.median.baseline_mape || 0), itemStyle: { color: PAL[3] } }],
          label: { show: true, position: "top", color: axisColor, formatter: p => p.value.toFixed(1) + "%" } }]
      });
    } catch (e) {
      console.error(e); this.err = e.message || String(e);
    } finally { this.loading = false; }
  },
  methods: { fmt, pctRaw }
};

/* ============ 根应用 ============ */
createApp({
  data: () => ({
    view: VIEW_KEYS.includes(_qView) ? _qView : "dashboard",
    menus: [
      { key: "dashboard", name: "经营看板", ico: "📈", desc: "GMV/客单价/转化率/复购率等核心经营指标" },
      { key: "rfm", name: "用户分群", ico: "👥", desc: "RFM 模型 + K-Means 聚类划分用户群体" },
      { key: "conversion", name: "转化分析", ico: "🔄", desc: "订单转化漏斗与复购情况" },
      { key: "prediction", name: "销量预测", ico: "🔮", desc: "品类未来周销量预测与预测区间" },
      { key: "recommend", name: "选品建议", ico: "🎯", desc: "增长潜力品类推荐与离线策略对照评估" },
      { key: "pricing", name: "定价建议", ico: "💰", desc: "价格弹性分析与建议价格区间" },
      { key: "experiment", name: "模型实验", ico: "🧪", desc: "预测模型离线评估与基线对照" },
    ],
  }),
  computed: {
    currentMenu() { return this.menus.find(m => m.key === this.view); }
  }
}).mixin({
  data: () => ({ loading: true, err: "" }),
  methods: { retry() { location.reload(); } }
}).component("dashboard", Dashboard)
  .component("rfm", Rfm)
  .component("conversion", Conversion)
  .component("prediction", Prediction)
  .component("recommend", Recommend)
  .component("pricing", Pricing)
  .component("experiment", Experiment)
  .mount("#app");
