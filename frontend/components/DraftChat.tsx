"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import type { DraftChatMessage } from "@/lib/types";
import { formatDate } from "./ui";

type Props = {
  draftId: string;
  text: string;
  savedText: string;
  messages: DraftChatMessage[];
  editable: boolean;
  busy: boolean;
  onBusy: (busy: boolean) => void;
  onUpdated: (text: string, messages: DraftChatMessage[]) => void;
  onNotice: (text: string, error?: boolean) => void;
};

export default function DraftChat(props: Props) {
  const [instruction, setInstruction] = useState("");
  const [error, setError] = useState("");
  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (props.busy || !instruction.trim()) return;
    props.onBusy(true); setError("");
    try {
      const result = await post<{ edited_text: string; chat: DraftChatMessage[] }>(
        `/api/drafts/${props.draftId}/chat`, { instruction: instruction.trim(), text: props.text, base_text: props.savedText },
      );
      props.onUpdated(result.edited_text, result.chat);
      setInstruction(""); props.onNotice("Черновик обновлён. Проверьте изменения перед одобрением.");
    } catch (cause) { setError((cause as Error).message); }
    finally { props.onBusy(false); }
  }
  return <section className="draft-chat" aria-label="Чат по исправлению черновика">
    <h3>Уточнить черновик с AI</h3>
    <div className="draft-chat-history" role="log" aria-live="polite" aria-relevant="additions">
      {props.messages.map(message => <div className={`draft-chat-message draft-chat-${message.role}`} key={message.id}>
        <div className="draft-chat-meta"><strong>{message.role === "user" ? "Вы" : "AI-помощник"}</strong><small>{formatDate(message.created_at)}</small></div>
        <p>{message.content}</p>
        {message.role === "assistant" && <details className="disclosure"><summary>Текст этой версии</summary><div className="document-text">{message.snapshot_text}</div></details>}
      </div>)}
    </div>
    {props.editable && <form className="form-stack" onSubmit={event => void send(event)}>
      <label className="field-label" htmlFor="draft-instruction">Что нужно исправить?</label>
      <textarea id="draft-instruction" required maxLength={8000} rows={3} disabled={props.busy} value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="Например: сократи ответ и сделай формулировки понятнее"/>
      <p className="muted">Будет изменён текущий текст, включая ваши ручные правки.</p>
      {error && <div className="alert alert-red" role="alert">{error}</div>}
      <button className="button button-primary" disabled={props.busy || !instruction.trim() || !props.text.trim()}>Исправить черновик</button>
    </form>}
    {props.busy && <p role="status">Выполняется запрос…</p>}
    {!props.editable && <p className="muted">Черновик уже рассмотрен. История уточнений доступна для просмотра.</p>}
  </section>;
}
