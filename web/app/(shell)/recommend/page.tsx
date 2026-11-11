import type { Metadata } from "next";
import { api, settled } from "@/lib/api";
import { fmt, money, pctRaw, signed } from "@/lib/format";
import { ErrorNote, PageHeader, Panel, Pill, PillRow, Table, Td, Tag } from "@/components/ui/primitives";
import { CategoryBubble, ProductGrowthBar } from "@/components/charts/recommend-charts";

export const metadata: Metadata = { title: "选品建议" };

export default async function RecommendPage() {
  const [rec, compare, selSummary, selProducts] = await Promise.all([
    settled(api.recommendProducts()),
    settled(api.recommendStrategyCompare()),
    settled(api.selectionSummary()),
    settled(api.selectionProducts(10)),
  ]);

  const windowText = rec.ok && rec.data.window ? `${rec.data.window.recent} ~ ${rec.data.window.end}` : "近 90 天 vs 前 90 天";
  const cmp = compare.ok ? compare.data : null;
  const sel = selSummary.ok ? selSummary.data : null;

  return (
    <div className="mx-auto min-w-0 max-w-shell px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="选品建议" desc="增长潜力品类推荐与离线策略对照评估" />

      <div className="mb-4">
        <PillRow>
          {sel && <Pill label="选品条目" value={fmt(sel.total)} />}
          {sel?.by_type?.map((t) => (
            <Pill key={t.selection_type} label={t.selection_type} value={fmt(t.cnt)} />
          ))}
          <Pill label="评估窗口" value={windowText} />
        </PillRow>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="品类：规模 × 增长率" subtitle="气泡大小 = 综合分（规模归一×0.5 + 增长率归一×0.5）">
          {rec.ok ? <CategoryBubble data={rec.data.data} /> : <ErrorNote message={rec.error} path="/recommendation/products" />}
        </Panel>
        <Panel title="商品增长榜 Top10" subtitle="按近期 GMV 排序的入选商品">
          {selProducts.ok ? (
            <ProductGrowthBar data={selProducts.data.data} />
          ) : (
            <ErrorNote message={selProducts.error} path="/selection/products" />
          )}
        </Panel>
      </div>

      <Panel
        title="智能选品推荐 Top10 品类"
        subtitle="综合分 = 规模（近期 GMV 归一）× 0.5 + 增长率（归一）× 0.5"
        className="mt-4"
      >
        {rec.ok ? (
          <Table head={["#", "品类", "近期 GMV", "前期 GMV", "增长率", "近期销量", "均价", "综合分"]}>
            {rec.data.data.map((d) => (
              <tr key={d.category} className="transition-colors hover:bg-surface2/40">
                <Td num={false} className="font-mono text-muted">{d.rank}</Td>
                <Td>{d.category}</Td>
                <Td num>{money(d.recent_gmv)}</Td>
                <Td num>{money(d.prev_gmv)}</Td>
                <Td num>
                  <Tag tone={d.growth_rate >= 0 ? "up" : "down"}>{signed(d.growth_rate * 100)}</Tag>
                </Td>
                <Td num>{fmt(d.recent_qty)}</Td>
                <Td num>{money(d.avg_price)}</Td>
                <Td num className="font-semibold text-fg">{d.score}</Td>
              </tr>
            ))}
          </Table>
        ) : (
          <ErrorNote message={rec.error} path="/recommendation/products" />
        )}
      </Panel>

      <Panel
        title="商品级选品榜 Top10"
        subtitle="算法 2 交付结果，含推荐等级（强推 / 观察）"
        className="mt-4"
      >
        {selProducts.ok ? (
          <Table head={["#", "商品 ID", "品类", "近期 GMV", "增长率", "均价", "综合分", "建议"]}>
            {selProducts.data.data.map((d) => (
              <tr key={d.product_id} className="transition-colors hover:bg-surface2/40">
                <Td num={false} className="font-mono text-muted">{d.rank}</Td>
                <Td muted className="font-mono text-[11px]">{d.product_id.slice(0, 8)}…</Td>
                <Td>{d.category}</Td>
                <Td num>{money(d.gmv_recent)}</Td>
                <Td num>
                  <Tag tone={(d.growth_pct ?? 0) >= 0 ? "up" : "down"}>{signed(d.growth_pct)}</Tag>
                </Td>
                <Td num>{money(d.avg_price)}</Td>
                <Td num>{d.score_total}</Td>
                <Td>
                  <Tag tone={d.recommendation === "强推" ? "up" : "neutral"}>{d.recommendation}</Tag>
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <ErrorNote message={selProducts.error} path="/selection/products" />
        )}
      </Panel>

      <Panel
        title="离线策略对照评估"
        subtitle="验证期 Top-10 命中前 20% 品类 —— 用留出期数据检验选品策略是否真有预测力"
        className="mt-4"
      >
        {cmp ? (
          <>
            <div className="grid gap-4 lg:grid-cols-2">
              {[cmp.strategy_A, cmp.strategy_B].map((s, i) =>
                s ? (
                  <div key={s.name} className="rounded-lg border border-line bg-surface2/30 p-3">
                    <p className="mb-2 text-[12px] text-muted">
                      {s.name} → 命中率{" "}
                      <b className={i === 0 ? "text-accent" : "text-mint"}>{pctRaw(s.hit_rate)}</b>
                    </p>
                    <Table head={["品类", "训练期 GMV", "增长率"]} dense>
                      {s.recommended.map((d) => (
                        <tr key={d.category}>
                          <Td>{d.category}</Td>
                          <Td num>{money(d.train_gmv)}</Td>
                          <Td num>{pctRaw(d.growth * 100)}</Td>
                        </tr>
                      ))}
                    </Table>
                  </div>
                ) : null,
              )}
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-muted">
              结论：{cmp.conclusion}（验证期 {cmp.validation_window}，前 20% 品类数 = {cmp.top20_count}）
            </p>
          </>
        ) : (
          <ErrorNote message={compare.ok ? "" : compare.error} path="/recommendation/strategy_compare" />
        )}
      </Panel>
    </div>
  );
}
