import { type ReactNode } from "react";

// A small, dependency-free Markdown renderer for LLM output (summaries, Q&A answers).
// Supports the subset models actually emit: headings, bold/italic, inline code, links,
// and bullet/numbered lists. Renders real React nodes (no dangerouslySetInnerHTML), so
// there's no HTML-injection surface even though the text comes from a local model.

type Block =
  | { kind: "h"; level: number; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "p"; lines: string[] };

const H = /^(#{1,6})\s+(.*)$/;
const UL = /^[-*+]\s+(.*)$/;
const OL = /^\d+[.)]\s+(.*)$/;

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const h = H.exec(line);
    if (h) {
      blocks.push({ kind: "h", level: h[1].length, text: h[2] });
      i++;
      continue;
    }
    if (UL.test(line)) {
      const items: string[] = [];
      while (i < lines.length && UL.test(lines[i])) items.push(UL.exec(lines[i++])![1]);
      blocks.push({ kind: "ul", items });
      continue;
    }
    if (OL.test(line)) {
      const items: string[] = [];
      while (i < lines.length && OL.test(lines[i])) items.push(OL.exec(lines[i++])![1]);
      blocks.push({ kind: "ol", items });
      continue;
    }
    // Paragraph: consecutive plain lines until a blank line or a new block type.
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !H.test(lines[i]) &&
      !UL.test(lines[i]) &&
      !OL.test(lines[i])
    ) {
      para.push(lines[i++]);
    }
    blocks.push({ kind: "p", lines: para });
  }
  return blocks;
}

// Earliest-match inline scan: code, bold, italic, link. Bold/italic/link inners recurse;
// code is literal. `key` keeps React happy across the recursion.
// Emphasis is asterisk-only (`**bold**`, `*italic*`): it's the dominant style LLMs emit,
// and it sidesteps both underscore false-positives (snake_case, __dunder__) and regex
// lookbehind, which throws a SyntaxError on older WebKit (macOS 13 / Safari 16.1).
function inline(text: string, key = "i"): ReactNode[] {
  const out: ReactNode[] = [];
  let rest = text;
  let n = 0;
  const patterns: { re: RegExp; render: (m: RegExpExecArray, k: string) => ReactNode }[] = [
    { re: /`([^`]+)`/, render: (m, k) => <code key={k} className="font-mono text-[0.9em] bg-surface-2 rounded px-1 py-0.5">{m[1]}</code> },
    { re: /\*\*([^*]+)\*\*/, render: (m, k) => <strong key={k} className="font-bold">{inline(m[1], k)}</strong> },
    { re: /\*([^*\n]+)\*/, render: (m, k) => <em key={k} className="italic">{inline(m[1], k)}</em> },
    { re: /\[([^\]]+)\]\(([^)\s]+)\)/, render: (m, k) => <a key={k} href={m[2]} target="_blank" rel="noreferrer" className="text-signal underline">{inline(m[1], k)}</a> },
  ];
  while (rest) {
    let best: { idx: number; len: number; node: ReactNode } | null = null;
    for (const { re, render } of patterns) {
      const m = re.exec(rest);
      if (m && (best === null || m.index < best.idx)) {
        best = { idx: m.index, len: m[0].length, node: render(m, `${key}-${n}`) };
      }
    }
    if (!best) {
      out.push(rest);
      break;
    }
    if (best.idx > 0) out.push(rest.slice(0, best.idx));
    out.push(best.node);
    rest = rest.slice(best.idx + best.len);
    n++;
  }
  return out;
}

const HEADING_CLASS: Record<number, string> = {
  1: "text-[1.3em] font-bold mt-1 mb-1",
  2: "text-[1.15em] font-bold mt-1 mb-1",
  3: "text-[1.05em] font-bold mt-1 mb-0.5",
};

export function Markdown({ content, className = "" }: { content: string; className?: string }) {
  const blocks = parse(content ?? "");
  return (
    <div className={`space-y-3 ${className}`}>
      {blocks.map((b, i) => {
        if (b.kind === "h") {
          return (
            <div key={i} className={HEADING_CLASS[b.level] ?? HEADING_CLASS[3]}>
              {inline(b.text, `h${i}`)}
            </div>
          );
        }
        if (b.kind === "ul") {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {b.items.map((it, j) => (
                <li key={j}>{inline(it, `ul${i}-${j}`)}</li>
              ))}
            </ul>
          );
        }
        if (b.kind === "ol") {
          return (
            <ol key={i} className="list-decimal pl-5 space-y-1">
              {b.items.map((it, j) => (
                <li key={j}>{inline(it, `ol${i}-${j}`)}</li>
              ))}
            </ol>
          );
        }
        return (
          <p key={i}>
            {b.lines.map((ln, j) => (
              <span key={j}>
                {inline(ln, `p${i}-${j}`)}
                {j < b.lines.length - 1 && <br />}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

export default Markdown;
