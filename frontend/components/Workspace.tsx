"use client";

import { useCallback, useEffect, useState } from "react";
import { post, put, request } from "@/lib/api";
import type { AppealRow, AuditRow, TemplateRow } from "@/lib/types";
import { Badge, EmptyState, formatDate, Icon } from "./ui";

type Notice = { onNotice: (text: string, error?: boolean) => void };

function Heading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div></div>;
}

export function ImportView({ onNotice, onOpenAppeal }: Notice & { onOpenAppeal: (id: string) => void }) {
  const [appealFile, setAppealFile] = useState<File | null>(null);
  const [caseFile, setCaseFile] = useState<File | null>(null);
  const [decisionFile, setDecisionFile] = useState<File | null>(null);
  const [externalId, setExternalId] = useState("");
  const [indexNow, setIndexNow] = useState(true);
  const [report, setReport] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function run(task: () => Promise<unknown>, message: string) {
    setBusy(true);
    try { const result = await task(); if (result !== undefined) setReport(result); onNotice(message); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setBusy(false); }
  }
  async function importJson(file: File | null, path: string) {
    if (!file) throw new Error("Выберите JSON-файл");
    const data = JSON.parse(await file.text());
    return post(`/api/import/${path}`, data);
  }
  async function uploadWord() {
    if (!externalId.trim() || !decisionFile) throw new Error("Укажите external_id и выберите .docx");
    const body = new FormData();
    body.append("file", decisionFile);
    return request(`/api/cases/decision-file?external_id=${encodeURIComponent(externalId.trim())}`, { method: "POST", body });
  }
  async function loadDemo() {
    const example = await request<{ template: TemplateRow; appeal: AppealRow }>("/examples/legal-claim-demo.json");
    const templates = await request<TemplateRow[]>("/api/templates");
    if (!templates.some(row => row.code === example.template.code && row.active)) await post("/api/templates", example.template);
    const imported = await post("/api/import/appeals", [example.appeal]);
    setReport(imported);
    const matches = await request<AppealRow[]>(`/api/appeals?q=${encodeURIComponent(example.appeal.external_id)}`);
    if (!matches.length) throw new Error("Демонстрационное обращение не найдено после импорта");
    onOpenAppeal(matches[0].id);
    onNotice("Пример добавлен. Запустите AI-анализ.");
    return undefined;
  }

  return <><Heading eyebrow="ДАННЫЕ И ИСТОЧНИКИ" title="Импорт данных" description="Загружайте входящие обращения, решения и документы для поиска похожих кейсов."/>
    <div className="import-grid"><section className="panel import-card"><div className="import-number">01</div><span className="import-icon blue"><Icon name="inbox" size={22}/></span><h2>Новые обращения</h2><p>JSON-выгрузка из Bitrix24. После загрузки обращения появятся в очереди.</p><a className="example-link" href="/examples/new-appeals.json" download><Icon name="download" size={16}/>Скачать образец</a><label className="file-drop"><Icon name="upload" size={22}/><strong>{appealFile?.name || "Выберите JSON-файл"}</strong><small>JSON · выгрузка обращений</small><input type="file" accept=".json,application/json" onChange={event => setAppealFile(event.target.files?.[0] || null)}/></label><button className="button button-primary full-width" disabled={busy} onClick={() => void run(() => importJson(appealFile, "appeals"), "Новые обращения загружены")}>Загрузить обращения</button></section>
      <section className="panel import-card"><div className="import-number">02</div><span className="import-icon green"><Icon name="database" size={22}/></span><h2>Решённые обращения</h2><p>История с ответами для семантического поиска и сопоставления кейсов.</p><a className="example-link" href="/examples/resolved-cases.json" download><Icon name="download" size={16}/>Скачать образец</a><label className="file-drop"><Icon name="upload" size={22}/><strong>{caseFile?.name || "Выберите JSON-файл"}</strong><small>JSON · решения и ответы</small><input type="file" accept=".json,application/json" onChange={event => setCaseFile(event.target.files?.[0] || null)}/></label><label className="checkbox-line"><input type="checkbox" checked={indexNow} onChange={event => setIndexNow(event.target.checked)}/>Сразу индексировать</label><button className="button button-primary full-width" disabled={busy} onClick={() => void run(() => importJson(caseFile, `resolved-cases${indexNow ? "?index_now=true" : ""}`), "Решённые обращения загружены")}>Загрузить решения</button></section>
      <section className="panel import-card"><div className="import-number">03</div><span className="import-icon amber"><Icon name="file" size={22}/></span><h2>Word-файл решения</h2><p>Прикрепите утверждённый .docx к ранее загруженному решённому обращению.</p><div className="field-group"><label htmlFor="external-id">Номер обращения</label><input id="external-id" value={externalId} onChange={event => setExternalId(event.target.value)} placeholder="external_id"/></div><label className="file-drop"><Icon name="upload" size={22}/><strong>{decisionFile?.name || "Выберите Word-файл"}</strong><small>DOCX · до 10 МБ</small><input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={event => setDecisionFile(event.target.files?.[0] || null)}/></label><button className="button button-primary full-width" disabled={busy} onClick={() => void run(uploadWord, "Word-файл решения сохранён")}>Прикрепить документ</button></section></div>
    <div className="lower-grid"><section className="panel demo-panel"><span className="demo-mark"><Icon name="spark" size={24}/></span><div><div className="section-kicker">БЫСТРЫЙ СТАРТ</div><h2>Пример для юриста</h2><p>Добавьте тестовое обращение о возмещении ущерба с фактами и шаблоном ответа.</p></div><button className="button button-secondary" disabled={busy} onClick={() => void run(loadDemo, "Пример добавлен")}>Добавить пример<Icon name="chevron" size={16}/></button></section><section className="panel report-panel"><div className="section-kicker">РЕЗУЛЬТАТ ОПЕРАЦИИ</div><h2>Отчёт об импорте</h2>{report ? <pre>{JSON.stringify(report, null, 2)}</pre> : <p className="muted">После загрузки здесь появится отчёт.</p>}</section></div>
  </>;
}

