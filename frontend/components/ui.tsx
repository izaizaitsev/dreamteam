import type { ReactNode } from "react";

type IconName = "grid" | "inbox" | "upload" | "layers" | "database" | "activity" | "settings" | "search" | "arrow" | "chevron" | "spark" | "refresh" | "download" | "file" | "check" | "clock" | "shield" | "plus" | "close";

const paths: Record<IconName, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  inbox: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 13h5l2 3h4l2-3h5"/></>,
  upload: <><path d="M12 16V3m0 0-4 4m4-4 4 4"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
  database: <><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/></>,
  activity: <><path d="M3 12h4l3-7 4 14 3-7h4"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l-2 2a1.7 1.7 0 0 0-1.8-.3l-1.5.6v2.2h-2.8v-2.2l-1.5-.6a1.7 1.7 0 0 0-1.8.3l-2-2a1.7 1.7 0 0 0 .3-1.8L6 13.5H3.8v-2.8H6l.6-1.5a1.7 1.7 0 0 0-.3-1.8l2-2a1.7 1.7 0 0 0 1.8.3l1.5-.6V3h2.8v2.2l1.5.6a1.7 1.7 0 0 0 1.8-.3l2 2a1.7 1.7 0 0 0-.3 1.8l.6 1.5h2.2v2.8H20l-.6 1.5Z"/></>,
  search: <><circle cx="10.7" cy="10.7" r="6.7"/><path d="m16 16 5 5"/></>,
  arrow: <><path d="M19 12H5m0 0 6-6m-6 6 6 6"/></>,
  chevron: <><path d="m9 18 6-6-6-6"/></>,
  spark: <><path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2ZM19 17l.7 1.3L21 19l-1.3.7L19 21l-.7-1.3L17 19l1.3-.7L19 17Z"/></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2.4 6M20 4v7h-7"/></>,
  download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v3h16v-3"/></>,
  file: <><path d="M6 2h8l5 5v15H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v6h5M8 13h8M8 17h8"/></>,
  check: <><path d="m4 12 5 5L20 6"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  shield: <><path d="m12 2 9 4v6c0 5-3.5 8.5-9 10-5.5-1.5-9-5-9-10V6l9-4Z"/><path d="m8 12 3 3 5-6"/></>,
  plus: <><path d="M12 4v16M4 12h16"/></>,
  close: <><path d="M5 5 19 19M19 5 5 19"/></>,
};

export function Icon({ name, size = 18, className = "" }: { name: IconName; size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "amber" | "blue" | "red" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function statusTone(status: string): "neutral" | "green" | "amber" | "blue" | "red" {
  if (["APPROVED", "RESOLVED", "READY_FOR_REVIEW"].includes(status)) return "green";
  if (["ERROR", "REJECTED"].includes(status)) return "red";
  if (["NEW", "PENDING", "CONTEXT_REQUIRED"].includes(status)) return "amber";
  return "blue";
}

export function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

export function EmptyState({ icon = "inbox", title, text }: { icon?: IconName; title: string; text: string }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={26}/></span><strong>{title}</strong><p>{text}</p></div>;
}
