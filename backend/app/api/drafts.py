"""Draft review HTTP endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .dependencies import lawyer
from ..services import review

router = APIRouter()


class DraftEdit(BaseModel):
    text: str = Field(min_length=1)
    actor: str = Field(min_length=1)


class Review(BaseModel):
    actor: str = Field(min_length=1)
    text: str | None = None


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
