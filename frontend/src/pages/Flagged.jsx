import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { fetchFlagged } from "../api";
import RiskBadge from "../components/RiskBadge";

export default function Flagged() {
  const [projects, setProjects] = useState([]);
  const [minLevel, setMinLevel] = useState("medium");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchFlagged(minLevel)
      .then((d) => setProjects(d.projects))
      .finally(() => setLoading(false));
  }, [minLevel]);

  const highCount = projects.filter((p) => p.risk_level === "high").length;

  return (
    <div className="px-10 py-8 max-w-6xl">
      <header className="mb-6">
        <h1 className="font-serif text-3xl text-ink-950">Flagged for Review</h1>
        <p className="mt-1.5 text-sm text-ink-950/55">
          Projects whose financial and/or visual evidence deviates enough to warrant an official's attention.
        </p>
      </header>

      {highCount > 0 && (
        <div className="flex items-start gap-3 bg-risk-high/8 border border-risk-high/25 px-5 py-3.5 mb-6">
          <AlertTriangle className="h-4.5 w-4.5 text-risk-high shrink-0 mt-0.5" />
          <p className="text-sm text-ink-950/80">
            <span className="font-medium text-risk-high">{highCount} project{highCount !== 1 ? "s" : ""}</span> currently
            cross the high-risk threshold and should be prioritized for audit.
          </p>
        </div>
      )}

      <div className="flex gap-2 mb-5">
        {["high", "medium"].map((lvl) => (
          <button
            key={lvl}
            onClick={() => setMinLevel(lvl)}
            className={`px-3 py-1.5 text-xs font-medium capitalize border ${
              minLevel === lvl
                ? "bg-ink-950 text-white border-ink-950"
                : "bg-white text-ink-950/60 border-ink-950/15 hover:border-ink-950/30"
            }`}
          >
            {lvl === "high" ? "High only" : "Medium & above"}
          </button>
        ))}
      </div>

      <div className="bg-white border border-ink-950/10 divide-y divide-ink-950/8">
        {projects.map((p) => (
          <Link
            key={p.project_id}
            to={`/projects/${p.project_id}`}
            className="flex items-center justify-between px-5 py-4 hover:bg-paper-100 transition-colors"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink-950/45">{p.project_id}</span>
                <span className="text-sm text-ink-950 capitalize">{p.category.replace("_", " ")}</span>
                <span className="text-xs text-ink-950/40">· {p.implementing_agency}</span>
              </div>
              <div className="text-xs text-ink-950/50 mt-1">
                {p.district}, {p.state} · Sanctioned ₹{Number(p.sanctioned_cost).toLocaleString("en-IN")} · Actual ₹{Number(p.actual_cost).toLocaleString("en-IN")}
              </div>
            </div>
            <div className="flex items-center gap-4 shrink-0">
              <div className="text-right text-xs text-ink-950/45">
                <div>Financial: {p.financial_risk_score.toFixed(0)}</div>
                <div>Visual: {p.visual_risk_score.toFixed(0)}</div>
              </div>
              <RiskBadge level={p.risk_level} score={p.overall_risk_score} />
            </div>
          </Link>
        ))}
        {!loading && projects.length === 0 && (
          <div className="px-5 py-8 text-center text-ink-950/45">No projects at this risk level.</div>
        )}
      </div>
    </div>
  );
}
