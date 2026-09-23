import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, downloadOriginal, patch, post, setToken, uploadDocument,
  type Citation, type Consultation, type DashboardItem, type DocumentJob,
  type DocumentSummary, type Draft, type Escalation, type User } from './api'

type Section = 'consultations' | 'generator' | 'deadlines'
const today = () => new Date().toLocaleDateString('en-CA')

function ErrorText({ error }: { error: unknown }) {
  return error ? <p role="alert" className="error">{error instanceof Error ? error.message : String(error)}</p> : null
}

function OriginalButton({ revisionId }: { revisionId: string }) {
  const [error, setError] = useState<unknown>(null)
  return <><button type="button" className="secondary" onClick={async () => { try { await downloadOriginal(revisionId) } catch (err) { setError(err) } }}>Скачать оригинал DOCX</button><ErrorText error={error} /></>
}

function CitationCards({ items }: { items: Citation[] }) {
  return <div className="citations"><h4>Фрагменты и происхождение</h4>{items.length ? items.map((item, index) =>
    <article className="citation" key={`${item.revision_id || index}-${index}`}>
      <strong>[{item.citation_id || `S${index + 1}`}] {item.title}</strong>
      <p className="muted">{item.document_category === 'obligation' ? 'Документ обязательств' : 'Нормативный документ'}{item.section ? ` · ${item.section}` : ''}</p>
      <p>{item.fragment}</p>
      {item.date_provenance === 'demo_random_unverified' && <p className="notice">Даты предложены демозаглушкой, не подтверждены источником.</p>}
      {item.revision_id && <OriginalButton revisionId={item.revision_id} />}
    </article>) : <p>Подтверждённых фрагментов нет.</p>}</div>
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { const result = await post<{ token: string; user: User }>('/login', { username, password }); setToken(result.token); onLogin(result.user) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <main className="login"><form className="panel" onSubmit={submit}><span className="eyebrow">Внутренний сервис</span><h1>Юридический помощник ЖКХ</h1>
    <label>Пользователь<input value={username} onChange={event => setUsername(event.target.value)} required /></label>
    <label>Пароль<input type="password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
    <button disabled={busy}>{busy ? 'Вход…' : 'Войти'}</button><ErrorText error={error} />
  </form></main>
}

function DocumentUploader({ category, user }: { category: 'normative' | 'obligation'; user: User }) {
  const client = useQueryClient()
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const job = useQuery({ queryKey: ['document-job', jobId], queryFn: () => api<DocumentJob>(`/documents/jobs/${jobId}`), enabled: !!jobId,
    refetchInterval: query => ['succeeded', 'failed', 'needs_review'].includes(query.state.data?.status || '') ? false : 1500 })
  const status = job.data?.status
  if (category === 'normative' && !['admin', 'lawyer'].includes(user.role)) return null
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!file) return
    setBusy(true); setError(null)
    try { const result = await uploadDocument(category, title, file); setJobId(result.job_id); setTitle(''); setFile(null) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  async function refresh() {
    await client.invalidateQueries({ queryKey: ['documents', category] })
    await client.invalidateQueries({ queryKey: ['deadline-dashboard'] })
  }
  return <form className="panel form" onSubmit={submit}><div className="card-top"><h3>Загрузить DOCX</h3><span className="badge">{category === 'obligation' ? 'Документ обязательств' : 'Нормативный документ'}</span></div>
    <label>Название документа<input value={title} onChange={event => setTitle(event.target.value)} minLength={3} required /></label>
    <label>Файл DOCX<input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={event => setFile(event.target.files?.[0] || null)} required /></label>
    <button disabled={busy || !file}>{busy ? 'Приём файла…' : 'Загрузить документ'}</button><ErrorText error={error} />
    {jobId && <div className="job-state" role="status">Обработка: {status || 'в очереди'}{job.data?.stage ? ` · этап ${job.data.stage}` : ''}
      {job.data?.error_message && <p className="error">{job.data.error_message}</p>}
      {status === 'succeeded' && <button type="button" className="secondary" onClick={refresh}>Показать документ в списке</button>}
    </div>}
  </form>
}

function Consultations({ user }: { user: User }) {
  const client = useQueryClient()
  const documents = useQuery({ queryKey: ['documents', 'normative'], queryFn: () => api<DocumentSummary[]>('/documents?document_category=normative') })
  const consultations = useQuery({ queryKey: ['consultations'], queryFn: () => api<Consultation[]>('/consultations') })
  const [question, setQuestion] = useState('')
  const [targetDate, setTargetDate] = useState(today())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await post('/consultations', { question, target_date: targetDate }); setQuestion(''); await client.invalidateQueries({ queryKey: ['consultations'] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <><header><span className="eyebrow">Модуль 1</span><h2>Консультации</h2></header>
    <DocumentUploader category="normative" user={user} />
    <h3>Нормативные документы</h3>{documents.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={documents.error} />
    {documents.data?.length === 0 && <p className="empty">Пока нет нормативных DOCX.</p>}
    {documents.data?.map(item => <article className="panel compact" key={item.revision_id}><div><strong>{item.title}</strong><p>{item.filename} · {item.status}</p>
      <small>Демо период: {item.valid_from || 'не задан'} — {item.valid_to || 'не задан'}; даты не подтверждены.</small></div><OriginalButton revisionId={item.revision_id} /></article>)}
    <form className="panel form" onSubmit={submit}><h3>Задать вопрос</h3><label>Вопрос<textarea value={question} onChange={event => setQuestion(event.target.value)} minLength={5} required /></label>
      <label>Дата анализа<input type="date" value={targetDate} onChange={event => setTargetDate(event.target.value)} required /></label>
      <button disabled={busy}>{busy ? 'Поиск…' : 'Получить черновик'}</button><ErrorText error={error} /></form>
    <h3>История консультаций</h3>{consultations.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={consultations.error} />
    {consultations.data?.length === 0 && <p className="empty">Консультаций пока нет.</p>}
    {consultations.data?.map(item => <article className="panel" key={item.id}><div className="card-top"><strong>{item.question}</strong><span className="badge">{item.status === 'insufficient_evidence' ? 'Недостаточно данных' : item.status === 'demo_unverified' ? 'Демо черновик' : 'Черновик'}</span></div>
      <p className="muted">Дата анализа: {item.target_date}</p>
      {item.status === 'insufficient_evidence' ? <p>По загруженным документам не найдено достаточно оснований для ответа.</p> : <p className="answer">{item.answer}</p>}
      <CitationCards items={item.citations} /></article>)}</>
}

function DraftEditor({ draft, revisionId, canReview }: { draft: Draft; revisionId: string; canReview: boolean }) {
  const client = useQueryClient()
  const [content, setContent] = useState(draft.content)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  async function action(path: string, edit = false) {
    setBusy(true); setError(null)
    try { if (edit) await patch(path, { content }); else await post(path); await client.invalidateQueries({ queryKey: ['obligation-drafts', revisionId] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <article className="panel"><div className="card-top"><h3>Проект ответа</h3><span className="badge">{draft.status === 'draft' ? 'Редактируемый черновик' : draft.status === 'legal_review' ? 'На проверке' : draft.status === 'approved' ? 'Утверждён' : 'Отклонён'}</span></div>
    <p className="muted">Локальный шаблон: {draft.template_id || '—'}</p>
    {draft.status === 'draft' ? <label>Текст черновика<textarea className="draft-editor" value={content} onChange={event => setContent(event.target.value)} /></label> : <p className="answer">{draft.content}</p>}
    {draft.status === 'draft' && <div className="actions"><button disabled={busy} onClick={() => action(`/drafts/${draft.id}`, true)}>Сохранить правки</button>{canReview && <button className="secondary" disabled={busy} onClick={() => action(`/drafts/${draft.id}/review`)}>Передать на проверку</button>}</div>}
    {draft.status === 'legal_review' && canReview && <div className="actions"><button disabled={busy} onClick={() => action(`/drafts/${draft.id}/approve`)}>Утвердить</button><button className="secondary" disabled={busy} onClick={() => action(`/drafts/${draft.id}/reject`)}>Отклонить</button></div>}
    <ErrorText error={error} /><CitationCards items={draft.citations} />
  </article>
}

function Generator({ user }: { user: User }) {
  const client = useQueryClient()
  const documents = useQuery({ queryKey: ['documents', 'obligation'], queryFn: () => api<DocumentSummary[]>('/documents?document_category=obligation') })
  const [selected, setSelected] = useState('')
  const drafts = useQuery({ queryKey: ['obligation-drafts', selected], queryFn: () => api<Draft[]>(`/obligation-documents/${selected}/drafts`), enabled: !!selected })
  const [question, setQuestion] = useState('')
  const [completionDate, setCompletionDate] = useState(today())
  const [completed, setCompleted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!selected) return
    setBusy(true); setError(null)
    try { await post(`/obligation-documents/${selected}/drafts`, { question, completion_date: completionDate, completed }); await client.invalidateQueries({ queryKey: ['obligation-drafts', selected] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  const selectedDocument = documents.data?.find(item => item.revision_id === selected)
  return <><header><span className="eyebrow">Модуль 2</span><h2>Генератор ответов</h2></header>
    <DocumentUploader category="obligation" user={user} />
    <h3>Документы обязательств</h3>{documents.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={documents.error} />
    {documents.data?.length === 0 && <p className="empty">Загрузите DOCX документа обязательств.</p>}
    <div className="document-list">{documents.data?.filter(item => item.status === 'published_demo').map(item =>
      <button key={item.revision_id} className={selected === item.revision_id ? 'selected' : 'secondary'} onClick={() => setSelected(item.revision_id)}>{item.title}</button>)}</div>
    {selectedDocument && <><article className="panel"><div className="card-top"><strong>{selectedDocument.title}</strong><OriginalButton revisionId={selectedDocument.revision_id} /></div>
      <p>{selectedDocument.source_fragment}</p><p className="notice">Предложенный срок: {selectedDocument.due_date || 'не задан'}. Это случайная демодата, не дата из документа.</p></article>
      <form className="panel form" onSubmit={submit}><h3>Новый черновик</h3><label>Вопрос или предмет ответа<textarea value={question} onChange={event => setQuestion(event.target.value)} minLength={5} required /></label>
        <label>Дата выполнения или планируемого выполнения<input type="date" value={completionDate} onChange={event => setCompletionDate(event.target.value)} required /></label>
        <fieldset><legend>Мероприятие выполнено?</legend><label className="radio"><input type="radio" name="completed" checked={completed} onChange={() => setCompleted(true)} />Да</label><label className="radio"><input type="radio" name="completed" checked={!completed} onChange={() => setCompleted(false)} />Нет</label></fieldset>
        <button disabled={busy}>{busy ? 'Создание…' : 'Создать редактируемый черновик'}</button><ErrorText error={error} />
      </form></>}
    {drafts.isLoading && <p role="status">Загрузка черновиков…</p>}<ErrorText error={drafts.error} />
    {drafts.data?.map(item => <DraftEditor key={item.id} draft={item} revisionId={selected} canReview={['admin', 'lawyer'].includes(user.role)} />)}</>
}

function Deadlines({ user }: { user: User }) {
  const client = useQueryClient()
  const dashboard = useQuery({ queryKey: ['deadline-dashboard'], queryFn: () => api<DashboardItem[]>('/deadline-dashboard') })
  const escalations = useQuery({ queryKey: ['director-escalations'], queryFn: () => api<Escalation[]>('/director-escalations'), enabled: ['admin', 'director'].includes(user.role) })
  const [error, setError] = useState<unknown>(null)
  const [busyId, setBusyId] = useState('')
  async function escalate(revisionId: string) {
    setBusyId(revisionId); setError(null)
    try { await post(`/deadline-dashboard/${revisionId}/escalate`); await client.invalidateQueries({ queryKey: ['deadline-dashboard'] }); await client.invalidateQueries({ queryKey: ['director-escalations'] }) }
    catch (err) { setError(err) } finally { setBusyId('') }
  }
  const items = dashboard.data || []
  return <><header><span className="eyebrow">Модуль 3</span><h2>Контроль сроков</h2></header>
    <div className="metrics"><div className="panel"><strong>{items.length}</strong><span>Документов со сроком</span></div><div className="panel"><strong>{items.filter(item => item.sla_state === 'overdue').length}</strong><span>Просрочено</span></div><div className="panel"><strong>{items.filter(item => item.sla_state === 'due_soon').length}</strong><span>Скоро срок</span></div></div>
    {dashboard.isLoading && <p role="status">Загрузка SLA…</p>}<ErrorText error={dashboard.error || error} />
    {dashboard.data?.length === 0 && <p className="empty">Опубликованных документов обязательств со сроком пока нет. Загрузите DOCX в модуле «Генератор».</p>}
    {items.map(item => <article className="panel" key={item.revision_id}><div className="card-top"><h3>{item.title}</h3><span className={`badge ${item.sla_state}`}>{item.sla_state === 'overdue' ? 'Просрочено' : item.sla_state === 'due_soon' ? 'Скоро срок' : 'Предстоит'}</span></div>
      <p><strong>SLA: {item.due_date}</strong> · {item.days_remaining < 0 ? `просрочено на ${-item.days_remaining} дн.` : `осталось ${item.days_remaining} дн.`}</p>
      <p className="notice">Дата создана случайной демозаглушкой и не подтверждена документом.</p>
      <div className="source-box"><strong>Связанный фрагмент документа</strong><p>{item.source_fragment || 'Фрагмент не найден'}</p><OriginalButton revisionId={item.revision_id} /></div>
      {item.escalated_at ? <p className="muted">Эскалировано директору: {new Date(item.escalated_at).toLocaleString('ru-RU')}</p> : user.role !== 'director' &&
        <button disabled={busyId === item.revision_id} onClick={() => escalate(item.revision_id)}>Эскалация директору</button>}
    </article>)}
    {['admin', 'director'].includes(user.role) && <section><h3>Эскалации для директора</h3><ErrorText error={escalations.error} />{escalations.data?.length === 0 && <p className="empty">Эскалаций нет.</p>}
      {escalations.data?.map(item => <div className="panel compact" key={item.id}><strong>{item.title}</strong><span>{new Date(item.created_at).toLocaleString('ru-RU')}</span></div>)}</section>}
  </>
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [section, setSection] = useState<Section>('consultations')
  const client = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<User>('/me'), enabled: !!sessionStorage.getItem('token') && !user, retry: false })
  const current = user || me.data
  function logout() { setToken(''); setUser(null); client.clear(); setSection('consultations') }
  if (!current) return <Login onLogin={value => { client.clear(); setUser(value) }} />
  return <div className="shell"><aside className="sidebar"><div className="brand"><span className="mark">§</span><div>Юрист ЖКХ<small>Рабочее пространство</small></div></div>
    <nav aria-label="Основные разделы">{([['consultations', 'Консультации'], ['generator', 'Генератор'], ['deadlines', 'Сроки и SLA']] as [Section, string][]).map(([id, label]) =>
      <button key={id} className={section === id ? 'active' : ''} onClick={() => setSection(id)}>{label}</button>)}</nav>
    <div className="profile"><strong>{current.username}</strong><small>{current.role}</small><button onClick={logout}>Выйти</button></div></aside>
    <main className="content">{section === 'consultations' && <Consultations user={current} />}{section === 'generator' && <Generator user={current} />}{section === 'deadlines' && <Deadlines user={current} />}</main></div>
}
