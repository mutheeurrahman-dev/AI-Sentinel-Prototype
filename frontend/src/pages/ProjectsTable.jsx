import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { fetchProjects } from "../api";
import RiskBadge from "../components/RiskBadge";

const CATEGORIES = ["road", "hand_pump", "school", "community_hall", "sanitation"];
const STATUSES = ["completed", "in_progress", "stalled"];

export default function ProjectsTable() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [riskLevel, setRiskLevel] = useState("");

  useEffect(() => {
    setLoading(true);
    fetchProjects({
      q: q || undefined,
      category: category || undefined,
      status: status || undefined,
      risk_level_filter: riskLevel || undefined,
      limit: 500,
    })
      .then((d) => setProjects(d.projects))
      .finally(() => setLoading(false));
  }, [q, category, status, riskLevel]);

  const sorted = useMemo(
    () => [...projects].sort((a, b) => b.overall_risk_score - a.overall_risk_score),
    [projects]
  );

  return (
    <div className="px-10 py-8 max-w-6xl">
      <header className="mb-6">
        <h1 className="font-serif text-3xl text-ink-950">All Projects</h1>
        <p className="mt-1.5 text-sm text-ink-950/55">
          Search and filter every monitored MPLADS project.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-ink-950/35" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search project ID, MP, agency…"
            className="pl-8 pr-3 py-2 text-sm border border-ink-950/15 bg-white w-64 focus:outline-none focus:ring-1 focus:ring-marigold-500"
          />
        </div>
        <Select value={category} onChange={setCategory} options={CATEGORIES} placeholder="All categories" />
        <Select value={status} onChange={setStatus} options={STATUSES} placeholder="All statuses" />
        <Select value={riskLevel} onChange={setRiskLevel} options={["high", "medium", "low"]} placeholder="All risk levels" />
        <span className="text-xs text-ink-950/45 ml-auto">{sorted.length} projects</span>
      </div>

      <div className="bg-white border border-ink-950/10">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-950/10 text-left text-xs text-ink-950/45">
              <th className="px-5 py-2.5 font-medium">Project</th>
              <th className="px-5 py-2.5 font-medium">Category</th>
              <th className="px-5 py-2.5 font-medium">Location</th>
              <th className="px-5 py-2.5 font-medium">MP</th>
              <th className="px-5 py-2.5 font-medium">Status</th>
              <th className="px-5 py-2.5 font-medium">Risk</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr key={p.project_id} className="border-b border-ink-950/6 last:border-0 hover:bg-paper-100">
                <td className="px-5 py-3">
                  <Link to={`/projects/${p.project_id}`} className="font-mono text-xs text-marigold-600 hover:underline">
                    {p.project_id}
                  </Link>
                </td>
                <td className="px-5 py-3 capitalize">{p.category.replace("_", " ")}</td>
                <td className="px-5 py-3 text-ink-950/70">{p.district}, {p.state}</td>
                <td className="px-5 py-3 text-ink-950/70">{p.mp_name}</td>
                <td className="px-5 py-3 capitalize text-ink-950/70">{p.status.replace("_", " ")}</td>
                <td className="px-5 py-3">
                  <RiskBadge level={p.risk_level} score={p.overall_risk_score} compact />
                </td>
              </tr>
            ))}
            {!loading && sorted.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-ink-950/45">
                  No projects match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Select({ value, onChange, options, placeholder }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2 text-sm border border-ink-950/15 bg-white focus:outline-none focus:ring-1 focus:ring-marigold-500 capitalize"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o} className="capitalize">
          {o.replace("_", " ")}
        </option>
      ))}
    </select>
  );
}
