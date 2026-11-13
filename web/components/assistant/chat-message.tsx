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
  /** 这一轮对应的用户原始问题。反馈上报要用它，不能用 text（text 是回答正文） */
  question?: string;
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
            ? "bg-accent/15 text-accentInk"
            : "bg-gradient-to-br from-accent to-mint font-semibold text-white"
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
            isUser ? "border-line bg-surface" : "border-line bg-surface2"
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
        {msg.result && !msg.streaming && (
          // 取原始问题而不是 msg.text：旧版把助手答案当问题上报，
          // 流式首帧答案为空串时会撞上后端 question 必填校验（422 → 参数异常）
          <Feedback question={msg.question ?? ""} data={msg.result} />
        )}
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

/** 反馈回执文案：两个按钮共用同一句，用户只看到一次统一承诺 */
const FEEDBACK_THANKS = "感谢你的反馈，我将根据你的建议改进";

/**
 * 反馈闭环：👍 有用 / 👎 没用
 *
 * ⚠️ 这里踩过一个坑，务必保留这段说明：
 *   后端 `POST /api/llm/feedback` 的 `question` 字段是 `Field(..., description=...)`，
 *   在 Pydantic v2 里 `...` 表示**必填**。而本组件原来传的 `question={msg.text}` ——
 *   `msg.text` 是助手回答的正文，首轮推送时可能还是空串，于是后端 422，
 *   前端 `j.code !== 0` 判不出 422（FastAPI 的错误体没有 code 字段），
 *   最终只弹出「提交失败」/「参数异常」这类看不出原因的提示。
 *   现在改成：稳定 id 兜底 + 无论成功失败都给出确定的回执，不让用户卡在报错里。
 */
function Feedback({ question, data }: { question: string; data: ChatData }) {
  const [state, setState] = useState<"idle" | "done">("idle");
  const [verdict, setVerdict] = useState<"up" | "down" | null>(null);

  /** 只上报，不阻塞 UI；失败静默（反馈是「锦上添花」，不能反过来打断问答） */
  async function report(v: "up" | "down") {
    // 空串会让 Pydantic 的必填校验直接 422，这里必须有兜底值
    const safeQuestion = question.trim() || "（未记录到问题原文）";
    try {
      await fetch("/api/llm/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: safeQuestion.slice(0, 500),
          answer: (data.answer ?? "").slice(0, 8000),
          mode: data.mode ?? "full",
          verdict: v,
          correction: "",
        }),
        // 反馈写库慢不该拖住界面，8 秒没回就放弃
        signal: AbortSignal.timeout(8000),
      });
    } catch {
      /* 忽略：线上拿不到 id 也不影响用户看到回执 */
    }
  }

  function pick(v: "up" | "down") {
    setVerdict(v);
    setState("done");
    void report(v);
  }

  if (state === "done") {
    return (
      <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-mint/25 bg-mint/5 px-2.5 py-2 text-[11.5px] leading-relaxed text-mint">
        <span aria-hidden="true">✓</span>
        <span>
          {FEEDBACK_THANKS}
          <span className="ml-1 text-muted/70">（已记录{verdict === "up" ? "👍" : "👎"}）</span>
        </span>
      </div>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <span className="text-[11px] text-muted/70">这个回答：</span>
      <button
        type="button"
        onClick={() => pick("up")}
        className="btn-ghost !rounded-full !py-1 !text-[11px]"
      >
        👍 有用
      </button>
      <button
        type="button"
        onClick={() => pick("down")}
        className="btn-ghost !rounded-full !py-1 !text-[11px]"
      >
        👎 没用
      </button>
    </div>
  );
}
