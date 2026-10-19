export type Role = "ADMIN" | "LAWYER" | "OPERATOR";

export type AppealRow = {
  id: string;
  external_id: string;
  source: string;
  title?: string | null;
  text: string;
  applicant_name?: string | null;
  building_id?: string | null;
  received_at?: string | null;
  due_at?: string | null;
  status: string;
  error?: string | null;
};

export type Classification = {
  legal_required: boolean;
  case_type: string;
  category?: { code: string; name: string };
  reasoning_summary: string;
  recommended_template_code?: string | null;
  required_context: { key: string; reason: string }[];
  warnings: string[];
};

export type SimilarCase = {
  id: string;
  external_id: string;
  appeal_text: string;
  decision_text?: string | null;
  decision_file_uri?: string | null;
  retrieval_score?: number;
};

export type DraftPayload = {
  full_text: string;
  missing_information: string[];
  warnings: string[];
  template_code?: string;
  template_version?: number;
};

export type Draft = {
  id: string;
  status: string;
  edited_text: string;
  document_uri?: string | null;
  ai_payload: DraftPayload | string;
};

export type AppealDetail = AppealRow & {
  classification?: Classification | null;
  context: { key: string; status: string; data: unknown; source: string; warning?: string }[];
  similar_cases: SimilarCase[];
  draft?: Draft | null;
  audit: AuditRow[];
};

export type TemplateRow = {
  id: string;
  code: string;
  name: string;
  category_code?: string | null;
  body: string;
  version: number;
  active: boolean;
};

export type AuditRow = {
  id: string;
  appeal_id?: string | null;
  action: string;
  actor?: string | null;
  details: string;
  created_at: string;
};
