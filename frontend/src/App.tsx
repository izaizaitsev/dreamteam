import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, post, setToken, upload, type Attachment, type Citation, type Consultation, type Draft, type Job, type Obligation, type Prescription, type Source, type User } from './api'

type Section = 'consultations' | 'obligations' | 'prescriptions' | 'sources'

function ErrorText({ error }: { error: unknown }) { return error ? <p role="alert" className="error">{error instanceof Error ? error.message : String(error)}</p> : null }
function Citations({ items }: { items: Citation[] }) {
  return <div className="citations"><h4>Проверяемые источники</h4>{items.length ? items.map(item => <article className="citation" key={item.citation_id}>
    <strong>[{item.citation_id}] {item.title}</strong><p>{item.section} · с {item.effective_from}{item.effective_to ? ` по ${item.effective_to}` : ''}</p>
    <p>{item.fragment}</p>{item.source_url && <a href={item.source_url} target="_blank" rel="noopener noreferrer">Открыть источник</a>}
  </article>) : <p>Подтверждённые источники отсутствуют.</p>}</div>
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

function Consultations() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['consultations'], queryFn: () => api<Consultation[]>('/consultations') })
  const [question, setQuestion] = useState('')
  const [targetDate, setTargetDate] = useState(new Date().toLocaleDateString('en-CA'))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await post<Consultation>('/consultations', { question, target_date: targetDate }); setQuestion(''); await client.invalidateQueries({ queryKey: ['consultations'] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <><header><span className="eyebrow">Работа с нормами</span><h2>Консультации</h2><p>Ответ строится по загруженным источникам и требует проверки юристом.</p></header>
    <form className="panel form" onSubmit={submit}><label>Вопрос<textarea value={question} onChange={event => setQuestion(event.target.value)} minLength={5} required placeholder="Опишите ситуацию и вопрос" /></label>
      <label>Дата, на которую нужны нормы<input type="date" value={targetDate} onChange={event => setTargetDate(event.target.value)} required /></label>
      <button disabled={busy}>{busy ? 'Ищем источники…' : 'Получить черновик ответа'}</button><ErrorText error={error} /></form>
    <h3>История</h3>{query.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={query.error} />
    {query.data?.length === 0 && <p className="empty">Пока нет консультаций.</p>}
    {query.data?.map(item => <article className="panel" key={item.id}><div className="card-top"><strong>{item.question}</strong><span className="badge">{item.status === 'ai_draft' ? 'Черновик ИИ' : 'Недостаточно источников'}</span></div>
      <p className="muted">Дата применения норм: {item.target_date}</p>
      {item.status === 'insufficient_evidence' ? <p>Доступных источников недостаточно для надёжного вывода. Добавьте или уточните нормативные документы.</p> : <p className="answer">{item.answer}</p>}
      <Citations items={item.citations} /></article>)}</>
}

function Obligations() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['obligations'], queryFn: () => api<Obligation[]>('/obligations') })
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [priority, setPriority] = useState('normal')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [jobId, setJobId] = useState('')
  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => api<Job>(`/jobs/${jobId}`), enabled: !!jobId,
    refetchInterval: query => ['succeeded', 'failed', 'cancelled'].includes(query.state.data?.status || '') ? false : 2000 })
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await post('/obligations', { title, description, due_date: dueDate, priority }); setTitle(''); setDescription(''); setDueDate(''); await client.invalidateQueries({ queryKey: ['obligations'] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  async function complete(id: string) { try { await post(`/obligations/${id}/complete`); await client.invalidateQueries({ queryKey: ['obligations'] }) } catch (err) { setError(err) } }
  async function check() { try { const result = await post<{ job_id: string }>('/deadline-checks'); setJobId(result.job_id) } catch (err) { setError(err) } }
  return <><header><span className="eyebrow">Контроль исполнения</span><h2>Обязательства и сроки</h2><p>Просматривайте ближайшие и просроченные задачи.</p></header>
    <form className="panel form" onSubmit={submit}><label>Название<input value={title} onChange={event => setTitle(event.target.value)} required minLength={2} /></label>
      <label>Описание<textarea value={description} onChange={event => setDescription(event.target.value)} /></label>
      <div className="row"><label>Срок<input type="date" value={dueDate} onChange={event => setDueDate(event.target.value)} required /></label>
      <label>Приоритет<select value={priority} onChange={event => setPriority(event.target.value)}><option value="low">Низкий</option><option value="normal">Обычный</option><option value="high">Высокий</option></select></label></div>
      <button disabled={busy}>Добавить обязательство</button><ErrorText error={error} /></form>
    <div className="section-heading"><h3>Список</h3><button className="secondary" onClick={check}>Проверить ближайшие сроки</button></div>
    {jobId && <div className="panel"><strong>Проверка сроков: {job.data?.status || 'ожидание'}</strong>{job.data?.result?.due.map(item => <p key={item.id}>{item.title}: {item.days_remaining < 0 ? `просрочено на ${-item.days_remaining} дн.` : `осталось ${item.days_remaining} дн.`}</p>)}<ErrorText error={job.error || job.data?.error} /></div>}
    {query.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={query.error} />{query.data?.length === 0 && <p className="empty">Обязательств пока нет.</p>}
    {query.data?.map(item => <article className="panel compact" key={item.id}><div><div className="card-top"><strong>{item.title}</strong><span className={`badge ${item.deadline_state}`}>{item.deadline_state === 'overdue' ? 'Просрочено' : item.deadline_state === 'due_soon' ? 'Скоро срок' : item.deadline_state === 'closed' ? 'Завершено' : 'Предстоит'}</span></div><p>{item.description}</p><small>Срок: {item.due_date} · Приоритет: {item.priority}</small></div>{item.status !== 'done' && <button className="secondary" onClick={() => complete(item.id)}>Завершить</button>}</article>)}</>
}

function Prescriptions({ user }: { user: User }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['prescriptions'], queryFn: () => api<Prescription[]>('/prescriptions') })
  const [selected, setSelected] = useState('')
  const drafts = useQuery({ queryKey: ['drafts', selected], queryFn: () => api<Draft[]>(`/prescriptions/${selected}/drafts`), enabled: !!selected })
  const attachments = useQuery({ queryKey: ['attachments', selected], queryFn: () => api<Attachment[]>(`/prescriptions/${selected}/attachments`), enabled: !!selected })
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [uploadState, setUploadState] = useState<'idle' | 'selected' | 'uploading' | 'ready' | 'failed'>('idle')
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { const item = await post<Prescription>('/prescriptions', { title, content }); setTitle(''); setContent(''); setSelected(item.id); await client.invalidateQueries({ queryKey: ['prescriptions'] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  async function action(path: string) { setBusy(true); setError(null); try { await post(path); await client.invalidateQueries({ queryKey: ['drafts', selected] }) } catch (err) { setError(err) } finally { setBusy(false) } }
  async function uploadFile() {
    if (!file || !selected) return
    setUploadState('uploading'); setError(null)
    try { await upload<Attachment>(`/prescriptions/${selected}/attachments`, file); setFile(null); setUploadState('ready'); await client.invalidateQueries({ queryKey: ['attachments', selected] }) }
    catch (err) { setError(err); setUploadState('failed') }
  }
  const source = query.data?.find(item => item.id === selected)
  const canDraft = ['admin', 'director', 'lawyer'].includes(user.role)
  const canReview = ['admin', 'lawyer'].includes(user.role)
  return <><header><span className="eyebrow">Документы</span><h2>Предписания и проекты ответов</h2><p>Созданный текст остаётся черновиком до явного решения проверяющего.</p></header>
    <form className="panel form" onSubmit={submit}><label>Название предписания<input value={title} onChange={event => setTitle(event.target.value)} minLength={2} required /></label>
      <label>Текст предписания<textarea value={content} onChange={event => setContent(event.target.value)} minLength={10} required /></label>
      <button disabled={busy}>Сохранить предписание</button><ErrorText error={error} /></form>
    <h3>Документы</h3>{query.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={query.error} />
    {query.data?.length === 0 && <p className="empty">Предписаний пока нет.</p>}
    <div className="document-list">{query.data?.map(item => <button className={selected === item.id ? 'selected' : 'secondary'} key={item.id} onClick={() => { setSelected(item.id); setFile(null); setUploadState('idle') }}>{item.title}</button>)}</div>
    {source && <section className="panel"><h3>{source.title}</h3><p className="answer">{source.content}</p>
      <div className="attachments"><h4>Приложения</h4><p className="muted">TXT или PDF с текстовым слоем, до 10 МБ. Текст будет учтён при создании черновика.</p>
        <label>Выберите файл<input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={event => { setFile(event.target.files?.[0] || null); setUploadState(event.target.files?.[0] ? 'selected' : 'idle') }} /></label>
        <button className="secondary" disabled={!file || uploadState === 'uploading'} onClick={uploadFile}>{uploadState === 'uploading' ? 'Загрузка…' : 'Загрузить приложение'}</button>
        {uploadState === 'ready' && <p role="status">Файл обработан и готов к использованию.</p>}
        {uploadState === 'failed' && <p role="status">Обработка файла не удалась.</p>}
        <ErrorText error={attachments.error} />
        {attachments.isLoading && <p role="status">Загрузка приложений…</p>}
        {attachments.data?.map(item => <p key={item.id}>{item.filename} · {item.status === 'ready' ? 'готов' : item.status}</p>)}
      </div>{canDraft && <button disabled={busy} onClick={() => action(`/prescriptions/${source.id}/drafts`)}>Создать новый черновик</button>}</section>}
    {drafts.isLoading && <p role="status">Загрузка черновиков…</p>}<ErrorText error={drafts.error} />
    {drafts.data?.map(item => <article className="panel" key={item.id}><div className="card-top"><h3>Проект ответа</h3><span className="badge">{({ draft: 'Черновик ИИ', legal_review: 'На проверке', approved: 'Утверждён', rejected: 'Отклонён' } as Record<string, string>)[item.status] || item.status}</span></div>
      <p className="answer">{item.content}</p><Citations items={item.citations} />
      {canReview && item.status === 'draft' && <button disabled={busy} onClick={() => action(`/drafts/${item.id}/review`)}>Передать на проверку</button>}
      {canReview && item.status === 'legal_review' && <div className="actions"><button disabled={busy} onClick={() => action(`/drafts/${item.id}/approve`)}>Утвердить</button><button disabled={busy} className="secondary" onClick={() => action(`/drafts/${item.id}/reject`)}>Отклонить</button></div>}
    </article>)}</>
}

function Sources({ user }: { user: User }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['sources'], queryFn: () => api<Source[]>('/sources') })
  const [title, setTitle] = useState('')
  const [section, setSection] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [content, setContent] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await post('/sources', { title, section, source_url: sourceUrl || null, effective_from: from, effective_to: to || null, content }); setContent(''); await client.invalidateQueries({ queryKey: ['sources'] }) }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <><header><span className="eyebrow">База знаний</span><h2>Нормативные источники</h2><p>Добавляйте проверенные тексты с датами действия. Система не создаёт правовые сведения самостоятельно.</p></header>
    {['admin', 'lawyer'].includes(user.role) && <form className="panel form" onSubmit={submit}>
      <label>Название документа<input value={title} onChange={event => setTitle(event.target.value)} required minLength={3} /></label>
      <label>Статья или раздел<input value={section} onChange={event => setSection(event.target.value)} required /></label>
      <label>Ссылка на первоисточник<input type="url" value={sourceUrl} onChange={event => setSourceUrl(event.target.value)} /></label>
      <div className="row"><label>Действует с<input type="date" value={from} onChange={event => setFrom(event.target.value)} required /></label><label>Действует до<input type="date" value={to} onChange={event => setTo(event.target.value)} /></label></div>
      <label>Проверенный текст<textarea value={content} onChange={event => setContent(event.target.value)} required minLength={10} /></label>
      <button disabled={busy}>{busy ? 'Индексация…' : 'Добавить источник'}</button><ErrorText error={error} />
    </form>}
    <h3>Загруженные редакции</h3>{query.isLoading && <p role="status">Загрузка…</p>}<ErrorText error={query.error} />
    {query.data?.length === 0 && <p className="empty">Источники ещё не загружены. Консультации будут показывать недостаточность данных.</p>}
    {query.data?.map(item => <article className="panel compact" key={item.id}><div><strong>{item.title}</strong><p>{item.section} · с {item.effective_from}{item.effective_to ? ` по ${item.effective_to}` : ''}</p>{item.source_url && <a href={item.source_url} target="_blank" rel="noopener noreferrer">Первоисточник</a>}</div></article>)}</>
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
    <nav aria-label="Основные разделы">{([['consultations', 'Консультации'], ['obligations', 'Сроки'], ['prescriptions', 'Предписания'], ['sources', 'Источники']] as [Section, string][]).map(([id, label]) => <button key={id} className={section === id ? 'active' : ''} onClick={() => setSection(id)}>{label}</button>)}</nav>
    <div className="profile"><strong>{current.username}</strong><small>{current.role}</small><button onClick={logout}>Выйти</button></div></aside>
    <main className="content">{section === 'consultations' && <Consultations />}{section === 'obligations' && <Obligations />}{section === 'prescriptions' && <Prescriptions user={current} />}{section === 'sources' && <Sources user={current} />}</main></div>
}
