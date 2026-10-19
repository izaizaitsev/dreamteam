"""Templates shipped with the application."""
import json

from ..repositories import sqlite as repository


AIR_CONDITIONER_CLAIM = {
    "code": "AIR_CONDITIONER_FACADE_CLAIM_V1",
    "name": "Претензия о демонтаже кондиционера с фасада",
    "category_code": "AIR_CONDITIONER_FACADE_CLAIM",
    "body": (
        "Исх. № {{outgoing_number}} от {{outgoing_date}}\n"
        "Кому: {{recipient_name}}\n"
        "Адрес: {{recipient_address}}\n\n"
        "Претензия о демонтаже кондиционера с фасада многоквартирного дома\n\n"
        "Уважаемый(ая) {{recipient_name}}!\n\n"
        "{{sender_name}} осуществляет управление многоквартирным домом по адресу: "
        "{{building_address}}. Основание управления: {{management_basis}}.\n\n"
        "Сведения об осмотре фасада: {{inspection_details}}.\n\n"
        "Правовое обоснование и сведения о необходимых согласованиях: {{legal_section}}\n\n"
        "При подтверждении указанных обстоятельств просим в течение 30 дней с даты "
        "получения настоящей претензии демонтировать наружный блок кондиционера, "
        "восстановить фасад в первоначальное состояние и письменно сообщить "
        "о выполнении требований.\n\n"
        "При отсутствии ответа или отказе от выполнения требований управляющая "
        "организация оставляет за собой право обратиться за защитой прав "
        "собственников помещений в установленном порядке после проверки материалов.\n\n"
        "Приложение: {{inspection_act_details}}\n\n"
        "{{signatory_name}}\n"
        "Исполнитель: {{executor_name}}, {{executor_phone}}"
    ),
    "required_context": [
        {"key": "building_info", "reason": "Адрес дома и сведения об управлении"},
        {"key": "work_history", "reason": "Акт и обстоятельства осмотра фасада"},
    ],
}


def seed_builtin_templates():
    template = AIR_CONDITIONER_CLAIM
    if repository.one("SELECT id FROM templates WHERE code=? LIMIT 1", (template["code"],)):
        return
    repository.execute(
        "INSERT INTO templates VALUES (?,?,?,?,?,?,?,?,?)",
        (repository.uid(), template["code"], template["name"], template["category_code"],
         template["body"], json.dumps(template["required_context"], ensure_ascii=False),
         1, 1, repository.now()),
    )