export function TemplatesView({ onNotice }: Notice) {
  const [rows, setRows] = useState<TemplateRow[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setRows(await request<TemplateRow[]>("/api/templates")); } catch (error) { onNotice((error as Error).message, true); } }, [onNotice]);
  useEffect(() => { void load(); }, [load]);
  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try { await post("/api/templates", { code, name, category_code: category || null, body }); setCode(""); setName(""); setCategory(""); setBody(""); await load(); onNotice("Версия шаблона сохранена"); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setBusy(false); }
  }
  return <><Heading eyebrow="БИБЛИОТЕКА ОТВЕТОВ" title="Шаблоны" description="Управляйте версиями ответов для разных категорий обращений."/><div className="workspace-grid"><section className="panel form-panel"><div className="section-kicker">НОВАЯ ВЕРСИЯ</div><h2>Создать шаблон</h2><form onSubmit={event => void create(event)} className="form-stack"><div className="field-group"><label htmlFor="template-code">Код шаблона</label><input id="template-code" required value={code} onChange={event => setCode(event.target.value)} placeholder="Например, LEAK_V1"/></div><div className="field-group"><label htmlFor="template-name">Название</label><input id="template-name" required value={name} onChange={event => setName(event.target.value)} placeholder="Краткое название"/></div><div className="field-group"><label htmlFor="template-category">Код категории</label><input id="template-category" value={category} onChange={event => setCategory(event.target.value)} placeholder="Необязательно"/></div><div className="field-group"><label htmlFor="template-body">Текст шаблона</label><textarea id="template-body" required value={body} onChange={event => setBody(event.target.value)} placeholder="Текст с полями {{applicant_name}}…"/></div><button className="button button-primary full-width" disabled={busy}>Сохранить версию</button></form></section><section className="panel library-panel"><div className="panel-heading"><div><div className="section-kicker">БИБЛИОТЕКА</div><h2>Доступные шаблоны</h2></div><span className="count-label">{rows.length}</span></div>{rows.length ? rows.map(row => <div className="template-card" key={row.id}><div><strong>{row.name}</strong><Badge tone={row.active ? "green" : "neutral"}>{row.active ? "Активен" : "Неактивен"}</Badge></div><p>{row.code} · версия {row.version}{row.category_code ? ` · ${row.category_code}` : ""}</p><pre>{row.body}</pre></div>) : <EmptyState icon="layers" title="Шаблонов пока нет" text="Создайте первый шаблон ответа в форме слева."/>}</section></div></>;
}

