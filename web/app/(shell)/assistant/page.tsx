"use client";

import { useEffect, useRef, useState } from "react";
import { ChatMessage, type ChatMessageData } from "@/components/assistant/chat-message";
import {
  CitationsPanel,
  EvalPanel,
  PanelTitle,
  Placeholder,
  RulesPanel,
  TracePanel,
} from "@/components/assistant/side-panels";
import { clientGet } from "@/lib/client-api";
import { PillSelect } from "@/components/ui/pill-select";
import { streamChat, type StageEvent, type StepEvent } from "@/lib/sse";
import type { ChatData, ChatMode, ChatTurn, ExampleGroups, LlmHealth } from "@/types/api";

const MODES: { key: ChatMode; label: string; hint: string }[] = [
  { key: "full", label: "full", hint: "全量：口径 + 检索 + 工具" },
  { key: "no_tools", label: "no_tools", hint: "消融：不调用工具" },
  { key: "no_rag", label: "no_rag", hint: "消融：不做检索" },
  { key: "baseline", label: "baseline", hint: "对照：裸底座直答" },
];

const WELCOME =
  "我是这个平台的经营决策助手。**我只用平台里的真实数据回答**，遇到数据不支持的问题会直接说做不到。\n\n" +
  "可以问我：GMV 口径、品类销量预测、选品推荐、定价建议、模型准不准。";

