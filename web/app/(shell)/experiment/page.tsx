import type { Metadata } from "next";
import { api, settled } from "@/lib/api";
import { fmt, pctRaw } from "@/lib/format";
import { ErrorNote, PageHeader, Panel, Table, Td, Tag } from "@/components/ui/primitives";
import { MedianCompareBar, ModelErrorBar } from "@/components/charts/experiment-charts";

export const metadata: Metadata = { title: "模型实验" };

export default async function ExperimentPage() {
  const [compare, median, stats] = await Promise.all([
    settled(api.experimentCompare()),
    settled(api.experimentMedian()),
    settled(api.experimentSummaryStats()),
  ]);

  const models = compare.ok ? compare.data.data : [];
  const med = median.ok ? median.data : null;
  const better = med?.main_model_better_categories;
  const rows = stats.ok ? stats.data.data.slice(0, 8) : [];

  return (
    <div className="min-w-0 px-4 py-5 sm:px-6 lg:px-7">
      <PageHeader title="模型实验" desc="预测模型离线评估与基线对照 · 结果如实呈现，不做乐观修饰" />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="各模型误差对比" subtitle="按 74 个品类分别建模后取均值">
          {compare.ok ? <ModelErrorBar data={models} /> : <ErrorNote message={compare.error} path="/experiment/compare" />}
        </Panel>
        <Panel title="稳健口径：MAPE 中位数" subtitle="均值易被极端品类拉偏，中位数更能反映整体水平">
          {med?.median ? (
            <MedianCompareBar
              mainModel={med.median.main_model_mape ?? 0}
              baseline={med.median.baseline_mape ?? 0}
            />
          ) : (
            <ErrorNote message={median.ok ? "" : median.error} path="/experiment/median" />
          )}
        </Panel>
      </div>

      <Panel title="预测模型离线对照" subtitle="74 个品类，留出 6 周作为验证窗口" className="mt-4">
        {compare.ok ? (
          <Table head={["模型", "品类数", "MAPE 均值", "WAPE 均值", "MAE 均值", "RMSE 均值", "较基线 MAPE"]}>
            {models.map((d) => (
              <tr key={d.model} className="transition-colors hover:bg-surface2/40">
                <Td>
                  <span className={d.is_baseline ? "text-amber" : "text-fg"}>{d.model}</span>
                  {d.is_baseline && (
                    <span className="ml-2">
                      <Tag>基线</Tag>
                    </span>
                  )}
                </Td>
                <Td num>{fmt(d.category_cnt)}</Td>
                <Td num className="font-semibold">{pctRaw(d.avg_mape)}</Td>
                <Td num>{pctRaw(d.avg_wape)}</Td>
                <Td num>{fmt(d.avg_mae, 2)}</Td>
                <Td num>{fmt(d.avg_rmse, 2)}</Td>
                <Td num>{d.is_baseline ? "—" : pctRaw(d.avg_mape_improve_pct)}</Td>
              </tr>
            ))}
          </Table>
        ) : (
          <ErrorNote message={compare.error} path="/experiment/compare" />
        )}
      </Panel>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel
          title="主模型优于基线的品类"
          subtitle="结论应如实表述为「部分品类优于基线」，而非全面碾压"
        >
          {better ? (
            <>
              <p className="tnum text-[32px] font-bold leading-none text-accent">
                {fmt(better.better)}
                <span className="text-[18px] font-normal text-muted">/{fmt(better.total)}</span>
              </p>
              <p className="mt-2 text-[12px] text-muted">
                占比 <b className="text-fg">{pctRaw(better.pct)}</b>
              </p>
            </>
          ) : (
            <ErrorNote message={median.ok ? "" : median.error} path="/experiment/median" />
          )}
        </Panel>

        <Panel title="数据集与实验概览">
          {stats.ok ? (
            <Table head={["指标", "数值"]} dense>
              {rows.map((d) => (
                <tr key={d.name}>
                  <Td>{d.name}</Td>
                  <Td num className="font-medium">
                    {d.value_text}
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            <ErrorNote message={stats.error} path="/experiment/summary-stats" />
          )}
        </Panel>
      </div>

      {med?.note && <p className="mt-3 text-[11.5px] leading-relaxed text-muted/80">{med.note}</p>}
    </div>
  );
}