export function IndexView({ onNotice }: Notice) {
  const [status, setStatus] = useState<{ total: number; indexed: number; pending: number } | null>(null);
  const [config, setConfig] = useState<{ embedding_model: string; embedding_configured: boolean; gigachat_model: string; gigachat_configured: boolean } | null>(null);
  const [report, setReport] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const [state, configuration] = await Promise.all([
        request<{ total: number; indexed: number; pending: number }>("/api/index/status"),
        request<{ embedding_model: string; embedding_configured: boolean; gigachat_model: string; gigachat_configured: boolean }>("/api/config"),
      ]);
      setStatus(state); setConfig(configuration);
    } catch (error) { onNotice((error as Error).message, true); }
  }, [onNotice]);
  useEffect(() => { void load(); }, [load]);
  async function update(action: "upsert" | "rebuild") {
    setBusy(true);
    try { setReport(await post(`/api/index/${action}`)); await load(); onNotice("Индексация завершена"); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setBusy(false); }
  }
  return <>
    <Heading eyebrow="ПОИСК И РЕЛЕВАНТНОСТЬ" title="Векторный индекс" description="Контролируйте базу решённых кейсов и подключение embedding API."/>
    <div className="metric-grid">
      <div className="metric-card"><span className="metric-icon metric-blue"><Icon name="database"/></span><div><span>Всего кейсов</span><strong>{status?.total ?? "—"}</strong><small>решённых обращений</small></div></div>
      <div className="metric-card"><span className="metric-icon metric-green"><Icon name="check"/></span><div><span>Индексировано</span><strong>{status?.indexed ?? "—"}</strong><small>готово к поиску</small></div></div>
      <div className="metric-card"><span className="metric-icon metric-amber"><Icon name="clock"/></span><div><span>Ожидают</span><strong>{status?.pending ?? "—"}</strong><small>переиндексации</small></div></div>
    </div>
    <div className="workspace-grid">
      <section className="panel form-panel"><div className="section-kicker">УПРАВЛЕНИЕ</div><h2>Индексация</h2><p className="body-copy">Добавьте новые кейсы в Qdrant или пересоздайте индекс при смене embedding-модели.</p><div className="form-stack"><button className="button button-primary full-width" disabled={busy} onClick={() => void update("upsert")}><Icon name="plus"/>Индексировать новые</button><button className="button button-secondary full-width" disabled={busy} onClick={() => void update("rebuild")}><Icon name="refresh"/>Переиндексировать все</button></div><div className="hint-box">Векторизация обращений выполняется через Cloud.ru API.</div></section>
      <section className="panel library-panel"><div className="section-kicker">ПОДКЛЮЧЕНИЯ</div><h2>Модели и сервисы</h2><div className="config-row"><span>Embedding</span><strong>{config?.embedding_model || "—"}</strong></div><div className="config-row"><span>Ключ embedding</span><Badge tone={config?.embedding_configured ? "green" : "amber"}>{config?.embedding_configured ? "Задан" : "Не задан"}</Badge></div><div className="config-row"><span>GigaChat</span><strong>{config?.gigachat_model || "—"}</strong></div><div className="config-row"><span>Ключ GigaChat</span><Badge tone={config?.gigachat_configured ? "green" : "amber"}>{config?.gigachat_configured ? "Задан" : "Не задан"}</Badge></div>{report !== null && <><div className="subheading">Отчёт</div><pre className="report-pre">{JSON.stringify(report, null, 2)}</pre></>}</section>
    </div>
  </>;
}

export function AuditView({ onNotice }: Notice) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  useEffect(() => { request<AuditRow[]>("/api/audit").then(setRows).catch(error => onNotice(error.message, true)); }, [onNotice]);
  return <><Heading eyebrow="ПРОЗРАЧНОСТЬ ПРОЦЕССА" title="Журнал действий" description="История операций с обращениями, документами и моделями."/><section className="panel list-panel"><div className="panel-heading"><div><h2>События системы</h2><p>Последние действия пользователей и AI-сервисов</p></div><span className="count-label">{rows.length} записей</span></div><div className="table-wrap"><table className="data-table"><thead><tr><th>ВРЕМЯ</th><th>ОБРАЩЕНИЕ</th><th>ДЕЙСТВИЕ</th><th>ПОЛЬЗОВАТЕЛЬ</th><th>ДЕТАЛИ</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{formatDate(row.created_at)}</td><td className="mono">{row.appeal_id || "—"}</td><td><span className="table-primary">{row.action}</span></td><td>{row.actor || "Система"}</td><td className="details-cell">{row.details}</td></tr>)}</tbody></table></div>{rows.length === 0 && <EmptyState icon="activity" title="Записей пока нет" text="Действия появятся после работы с обращениями."/>}</section></>;
}