export default function AssistantPage() {
  const [msgs, setMsgs] = useState<ChatMessageData[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<ChatMode>("full");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<LlmHealth | null>(null);
  const [examples, setExamples] = useState<ExampleGroups>({});
  const [streamSteps, setStreamSteps] = useState<StepEvent[]>([]);
  const [streamStages, setStreamStages] = useState<StageEvent[]>([]);
  const [lastData, setLastData] = useState<ChatData | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  const historyRef = useRef<ChatTurn[]>([]);
  const accRef = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  /* ---- 启动：健康检查 + 示例问题 ---- */
  useEffect(() => {
    clientGet<LlmHealth>("/llm/health")
      .then(setHealth)
      .catch(() => setHealth(null));
    clientGet<{ data: ExampleGroups }>("/llm/examples")
      .then((r) => setExamples(r.data ?? {}))
      .catch(() => setExamples({}));
  }, []);

  /* ---- 新消息到达时滚到底部 ---- */
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs]);

  async function ask(raw: string) {
    const question = raw.trim();
    if (!question || busy) return;

    const uid = `u-${Date.now()}`;
    const bid = `b-${Date.now()}`;
    accRef.current = "";
    setInput("");
    setStreamSteps([]);
    setStreamStages([]);
    setBusy(true);

    setMsgs((prev) => [
      ...prev,
      { id: uid, role: "user", text: question, streaming: false, stages: [], steps: [], result: null },
      {
        id: bid,
        role: "assistant",
        text: "",
        streaming: true,
        stages: [],
        steps: [],
        result: null,
        // 记下本轮提问，供 👍/👎 上报使用；不能用 text 顶替（那是回答正文）
        question,
      },
    ]);

    const patch = (fn: (m: ChatMessageData) => ChatMessageData) =>
      setMsgs((prev) => prev.map((m) => (m.id === bid ? fn(m) : m)));

    let steps: StepEvent[] = [];
    let stages: StageEvent[] = [];
    let finished = false;

    await streamChat(
      { question, mode, history: historyRef.current.slice(-12) },
      {
        onStage: (d) => {
          stages = [...stages, d];
          setStreamStages(stages);
          patch((m) => ({ ...m, stages }));
        },
        onStep: (d) => {
          steps = [...steps, d];
          setStreamSteps(steps);
          patch((m) => ({ ...m, steps }));
        },
        onDelta: (t) => {
          accRef.current += t;
          const acc = accRef.current;
          patch((m) => ({ ...m, text: acc }));
        },
        onResult: (d) => {
          const data = d as unknown as ChatData;
          finished = true;
          setLastData(data);
          // 兜底：若因网络问题没收到任何 delta，用完整答案补齐
          if (!accRef.current && data.answer) accRef.current = data.answer;
          patch((m) => ({ ...m, result: data, streaming: false, text: accRef.current || data.answer || "" }));
        },
        onError: (message) => {
          finished = true;
          patch((m) => ({ ...m, error: message, streaming: false }));
        },
      },
    );

    if (!finished) {
      patch((m) => ({ ...m, streaming: false }));
    }

    // 把这一轮写入多轮历史，支持「再按月拆」「那第二名呢」这类追问
    historyRef.current.push(
      { role: "user", content: question },
      { role: "assistant", content: accRef.current },
    );
    if (historyRef.current.length > 24) {
      historyRef.current = historyRef.current.slice(-24);
    }

    setBusy(false);
    inputRef.current?.focus();
  }

  const statusBadges = buildBadges(health);

  return (
    <div className="flex h-[calc(100dvh-45px)] lg:h-dvh">
      {/* ===== 左侧：对话 ===== */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-2 border-b border-line bg-surface2 px-4 py-2.5">
          <div className="mr-1 min-w-0">
            <h1 className="text-[14px] font-bold leading-tight text-fg">🧭 经营决策助手</h1>
            <p className="text-[10.5px] text-muted">口径库 + 工具调用 + 检索</p>
          </div>

          <div className="hidden flex-wrap gap-1.5 sm:flex">
            {statusBadges.map((b) => (
              <span
                key={b.text}
                className={`rounded-full border px-2 py-0.5 text-[10.5px] ${
                  b.ok
                    ? "border-mint/30 bg-mint/10 text-mint"
                    : "border-amber/30 bg-amber/10 text-amber"
                }`}
              >
                {b.text}
              </span>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <PillSelect
              value={mode}
              onChange={(v) => setMode(v)}
              align="end"
              ariaLabel="消融模式（用于对比实验）"
              title="消融模式（用于对比实验）"
              options={MODES.map((m) => ({ value: m.key, label: m.label, hint: m.hint }))}
            />
            <button
              onClick={() => setPanelOpen((v) => !v)}
              className="btn-ghost lg:hidden"
              aria-label="切换侧栏信息面板"
            >
              {panelOpen ? "✕" : "☰"}
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {msgs.length === 0 && (
            <ChatMessage
              msg={{
                id: "welcome",
                role: "assistant",
                text: WELCOME,
                streaming: false,
                stages: [],
                steps: [],
                result: null,
                // 欢迎语不是回答，不参与反馈上报
                question: "",
              }}
            />
          )}
          {msgs.map((m) => (
            <ChatMessage key={m.id} msg={m} />
          ))}
          {msgs.length === 0 && (
            <p className="pl-[42px] text-[11.5px] text-muted/70">建议先点右侧示例问题</p>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="flex gap-2 border-t border-line px-3 py-2.5"
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="问问经营数据，例如：美妆这个品类未来 4 周能卖多少？"
            autoComplete="off"
            className="min-w-0 flex-1 rounded-[10px] border border-line bg-surface2 px-3.5 py-2.5 text-[13px] text-fg outline-none transition-colors placeholder:text-muted/60 focus:border-accent"
          />
          <button type="submit" disabled={busy || !input.trim()} className="btn-primary">
            {busy ? "生成中" : "发送"}
          </button>
        </form>
      </section>

      {/* ===== 右侧：信息面板 ===== */}
      <aside
        className={`${
          panelOpen ? "block" : "hidden"
        } w-full shrink-0 overflow-y-auto border-l border-line bg-canvas px-3.5 py-3.5 lg:block lg:w-[322px]`}
      >
        <div className="space-y-3.5">
          <Panel title="示例问题">
            {Object.keys(examples).length === 0 ? (
              <Placeholder>示例加载中…</Placeholder>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(examples).flatMap(([, qs]) =>
                  qs.map((q) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      disabled={busy}
                      className="chip !text-[11px] disabled:opacity-50"
                    >
                      {q}
                    </button>
                  )),
                )}
              </div>
            )}
          </Panel>

          <Panel title="取数轨迹">
            <TracePanel data={lastData} steps={streamSteps} streaming={busy} />
          </Panel>

          <Panel title="数据依据">
            <CitationsPanel data={lastData} />
          </Panel>

          <Panel title="口径与依据">
            <RulesPanel data={lastData} />
          </Panel>

          <Panel title="快速评测（前 6 题）">
            <EvalPanel />
          </Panel>

          {streamStages.length > 0 && busy && (
            <Panel title="处理阶段">
              <div className="space-y-1">
                {streamStages.map((s, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px] text-muted">
                    <span className={s.done ? "text-mint" : "text-accentInk"}>
                      {s.done ? "✓" : "·"}
                    </span>
                    {s.label}
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </aside>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-line bg-surface px-3 py-2.5">
      <PanelTitle>{title}</PanelTitle>
      {children}
    </div>
  );
}

function buildBadges(h: LlmHealth | null): { text: string; ok: boolean }[] {
  if (!h) return [{ text: "健康检查失败", ok: false }];
  const rules = h.knowledge?.rules ?? 0;
  const chunks = h.knowledge?.rag?.chunks ?? 0;
  const tools = h.tools?.tools_registered ?? h.tools?.tools ?? 0;
  const provider = h.config?.provider ?? "?";
  return [
    { text: `口径 ${rules} 条`, ok: rules > 0 },
    { text: `工具 ${tools} 个`, ok: tools > 0 },
    { text: `文档 ${chunks} 段`, ok: chunks > 0 },
    { text: `底座 ${provider}`, ok: provider !== "offline" },
    { text: `数据源 ${h.tools?.datasource ?? "?"}`, ok: true },
  ];
}
