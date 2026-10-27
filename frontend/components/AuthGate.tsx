"use client";

import { useEffect, useState } from "react";
import { post, request } from "@/lib/api";
import Dashboard from "./Dashboard";

export default function AuthGate() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    request("/api/me").then(() => setAuthenticated(true)).catch(() => {}).finally(() => setChecking(false));
    const expired = () => { setAuthenticated(false); setPassword(""); };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);

  async function login(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await post("/api/auth/login", { username, password });
      setPassword(""); setAuthenticated(true);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  async function logout() {
    try { await post("/api/auth/logout"); setAuthenticated(false); }
    catch (cause) { setError((cause as Error).message); }
  }

  if (checking) return <div className="loading-page">Проверяем сессию…</div>;
  if (authenticated) return <><Dashboard onLogout={() => void logout()}/>{error && <div className="alert alert-red" role="alert">{error}</div>}</>;
  return <main className="login-page"><section className="panel form-panel login-panel">
    <div className="eyebrow">DREAMTEAM</div><h1>Вход администратора</h1>
    <p className="body-copy">Введите учётные данные администратора.</p>
    <form className="form-stack" onSubmit={event => void login(event)}>
      <div className="field-group"><label htmlFor="login-username">Логин</label><input id="login-username" autoComplete="username" required maxLength={256} value={username} onChange={event => setUsername(event.target.value)}/></div>
      <div className="field-group"><label htmlFor="login-password">Пароль</label><input id="login-password" type="password" autoComplete="current-password" required maxLength={1024} value={password} onChange={event => setPassword(event.target.value)}/></div>
      {error && <div className="alert alert-red" role="alert">{error}</div>}
      <button className="button button-primary full-width" disabled={busy}>{busy ? "Входим…" : "Войти"}</button>
    </form>
  </section></main>;
}
