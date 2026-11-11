"use client";

import { useState } from "react";
import { renderMarkdown } from "@/lib/markdown";
import { ChartCard } from "@/components/assistant/chart-card";
import type { StageEvent, StepEvent } from "@/lib/sse";
import type { ChatData } from "@/types/api";

export interface ChatMessageData {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming: boolean;
  stages: StageEvent[];
  steps: StepEvent[];
  result: ChatData | null;
  error?: string;
}

/** 当前正在做什么：取最后一个未完成/最新的阶段 */
function currentActivity(stages: StageEvent[], steps: StepEvent[]): string {
  const lastStep = steps[steps.length - 1];
  if (lastStep) return `已调用 ${lastStep.tool}（${lastStep.elapsed_ms} ms）`;
  const last = stages[stages.length - 1];
  return last?.label ?? "正在思考";
}

export function ChatMessage({ msg }: { msg: ChatMessageData }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] text-[12px] ${
          isUser
            ? "bg-[#243a5e] text-fg"
            : "bg-gradient-to-br from-accent to-mint font-semibold text-[#06202e]"
        }`}
      >
        {isUser ? "我" : "AI"}
      </div>

      <div className="min-w-0 flex-1">
        <div className={`mb-1 text-[11px] text-muted ${isUser ? "text-right" : ""}`}>
          {isUser ? "你" : "经营决策助手"}
        </div>

        <div
          className={`rounded-[10px] border px-3.5 py-3 ${
            isUser ? "border-line bg-[#1c2a44]" : "border-line bg-[#141d30]"
          }`}
        >
          {/* 流式中的过程提示：让等待可见，而不是转圈 */}
          {msg.streaming && !msg.text && (
            <div className="flex items-center gap-2 text-[12.5px] text-muted">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
              {currentActivity(msg.stages, msg.steps)}
            </div>
          )}

          {msg.text && (
            <div className={`prose-chat ${msg.streaming ? "stream-caret" : ""}`}>
              {renderMarkdown(msg.text)}
            </div>
          )}

          {msg.error && (
            <div className="mt-2 rounded-lg border border-coral/30 bg-coral/10 px-2.5 py-2 text-[12px] text-coral">
              {msg.error}
            </div>
          )}

          {!msg.streaming &&
            msg.result?.charts?.map((opt, i) => <ChartCard key={i} option={opt} index={i} />)}
        </div>

        {msg.result && !msg.streaming && <MetaRow data={msg.result} />}
        {msg.result && !msg.streaming && <Feedback question={msg.text} data={msg.result} />}
      </div>
    </div>
  );
}

/** 回答脚注：模式 / 置信度 / 耗时 / 底座 / 数据源 */
function MetaRow({ data }: { data: ChatData }) {
  const bits = [
    `模式 ${data.mode ?? "full"}`,
    `置信度 ${data.confidence ?? "-"}`,
    `${data.elapsed_ms ?? 0} ms`,
    data.provider === "offline" ? "离线规则引擎" : `${data.provider ?? "?"}/${data.model ?? ""}`,
    data.refused ? "已拒答" : "",
    `数据源 ${data.datasource ?? "-"}`,
  ].filter(Boolean);

  return (
    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted/80">
      {bits.map((b) => (
        <span key={b}>{b}</span>
      ))}
    </div>
  );
}

/** 反馈闭环：👍 / 👎 + 纠正，写回后端的反馈库，进入下一轮回归 */
function Feedback({ question, data }: { question: string; data: ChatData }) {
  const [state, setState] = useState<"idle" | "fixing" | "done">("idle");
  const [savedId, setSavedId] = useState<number | null>(null);
  const [err, setErr] = useState("");

  async function submit(verdict: "up" | "down", correction = "") {
    try {
      const res = await fetch("/api/llm/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          answer: data.answer ?? "",
          mode: data.mode ?? "full",
          verdict,
          correction,
        }),
      });
      const j = await res.json();
      if (j.code !== 0) throw new Error(j.message || "提交失败");
      setSavedId(j.data.id);
      setState("done");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  if (state === "done") {
    return (
      <div className="mt-2 text-[11px] text-mint">
        ✓ 已记录 #{savedId}，经人工审核后进入下一轮回归
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <button onClick={() => submit("up")} className="btn-ghost !rounded-full !py-1 !text-[11px]">
        👍 有用
      </button>
      <button
        onClick={() => setState("fixing")}
        className="btn-ghost !rounded-full !py-1 !text-[11px]"
      >
        👎 答得不对
      </button>

      {state === "fixing" && (
        <form
          className="flex w-full gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            const input = (e.currentTarget.elements.namedItem("fix") as HTMLInputElement)?.value ?? "";
            submit("down", input);
          }}
        >
          <input
            name="fix"
            autoFocus
            placeholder="哪里不对？例如：客单价应为 136.68"
            className="min-w-0 flex-1 rounded-lg border border-line bg-[#141d30] px-2.5 py-1.5 text-[12px] text-fg outline-none focus:border-accent"
          />
          <button type="submit" className="rounded-lg bg-accent px-3 py-1.5 text-[12px] font-medium text-white">
            提交
          </button>
        </form>
      )}

      {err && <span className="text-[11px] text-coral">{err}</span>}
    </div>
  );
}
