import type { Metadata } from "next";
import { api, settled } from "@/lib/api";
import { fmt, money, pctRaw } from "@/lib/format";
import { ErrorNote, PageHeader, Panel, Pill, PillRow, Table, Td, Tag } from "@/components/ui/primitives";
import { ElasticityScatter, PricingCategoryBar } from "@/components/charts/pricing-charts";

export const metadata: Metadata = { title: "定价建议" };

export default async function PricingPage() {
  const [summary, suggestions, byCategory, skipped] = await Promise.all([
    settled(api.pricingSummary()),
    settled(api.pricingSuggestions(50)),
    settled(api.pricingByCategory()),
    settled(api.pricingSkipped()),
  ]);

  const s = summary.ok ? summary.data : null;
  const rows = suggestions.ok ? suggestions.data.data : [];
  const cats = byCategory.ok ? byCategory.data.data : [];
  const skip = skipped.ok ? skipped.data.data : [];

  return (
    <div className="min-w-0 px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="定价建议" desc="价格弹性分析与建议价格区间" />

      {s ? (
        <div className="mb-4">
          <PillRow>
            <Pill label="分析商品" value={fmt(s.total)} />
            <Pill label="可给建议价" value={fmt(s.has_suggestion)} tone="mint" />
            <Pill label="样本不足" value={fmt(s.no_suggestion)} tone="amber" />
            <Pill label="高置信建议" value={fmt(s.confidence?.["高"] ?? 0)} tone="accent" />
            <Pill label="平均预期营收变化" value={pctRaw(s.avg_expected_revenue_change_pct)} />
          </PillRow>
        </div>
      ) : (
        <ErrorNote message={summary.ok ? "" : summary.error} path="/pricing/summary" />
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="各品类可给建议价商品数" subtitle="堆叠展示「可给建议价」与「样本不足」的比例">
          {byCategory.ok ? (
            <PricingCategoryBar data={cats} />
          ) : (
            <ErrorNote message={byCategory.error} path="/pricing/by-category" />
          )}
        </Panel>
        <Panel title="价格弹性 × 预期营收变化" subtitle="虚线为营收变化 0 轴，其下方为负收益调价">
          {suggestions.ok ? (
            <ElasticityScatter data={rows} />
          ) : (
            <ErrorNote message={suggestions.error} path="/pricing/suggestions" />
          )}
        </Panel>
      </div>

      <Panel
        title="商品定价建议"
        subtitle="建议价仅供经营决策参考。无建议价表示数据不足，不会被误显示为 0"
        className="mt-4"
      >
        {suggestions.ok ? (
          <Table head={["商品 ID", "品类", "置信度", "当前价", "建议价", "调价幅度", "预期营收变化", "依据"]}>
            {rows.map((d) => (
              <tr key={d.product_id} className="transition-colors hover:bg-surface2/40">
                <Td muted className="font-mono text-[11px]">{d.product_id.slice(0, 10)}…</Td>
                <Td>{d.category}</Td>
                <Td>
                  <Tag tone={d.confidence === "高" ? "up" : "neutral"}>{d.confidence}</Tag>
                </Td>
                <Td num>{money(d.current_price)}</Td>
                <Td num className={d.has_suggestion ? "font-semibold text-fg" : "text-muted"}>
                  {d.has_suggestion ? money(d.suggested_price) : "数据不足"}
                </Td>
                <Td num>{d.has_suggestion ? pctRaw(d.price_change_pct) : "-"}</Td>
                <Td num>{d.has_suggestion ? pctRaw(d.expected_revenue_change_pct) : "-"}</Td>
                <Td muted className="max-w-[180px] truncate text-[11px]" >
                  {d.elasticity_source || d.note || "—"}
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <ErrorNote message={suggestions.error} path="/pricing/suggestions" />
        )}
      </Panel>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="按品类汇总">
          {byCategory.ok ? (
            <Table head={["品类", "商品数", "有建议价", "平均当前价", "平均调价幅度"]}>
              {cats.map((d) => (
                <tr key={d.category} className="transition-colors hover:bg-surface2/40">
                  <Td>{d.category}</Td>
                  <Td num>{fmt(d.product_cnt)}</Td>
                  <Td num>{fmt(d.has_suggestion)}</Td>
                  <Td num>{money(d.avg_current_price)}</Td>
                  <Td num>{pctRaw(d.avg_change_pct)}</Td>
                </tr>
              ))}
            </Table>
          ) : (
            <ErrorNote message={byCategory.error} path="/pricing/by-category" />
          )}
        </Panel>

        <Panel
          title="未给建议价的商品"
          subtitle={`共 ${fmt(skip.length)} 个：月度观测不足或价格变异太小，无法估计弹性`}
        >
          {skipped.ok ? (
            <Table head={["商品 ID", "品类", "观测月", "价格 CV"]}>
              {skip.slice(0, 10).map((d) => (
                <tr key={d.product_id} className="transition-colors hover:bg-surface2/40">
                  <Td muted className="font-mono text-[11px]">{d.product_id.slice(0, 8)}…</Td>
                  <Td>{d.category}</Td>
                  <Td num>{d.months_observed}</Td>
                  <Td num>{fmt(d.price_cv_pct, 2)}%</Td>
                </tr>
              ))}
            </Table>
          ) : (
            <ErrorNote message={skipped.error} path="/pricing/skipped" />
          )}
        </Panel>
      </div>
    </div>
  );
}
