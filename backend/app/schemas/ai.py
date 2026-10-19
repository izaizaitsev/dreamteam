from pydantic import BaseModel, Field


class RequiredContext(BaseModel):
    key: str
    reason: str = ""
    required: bool = True



class Category(BaseModel):
    code: str = "OTHER"
    name: str = "Другое"



class Classification(BaseModel):
    legal_required: bool
    case_type: str
    category: Category
    confidence: float = Field(ge=0, le=1)
    reasoning_summary: str
    recommended_template_code: str | None = None
    required_context: list[RequiredContext] = []
    warnings: list[str] = []



class Draft(BaseModel):
    subject: str
    issue_summary: str = ""
    factual_section: str = ""
    work_section: str = ""
    legal_section: str = ""
    closing_section: str = ""
    # A stored template assembles the final text from the section fields.
    full_text: str = ""
    used_case_ids: list[str] = []
    used_context_keys: list[str] = []
    missing_information: list[str] = []
    warnings: list[str] = []
    confidence: float = Field(ge=0, le=1)
