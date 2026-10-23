import { useEffect, useState } from "react";
import { api, CATEGORY_LABELS, timeAgo, type CommunityComment, type CommunityPost } from "../api";
import Composer from "../components/Composer";
import { CatIcon, IconComment, IconEye, IconHeart, IconMap, IconPin, IconPlus } from "../icons";
import { useApp } from "../state";

type Show = "all" | "alerts" | "good";
const GOOD = ["good_news", "safety_update"];

function CommentThread({ post, onCount }: { post: CommunityPost; onCount: (n: number) => void }) {
  const [comments, setComments] = useState<CommunityComment[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CommunityComment[]>(`/api/posts/${post.id}/comments`).then(setComments).catch(() => setComments([]));
  }, [post.id]);

  async function send() {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ comment: CommunityComment; published: boolean }>(`/api/posts/${post.id}/comments`, { body: { text } });
      const next = [...(comments ?? []), r.comment];
      setComments(next);
      onCount(next.filter((c) => c.status === "published" || c.status === "revised").length);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't post that comment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="thread" onClick={(e) => e.stopPropagation()}>
      {comments === null ? (
        <div className="tiny faint">Loading comments…</div>
      ) : comments.length === 0 ? (
        <div className="tiny faint">No comments yet. Saw something too? Add what you know.</div>
      ) : (
        comments.map((c) => {
          const shown = c.status === "published" || c.status === "revised";
          return (
            <div key={c.id} className={`comment ${shown ? "" : "held"}`}>
              <div className="tiny faint"><b style={{ color: "var(--text)" }}>{c.author}</b> · {timeAgo(c.created_at)}
                {c.demo && <span className="chip demo" style={{ marginLeft: 6, padding: "1px 6px" }}>demo</span>}
                {c.status === "revised" && <span className="chip shield" style={{ marginLeft: 6, padding: "1px 6px" }}>edited by Moderator</span>}
              </div>
              {shown ? (
                <div className="small">{c.text}</div>
              ) : (
                <>
                  <div className="small faint" style={{ textDecoration: "line-through" }}>{c.raw_text}</div>
                  <div className="tiny" style={{ color: "var(--amber)", marginTop: 3 }}>Only you can see this: not posted. {c.note}</div>
                  {c.status === "redirect_911" && <a className="btn danger sm" style={{ marginTop: 6 }} href="tel:911">Call 911</a>}
                  {c.support && <a className="btn primary sm" style={{ marginTop: 6 }} href="tel:988">Call or text 988</a>}
                </>
              )}
            </div>
          );
        })
      )}
      <div className="comment-box">
        <input className="input" value={text} maxLength={400} placeholder="Add a comment…" disabled={busy}
               onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
        <button className="btn primary sm" disabled={busy || !text.trim()} onClick={send}>{busy ? "Checking…" : "Post"}</button>
      </div>
      {busy && <div className="tiny faint">Beacon's Moderator is checking your comment…</div>}
      {error && <div className="tiny" style={{ color: "var(--sos-deep)" }}>{error}</div>}
    </div>
  );
}

