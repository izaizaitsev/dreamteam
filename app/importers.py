"""Bitrix export boundary. Change mappings here when a real export is available."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import re


def normalize_text(value: str) -> str:
    value = re.sub(r"<[^>]*>", " ", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(re.sub(r"[\t ]+", " ", line).strip()
                     for line in value.split("\n") if line.strip())


class AppealImportDTO(BaseModel):
    external_id: str = Field(min_length=1)
    source: str = "Bitrix24"
    title: str | None = None
    text: str = Field(min_length=1)
    applicant_name: str | None = None
    applicant_type: str | None = None
    building_id: str | None = None
    apartment_id: str | None = None
    received_at: datetime | None = None
    due_at: datetime | None = None
    status: str | None = None
    raw_payload: dict = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        cleaned = normalize_text(value)
        if not cleaned:
            raise ValueError("Пустой текст обращения")
        return cleaned


class BitrixJsonAdapter:
    def convert(self, row: dict) -> AppealImportDTO:
        if not isinstance(row, dict):
            raise ValueError("Ожидается JSON-объект")
        applicant = row.get("applicant") or {}
        obj = row.get("object") or {}
        return AppealImportDTO(
            external_id=str(row.get("external_id") or row.get("ID") or row.get("id") or ""),
            source=row.get("source") or "Bitrix24",
            title=row.get("title") or row.get("TITLE"),
            text=row.get("text") or row.get("DESCRIPTION") or row.get("description") or "",
            applicant_name=applicant.get("name") or row.get("applicant_name"),
            applicant_type=applicant.get("type") or row.get("applicant_type"),
            building_id=obj.get("building_id") or row.get("building_id"),
            apartment_id=obj.get("apartment_id") or row.get("apartment_id"),
            received_at=row.get("received_at"), due_at=row.get("due_at"),
            status=row.get("status") or row.get("STATUS_ID"), raw_payload=row,
        )


def records(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "appeals", "cases", "result"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    raise ValueError("Ожидается массив или объект JSON")
