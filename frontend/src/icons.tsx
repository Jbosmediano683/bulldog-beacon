// Inline line icons (no icon library needed).
type P = { size?: number };
const base = (size = 22) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 1.9, strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
});

export const IconHome = ({ size }: P) => (
  <svg {...base(size)}><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /><path d="M10 21v-6h4v6" /></svg>
);
export const IconUsers = ({ size }: P) => (
  <svg {...base(size)}><circle cx="9" cy="8" r="3.2" /><path d="M2.8 20c.6-3.4 3.2-5.4 6.2-5.4s5.6 2 6.2 5.4" /><circle cx="17" cy="9.2" r="2.6" /><path d="M15.6 14.4c2.8-.2 5 1.5 5.6 4.6" /></svg>
);
export const IconMap = ({ size }: P) => (
  <svg {...base(size)}><path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4z" /><path d="M9 4v13M15 6.5v13" /></svg>
);
export const IconChat = ({ size }: P) => (
  <svg {...base(size)}><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12z" /><path d="M8.5 11h.01M12 11h.01M15.5 11h.01" /></svg>
);
export const IconWalk = ({ size }: P) => (
  <svg {...base(size)}><circle cx="13" cy="4.5" r="2" /><path d="m9 21 2.5-6.5L14 17v4M8.5 11.5 11 8l3 1.5 2 3.5M11 8l-1 6.5" /></svg>
);
export const IconPhone = ({ size }: P) => (
  <svg {...base(size)}><path d="M5 3h3.5l1.5 5-2.2 1.4a12 12 0 0 0 6.8 6.8L16 14l5 1.5V19a2 2 0 0 1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2z" /></svg>
);
export const IconShield = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3 4.5 6v5.5c0 4.6 3.1 8.4 7.5 9.5 4.4-1.1 7.5-4.9 7.5-9.5V6L12 3z" /><path d="m9 12 2 2 4-4" /></svg>
);
export const IconRadio = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="2" /><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19 5a10 10 0 0 1 0 14M5 19A10 10 0 0 1 5 5" /></svg>
);
export const IconChart = ({ size }: P) => (
  <svg {...base(size)}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>
);
export const IconPin = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg>
);
export const IconSend = ({ size }: P) => (
  <svg {...base(size)}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const IconPlus = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 5v14M5 12h14" /></svg>
);
export const IconX = ({ size }: P) => (
  <svg {...base(size)}><path d="M6 6l12 12M18 6 6 18" /></svg>
);
export const IconHeart = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 20s-7.5-4.6-9-9.4C2 7.3 4.3 4.5 7.4 4.5c2 0 3.4 1 4.6 2.6 1.2-1.6 2.6-2.6 4.6-2.6 3.1 0 5.4 2.8 4.4 6.1-1.5 4.8-9 9.4-9 9.4z" /></svg>
);
export const IconCar = ({ size }: P) => (
  <svg {...base(size)}><path d="M5 16V11l2-5h10l2 5v5M3 16h18v3h-3v-1H6v1H3z" /><circle cx="7.5" cy="13.5" r=".8" /><circle cx="16.5" cy="13.5" r=".8" /></svg>
);
export const IconEye = ({ size }: P) => (
  <svg {...base(size)}><path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.8" /></svg>
);
export const IconBag = ({ size }: P) => (
  <svg {...base(size)}><path d="M5 8h14l-1 12H6L5 8z" /><path d="M9 8V6.5a3 3 0 0 1 6 0V8" /></svg>
);
export const IconAlert = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3.5 21.5 20h-19L12 3.5z" /><path d="M12 10v4.5M12 17.2h.01" /></svg>
);
export const IconOctagon = ({ size }: P) => (
  <svg {...base(size)}><path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2L8.2 3z" /><path d="M12 8v5M12 16h.01" /></svg>
);
export const IconBadge = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 3 5 6v5.5c0 4.3 3 7.9 7 9 4-1.1 7-4.7 7-9V6l-7-3z" /><path d="m12 8.5 1.1 2.3 2.5.3-1.8 1.7.5 2.5-2.3-1.3-2.3 1.3.5-2.5-1.8-1.7 2.5-.3L12 8.5z" /></svg>
);
export const IconCone = ({ size }: P) => (
  <svg {...base(size)}><path d="M10 4h4l4.5 15h-13L10 4z" /><path d="M8.3 10h7.4M6.8 15h10.4M3.5 19h17" /></svg>
);
export const IconCross = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v9M7.5 12h9" /></svg>
);
export const IconFlame = ({ size }: P) => (
  <svg {...base(size)}><path d="M12 21c-3.9 0-6.5-2.6-6.5-6.2 0-3.1 2.2-5.1 3.6-7.4.3 1.7 1.2 2.9 2.4 3.4-.1-2.9 1.1-5.5 3.4-7.3.2 2.8 1.7 4.5 2.9 6.2 1 1.4 1.7 3 1.7 5.1 0 3.6-2.8 6.2-7.5 6.2z" /></svg>
);
export const IconMegaphone = ({ size }: P) => (
  <svg {...base(size)}><path d="M4 10v4h3l8 4.5V5.5L7 10H4z" /><path d="M18.5 9.5a3.5 3.5 0 0 1 0 5M7.5 14.2 9 19.5h2.5" /></svg>
);
export const IconInfo = ({ size }: P) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.8h.01" /></svg>
);
export const IconComment = ({ size }: P) => (
  <svg {...base(size)}><path d="M20 12.5a7.5 7.5 0 0 1-10.9 6.7L4 20.5l1.4-4.3A7.5 7.5 0 1 1 20 12.5z" /></svg>
);
export const IconCalendar = ({ size }: P) => (
  <svg {...base(size)}><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>
);
export const IconTicket = ({ size }: P) => (
  <svg {...base(size)}><path d="M3.5 8V6h17v2a2.5 2.5 0 0 0 0 5v2h-17v-2a2.5 2.5 0 0 0 0-5z" transform="translate(0 1.5)" /><path d="M14 7.5v10" strokeDasharray="2 2" /></svg>
);
export const IconCheck = ({ size }: P) => (
  <svg {...base(size)}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
);
export const IconMoon = ({ size }: P) => (
  <svg {...base(size)}><path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z" /></svg>
);
export const IconLightbulb = ({ size }: P) => (
  <svg {...base(size)}><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z" /></svg>
);
export const IconChevron = ({ size }: P) => (
  <svg {...base(size)}><path d="m9 6 6 6-6 6" /></svg>
);
export const IconExternal = ({ size }: P) => (
  <svg {...base(size)}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
);

/** One quiet line icon per alert category (no emoji). */
export function CatIcon({ category, size = 18 }: { category: string; size?: number }) {
  const C = {
    suspicious_activity: IconEye, vehicle_break_in: IconCar, theft: IconBag, harassment: IconAlert,
    assault: IconOctagon, police_activity: IconBadge, hazard: IconCone, medical: IconCross, fire: IconFlame,
    gathering: IconMegaphone, safety_update: IconShield, good_news: IconHeart, other: IconInfo,
  }[category] ?? IconInfo;
  return <C size={size} />;
}
