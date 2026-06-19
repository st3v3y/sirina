import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon } from "./Icon";

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <section className={`bg-surface border border-line-2 rounded-card shadow-card ${className}`}>
      {children}
    </section>
  );
}

type BtnVariant = "primary" | "secondary" | "dark" | "ghost";
export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant }) {
  const base =
    "inline-flex items-center justify-center gap-2 text-sm font-medium rounded-field h-9 px-3.5 disabled:opacity-50 transition-colors";
  const v: Record<BtnVariant, string> = {
    primary: "bg-signal-grad text-white shadow-[var(--shadow-rec)]",
    secondary: "bg-surface border border-line text-ink-2 hover:bg-surface-2",
    dark: "bg-ink text-paper hover:opacity-90",
    ghost: "text-ink-2 hover:bg-surface-2",
  };
  return <button className={`${base} ${v[variant]} ${className}`} {...props} />;
}

type Tone = "ok" | "warn" | "neutral";
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const tones: Record<Tone, string> = {
    ok: "bg-ok/15 text-ok-deep",
    warn: "bg-warn/15 text-warn-deep",
    neutral: "bg-line-2 text-muted",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-bold tracking-wide uppercase ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Avatar({ name, color, size = 28 }: { name: string; color?: string | null; size?: number }) {
  const initials =
    name
      .split(/\s+/)
      .map((w) => w[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("")
      .toUpperCase() || "?";
  return (
    <span
      className="rounded-full text-white inline-flex items-center justify-center font-semibold shrink-0"
      style={{ width: size, height: size, background: color || "var(--color-cat-neutral)", fontSize: size * 0.38 }}
    >
      {initials}
    </span>
  );
}

export function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`w-11 h-6 rounded-full relative transition-colors ${checked ? "bg-signal" : "bg-line-3"}`}
    >
      <span
        className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all"
        style={{ left: checked ? 22 : 2 }}
      />
    </button>
  );
}

export function Stepper({
  value,
  onChange,
  step = 1,
}: {
  value: number | "";
  onChange: (v: number | "") => void;
  step?: number;
}) {
  const num = typeof value === "number" ? value : 0;
  return (
    <div className="flex items-center w-[120px] h-[38px] border border-line rounded-field bg-surface overflow-hidden">
      <input
        type="number"
        step={step}
        value={value === "" ? "" : value}
        onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        className="flex-1 min-w-0 text-center text-[13.5px] font-mono bg-transparent focus:outline-none"
      />
      <div className="flex flex-col border-l border-line-2">
        <button onClick={() => onChange(num + step)} className="w-7 h-[18px] flex items-center justify-center border-b border-line-2 text-muted hover:text-ink">
          <Icon name="chevron-up" size={9} />
        </button>
        <button onClick={() => onChange(num - step)} className="w-7 h-[18px] flex items-center justify-center text-muted hover:text-ink">
          <Icon name="chevron-down" size={9} />
        </button>
      </div>
    </div>
  );
}

export function Slider({
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.001,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-[200px] accent-ink"
    />
  );
}

export function Select({
  value,
  onChange,
  className = "",
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`h-[38px] min-w-[180px] px-3 border border-line rounded-field bg-surface text-[13.5px] text-ink focus:outline-none focus:border-line-3 ${className}`}
    >
      {children}
    </select>
  );
}

export function SegmentedSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="inline-flex rounded-field border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`px-3 h-8 rounded-[7px] text-[13px] ${
            value === o.value ? "bg-ink text-paper" : "text-ink-2 hover:text-ink"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A label/help + control row used by Settings cards. */
export function FieldRow({
  label,
  help,
  children,
}: {
  label: ReactNode;
  help?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-6 py-3.5 border-t border-line-2 first:border-t-0">
      <div className="w-[230px] shrink-0">
        <div className="text-[13.5px] font-semibold">{label}</div>
        {help && <div className="text-xs text-muted mt-0.5">{help}</div>}
      </div>
      <div className="flex-1 flex justify-end">{children}</div>
    </div>
  );
}
