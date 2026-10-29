const fieldLabels: Record<string, string> = {
  work_history: "История выполненных работ",
  dispatch_requests: "Заявки в диспетчерскую службу",
  previous_appeals: "Предыдущие обращения",
  building_info: "Сведения о доме",
  building_id: "Идентификатор дома",
  apartment_id: "Квартира",
  applicant_name: "Имя заявителя",
  received_at: "Дата получения",
  appeal_text: "Текст обращения",
  title: "Тема",
  subject: "Тема ответа",
  issue_summary: "Суть обращения",
  factual_section: "Обстоятельства",
  work_section: "Выполненные работы",
  legal_section: "Правовое обоснование",
  closing_section: "Заключение",
  id: "Идентификатор",
  external_id: "Номер обращения",
  date: "Дата",
  address: "Адрес",
  status: "Статус",
  description: "Описание",
  text: "Текст",
  result: "Результат",
  contractor: "Подрядчик",
};

export function fieldLabel(key: string): string {
  return fieldLabels[key] || key;
}

export function contextStatus(status: string): string {
  return ({ available: "Получены", missing: "Нет данных", unavailable: "Недоступны" } as Record<string, string>)[status] || "Неизвестно";
}

export function contextSource(source: string): string {
  return ({ "Bitrix24 import": "Импорт из Битрикс24", "no connected source": "Источник не подключён", "tool registry": "Источники данных" } as Record<string, string>)[source] || source;
}

export function contextData(data: unknown): string {
  function translate(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(translate);
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [fieldLabel(key), translate(item)]));
    }
    return value;
  }
  return data == null ? "Данные отсутствуют" : JSON.stringify(translate(data), null, 2);
}
