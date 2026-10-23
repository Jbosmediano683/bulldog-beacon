import { useState, type ReactNode } from "react";
import { api } from "./api";
import Insights from "./components/Insights";
import Sheet from "./components/Sheet";
import SosOverlay from "./components/SosOverlay";
import { IconChart, IconChat, IconHome, IconMap, IconPhone, IconPin, IconRadio, IconUsers, IconWalk } from "./icons";
import Alerts from "./screens/Alerts";
import BluePhones from "./screens/BluePhones";
import Community from "./screens/Community";
import Chat from "./screens/Chat";
import Dispatch from "./screens/Dispatch";
import Home from "./screens/Home";
import Me from "./screens/Me";
import Resources from "./screens/Resources";
import Shuttle from "./screens/Shuttle";
import Usage from "./screens/Usage";
import WalkScreen from "./screens/Walk";
import { useApp, type Tab } from "./state";

const MEMBER_TABS: { id: Tab; label: string; icon: ReactNode }[] = [
  { id: "home", label: "Home", icon: <IconHome /> },
  { id: "community", label: "Community", icon: <IconUsers /> },
  { id: "alerts", label: "Map", icon: <IconMap /> },
  { id: "ask", label: "Ask Beacon", icon: <IconChat /> },
  { id: "walk", label: "Walk", icon: <IconWalk /> },
  { id: "resources", label: "Resources", icon: <IconPhone /> },
];
const DISPATCH_TABS: typeof MEMBER_TABS = [
  { id: "dispatch", label: "Dispatch", icon: <IconRadio /> },
  { id: "community", label: "Community", icon: <IconUsers /> },
  { id: "alerts", label: "Map", icon: <IconMap /> },
  { id: "ask", label: "Ask Beacon", icon: <IconChat /> },
  { id: "resources", label: "Resources", icon: <IconPhone /> },
  { id: "usage", label: "AI usage", icon: <IconChart /> },
];

export default function Shell() {
  const { user, here, tab, go, places, setHereId, sosId, toastText } = useApp();
  const [picker, setPicker] = useState(false);
  const [me, setMe] = useState(false);
  const [q, setQ] = useState("");
  const tabs = user.role === "dispatcher" ? DISPATCH_TABS : MEMBER_TABS;
  const initials = user.name.replace(/\(.*\)/, "").trim().split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  const screen = {
    home: <Home />, community: <Community />, alerts: <Alerts />, walk: <WalkScreen />, resources: <Resources />,
    dispatch: <Dispatch />, usage: <Usage />, ask: null, bluephones: <BluePhones />, shuttle: <Shuttle />,
  }[tab];

  return (
    <div className="stage">
      <div className="phone">
        <header className="topbar">
          <div className="brand">
            <img src="/beacon.svg" alt="" />
            <div>
              <div className="brand-name">Bulldog Beacon</div>
              <div className="brand-sub" title="Light and safety (a play on Yale's motto, Lux et Veritas)">Lux et Securitas</div>
            </div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="loc-chip" onClick={() => setPicker(true)} title="Where are you? (demo location)">
              <IconPin size={14} />
              <span>{here?.name.replace(/\s*\(.*\)/, "") ?? "Pick location"}</span>
            </button>
            <button className="avatar" onClick={() => setMe(true)} title={user.name}>{initials}</button>
          </div>
        </header>

        {tab === "ask" ? <Chat /> : <main className="app-scroll">{screen}</main>}

        <nav className="tabbar" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }}>
          {tabs.map((t) => (
            <button key={t.id} className={tab === t.id || (t.id === "resources" && (tab === "bluephones" || tab === "shuttle")) ? "on" : ""} onClick={() => go(t.id)}>
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>

        {sosId !== null && <SosOverlay />}
        {toastText && <div className="toast">{toastText}</div>}

        {picker && (
          <Sheet onClose={() => setPicker(false)}>
            <div className="h2">Where are you?</div>
            <p className="small muted" style={{ margin: "4px 0 12px" }}>
              Beacon uses this for nearby alerts, chat answers, and SOS. On a phone in New Haven it would use GPS; in this demo
              you choose.
            </p>
            <input className="input" placeholder="Search places" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
            <div className="stack" style={{ marginTop: 12, gap: 6 }}>
              {places
                .filter((p) => (p.name + " " + p.aliases.join(" ")).toLowerCase().includes(q.toLowerCase()))
                .map((p) => (
                  <button key={p.id} className="card tight click row" style={{ textAlign: "left" }}
                          onClick={() => { setHereId(p.id); setPicker(false); setQ(""); }}>
                    <IconPin size={16} />
                    <div className="grow">
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{p.name}</div>
                      <div className="tiny faint">{p.address.replace(", New Haven, CT", "")} · {p.kind}</div>
                    </div>
                    {here?.id === p.id && <span className="chip ok">Here</span>}
                  </button>
                ))}
            </div>
          </Sheet>
        )}
        {me && (
          <Sheet onClose={() => setMe(false)}>
            <Me
              onUsage={() => { setMe(false); go("usage"); }}
              onSignOut={async () => {
                await api("/api/auth/logout", { method: "POST", body: {} });
                window.location.reload();
              }}
            />
          </Sheet>
        )}
      </div>
      <Insights />
    </div>
  );
}
