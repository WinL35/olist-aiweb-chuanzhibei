"use client";

import { useState } from "react";
import type { StageEvent, StepEvent } from "@/lib/sse";
import type { ChatData, EvalResult } from "@/types/api";

/* ============ 取数轨迹 ============ */

export function TracePanel({
  data,
  steps,
  streaming,
}: {
  data: ChatData | null;
  steps: StepEvent[];
  streaming: boolean;
}) {
  // 流式中优先展示实时步骤；结束后回落到完整 trace
  if (streaming && steps.length) {
    return (
      <div className="space-y-1.5">
        {steps.map((s, i) => (
          <div
            key={i}
            className={`rounded-lg border-l-[3px] bg-[#141d30] px-2.5 py-2 text-[11.5px] ${
              s.ok ? "border-accent" : "border-coral"
            }`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span>
                <span className="text-muted">#{s.step}</span> <b>{s.tool}</b>
              </span>
              <span className="tnum shrink-0 text-[10.5px] text-mint">{s.elapsed_ms}ms</span>
            </div>
            {!s.ok && <div className="mt-1 text-[10.5px] text-coral">{s.error || "调用失败"}</div>}
          </div>
        ))}
        <div className="rounded-lg border-l-[3px] border-mint bg-[#141d30] px-2.5 py-2 text-[11.5px] text-muted">
          正在生成回答…
        </div>
      </div>
    );
  }

  const trace = data?.trace ?? [];
  if (!trace.length) {
    if (data?.tools_used?.length) {
      return (
        <div className="space-y-1.5">
          {data.tools_used.map((t) => (
            <div key={t} className="rounded-lg bg-[#141d30] px-2.5 py-2 text-[11.5px]">
              <b>{t}</b>
              <div className="text-[10.5px] text-muted">离线引擎按意图自动调用</div>
            </div>
          ))}
        </div>
      );
    }
    return <Placeholder>{data?.mode === "no_tools" ? "no_tools 模式：未调用工具" : "未调用工具"}</Placeholder>;
  }

  return (
    <div className="space-y-1.5">
      {trace.map((s, i) =>
        s.action === "tool" ? (
          <div
            key={i}
            className={`rounded-lg border-l-[3px] bg-[#141d30] px-2.5 py-2 text-[11.5px] ${
              s.ok ? "border-accent" : "border-coral"
            }`}
          >
            <div>
              <span className="text-muted">#{s.step}</span> 调用 <b>{s.tool}</b>
            </div>
            <div className="mt-0.5 break-all font-mono text-[10.5px] text-muted/70">
              {JSON.stringify(s.args ?? {})}
            </div>
            {!s.ok && <div className="mt-1 text-[10.5px] text-coral">{s.error || "失败"}</div>}
          </div>
        ) : (
          <div
            key={i}
            className="rounded-lg border-l-[3px] border-mint bg-[#141d30] px-2.5 py-2 text-[11.5px]"
          >
            <span className="text-muted">#{s.step}</span> 生成回答（{s.content_chars ?? 0} 字）
          </div>
        ),
      )}
    </div>
  );
}

/* ============ 数据依据 ============ */

export function CitationsPanel({ data }: { data: ChatData | null }) {
  const list = data?.citations ?? [];
  if (!list.length) return <Placeholder>本次回答无数字引用</Placeholder>;

  return (
    <div className="space-y-0">
      {list.map((c, i) => (
        <div
          key={i}
          className="flex items-start justify-between gap-2 border-b border-dashed border-[#223049] py-1.5 text-[11.5px] last:border-0"
        >
          <span className="min-w-0 text-muted">
            {c["指标"]}
            <br />
            <span className="text-[10.5px] opacity-60">{c["来源"]}</span>
          </span>
          <span className="tnum shrink-0 text-right font-medium text-white">{String(c["值"])}</span>
        </div>
      ))}
    </div>
  );
}

/* ============ 口径与依据 ============ */

export function RulesPanel({ data }: { data: ChatData | null }) {
  const policies = data?.policy_hits ?? [];
  const rules = data?.rules_applied ?? [];
  const snippets = data?.snippets ?? [];
  const limitations = data?.limitations ?? [];

  if (!policies.length && !rules.length && !snippets.length) {
    return <Placeholder>未命中口径与文档片段</Placeholder>;
  }

  return (
    <div className="space-y-1">
      {policies.length > 0 && (
        <div className="rounded-md border border-amber/30 bg-amber/10 px-2 py-1.5 text-[11px] text-amber">
          ⚖ 口径拦截：{policies.join("；")}
        </div>
      )}

      {rules.map((r) => (
        <div
          key={r.id}
          className="flex items-start justify-between gap-2 border-b border-dashed border-[#223049] py-1 text-[11.5px] last:border-0"
        >
          <span className="text-muted">
            口径 {r.id}
            <br />
            <span className="text-[10.5px] opacity-60">{r.topic}</span>
          </span>
        </div>
      ))}

      {snippets.map((s, i) => (
        <div
          key={i}
          className="flex items-start justify-between gap-2 border-b border-dashed border-[#223049] py-1 text-[11.5px] last:border-0"
        >
          <span className="min-w-0 text-muted">
            《{s.source}》
            <br />
            <span className="text-[10.5px] opacity-60">{s.heading}</span>
          </span>
          {s.score !== undefined && (
            <span className="tnum shrink-0 text-[10.5px] text-muted/60">{s.score}</span>
          )}
        </div>
      ))}

      {limitations.length > 0 && (
        <div className="pt-1">
          <div className="text-[11px] text-amber">局限</div>
          {limitations.map((x, i) => (
            <div key={i} className="text-[10.5px] leading-relaxed text-muted">
              · {x}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ============ 快速评测 ============ */

export function EvalPanel() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<EvalResult | null>(null);
  const [err, setErr] = useState("");

  async function run() {
    setRunning(true);
    setErr("");
    try {
      const res = await fetch("/api/llm/eval/run?limit=6&modes=baseline,full");
      const j = await res.json();
      if (j.code !== 0) throw new Error(j.message || "评测失败");
      setResult(j.data as EvalResult);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      {result ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-muted">
                <th className="py-1 text-left font-semibold">模式</th>
                <th className="py-1 text-right font-semibold">A</th>
                <th className="py-1 text-right font-semibold">B</th>
                <th className="py-1 text-right font-semibold">C</th>
                <th className="py-1 text-right font-semibold">D</th>
                <th className="py-1 text-right font-semibold">总</th>
              </tr>
            </thead>
            <tbody>
              {result.summary.map((r) => (
                <tr key={r.mode} className="border-t border-[#223049]">
                  <td className="py-1">{r.mode}</td>
                  <td className="tnum py-1 text-right">{r.A ?? "-"}%</td>
                  <td className="tnum py-1 text-right">{r.B ?? "-"}%</td>
                  <td className="tnum py-1 text-right">{r.C ?? "-"}%</td>
                  <td className="tnum py-1 text-right">{r.D ?? "-"}%</td>
                  <td className="tnum py-1 text-right font-semibold text-white">{r.acc}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-1.5 text-[10.5px] text-muted/70">
            {result.simulated ? "⚠️ 离线规则引擎，数值仅反映管线有效性" : "真实底座"}
          </div>
        </div>
      ) : (
        <Placeholder>点下面的按钮跑一次（6 题 × 2 模式）</Placeholder>
      )}

      <button
        onClick={run}
        disabled={running}
        className="btn-ghost mt-2 !text-[11px] disabled:opacity-50"
      >
        {running ? "评测中…" : "运行评测"}
      </button>
      {err && <div className="mt-1 text-[10.5px] text-coral">{err}</div>}
    </div>
  );
}

/* ============ 通用 ============ */

export function Placeholder({ children }: { children: React.ReactNode }) {
  return <div className="py-1 text-[11.5px] text-muted">{children}</div>;
}

export function PanelTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2 text-[10.5px] font-semibold uppercase tracking-wider text-muted">
      {children}
    </h3>
  );
}

export type { StageEvent };
