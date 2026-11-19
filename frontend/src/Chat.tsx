import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Trip } from "./types";
import { Icon } from "./ui";

type Msg = { role: "user" | "assistant"; content: string; meta?: string };

const STARTERS = [
  "My train is running 2 hours late",
  "It's going to rain this afternoon, what can I do indoors?",
  "What's near my hotel that's worth seeing?",
  "Add lunch at a good local restaurant at 13:30",
];

export default function Chat({ trip, onTrip }: { trip: Trip; onTrip: (t: Trip) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  // Braces matter: newer browsers return a Promise from scrollIntoView, which React would treat as a cleanup function.
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [msgs, busy]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    const history = msgs.map(({ role, content }) => ({ role, content }));
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api.chat(trip.id, text, history);
      onTrip(r.trip);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, meta: [r.provider, r.tools.length ? `used ${[...new Set(r.tools)].join(", ")}` : ""].filter(Boolean).join(" · ") }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", content: `Sorry, that failed: ${e.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-[340px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-sky-600 text-white"><Icon name="sparkle" /></span>
        <div className="min-w-0">
          <div className="font-semibold text-slate-900">Copilot assistant</div>
          <div className="truncate text-[11px] text-slate-500">Reads your trip, reports changes, finds places, adds items. Approvals stay with you.</div>
        </div>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50/50 p-4 text-sm" aria-live="polite">
        {msgs.length === 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">Try asking</p>
            <div className="space-y-2">
              {STARTERS.map((s) => (
                <button key={s} onClick={() => send(s)}
                  className="flex w-full items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-slate-700 transition hover:border-teal-300 hover:bg-teal-50/50">
                  <span>{s}</span><Icon name="send" className="h-3.5 w-3.5 text-slate-300" />
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "ml-10 rounded-2xl rounded-br-md bg-teal-600 px-3.5 py-2.5 text-white" : "mr-8 rounded-2xl rounded-bl-md border border-slate-200 bg-white px-3.5 py-2.5 text-slate-800"}>
            <p className="whitespace-pre-line leading-relaxed">{m.content.replace(/\*\*/g, "")}</p>
            {m.meta && <p className={`mt-1.5 text-[10px] uppercase tracking-wide ${m.role === "user" ? "text-teal-100" : "text-slate-400"}`}>{m.meta}</p>}
          </div>
        ))}
        {busy && <div className="mr-8 inline-flex items-center gap-1 rounded-2xl border border-slate-200 bg-white px-3.5 py-3" role="status" aria-label="Copilot is thinking"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-500" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-500 [animation-delay:150ms]" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-500 [animation-delay:300ms]" /></div>}
        <div ref={end} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(q); }} className="flex items-center gap-2 border-t border-slate-100 p-3">
        <label htmlFor="chat-input" className="sr-only">Message Copilot</label>
        <input id="chat-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about changes, places or delays…"
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm placeholder:text-slate-400 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100" />
        <button disabled={busy || !q.trim()} aria-label="Send"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal-600 text-white transition hover:bg-teal-700 disabled:opacity-40">
          <Icon name="send" />
        </button>
      </form>
    </div>
  );
}
