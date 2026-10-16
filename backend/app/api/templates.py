"""Templates API routes."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..repositories import sqlite as s
from .dependencies import auth, admin

router = APIRouter()


class TemplateInput(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category_code: str | None = None
    body: str = Field(min_length=1)
    required_context: list[dict] = []
    active: bool = True



@router.get("/api/templates", dependencies=[Depends(auth)])
def templates():
    return s.all_rows("SELECT * FROM templates ORDER BY code,version DESC")



@router.post("/api/templates", dependencies=[Depends(admin)])
def create_template(body: TemplateInput):
    version = s.one("SELECT MAX(version) AS n FROM templates WHERE code=?", (body.code,))["n"] or 0
    template_id = s.uid()
    s.execute("INSERT INTO templates VALUES (?,?,?,?,?,?,?,?,?)",
        (template_id, body.code, body.name, body.category_code, body.body,
         json.dumps(body.required_context, ensure_ascii=False), int(body.active), version + 1, s.now()))
    s.audit(None, "template_created", details={"template_id": template_id, "code": body.code})
    return {"id": template_id, "version": version + 1}



@router.put("/api/templates/{template_id}", dependencies=[Depends(admin)])
def update_template(template_id: str, body: TemplateInput):
    if not s.one("SELECT id FROM templates WHERE id=?", (template_id,)):
        raise HTTPException(404, "Шаблон не найден")
    return create_template(body)
