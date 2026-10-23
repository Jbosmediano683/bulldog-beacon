import { useState, type FormEvent } from "react";
import { api, ApiError, type User } from "../api";

const DEMOS = [
  { netid: "hd2026", password: "Bulldog#2026", label: "Student", who: "Handsome Dan · Yale SOM" },
  { netid: "ycci01", password: "NightShift#2026", label: "Night-shift staff", who: "Jordan Lee · YCCI research coordinator" },
  { netid: "ypd001", password: "Dispatch#2026", label: "Dispatcher console", who: "Simulated Yale PD dispatch view" },
];

export default function Login({ onSignedIn }: { onSignedIn: (u: User) => void }) {
  const [netid, setNetid] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [affiliation, setAffiliation] = useState<"student" | "staff" | "faculty">("student");
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(body: Record<string, string>) {
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await api<User>("/api/auth/login", { body }));
    } catch (e) {
      if (e instanceof ApiError && e.message === "new_netid") {
        setIsNew(true);
        setError(null);
      } else {
        setError(e instanceof Error ? e.message : "Sign-in failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const body: Record<string, string> = { netid, password };
    if (isNew) Object.assign(body, { name, affiliation });
    signIn(body);
  }

  return (
    <div className="login-wrap">
      <div className="login">
        <div className="pitch">
          <div className="row" style={{ justifyContent: "center", gap: 12 }}>
            <img src="/beacon.svg" width={48} height={48} alt="" style={{ borderRadius: 14 }} />
            <div className="brand-name">Bulldog Beacon</div>
          </div>
          <div className="pitch-motto">Lux et Securitas</div>
          <p className="muted" style={{ margin: "10px auto 0", maxWidth: 370 }}>
            Light and safety for the Yale community: one-tap SOS, walk-home check-ins, a calm and fair community board,
            and a safety assistant that knows Yale.
          </p>
        </div>

        <div className="cas-head">
          <div className="y">Y</div>
          <div>
            <div style={{ fontWeight: 700 }}>Yale University</div>
            <div className="tiny" style={{ opacity: 0.85 }}>Central Authentication Service · demo sign-in</div>
          </div>
        </div>
        <form className="cas-body stack" onSubmit={submit}>
          <div className="field">
            <label htmlFor="netid">NetID</label>
            <input id="netid" className="input" autoComplete="username" value={netid}
                   onChange={(e) => { setNetid(e.target.value); setIsNew(false); }} placeholder="e.g. abc123" />
          </div>
          <div className="field">
            <label htmlFor="pw">Password</label>
            <input id="pw" className="input" type="password" autoComplete="current-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          {isNew && (
            <>
              <div className="small" style={{ color: "var(--muted)" }}>
                First time on Beacon with this NetID. In this demo, signing in creates your account (password: 8+ characters).
              </div>
              <div className="field">
                <label htmlFor="name">Your name</label>
                <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="aff">I am</label>
                <select id="aff" className="input" value={affiliation}
                        onChange={(e) => setAffiliation(e.target.value as typeof affiliation)}>
                  <option value="student">a student</option>
                  <option value="staff">staff</option>
                  <option value="faculty">faculty</option>
                </select>
              </div>
            </>
          )}
          {error && <div className="err">{error}</div>}
          <button className="btn primary block" disabled={busy || !netid || !password}>
            {busy ? "Signing in…" : isNew ? "Create account and sign in" : "Sign in"}
          </button>

          <div className="divider" style={{ background: "var(--line)" }} />
          <div className="small" style={{ color: "var(--muted)", fontWeight: 600 }}>Or try a demo account</div>
          {DEMOS.map((d) => (
            <button type="button" key={d.netid} className="demo-btn" disabled={busy}
                    onClick={() => signIn({ netid: d.netid, password: d.password })}>
              <b>{d.label}</b> <span style={{ color: "var(--muted)" }}>({d.netid})</span>
              <small>{d.who}</small>
            </button>
          ))}
          <div className="tiny" style={{ color: "var(--faint)" }}>
            Real deployment would use Yale CAS single sign-on, so only people with a Yale NetID can join.
          </div>
        </form>
        <p className="disclaimer" style={{ textAlign: "center", marginTop: 16 }}>Bulldog Beacon is an independent student project (MGT 409, Yale School of Management). It is not an official Yale University service and is not affiliated with or endorsed by Yale University. In an emergency, call 911.</p>
      </div>
    </div>
  );
}