export function SettingsView({ onNotice }: Notice) {
  const [giga, setGiga] = useState<{ configured: boolean; model: string } | null>(null);
  const [embedding, setEmbedding] = useState<{ configured: boolean; model: string } | null>(null);
  const [health, setHealth] = useState<{ db: string; embedding: string } | null>(null);
  const [gigaKey, setGigaKey] = useState("");
  const [embeddingKey, setEmbeddingKey] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const [gigaSettings, embeddingSettings, embeddingHealth, db] = await Promise.all([
        request<{ configured: boolean; model: string }>("/api/settings/gigachat"),
        request<{ configured: boolean; model: string }>("/api/settings/embedding"),
        request<{ status: string }>("/health/embedding"),
        request<{ status: string }>("/health/db"),
      ]);
      setGiga(gigaSettings); setEmbedding(embeddingSettings);
      setHealth({ db: db.status, embedding: embeddingHealth.status });
    } catch (error) { onNotice((error as Error).message, true); }
  }, [onNotice]);
  useEffect(() => { void load(); }, [load]);
  async function saveGiga(event: React.FormEvent) {
    event.preventDefault(); if (!gigaKey.trim()) { onNotice("Введите ключ GigaChat", true); return; }
    setBusy(true);
    try { await put("/api/settings/gigachat", { auth_key: gigaKey.trim() }); setGigaKey(""); await load(); onNotice("Ключ GigaChat сохранён"); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setBusy(false); }
  }
  async function saveEmbedding(event: React.FormEvent) {
    event.preventDefault(); if (!embeddingKey.trim()) { onNotice("Введите ключ embedding API", true); return; }
    setBusy(true);
    try { await put("/api/settings/embedding", { api_key: embeddingKey.trim() }); setEmbeddingKey(""); await load(); onNotice("Ключ embedding API сохранён"); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setBusy(false); }
  }
  return <>
    <Heading eyebrow="КОНФИГУРАЦИЯ" title="Настройки" description="Проверьте подключения и настройте ключи AI-сервисов."/>
    <div className="settings-grid">
      <section className="panel form-panel"><div className="section-kicker">ВЕКТОРИЗАЦИЯ</div><h2>Ключ embedding API</h2><p className="body-copy">Cloud.ru · <strong>{embedding?.model || "—"}</strong></p><div className="setting-status"><Badge tone={embedding?.configured ? "green" : "amber"}>{embedding?.configured ? "Ключ сохранён" : "Ключ не задан"}</Badge></div><p className="muted">Ключ скрыт после сохранения. Для сохранения при пересоздании контейнера задайте API_KEY в локальном .env.</p><form className="form-stack" onSubmit={event => void saveEmbedding(event)}><div className="field-group"><label htmlFor="embedding-key">API key</label><input id="embedding-key" type="password" autoComplete="new-password" value={embeddingKey} onChange={event => setEmbeddingKey(event.target.value)} placeholder="Введите ключ Cloud.ru"/></div><button className="button button-primary full-width" disabled={busy}>Сохранить ключ</button></form></section>
      <section className="panel form-panel"><div className="section-kicker">ЯЗЫКОВАЯ МОДЕЛЬ</div><h2>Ключ GigaChat</h2><p className="body-copy">Модель: <strong>{giga?.model || "—"}</strong></p><div className="setting-status"><Badge tone={giga?.configured ? "green" : "amber"}>{giga?.configured ? "Ключ сохранён" : "Ключ не задан"}</Badge></div><p className="muted">Ключ не показывается после сохранения. Для постоянной настройки задайте GIGACHAT_AUTH_KEY в локальном .env.</p><form className="form-stack" onSubmit={event => void saveGiga(event)}><div className="field-group"><label htmlFor="giga-key">Authorization key</label><input id="giga-key" type="password" autoComplete="new-password" value={gigaKey} onChange={event => setGigaKey(event.target.value)} placeholder="Введите ключ"/></div><button className="button button-primary full-width" disabled={busy}>Сохранить ключ</button></form></section>
      <section className="panel diagnostics-panel"><div className="section-kicker">ДИАГНОСТИКА</div><h2>Состояние сервисов</h2>{([["База данных", health?.db], ["Embedding API", health?.embedding]] as const).map(([name, status]) => <div className="health-row" key={name}><div><span className={`health-dot ${status === "ok" || status === "configured" ? "healthy" : "unhealthy"}`}/><strong>{name}</strong></div><Badge tone={status === "ok" || status === "configured" ? "green" : "amber"}>{status || "проверяем"}</Badge></div>)}<div className="hint-box">Статус embedding показывает наличие ключа. Фактическое соединение проверяется при векторизации.</div></section>
    </div>
  </>;
}