function PostCard({ post, onChange }: { post: CommunityPost; onChange: (p: CommunityPost) => void }) {
  const { go, toast } = useApp();
  const [open, setOpen] = useState(false);
  const good = GOOD.includes(post.category);

  async function react(kind: "like" | "confirm") {
    if (post.mine) return;
    try {
      const r = await api<Partial<CommunityPost>>(`/api/posts/${post.id}/react`, { body: { kind } });
      onChange({ ...post, ...r });
      if (kind === "confirm" && r.confirmed) toast("Thanks. Your confirmation helps others trust this alert.");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't do that.");
    }
  }

  return (
    <div className={`card post-card ${good ? "good" : ""}`}>
      <div className="row between" style={{ alignItems: "flex-start" }}>
        <div className="row" style={{ gap: 7 }}>
          {!good && <i className={`sev ${post.severity}`} />}
          <span className="small"><b>{post.author}</b> <span className="faint">· {timeAgo(post.created_at)}</span></span>
        </div>
        <span className={`chip ${good ? "ok" : ""}`}><CatIcon category={post.category} size={13} /> {CATEGORY_LABELS[post.category] ?? post.category}</span>
      </div>
      {post.title && <div className="post-title">{post.title}</div>}
      <div className="post-text">{post.text}</div>
      <div className="row wrap tiny muted" style={{ gap: 8, marginTop: 6 }}>
        {post.place_name && <span className="row" style={{ gap: 3 }}><IconPin size={13} /> {post.place_name}</span>}
        {post.demo && <span className="chip demo" style={{ padding: "1px 7px" }}>Demo post (fictional)</span>}
      </div>
      <div className="post-actions">
        {!good && (
          <button className={`act-btn ${post.confirmed ? "on" : ""}`} disabled={post.mine} onClick={() => react("confirm")}
                  title={post.mine ? "Your own post" : "Confirm you saw this too"}>
            <IconEye /> {post.confirmed ? "You saw this" : "I saw this too"}{post.confirms ? ` · ${post.confirms}` : ""}
          </button>
        )}
        <button className={`act-btn ${post.liked ? "on" : ""}`} disabled={post.mine} onClick={() => react("like")}
                title={post.mine ? "Your own post" : good ? "Like" : "Thank the poster"}>
          <IconHeart /> {good ? "Like" : "Thanks"}{post.likes ? ` · ${post.likes}` : ""}
        </button>
        <button className={`act-btn ${open ? "on" : ""}`} onClick={() => setOpen(!open)}>
          <IconComment /> {post.comments || ""} {post.comments === 1 ? "comment" : "comments"}
        </button>
        {post.incident_id && (
          <button className="act-btn" onClick={() => go("alerts", { incidentId: post.incident_id ?? undefined })}><IconMap /> Map</button>
        )}
      </div>
      {open && <CommentThread post={post} onCount={(n) => onChange({ ...post, comments: n })} />}
    </div>
  );
}

export default function Community() {
  const { user } = useApp();
  const [show, setShow] = useState<Show>("all");
  const [posts, setPosts] = useState<CommunityPost[] | null>(null);
  const [composing, setComposing] = useState(false);

  const load = () => api<CommunityPost[]>(`/api/community?show=${show}`).then(setPosts).catch(() => setPosts([]));
  useEffect(() => {
    setPosts(null);
    load();
    const t = window.setInterval(load, 20000);
    return () => window.clearInterval(t);
  }, [show]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <div className="h1">Community</div>
      <div className="small muted">
        Alerts, updates, and good news from the Yale community. Names are never shown, and Beacon's Moderator checks every
        post and comment before anyone sees it.
      </div>
      <div className="layer-toggle">
        {([["all", "Everything"], ["alerts", "Alerts"], ["good", "Good news"]] as const).map(([id, label]) => (
          <button key={id} className={show === id ? "on" : ""} onClick={() => setShow(id)}>{label}</button>
        ))}
      </div>
      <div className="stack" style={{ marginTop: 10 }}>
        {posts === null ? (
          <div className="card empty small">Loading…</div>
        ) : posts.length === 0 ? (
          <div className="card empty small">Nothing here this week.</div>
        ) : (
          posts.map((p) => (
            <PostCard key={p.id} post={p} onChange={(np) => setPosts((cur) => (cur ?? []).map((x) => (x.id === np.id ? np : x)))} />
          ))
        )}
      </div>
      <div style={{ height: 70 }} />
      {user.role !== "dispatcher" && (
        <button className="fab" onClick={() => setComposing(true)}><IconPlus size={18} /> Post</button>
      )}
      {composing && (
        <Composer defaultCategory={show === "good" ? "good_news" : undefined} onClose={() => setComposing(false)}
                  onPublished={() => { window.setTimeout(load, 1500); window.setTimeout(load, 8000); }} />
      )}
    </div>
  );
}
