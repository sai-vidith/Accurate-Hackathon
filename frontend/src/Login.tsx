import { useState, type FormEvent } from "react";
import { api } from "./api";
import { saveSession } from "./auth";
import { Btn, Icon, Logo, Notice, Segmented, Spinner, inputCls, type IconName } from "./ui";

const FEATURES: [IconName, string][] = [
  ["file", "Upload or create your itinerary"],
  ["clock", "Report a delay and see the impact"],
  ["check", "Compare plans and approve changes"],
  ["map", "View your trip on a map"],
];

/** Brand panel: a travel scene with a small illustration of how a disruption becomes a choice of plans. */
function Scene() {
  return (
    <div className="relative hidden overflow-hidden bg-gradient-to-br from-teal-700 via-teal-600 to-sky-700 lg:block">
      <svg viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden="true">
        <circle cx="470" cy="140" r="60" fill="white" opacity=".10" />
        <circle cx="470" cy="140" r="34" fill="white" opacity=".12" />
        <path d="M0 610 C 120 540, 230 590, 330 545 S 520 470, 600 520 L600 800 L0 800Z" fill="white" opacity=".07" />
        <path d="M0 680 C 140 630, 260 690, 380 640 S 540 600, 600 630 L600 800 L0 800Z" fill="white" opacity=".09" />
        <path d="M0 740 C 160 710, 300 760, 440 720 S 560 705, 600 715 L600 800 L0 800Z" fill="white" opacity=".12" />
        <path d="M70 560 Q 200 380, 300 470 T 520 300" fill="none" stroke="white" strokeWidth="3" strokeDasharray="2 12" strokeLinecap="round" opacity=".7" className="animate-dash" />
        {[[70, 560], [300, 470], [520, 300]].map(([x, y]) => (
          <g key={x} transform={`translate(${x} ${y})`}><circle r="12" fill="white" opacity=".2" /><circle r="5.5" fill="white" /></g>
        ))}
      </svg>
      <div className="relative flex h-full flex-col justify-between p-12 text-white">
        <span className="flex items-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 ring-1 ring-white/25 backdrop-blur"><Icon name="plane" className="h-5 w-5" /></span>
          <span className="text-lg font-bold tracking-tight">Disruption Copilot</span>
        </span>

        <div>
          <h1 className="text-5xl font-bold leading-[1.05] tracking-tight">When plans break,<br /><span className="text-teal-100">recover in minutes.</span></h1>
          <p className="mt-5 max-w-md text-lg text-teal-50/90">Smart trip planning, disruption handling, and rescheduling you approve.</p>
          <ul className="mt-8 grid max-w-md grid-cols-2 gap-3">
            {FEATURES.map(([icon, t]) => (
              <li key={t} className="flex items-center gap-2.5 rounded-xl bg-white/10 px-3 py-2.5 text-sm ring-1 ring-white/15 backdrop-blur">
                <Icon name={icon} className="h-4 w-4 text-teal-100" />{t}
              </li>
            ))}
          </ul>
        </div>

        {/* illustration of the flow (not live data) */}
        <div className="relative max-w-sm animate-float" aria-hidden="true">
          <div className="rounded-2xl bg-white p-4 text-slate-900 shadow-2xl shadow-teal-900/30">
            <div className="flex items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-red-50 text-red-600"><Icon name="train" /></span>
              <div className="min-w-0 flex-1"><div className="text-sm font-semibold">Train delayed</div><div className="text-xs text-slate-500">Arrives 2 hours late</div></div>
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700 ring-1 ring-red-200">+2h</span>
            </div>
            <div className="my-3 h-px bg-slate-100" />
            <div className="space-y-2">
              {[["Shift later stops", true], ["Swap for an indoor visit", false], ["Skip one stop", false]].map(([t, rec]) => (
                <div key={t as string} className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs ${rec ? "bg-teal-50 text-teal-900 ring-1 ring-teal-200" : "bg-slate-50 text-slate-600"}`}>
                  <span className={`h-3 w-3 rounded-full ${rec ? "border-[3px] border-teal-600 bg-white" : "border border-slate-300"}`} />{t as string}
                  {rec && <span className="ml-auto font-semibold text-teal-700">Recommended</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Login({ backendDown }: { backendDown: boolean }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === "register" && password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    try {
      const s = mode === "login" ? await api.login(username, password) : await api.register(username, password);
      saveSession(s);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const label = "mb-1.5 block text-sm font-medium text-slate-700";

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <Scene />
      <div className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-8 lg:hidden">
            <div className="mb-6"><Logo /></div>
            <h1 className="text-3xl font-bold leading-tight tracking-tight">When plans break, <span className="text-teal-600">recover in minutes.</span></h1>
            <p className="mt-2 text-slate-600">Smart trip planning, disruption handling, and rescheduling you approve.</p>
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p className="mb-6 mt-1 text-sm text-slate-500">{mode === "login" ? "Sign in to open your trips." : "Your trips stay private to this account."}</p>

          <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/70 sm:p-7">
            <Segmented value={mode} onChange={(k) => { setMode(k); setError(null); }}
              options={[["login", "Sign in"], ["register", "Create account"]] as const} className="mb-6" />

            <label className={label} htmlFor="username">Username</label>
            <div className="relative">
              <Icon name="users" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input id="username" autoComplete="username" autoFocus className={`${inputCls} pl-10`} value={username}
                onChange={(e) => setUsername(e.target.value)} placeholder="e.g. asha or asha@example.com" required />
            </div>

            <label className={`${label} mt-4`} htmlFor="password">Password</label>
            <div className="relative">
              <Icon name="lock" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input id="password" type={show ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"}
                className={`${inputCls} pl-10 pr-16`} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === "register" ? 6 : undefined} />
              <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100">
                {show ? "Hide" : "Show"}
              </button>
            </div>
            {mode === "register" && (
              <div className="animate-fade-up">
                <label className={`${label} mt-4`} htmlFor="confirm">Confirm password</label>
                <div className="relative">
                  <Icon name="lock" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input id="confirm" type={show ? "text" : "password"} autoComplete="new-password" className={`${inputCls} pl-10`}
                    value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
                </div>
                <p className="mt-2 text-xs text-slate-500">At least 6 characters. Usernames: 3–40 letters, numbers, . _ @ -</p>
              </div>
            )}

            {error && <Notice tone="red" icon="alert" className="mt-4">{error}</Notice>}
            {backendDown && <Notice tone="amber" icon="alert" className="mt-4">Can't reach the backend. Start it with <code>./start.sh</code>.</Notice>}

            <Btn type="submit" disabled={busy} className="mt-6 w-full py-3">
              {busy ? <Spinner light label={mode === "login" ? "Signing in…" : "Creating account…"} /> : <>{mode === "login" ? "Sign in" : "Create account"} <Icon name="back" className="h-4 w-4 rotate-180" /></>}
            </Btn>
          </form>
        </div>
      </div>
    </div>
  );
}
