"use client";

import { useCallback, useEffect, useState } from "react";
import { download, post, put, request } from "@/lib/api";
import type { AppealDetail, AppealRow, DraftPayload, Role } from "@/lib/types";
import { Badge, EmptyState, formatDate, Icon, statusTone } from "./ui";

type Props = { selected: string | null; onSelect: (id: string | null) => void; role: Role; onNotice: (text: string, error?: boolean) => void };

export function Appeals(props: Props) {
  return props.selected ? <AppealCard {...props} id={props.selected}/> : <AppealList {...props}/>;
}

function AppealList({ onSelect, onNotice }: Props) {
  const [rows, setRows] = useState<AppealRow[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (query = "") => {
    setLoading(true);
    try { setRows(await request<AppealRow[]>(`/api/appeals${query ? `?q=${encodeURIComponent(query)}` : ""}`)); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setLoading(false); }
  }, [onNotice]);
  useEffect(() => { void load(); }, [load]);
  const pending = rows.filter(row => row.status === "NEW").length;
  const review = rows.filter(row => ["READY_FOR_REVIEW", "CONTEXT_REQUIRED", "APPROVED"].includes(row.status)).length;

  return <>
    <div className="page-heading"><div><div className="eyebrow">ОБРАБОТКА ОБРАЩЕНИЙ</div><h1>Очередь обращений</h1><p>Проверяйте новые обращения и ведите их до окончательного решения.</p></div><button className="button button-quiet" onClick={() => void load(search)}><Icon name="refresh"/>Обновить</button></div>
    <div className="metric-grid"><div className="metric-card"><span className="metric-icon metric-blue"><Icon name="inbox"/></span><div><span>Всего обращений</span><strong>{rows.length}</strong><small>в текущей выборке</small></div></div><div className="metric-card"><span className="metric-icon metric-amber"><Icon name="clock"/></span><div><span>Новые</span><strong>{pending}</strong><small>ожидают обработки</small></div></div><div className="metric-card"><span className="metric-icon metric-green"><Icon name="shield"/></span><div><span>На проверке</span><strong>{review}</strong><small>требуют внимания</small></div></div></div>
    <section className="panel list-panel"><div className="panel-heading"><div><h2>Все обращения</h2><p>История и текущий статус входящих запросов</p></div><span className="count-label">{rows.length} записей</span></div><form className="toolbar" onSubmit={event => { event.preventDefault(); void load(search); }}><div className="search-field"><Icon name="search" size={18}/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Найти по номеру, теме или тексту" aria-label="Поиск обращений"/></div><button className="button button-secondary" type="submit">Найти</button></form>
      <div className="table-wrap"><table className="data-table"><thead><tr><th>ОБРАЩЕНИЕ</th><th>ИСТОЧНИК</th><th>ЗАЯВИТЕЛЬ</th><th>СРОК</th><th>СТАТУС</th><th></th></tr></thead><tbody>{rows.map(row => <tr key={row.id} onClick={() => onSelect(row.id)} tabIndex={0} onKeyDown={event => { if (event.key === "Enter") onSelect(row.id); }}><td><div className="table-primary">{row.external_id}</div><div className="table-secondary truncate">{row.title || row.text.slice(0, 100)}</div></td><td>{row.source || "—"}</td><td>{row.applicant_name || "—"}</td><td>{formatDate(row.due_at)}</td><td><Badge tone={statusTone(row.status)}>{row.status}</Badge></td><td><Icon name="chevron" size={16}/></td></tr>)}</tbody></table></div>
      {!loading && rows.length === 0 && <EmptyState title="Обращений пока нет" text="Загрузите JSON-файл в разделе «Импорт данных»."/>}
      {loading && <div className="loading-line">Загружаем обращения…</div>}
    </section>
  </>;
}

