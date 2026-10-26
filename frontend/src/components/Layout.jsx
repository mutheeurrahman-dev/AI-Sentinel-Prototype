import { NavLink, Outlet } from "react-router-dom";
import { ShieldCheck, LayoutGrid, ListChecks, FlagTriangleRight } from "lucide-react";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/projects", label: "All projects", icon: ListChecks },
  { to: "/flagged", label: "Flagged for review", icon: FlagTriangleRight },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-64 shrink-0 bg-ink-950 text-paper-100 flex flex-col">
        <div className="px-6 py-7 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="h-6 w-6 text-marigold-500" strokeWidth={1.75} />
            <span className="font-serif text-lg tracking-tight">AI Sentinel</span>
          </div>
          <p className="mt-1.5 text-[11px] text-paper-100/50 leading-snug">
            MPLADS Fraud &amp; Verification Platform
          </p>
        </div>
        <nav className="flex-1 px-3 py-5 space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-white/10 text-white"
                    : "text-paper-100/60 hover:bg-white/5 hover:text-paper-100"
                }`
              }
            >
              <Icon className="h-4 w-4" strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-6 py-4 border-t border-white/10 text-[11px] text-paper-100/40 leading-relaxed">
          Smart India Hackathon 2026 — PS SIH26102
          <br />
          Prototype build. Simulated data.
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
