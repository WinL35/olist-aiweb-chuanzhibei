import type { ReactNode } from "react";

/**
 * 极简 Markdown 渲染
 *
 * 只支持模型实际会输出的三种结构：**加粗**、## 小标题、- 无序列表。
 * 刻意不引入 markdown 库：一是体积，二是「越少解析越不容易被注入」。
 * 用 React 元素而不是 innerHTML，天然免疫 XSS。
 */
export function renderMarkdown(text: string): ReactNode {
  if (!text) return null;

  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let listBuffer: string[] = [];
  let key = 0;

  const flushList = () => {
    if (!listBuffer.length) return;
    blocks.push(
      <ul key={`ul-${key++}`}>
        {listBuffer.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>,
    );
    listBuffer = [];
  };

  for (const raw of lines) {
    const line = raw.trim();

    if (!line) {
      flushList();
      continue;
    }

    // 无序列表
    if (/^[-*•]\s+/.test(line)) {
      listBuffer.push(line.replace(/^[-*•]\s+/, ""));
      continue;
    }

    // 小标题：## xxx / ### xxx / **xxx**（独占一行）
    const headingMatch = line.match(/^#{2,4}\s+(.*)$/);
    const boldOnly = line.match(/^\*\*([^*]+)\*\*[:：]?$/);
    if (headingMatch || boldOnly) {
      flushList();
      const title = (headingMatch?.[1] ?? boldOnly?.[1] ?? "").replace(/\*\*/g, "");
      blocks.push(<h4 key={`h-${key++}`}>{title}</h4>);
      continue;
    }

    flushList();
    blocks.push(<p key={`p-${key++}`}>{renderInline(line)}</p>);
  }
  flushList();

  return <>{blocks}</>;
}

/** 行内加粗 + 行内代码 */
function renderInline(text: string): ReactNode {
  const parts: ReactNode[] = [];
  // 同时匹配 **加粗** 与 `代码`
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={i++}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(
        <code
          key={i++}
          className="rounded bg-surface2 px-1 py-0.5 font-mono text-[12px] text-mint"
        >
          {token.slice(1, -1)}
        </code>,
      );
    }
    last = m.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));

  return parts.length === 1 ? parts[0] : <>{parts}</>;
}
