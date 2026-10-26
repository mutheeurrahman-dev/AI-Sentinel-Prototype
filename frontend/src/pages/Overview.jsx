import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { fetchStats, fetchFlagged } from "../api";
import RiskBadge from "../components/RiskBadge";

const RISK_COLORS = { high: "#B4231E", medium: "#B0651C", low: "#2F6B4F" };

export default function Overview() {
  const [stats, setStats] = useState(null);
  const [flagged, setFlagged] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchStats(), fetchFlagged("high")])
      .then(([s, f]) => {
        setStats(s);
        setFlagged(f.projects.slice(0, 6));
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading || !stats) {
    return <div className="p-10 text-ink-950/50 text-sm">Loading overview…</div>;
  }

  const pieData = [
    { name: "High", key: "high", value: stats.risk_counts.high },
    { name: "Medium", key: "medium", value: stats.risk_counts.medium },
    { name: "Low", key: "low", value: stats.risk_counts.low },
  ];

  const stateBarData = stats.flagged_by_state
    .map((s) => ({ state: s.state, flagged: s.high + s.medium }))
    .sort((a, b) => b.flagged - a.flagged)
    .slice(0, 8);

  return (
    <div className="px-10 py-8 max-w-6xl">
      <header className="mb-8">
        <h1 className="font-serif text-3xl text-ink-950">National Overview</h1>
        <p className="mt-1.5 text-sm text-ink-950/55">
          Financial and visual verification signals across all monitored MPLADS projects.
        </p>
      </header>

      <section className="grid grid-cols-4 gap-4 mb-10">
        <SummaryCard label="Total projects" value={stats.total_projects} />
        <SummaryCard label="High risk" value={stats.risk_counts.high} accent="text-risk-high" />
        <SummaryCard label="Medium risk" value={stats.risk_counts.medium} accent="text-risk-medium" />
        <SummaryCard label="Low risk" value={stats.risk_counts.low} accent="text-risk-low" />
      </section>

      <section className="grid grid-cols-5 gap-6 mb-10">
        <div className="col-span-3 bg-white border border-ink-950/10 p-6">
          <h2 className="font-serif text-base text-ink-950 mb-4">
            Flagged projects by state
          </h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={stateBarData} margin={{ left: -10 }}>
              <CartesianGrid stroke="#0B122010" vertical={false} />
              <XAxis dataKey="state" tick={{ fontSize: 11 }} interval={0} angle={-30} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="flagged" fill="#B0651C" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="col-span-2 bg-white border border-ink-950/10 p-6">
          <h2 className="font-serif text-base text-ink-950 mb-4">Risk distribution</h2>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                {pieData.map((d) => (
                  <Cell key={d.key} fill={RISK_COLORS[d.key]} />
                ))}
              </Pie>
              <Legend verticalAlign="bottom" height={30} iconType="circle" />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-base text-ink-950">Highest-risk projects</h2>
          <Link to="/flagged" className="text-sm text-marigold-600 hover:underline">
            View all flagged →
          </Link>
        </div>
        <div className="bg-white border border-ink-950/10 divide-y divide-ink-950/8">
          {flagged.map((p) => (
            <Link
              key={p.project_id}
              to={`/projects/${p.project_id}`}
              className="flex items-center justify-between px-5 py-3.5 hover:bg-paper-100 transition-colors"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-ink-950/45">{p.project_id}</span>
                  <span className="text-sm text-ink-950">{p.category.replace("_", " ")}</span>
                </div>
                <div className="text-xs text-ink-950/50 mt-0.5">
                  {p.district}, {p.state} · {p.implementing_agency}
                </div>
              </div>
              <RiskBadge level={p.risk_level} score={p.overall_risk_score} />
            </Link>
          ))}
          {flagged.length === 0 && (
            <div className="px-5 py-6 text-sm text-ink-950/50">No high-risk projects currently.</div>
          )}
        </div>
      </section>
    </div>
  );
}

function SummaryCard({ label, value, accent = "text-ink-950" }) {
  return (
    <div className="bg-white border border-ink-950/10 px-5 py-4">
      <div className="text-xs text-ink-950/50 mb-1">{label}</div>
      <div className={`font-serif text-3xl ${accent}`}>{value}</div>
    </div>
  );
}
