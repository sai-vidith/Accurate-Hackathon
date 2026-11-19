// The login session: a JWT from the backend, kept in this browser so a refresh doesn't log you out.
export type User = { id: string; username: string; role: "user" | "admin"; created_at?: string; last_login?: string | null };

const KEY = "copilot.session";

export function getSession(): { token: string; user: User } | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveSession(s: { token: string; user: User } | null) {
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s));
    else localStorage.removeItem(KEY);
  } catch {
    /* private window: the session just lasts until refresh */
  }
  memory = s;
  window.dispatchEvent(new Event("copilot:session"));
}

let memory: { token: string; user: User } | null = getSession();
export const token = () => memory?.token ?? null;
