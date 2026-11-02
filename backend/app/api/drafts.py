"""Draft review HTTP endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .dependencies import auth, lawyer, ai_failure
from ..services import draft_chat, review

router = APIRouter()


class DraftEdit(BaseModel):
    text: str = Field(min_length=1)
    actor: str = Field(min_length=1)


class Review(BaseModel):
    actor: str = Field(min_length=1)
    text: str | None = None


class ChatInput(BaseModel):
    instruction: str = Field(min_length=1, max_length=8000)
    text: str = Field(min_length=1, max_length=100000)
    base_text: str = Field(max_length=100000)


@router.post("/api/drafts/{draft_id}/chat", dependencies=[Depends(lawyer)])
async def chat(draft_id: str, body: ChatInput, role: str = Depends(auth)):
    try:
        return await draft_chat.refine(draft_id, body.instruction, body.text, body.base_text, role)
    except review.ReviewError as exc:
        translate(exc)
    except Exception as exc:
        ai_failure(exc)


def translate(exc: review.ReviewError):
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.put("/api/drafts/{draft_id}", dependencies=[Depends(lawyer)])
def edit_draft(draft_id: str, body: DraftEdit):
    try:
        return review.edit_draft(draft_id, body.text, body.actor)
    except review.ReviewError as exc:
        translate(exc)


@router.post("/api/drafts/{draft_id}/approve", dependencies=[Depends(lawyer)])
def approve(draft_id: str, body: Review):
    try:
        return review.review_draft(draft_id, body.actor, body.text, "APPROVED")
    except review.ReviewError as exc:
        translate(exc)


@router.post("/api/drafts/{draft_id}/reject", dependencies=[Depends(lawyer)])
def reject(draft_id: str, body: Review):
    try:
        return review.review_draft(draft_id, body.actor, body.text, "REJECTED")
    except review.ReviewError as exc:
        translate(exc)


@router.get("/api/drafts/{draft_id}/export-docx", dependencies=[Depends(lawyer)])
def export_docx(draft_id: str):
    try:
        path = review.export_docx(draft_id)
    except review.ReviewError as exc:
        translate(exc)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename=f"response-{draft_id}.docx")
