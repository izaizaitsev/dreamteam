from pydantic import BaseModel, ConfigDict


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    header: dict[str, str | None]
    body: str
    closing: str | None
    subject: str = ""
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
