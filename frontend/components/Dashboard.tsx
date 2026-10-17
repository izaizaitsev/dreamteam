"use client";

import { useCallback, useEffect, useState } from "react";
import { request } from "@/lib/api";
import type { Role } from "@/lib/types";
import { Icon } from "./ui";
import { Appeals } from "./Appeals";
import { ImportView, TemplatesView, IndexView, AuditView, SettingsView } from "./Workspace";

type View = "appeals" | "import" | "templates" | "index" | "audit" | "settings";
const navigation: { id: View; title: string; icon: Parameters<typeof Icon>[0]["name"] }[] = [
  { id: "appeals", title: "Обращения", icon: "inbox" },
  { id: "import", title: "Импорт данных", icon: "upload" },
  { id: "templates", title: "Шаблоны", icon: "layers" },
  { id: "index", title: "Векторный индекс", icon: "database" },
  { id: "audit", title: "Журнал действий", icon: "activity" },
  { id: "settings", title: "Настройки", icon: "settings" },
];

export default function Dashboard() {
  const [view, setView] = useState<View>("appeals");
  const [selected, setSelected] = useState<string | null>(null);
  const [role, setRole] = useState<Role>("ADMIN");
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const showNotice = useCallback((text: string, error = false) => { setNotice({ text, error }); }, []);

  useEffect(() => {
    request<{ role: Role }>("/api/me").then(data => setRole(data.role)).catch(error => showNotice(error.message, true));
  }, [showNotice]);
  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(null), 7000);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  function navigate(next: View) { setView(next); setSelected(null); setSidebarOpen(false); }
  const pageTitle = selected ? "Карточка обращения" : navigation.find(item => item.id === view)?.title;
  const common = { onNotice: showNotice };

  return <div className="app-shell">
    {sidebarOpen && <button className="sidebar-scrim" aria-label="Закрыть меню" onClick={() => setSidebarOpen(false)}/>}
    <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
      <div className="brand"><span className="brand-mark"><Icon name="spark" size={22}/></span><div><strong>Legal Copilot</strong><small>ЖКХ · рабочее пространство</small></div></div>
      <div className="sidebar-label">РАБОЧЕЕ МЕСТО</div>
      <nav aria-label="Основная навигация" className="sidebar-nav">
        {navigation.filter(item => role === "ADMIN" || item.id === "appeals").map(item =>
          <button key={item.id} className={`nav-item ${view === item.id ? "nav-item-active" : ""}`} onClick={() => navigate(item.id)}><Icon name={item.icon}/><span>{item.title}</span>{view === item.id && <span className="nav-active-dot"/>}</button>)}
      </nav>
      <div className="sidebar-bottom"><span className="online-dot"/><div><strong>Система активна</strong><small>Внутренний контур</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><button className="menu-button" aria-label="Открыть меню" onClick={() => setSidebarOpen(true)}><Icon name="grid"/></button><div className="breadcrumbs"><span>Рабочее пространство</span><Icon name="chevron" size={14}/><strong>{pageTitle}</strong></div><div className="topbar-right"><span className="role-label"><Icon name="shield" size={15}/>{role}</span><span className="avatar">{role[0]}</span></div></header>
      <main className="content-wrap">
        {view === "appeals" && <Appeals key={selected || "list"} selected={selected} onSelect={setSelected} role={role} {...common}/>}
        {view === "import" && <ImportView onOpenAppeal={(id) => { setSelected(id); setView("appeals"); }} {...common}/>}
        {view === "templates" && <TemplatesView {...common}/>}
        {view === "index" && <IndexView {...common}/>}
        {view === "audit" && <AuditView {...common}/>}
        {view === "settings" && <SettingsView {...common}/>}
      </main>
    </div>
    {notice && <div role="status" className={`toast ${notice.error ? "toast-error" : "toast-success"}`}><Icon name={notice.error ? "close" : "check"} size={18}/><span>{notice.text}</span><button aria-label="Закрыть уведомление" onClick={() => setNotice(null)}><Icon name="close" size={16}/></button></div>}
  </div>;
}
