const CONFIG = {
  high: { label: "High risk", dot: "bg-risk-high", text: "text-risk-high", ring: "ring-risk-high/25" },
  medium: { label: "Medium risk", dot: "bg-risk-medium", text: "text-risk-medium", ring: "ring-risk-medium/25" },
  low: { label: "Low risk", dot: "bg-risk-low", text: "text-risk-low", ring: "ring-risk-low/25" },
};

export default function RiskBadge({ level, score, compact = false }) {
  const cfg = CONFIG[level] || CONFIG.low;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full ring-1 ${cfg.ring} bg-white px-2.5 py-1 text-xs font-medium ${cfg.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      {compact ? cfg.label.replace(" risk", "") : cfg.label}
      {typeof score === "number" && <span className="text-ink-950/40 font-mono">{score.toFixed(0)}</span>}
    </span>
  );
}
