import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Place, type RunUsage, type User } from "./api";

export type Tab = "home" | "community" | "alerts" | "ask" | "walk" | "resources" | "dispatch" | "usage";
export type MapLayer = "all" | "safety" | "events";

export type ActivityItem = {
  id: string;
  at: number;
  agent: "moderator" | "corroborator" | "concierge" | "responder" | "rule";
  title: string;
  detail?: string;
  run?: RunUsage | null;
  tone?: "ok" | "shield" | "warn";
};

type AppState = {
  user: User;
  setUser: (u: User | null) => void;
  places: Place[];
  placeById: (id: number | null | undefined) => Place | undefined;
  here: Place | undefined;
  setHereId: (id: number) => void;
  tab: Tab;
  go: (tab: Tab, opts?: { incidentId?: number; eventId?: number; walkDraft?: WalkDraft; chatPrompt?: string; mapLayer?: MapLayer }) => void;
  mapLayer: MapLayer;
  setMapLayer: (layer: MapLayer) => void;
  focusIncidentId: number | null;
  clearFocus: () => void;
  focusEventId: number | null;
  clearFocusEvent: () => void;
  walkDraft: WalkDraft | null;
  clearWalkDraft: () => void;
  chatPrompt: string | null;
  clearChatPrompt: () => void;
  activity: ActivityItem[];
  log: (item: Omit<ActivityItem, "id" | "at">) => void;
  sosId: number | null;
  setSosId: (id: number | null) => void;
  toast: (text: string) => void;
  toastText: string | null;
};

export type WalkDraft = { origin_place_id?: number | null; dest_place_id?: number | null; minutes?: number | null };

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

function defaultPlaceFor(user: User, places: Place[]): number {
  const saved = Number(localStorage.getItem(`beacon-here-${user.netid}`));
  if (saved && places.some((p) => p.id === saved)) return saved;
  const unit = (user.unit || "").toLowerCase();
  const match =
    (unit.includes("clinical") && places.find((p) => p.name.includes("YCCI"))) ||
    (unit.includes("police") && places.find((p) => p.name.includes("Yale Police"))) ||
    (unit.includes("management") && places.find((p) => p.name.includes("Evans"))) ||
    places.find((p) => p.name.includes("Sterling Memorial"));
  return match ? match.id : places[0]?.id ?? 1;
}

export function AppProvider({ user, setUser, children }: { user: User; setUser: (u: User | null) => void; children: ReactNode }) {
  const [places, setPlaces] = useState<Place[]>([]);
  const [hereId, setHereIdState] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>(user.role === "dispatcher" ? "dispatch" : "home");
  const [focusIncidentId, setFocus] = useState<number | null>(null);
  const [focusEventId, setFocusEvent] = useState<number | null>(null);
  const [walkDraft, setWalkDraft] = useState<WalkDraft | null>(null);
  const [chatPrompt, setChatPrompt] = useState<string | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [sosId, setSosId] = useState<number | null>(null);
  const [toastText, setToastText] = useState<string | null>(null);
  const [mapLayer, setMapLayer] = useState<MapLayer>("all");

  useEffect(() => {
    api<Place[]>("/api/places").then((ps) => {
      setPlaces(ps);
      setHereIdState(defaultPlaceFor(user, ps));
    });
  }, [user]);

  const placeById = useCallback((id: number | null | undefined) => places.find((p) => p.id === id), [places]);

  const setHereId = useCallback(
    (id: number) => {
      setHereIdState(id);
      localStorage.setItem(`beacon-here-${user.netid}`, String(id));
    },
    [user.netid],
  );

  const go = useCallback<AppState["go"]>((t, opts) => {
    if (opts?.incidentId) setFocus(opts.incidentId);
    if (opts?.eventId) setFocusEvent(opts.eventId);
    if (opts?.walkDraft) setWalkDraft(opts.walkDraft);
    if (opts?.chatPrompt) setChatPrompt(opts.chatPrompt);
    if (opts?.mapLayer) setMapLayer(opts.mapLayer);
    else if (opts?.incidentId) setMapLayer("all");
    setTab(t);
    document.querySelector(".app-scroll")?.scrollTo({ top: 0 });
  }, []);

  const log = useCallback((item: Omit<ActivityItem, "id" | "at">) => {
    setActivity((a) => [{ ...item, id: Math.random().toString(36).slice(2), at: Date.now() }, ...a].slice(0, 40));
  }, []);

  const toast = useCallback((text: string) => {
    setToastText(text);
    window.setTimeout(() => setToastText((cur) => (cur === text ? null : cur)), 3800);
  }, []);

  const value = useMemo<AppState>(
    () => ({
      user, setUser, places, placeById, here: placeById(hereId), setHereId, tab, go,
      focusIncidentId, clearFocus: () => setFocus(null), focusEventId, clearFocusEvent: () => setFocusEvent(null), walkDraft, clearWalkDraft: () => setWalkDraft(null),
      chatPrompt, clearChatPrompt: () => setChatPrompt(null), activity, log, sosId, setSosId, toast, toastText,
      mapLayer, setMapLayer,
    }),
    [user, setUser, places, placeById, hereId, setHereId, tab, go, focusIncidentId, focusEventId, walkDraft, chatPrompt, activity, log, sosId, toast, toastText, mapLayer],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
