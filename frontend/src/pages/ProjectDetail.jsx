import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, AlertCircle, ImageOff } from "lucide-react";
import { fetchProjectDetail, mediaUrl } from "../api";
import RiskBadge from "../components/RiskBadge";

const STAGE_LABEL = {
  empty_site: "Empty site",
  foundation_stage: "Foundation stage",
  under_construction: "Under construction",
  near_complete: "Near complete",
  finished_building: "Finished building",
};

function stageFromFilename(filename = "") {
  const tag = Object.keys(STAGE_LABEL).find((t) => filename.includes(t));
  return tag ? STAGE_LABEL[tag] : null;
}

export default function ProjectDetail() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetchProjectDetail(id)
      .then(setProject)
      .catch(() => setError("Project not found."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="p-10 text-ink-950/50 text-sm">Loading project…</div>;
  if (error || !project) return <div className="p-10 text-risk-high text-sm">{error}</div>;

  const costDelta = project.actual_cost - project.sanctioned_cost;
  const costPct = project.sanctioned_cost ? (costDelta / project.sanctioned_cost) * 100 : 0;

  return (
    <div className="px-10 py-8 max-w-5xl">
      <Link to="/projects" className="inline-flex items-center gap-1.5 text-sm text-ink-950/55 hover:text-ink-950 mb-5">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to all projects
      </Link>

      <header className="flex items-start justify-between mb-8">
        <div>
          <div className="font-mono text-xs text-ink-950/45 mb-1">{project.project_id}</div>
          <h1 className="font-serif text-3xl text-ink-950 capitalize">{project.category.replace("_", " ")} project</h1>
          <p className="mt-1 text-sm text-ink-950/60">
            {project.district}, {project.state} · MP: {project.mp_name} · {project.implementing_agency}
          </p>
        </div>
        <RiskBadge level={project.risk_level} score={project.overall_risk_score} />
      </header>

      {/* Financial summary */}
      <section className="grid grid-cols-3 gap-4 mb-8">
        <Fact label="Sanctioned cost" value={`₹${Number(project.sanctioned_cost).toLocaleString("en-IN")}`} />
        <Fact
          label="Actual cost"
          value={`₹${Number(project.actual_cost).toLocaleString("en-IN")}`}
          sub={`${costPct > 0 ? "+" : ""}${costPct.toFixed(0)}% vs sanctioned`}
          subClass={costPct > 25 ? "text-risk-high" : "text-ink-950/45"}
        />
        <Fact label="Status" value={project.status.replace("_", " ")} capitalize />
        <Fact label="Sanction date" value={project.sanction_date} />
        <Fact label="Expected completion" value={project.expected_completion_date} />
        <Fact label="Actual completion" value={project.actual_completion_date || "— not yet marked complete"} />
      </section>

      {/* Risk breakdown + reasons */}
      <section className="grid grid-cols-2 gap-6 mb-8">
        <FlagPanel
          title="Financial anomaly flags"
          score={project.financial_risk_score}
          reasons={project.financial_flags}
          emptyText="No financial anomalies detected."
        />
        <FlagPanel
          title="Visual / photo evidence flags"
          score={project.visual_risk_score}
          reasons={project.visual_flags.map((f) => f.reason)}
          emptyText="No visual anomalies detected."
        />
      </section>

      {/* Submission history with photo evidence */}
      <section>
        <h2 className="font-serif text-lg text-ink-950 mb-4">Submission history</h2>
        <div className="space-y-4">
          {project.submissions.map((s) => (
            <SubmissionCard key={s.submission_id} submission={s} />
          ))}
          {project.submissions.length === 0 && (
            <p className="text-sm text-ink-950/45">No progress submissions recorded yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function Fact({ label, value, sub, subClass = "text-ink-950/45", capitalize }) {
  return (
    <div className="bg-white border border-ink-950/10 px-4 py-3">
      <div className="text-xs text-ink-950/45 mb-1">{label}</div>
      <div className={`text-sm text-ink-950 ${capitalize ? "capitalize" : ""}`}>{value}</div>
      {sub && <div className={`text-xs mt-0.5 ${subClass}`}>{sub}</div>}
    </div>
  );
}

function FlagPanel({ title, score, reasons, emptyText }) {
  return (
    <div className="bg-white border border-ink-950/10 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-serif text-base text-ink-950">{title}</h3>
        <span className="font-mono text-xs text-ink-950/45">{score.toFixed(0)} / 100</span>
      </div>
      {reasons.length > 0 ? (
        <ul className="space-y-2">
          {reasons.map((r, i) => (
            <li key={i} className="flex gap-2 text-sm text-ink-950/75">
              <AlertCircle className="h-4 w-4 text-marigold-600 shrink-0 mt-0.5" />
              <span>{r}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-950/45">{emptyText}</p>
      )}
    </div>
  );
}

function SubmissionCard({ submission: s }) {
  const [imgError, setImgError] = useState(false);
  const stage = stageFromFilename(s.photo_filename);
  const isFlagged = s.visual_risk_score > 0;

  return (
    <div className="bg-white border border-ink-950/10 p-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <span className="text-sm text-ink-950">Submitted {s.submission_date}</span>
          <span className="text-xs text-ink-950/45 ml-2">Claimed progress: {s.progress_percent_claimed}%</span>
        </div>
        {isFlagged && <RiskBadge level={s.visual_risk_score >= 60 ? "high" : "medium"} score={s.visual_risk_score} compact />}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-ink-950/45 mb-1.5">Submitted photo {stage && `· detected stage: ${stage}`}</div>
          {imgError ? (
            <div className="h-40 flex items-center justify-center bg-paper-100 text-ink-950/30 border border-ink-950/10">
              <ImageOff className="h-6 w-6" />
            </div>
          ) : (
            <img
              src={mediaUrl("photos", s.photo_filename)}
              onError={() => setImgError(true)}
              className="h-40 w-full object-cover border border-ink-950/10"
              alt="Site submission"
            />
          )}
        </div>
        <div>
          <div className="text-xs text-ink-950/45 mb-1.5">Receipt</div>
          <ReceiptImage filename={s.receipt_filename} />
        </div>
      </div>
    </div>
  );
}

function ReceiptImage({ filename }) {
  const [imgError, setImgError] = useState(false);
  if (!filename || imgError) {
    return (
      <div className="h-40 flex items-center justify-center bg-paper-100 text-ink-950/30 border border-ink-950/10">
        <ImageOff className="h-6 w-6" />
      </div>
    );
  }
  return (
    <img
      src={mediaUrl("receipts", filename)}
      onError={() => setImgError(true)}
      className="h-40 w-full object-cover border border-ink-950/10"
      alt="Receipt"
    />
  );
}