function AppealCard({ id, onSelect, role, onNotice }: Props & { id: string }) {
  const [item, setItem] = useState<AppealDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actor, setActor] = useState("");
  const [editedText, setEditedText] = useState("");
  const [decisionUri, setDecisionUri] = useState("");
  const [indexResolved, setIndexResolved] = useState(false);
  const load = useCallback(async () => {
    const data = await request<AppealDetail>(`/api/appeals/${id}`);
    setItem(data);
    setEditedText(data.draft?.edited_text || "");
    setDecisionUri(data.draft?.document_uri || "");
  }, [id]);
  useEffect(() => {
    setActor(sessionStorage.getItem("actor") || "");
    load().catch(error => onNotice(error.message, true));
  }, [load, onNotice]);
  async function run(label: string, task: () => Promise<unknown>, refresh = true) {
    setBusy(label);
    try { await task(); if (refresh) await load(); onNotice(`${label}: готово`); }
    catch (error) { onNotice((error as Error).message, true); }
    finally { setBusy(null); }
  }
  function reviewer() {
    const value = actor.trim();
    if (!value) throw new Error("Введите имя проверяющего");
    sessionStorage.setItem("actor", value);
    return value;
  }
  if (!item) return <div className="loading-page">Загружаем карточку обращения…</div>;
  const classification = item.classification;
  const draft = item.draft;
  const payload: DraftPayload | null = draft ? (typeof draft.ai_payload === "string" ? JSON.parse(draft.ai_payload) : draft.ai_payload) : null;
  const canEdit = draft?.status === "PENDING" && role !== "OPERATOR";
  const canRun = role !== "OPERATOR";
  const stageButtons: { title: string; path: string }[] = [
    { title: "Поиск похожих", path: "retrieve" }, { title: "Классифицировать", path: "classify" },
    { title: "Обновить контекст", path: "load-context" }, { title: "Создать черновик", path: "generate-draft" },
  ];

  return <>
    <button className="back-link" onClick={() => onSelect(null)}><Icon name="arrow" size={17}/>К очереди обращений</button>
    <div className="page-heading detail-heading"><div><div className="eyebrow">КАРТОЧКА ОБРАЩЕНИЯ · {item.external_id}</div><h1>{item.title || item.external_id}</h1><div className="heading-meta"><Badge tone={statusTone(item.status)}>{item.status}</Badge><span>{item.source}</span><span>Получено: {formatDate(item.received_at)}</span></div></div>{canRun && <button className="button button-primary" disabled={!!busy} onClick={() => void run("AI-анализ", () => post(`/api/appeals/${id}/process`))}><Icon name="spark"/>{busy === "AI-анализ" ? "Выполняется…" : "Запустить AI-анализ"}</button>}</div>
    {canRun && <div className="stage-bar"><span>ОТДЕЛЬНЫЕ ЭТАПЫ</span>{stageButtons.map(stage => <button key={stage.path} disabled={!!busy} onClick={() => void run(stage.title, () => post(`/api/appeals/${id}/${stage.path}`))}>{stage.title}<Icon name="chevron" size={14}/></button>)}</div>}
    {item.error && <div className="alert alert-red">{item.error}</div>}
    <div className="detail-grid"><div className="detail-main">
      <section className="panel"><div className="panel-heading"><div><div className="section-kicker">01 / ИСХОДНЫЕ ДАННЫЕ</div><h2>Обращение</h2></div><span className="panel-icon"><Icon name="file"/></span></div><div className="metadata-grid"><div><span>Заявитель</span><strong>{item.applicant_name || "—"}</strong></div><div><span>Дом</span><strong>{item.building_id || "—"}</strong></div><div><span>Срок ответа</span><strong>{formatDate(item.due_at)}</strong></div></div><div className="subheading">Текст обращения</div><div className="document-text">{item.text}</div></section>
      <section className="panel"><div className="panel-heading"><div><div className="section-kicker">02 / АНАЛИЗ</div><h2>Результат AI</h2></div><span className="panel-icon accent"><Icon name="spark"/></span></div>{classification ? <><div className="analysis-summary"><div><small>ЮРИДИЧЕСКОЕ СОПРОВОЖДЕНИЕ</small><strong>{classification.legal_required ? "Требуется юрист" : "Не требуется"}</strong></div><div><small>ТИП ОБРАЩЕНИЯ</small><strong>{classification.case_type}</strong></div></div><div className="subheading">Категория</div><p>{classification.category?.name || "—"} <span className="muted">{classification.category?.code}</span></p><div className="subheading">Основание</div><p className="body-copy">{classification.reasoning_summary}</p>{classification.required_context.length > 0 && <><div className="subheading">Необходимые данные</div><div className="chip-list">{classification.required_context.map((entry, i) => <span className="chip" key={`${entry.key}-${i}`}>{entry.key}{entry.reason && <span> · {entry.reason}</span>}</span>)}</div></>}{classification.warnings.map((warning, i) => <div className="alert alert-amber" key={i}>{warning}</div>)}</> : <EmptyState icon="spark" title="Анализ ещё не выполнен" text="Запустите AI-анализ или отдельный этап классификации."/>}</section>
      <section className="panel"><div className="panel-heading"><div><div className="section-kicker">03 / ПРОВЕРКА</div><h2>Черновик ответа</h2></div>{draft && <Badge tone={statusTone(draft.status)}>{draft.status}</Badge>}</div>{draft && payload ? <>{payload.template_code && <div className="template-note"><Icon name="layers" size={16}/>Заполнен шаблон {payload.template_code} · версия {payload.template_version}</div>}{payload.missing_information.map((value, i) => <div className="alert alert-amber" key={`missing-${i}`}>Нет данных: {value}</div>)}{payload.warnings.map((value, i) => <div className="alert alert-amber" key={`warning-${i}`}>{value}</div>)}<label className="field-label" htmlFor="draft-text">Текст ответа</label><textarea id="draft-text" className="draft-editor" readOnly={!canEdit} value={editedText} onChange={event => setEditedText(event.target.value)}/>{canEdit && <><div className="review-controls"><input value={actor} onChange={event => setActor(event.target.value)} placeholder="Имя проверяющего" aria-label="Имя проверяющего"/><button className="button button-secondary" disabled={!!busy} onClick={() => void run("Сохранение", () => put(`/api/drafts/${draft.id}`, { actor: reviewer(), text: editedText }))}>Сохранить</button><button className="button button-primary" disabled={!!busy} onClick={() => void run("Одобрение", () => post(`/api/drafts/${draft.id}/approve`, { actor: reviewer(), text: editedText }))}>Одобрить</button><button className="button button-danger" disabled={!!busy} onClick={() => void run("Отклонение", () => post(`/api/drafts/${draft.id}/reject`, { actor: reviewer(), text: editedText }))}>Отклонить</button></div></>}{draft.status === "APPROVED" && canRun && <div className="resolved-box"><div><strong>Ответ одобрен</strong><p>Экспортируйте Word-файл и сохраните обращение как решённый кейс.</p></div><button className="button button-secondary" disabled={!!busy} onClick={() => void run("Экспорт Word", () => download(`/api/drafts/${draft.id}/export-docx`, `response-${draft.id}.docx`))}><Icon name="download"/>Скачать Word</button><div className="resolved-controls"><input value={actor} onChange={event => setActor(event.target.value)} placeholder="Имя проверяющего" aria-label="Имя проверяющего"/><input value={decisionUri} onChange={event => setDecisionUri(event.target.value)} placeholder="Путь к итоговому документу (необязательно)"/><label className="checkbox-line"><input type="checkbox" checked={indexResolved} onChange={event => setIndexResolved(event.target.checked)}/>Сразу индексировать</label><button className="button button-primary" disabled={!!busy} onClick={() => void run("Сохранение кейса", async () => { const result = await post<{ index_error?: string }>(`/api/appeals/${id}/mark-resolved`, { actor: reviewer(), decision_file_uri: decisionUri || null, index_now: indexResolved }); if (result.index_error) onNotice(result.index_error, true); })}>Отметить решённым</button></div></div>}<details className="disclosure"><summary>Исходный текст AI</summary><div className="document-text">{payload.full_text}</div></details></> : <EmptyState icon="file" title="Черновика пока нет" text="Он появится после анализа обращения, которому требуется юрист."/>}</section>
    </div><div className="detail-side"><section className="panel side-panel"><div className="panel-heading"><div><div className="section-kicker">КОНТЕКСТ</div><h2>Собранные данные</h2></div></div>{item.context.length ? item.context.map((entry, i) => <div className="context-item" key={`${entry.key}-${i}`}><div><strong>{entry.key}</strong><Badge tone={entry.status === "available" ? "green" : "amber"}>{entry.status}</Badge></div><small>{entry.source}</small><pre>{JSON.stringify(entry.data, null, 2)}</pre>{entry.warning && <p className="muted">{entry.warning}</p>}</div>) : <p className="muted">Контекст ещё не загружен.</p>}</section>
      <section className="panel side-panel"><div className="panel-heading"><div><div className="section-kicker">ПРАКТИКА</div><h2>Похожие обращения</h2></div><span className="count-label">{item.similar_cases.length}</span></div>{item.similar_cases.length ? item.similar_cases.map((caseItem, i) => <div className="case-item" key={`${caseItem.id}-${i}`}><div className="case-item-top"><strong>{caseItem.external_id}</strong>{caseItem.retrieval_score != null && <small>{Number(caseItem.retrieval_score).toFixed(2)}</small>}</div><p>{caseItem.appeal_text}</p><details className="disclosure"><summary>Посмотреть решение</summary><div className="document-text">{caseItem.decision_text || "Текст решения не приложен"}</div>{caseItem.decision_file_uri && <p className="muted">{caseItem.decision_file_uri}</p>}</details>{caseItem.decision_file_uri && <button className="text-button" onClick={() => void run("Скачивание Word", () => download(`/api/cases/${encodeURIComponent(caseItem.id)}/decision-file`, `resolved-${caseItem.id}.docx`), false)}><Icon name="download" size={15}/>Скачать Word</button>}</div>) : <p className="muted">Индекс пока пуст или поиск не запускался.</p>}</section>
      <section className="panel side-panel"><div className="panel-heading"><div><div className="section-kicker">ИСТОРИЯ</div><h2>Действия</h2></div></div>{item.audit.length ? <div className="timeline">{item.audit.map(entry => <div className="timeline-item" key={entry.id}><span className="timeline-dot"/><strong>{entry.action}</strong><small>{formatDate(entry.created_at)} · {entry.actor || "Система"}</small></div>)}</div> : <p className="muted">Действий пока нет.</p>}</section>
    </div></div>
  </>;
}
