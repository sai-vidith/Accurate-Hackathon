import { useEffect, useState } from "react";
import Admin from "./Admin";
import { api } from "./api";
import { getSession, saveSession, type User } from "./auth";
import Home from "./Home";
import Login from "./Login";
import TripView from "./TripView";
import type { Status } from "./types";
import { Icon, Logo, Notice, Toaster } from "./ui";

export default function App() {
  const params = new URLSearchParams(location.search);
  const [tripId, setTripId] = useState<string | null>(() => params.get("trip"));
  const [page, setPage] = useState<"app" | "admin">(() => (params.get("page") === "admin" ? "admin" : "app"));
  const [user, setUser] = useState<User | null>(() => getSession()?.user ?? null);
  const [status, setStatus] = useState<Status | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => { api.status().then(setStatus).catch(() => setDown(true)); }, []);
  // log in / out (also when a token expires mid-session)
  useEffect(() => {
    const sync = () => setUser(getSession()?.user ?? null);
    window.addEventListener("copilot:session", sync);
    return () => window.removeEventListener("copilot:session", sync);
  }, []);
  // confirm a remembered login is still valid (the account may have been removed or the token expired)
  useEffect(() => { if (user) api.me().catch(() => undefined); }, [user?.id]);
  useEffect(() => {
    const url = page === "admin" ? "?page=admin" : tripId ? `?trip=${tripId}` : location.pathname;
    history.replaceState(null, "", url);
  }, [tripId, page]);

  const logout = () => { saveSession(null); setTripId(null); setPage("app"); };
  const isAdmin = user?.role === "admin";
  const showAdmin = page === "admin" && isAdmin;

  const nav = (label: string, active: boolean, onClick: () => void, icon: "map" | "activity") => (
    <button onClick={onClick} aria-current={active ? "page" : undefined}
      className={`relative flex h-16 items-center gap-2 px-1 text-sm font-medium transition ${active ? "text-teal-700" : "text-slate-500 hover:text-slate-900"}`}>
      <Icon name={icon} className="h-4 w-4" />{label}
      {active && <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-teal-600" />}
    </button>
  );

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900 antialiased">
      {user && <header className="sticky top-0 z-[600] border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
          <button onClick={() => { setTripId(null); setPage("app"); }} aria-label="Disruption Copilot home"><Logo /></button>
          {user && (
            <div className="flex items-center gap-5">
              <nav className="hidden items-center gap-6 sm:flex" aria-label="Main">
                {nav("My trips", !showAdmin, () => { setPage("app"); setTripId(null); }, "map")}
                {isAdmin && nav("Activity monitor", showAdmin, () => setPage("admin"), "activity")}
              </nav>
              <div className="flex items-center gap-2 border-l border-slate-200 pl-5">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-teal-500 to-sky-600 text-xs font-bold uppercase text-white" aria-hidden="true">
                  {user.username.slice(0, 2)}
                </span>
                <span className="hidden flex-col leading-tight md:flex">
                  <span className="max-w-[140px] truncate text-sm font-medium text-slate-900">{user.username}</span>
                  <span className="text-[11px] text-slate-500">{isAdmin ? "Administrator" : "Traveler"}</span>
                </span>
                <button onClick={logout} title="Log out" aria-label="Log out"
                  className="ml-1 rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900">
                  <Icon name="logout" />
                </button>
              </div>
            </div>
          )}
        </div>
        {user && isAdmin && (
          <nav className="flex gap-6 border-t border-slate-100 px-4 sm:hidden" aria-label="Main">
            {nav("My trips", !showAdmin, () => { setPage("app"); setTripId(null); }, "map")}
            {nav("Activity monitor", showAdmin, () => setPage("admin"), "activity")}
          </nav>
        )}
      </header>}
      {!user ? (
        <Login backendDown={down} />
      ) : down ? (
        <div className="mx-auto max-w-xl p-10">
          <Notice tone="red" icon="alert">Can't reach the backend. Start it with <code>./start.sh</code> in the project folder.</Notice>
        </div>
      ) : showAdmin ? (
        <Admin />
      ) : tripId ? (
        <TripView key={user.id} id={tripId} back={() => setTripId(null)} />
      ) : (
        <Home key={user.id} user={user} open={setTripId} status={status} />
      )}
      <Toaster />
    </div>
  );
}
