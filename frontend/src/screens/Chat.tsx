import { useEffect, useRef, useState } from "react";
import { api, fmtCost, fmtTokens, telHref, type Action, type ChatMessage } from "../api";
import EscortSheet from "../components/EscortSheet";
import { IconPhone, IconSend, IconShield, IconWalk } from "../icons";
import { useApp } from "../state";

/** Render the model's light markdown (**bold**, *italic*) without injecting HTML. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") && p.length > 4 ? <b key={i}>{p.slice(2, -2)}</b>
          : p.startsWith("*") && p.endsWith("*") && p.length > 2 ? <i key={i}>{p.slice(1, -1)}</i>
            : p,
      )}
    </>
  );
}

const SUGGESTIONS = [
  "Is it OK to walk from YCCI to the Temple Street Garage right now?",
  "What's been reported near the Air Rights Garage tonight?",
  "How do I get a walking escort, and is Safe Ride running?",
  "All the crime news has me anxious. Anything nice happening at Yale today?",
];

export default function Chat() {
  const { here, go, placeById, log, chatPrompt, clearChatPrompt } = useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [escort, setEscort] = useState<Action | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<ChatMessage[]>("/api/chat/history").then(setMessages).catch(() => {});
  }, []);

  useEffect(() => {
    if (chatPrompt) {
      setInput(chatPrompt);
      clearChatPrompt();
    }
  }, [chatPrompt, clearChatPrompt]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "", pending: true }]);
    try {
      const r = await api<ChatMessage & { reply: string }>("/api/chat", { body: { message: msg, place_id: here?.id } });
      setMessages((m) => [...m.slice(0, -1), { role: "assistant", content: r.reply, actions: r.actions, incidents: r.incidents, guards: r.guards, run: r.run }]);
    } catch (e) {
      setMessages((m) => [...m.slice(0, -1), {
        role: "assistant",
        content: `${e instanceof Error ? e.message : "Something went wrong."}\n\nIf this is an emergency, call 911 or Yale Police at (203) 432-4400.`,
      }]);
    } finally {
      setBusy(false);
    }
  }

  function act(a: Action) {
    if (a.kind === "start_walk") go("walk", { walkDraft: { origin_place_id: a.origin_place_id, dest_place_id: a.dest_place_id, minutes: a.minutes } });
    else if (a.kind === "open_map") go("alerts", { incidentId: a.incident_id ?? undefined });
    else if (a.kind === "open_resources") go("resources");
    else if (a.kind === "request_escort") setEscort(a);
    else if (a.kind === "call" && a.phone) {
      log({ agent: "rule", title: `Call button: ${a.label}`, detail: `Opens the phone dialer (${a.phone}); nothing is dialed automatically.` });
      window.location.href = telHref(a.phone);
    }
  }

  return (
    <>
      <div className="app-scroll" ref={scroller}>
        <div className="chat">
          {messages.length === 0 && (
            <div>
              <div className="h1">Ask Beacon</div>
              <p className="small muted" style={{ margin: "4px 0 14px" }}>
                Beacon checks the community board, verified Yale resources, and what's open right now, then helps you make a plan.
                It can suggest calls and walks, but you decide. In an emergency, call 911.
              </p>
              <div className="suggests">
                {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
              </div>
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="bubble user">{m.content}</div>
            ) : (
              <div key={i} className="bubble bot">
                <div className="bot-head"><img src="/beacon.svg" alt="" />Beacon</div>
                {m.pending ? (
                  <div className="row small muted"><span className="typing"><i /><i /><i /></span> Checking the board and Yale resources…</div>
                ) : (
                  <>
                    <div><Rich text={m.content} /></div>
                    {(m.incidents?.length ?? 0) > 0 && (
                      <div className="cites">
                        {m.incidents!.map((inc) => (
                          <button key={inc.id} className="cite" onClick={() => go("alerts", { incidentId: inc.id })}>
                            <i className={`sev ${inc.severity}`} />
                            <span className="grow">{inc.title}</span>
                            {inc.demo && <span className="chip demo" style={{ padding: "1px 6px" }}>demo</span>}
                            <span className="faint">›</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {(m.actions?.length ?? 0) > 0 && (
                      <div className="acts">
                        {m.actions!.map((a, j) => (
                          <button key={j} className={`btn sm ${a.kind === "call" && a.phone === "911" ? "danger" : j === 0 ? "primary" : ""}`} onClick={() => act(a)}>
                            {a.kind === "start_walk" && <IconWalk size={15} />}{a.kind === "call" && <IconPhone size={15} />}{a.kind === "request_escort" && <IconShield size={15} />}{a.label}
                          </button>
                        ))}
                      </div>
                    )}
                    {(m.guards ?? []).map((g, j) => (
                      <div key={j} className="guard-note"><IconShield size={14} /> <span>Safety check: {g}</span></div>
                    ))}
                    {m.run && (
                      <div className="runline">
                        <span>{m.run.tool_calls} tool call{m.run.tool_calls === 1 ? "" : "s"}</span>
                        <span>{fmtTokens(m.run.input_tokens)} in · {fmtTokens(m.run.cached_tokens)} cached · {fmtTokens(m.run.output_tokens)} out</span>
                        <span>{fmtCost(m.run.cost_usd)}</span>
                        <span>{(m.run.latency_ms / 1000).toFixed(1)} s</span>
                      </div>
                    )}
                  </>
                )}
              </div>
            ),
          )}
        </div>
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <textarea value={input} rows={1} placeholder="Ask Beacon…"
                  onChange={(e) => setInput(e.target.value)} maxLength={800}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} />
        <button className="send" disabled={busy || !input.trim()} aria-label="Send"><IconSend /></button>
      </form>
      {escort && (
        <EscortSheet onClose={() => setEscort(null)} fromId={escort.origin_place_id ?? here?.id}
                     toId={placeById(escort.dest_place_id) ? escort.dest_place_id : null} />
      )}
    </>
  );
}
