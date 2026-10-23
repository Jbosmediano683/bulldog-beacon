import { useState } from "react";
import { api, CATEGORY_LABELS, fmtCost, fmtTokens, type PostResult } from "../api";
import { CatIcon, IconCheck, IconShield } from "../icons";
import { useApp } from "../state";
import Sheet from "./Sheet";

const CATS = ["suspicious_activity", "vehicle_break_in", "theft", "harassment", "assault", "police_activity", "hazard", "medical", "gathering", "safety_update", "good_news", "other"];

const ISSUE_LABELS: Record<string, string> = {
  profiling: "Described someone by who they are, not what they did",
  personal_info: "Personal info (names, numbers, plates)",
  unverified_claim: "Second-hand rumor",
  prompt_injection: "Text aimed at the app, not the community",
  harassment_or_threat: "Harassment or a threat",
  graphic_detail: "Graphic detail",
  off_topic: "Not a safety report",
  ongoing_emergency: "Emergency happening now",
  spam: "Spam",
  self_harm: "Mentions self-harm",
};

export default function Composer({ onClose, onPublished, defaultCategory }: {
  onClose: () => void; onPublished: () => void; defaultCategory?: string;
}) {
  const { places, here, toast } = useApp();
  const [category, setCategory] = useState(defaultCategory ?? "suspicious_activity");
  const [placeId, setPlaceId] = useState<number>(here?.id ?? places[0]?.id);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PostResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<PostResult>("/api/posts", { body: { text, category, place_id: placeId } });
      setResult(r);
      if (r.published) {
        onPublished();
        toast("Alert published to the community");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't post.");
    } finally {
      setBusy(false);
    }
  }

  const m = result?.moderation;
  const status = result?.post.status;

  return (
    <Sheet onClose={onClose}>
      {busy ? (
        <div className="reviewing">
          <div className="scan" />
          <div className="h2">Beacon's Moderator is reviewing your alert</div>
          <div className="small muted" style={{ maxWidth: 300 }}>
            Checking that it's useful, fair, and private before the community sees it. Usually a few seconds.
          </div>
        </div>
      ) : result && m ? (
        <div className="stack">
          <div className={`verdict ${status}`}>
            <div className="h2">
              {status === "published" && <><IconCheck size={18} /> Published</>}
              {status === "revised" && <><IconCheck size={18} /> Published with edits</>}
              {status === "blocked" && "Not published"}
              {status === "held" && "Saved, not published yet"}
              {status === "redirect_911" && "This sounds like an emergency"}
            </div>
            {m.note_to_author && <div className="small" style={{ marginTop: 6 }}>{m.note_to_author}</div>}
            {status === "revised" && (
              <div className="diff">
                <div className="was">{result.post.raw_text}</div>
                <div className="now">{result.post.text}</div>
              </div>
            )}
            {m.support && (
              <div className="row" style={{ gap: 8, marginTop: 12 }}>
                <a className="btn primary grow" href="tel:988">Call or text 988</a>
                <a className="btn grow" href="tel:2034320123">On-call clinician</a>
              </div>
            )}
            {status === "redirect_911" && (
              <div className="row" style={{ gap: 8, marginTop: 12 }}>
                <a className="btn danger grow" href="tel:911">Call 911</a>
                <a className="btn grow" href="tel:2034324400">Yale PD</a>
              </div>
            )}
            {(m.issues?.length ?? 0) > 0 && (
              <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
                {m.issues!.map((i) => <span key={i} className="chip shield"><IconShield size={13} /> {ISSUE_LABELS[i] ?? i}</span>)}
              </div>
            )}
          </div>
          {result.published && m.title && (
            <div className="card tight">
              <div className="tiny faint">How it appears on the map</div>
              <div style={{ fontWeight: 650, marginTop: 3 }}>{m.title}</div>
              {m.advice && <div className="small muted" style={{ marginTop: 4 }}><b>What to do:</b> {m.advice}</div>}
              <div className="tiny faint" style={{ marginTop: 6 }}>Your name is never shown. The Corroborator is checking for matching reports nearby.</div>
            </div>
          )}
          <div className="tiny faint">
            {m.layer === "rule"
              ? "Stopped by Beacon's code rules before any AI saw it (0 tokens)."
              : result.run && `Moderator: ${fmtTokens(result.run.input_tokens)} in (${fmtTokens(result.run.cached_tokens)} cached) · ${fmtTokens(result.run.output_tokens)} out · ${fmtCost(result.run.cost_usd)} · ${(result.run.latency_ms / 1000).toFixed(1)} s`}
          </div>
          <div className="row" style={{ gap: 8 }}>
            {!result.published && <button className="btn grow" onClick={() => setResult(null)}>Edit and try again</button>}
            <button className="btn primary grow" onClick={onClose}>Done</button>
          </div>
        </div>
      ) : (
        <div className="stack">
          <div>
            <div className="h2">Post to the community</div>
            <div className="small muted">An alert your Yale neighbors should know about, or some good news to share.</div>
          </div>
          <div className="verdict redirect_911 small" style={{ padding: "9px 12px" }}>
            Happening right now and someone's in danger? <a href="tel:911" style={{ color: "var(--sos-deep)", fontWeight: 700 }}>Call 911</a> first.
          </div>
          <div className="field">
            <label>What kind of alert?</label>
            <div className="cat-grid">
              {CATS.map((c) => (
                <button key={c} type="button" className={category === c ? "on" : ""} onClick={() => setCategory(c)}>
                  <CatIcon category={c} /> {CATEGORY_LABELS[c]}
                </button>
              ))}
            </div>
          </div>
          <div className="field">
            <label>Where?</label>
            <select className="select" value={placeId} onChange={(e) => setPlaceId(Number(e.target.value))}>
              {places.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>What happened?</label>
            <textarea className="textarea" value={text} maxLength={600} onChange={(e) => setText(e.target.value)}
                      placeholder="What happened, when, and what the person did. e.g. 'Someone trying car door handles on level 2 around 9:30, gray hoodie, headed toward Crown St.'" />
            <div className="tiny faint" style={{ textAlign: "right" }}>{text.length}/600</div>
          </div>
          <div className="tips">
            <b>Helpful alerts describe actions, not people.</b> Include clothing, direction, and time. Leave out race, names,
            phone numbers, and plates (give those to Yale PD at (203) 432-4400). Beacon's Moderator checks every alert.
          </div>
          {error && <div className="verdict blocked small">{error}</div>}
          <button className="btn primary block" disabled={text.trim().length < 8} onClick={submit}>Submit for review</button>
        </div>
      )}
    </Sheet>
  );
}
