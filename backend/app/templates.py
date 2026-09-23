"""Local demo templates. No model call is made for obligation drafts."""
import secrets
from datetime import date

TEMPLATES = (
    "В ответ на документ «{title}» сообщаем: {statement}\nВопрос: {question}\n{completion}\nОснование для проверки: {fragment}\n\nЧерновик требует проверки и редактирования ответственным сотрудником.",
    "По документу «{title}» подготовлен проект ответа. {statement}\nПо вопросу «{question}»: {completion}\nФрагмент исходного документа: {fragment}\n\nПроверьте факты перед отправкой.",
    "Проект служебного ответа по документу «{title}».\n{statement}\n{completion}\nПроверяемый вопрос: {question}\nСвязанный фрагмент: {fragment}\n\nТекст не является утверждённым ответом.",
)

def render_obligation_draft(document: dict, question: str, completed: bool, completion_date: date) -> tuple[str, str]:
    index = secrets.randbelow(len(TEMPLATES))
    statement = "Мероприятие выполнено." if completed else "Мероприятие пока не выполнено."
    completion = (f"Дата выполнения: {completion_date.isoformat()}." if completed else
                  f"Планируемая дата выполнения: {completion_date.isoformat()}.")
    return TEMPLATES[index].format(title=document["title"], statement=statement, question=question,
        completion=completion, fragment=document.get("source_fragment") or "Фрагмент отсутствует"), f"local-{index + 1}"
