import type { Metadata } from "next";
import { api, settled } from "@/lib/api";
import { fmt, money, pctRaw } from "@/lib/format";
import { ErrorNote, PageHeader, Panel, Pill, PillRow, Table, Td } from "@/components/ui/primitives";
import { FunnelChart, RepurchaseMoneyBar, RepurchasePie } from "@/components/charts/conversion-charts";

export const metadata: Metadata = { title: "转化分析" };

export default async function ConversionPage() {
  const [funnel, repurchase] = await Promise.all([
    settled(api.conversionFunnel()),
    settled(api.conversionRepurchase()),
  ]);

  const rp = repurchase.ok ? repurchase.data.data : [];

  return (
    <div className="mx-auto min-w-0 max-w-shell px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="转化分析" desc="订单转化漏斗与复购情况" />

      {rp.length > 0 && (
        <div className="mb-4">
          <PillRow>
            {rp.map((d) => (
              <Pill
                key={d.type}
                label={d.type}
                value={`${fmt(d.customers)} 人 · ${pctRaw(d.customer_pct)}`}
              />
            ))}
          </PillRow>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="订单转化漏斗" subtitle="下单 → 已批准 → 已发货 → 已送达 → 已评价">
          {funnel.ok ? (
            <FunnelChart data={funnel.data.data} />
          ) : (
            <ErrorNote message={funnel.error} path="/conversion/funnel" />
          )}
        </Panel>
        <Panel title="单次 vs 复购客户">
          {repurchase.ok ? (
            <RepurchasePie data={rp} />
          ) : (
            <ErrorNote message={repurchase.error} path="/conversion/repurchase" />
          )}
        </Panel>
      </div>

      <Panel title="复购客户金额贡献对比" subtitle="柱=金额贡献，线=客户占比" className="mt-4">
        {repurchase.ok ? (
          <RepurchaseMoneyBar data={rp} />
        ) : (
          <ErrorNote message={repurchase.error} path="/conversion/repurchase" />
        )}
      </Panel>

      {rp.length > 0 && (
        <Panel title="复购明细" className="mt-4">
          <Table head={["客户类型", "客户数", "金额贡献", "客户占比"]}>
            {rp.map((d) => (
              <tr key={d.type} className="transition-colors hover:bg-surface2/40">
                <Td>{d.type}</Td>
                <Td num>{fmt(d.customers)}</Td>
                <Td num>{money(d.monetary)}</Td>
                <Td num>{pctRaw(d.customer_pct)}</Td>
              </tr>
            ))}
          </Table>
        </Panel>
      )}
    </div>
  );
}
