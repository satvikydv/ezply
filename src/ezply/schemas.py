from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    environment: str


class SourceResponse(BaseModel):
    name: str
    display_name: str
    category: str


class SourceListResponse(BaseModel):
    sources: list[SourceResponse]


class ImportJobsResponse(BaseModel):
    source_name: str
    imported_count: int
    skipped_count: int


class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    location: str | None
    seniority: str | None
    source: str
    source_url: str
    description: str
    posted_at: str | None = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class FitScoreRequest(BaseModel):
    resume_text: str
    job_text: str
    mode: str = "auto"  # "auto", "keyword", or "llm"


class FitScoreResponse(BaseModel):
    score: float
    summary: str
    matched_keywords: list[str]
    missing_keywords: list[str]
    reasoning: str = ""
    suggestions: list[str] = []
    scoring_mode: str = "keyword"


class JobRankRequest(BaseModel):
    resume_text: str | None = None
    limit: int = 25


class RankedJobResponse(BaseModel):
    job: JobResponse
    fit_score: FitScoreResponse


class JobRankResponse(BaseModel):
    ranked_jobs: list[RankedJobResponse]


class ResumeProfileRequest(BaseModel):
    display_name: str = "Primary Resume"
    resume_text: str


class ResumeProfileResponse(BaseModel):
    id: int
    display_name: str
    resume_text: str


class ResumeProfileUpsertResponse(BaseModel):
    resume: ResumeProfileResponse


class AutofillProfileRequest(BaseModel):
    display_name: str = "Primary Autofill"
    profile: dict
    passphrase: str


class AutofillProfileResponse(BaseModel):
    id: int
    display_name: str
    created_at: str


class AutofillExportRequest(BaseModel):
    passphrase: str


class AutofillExportResponse(BaseModel):
    profile: dict


class AssistedApplyRequest(BaseModel):
    job_id: int
    passphrase: str
    confirm_submit: bool = False


class AssistedApplyResponse(BaseModel):
    job_id: int
    job_url: str
    filled: dict
    ready_to_submit: bool


class AttemptCreateRequest(BaseModel):
    job_id: int
    passphrase: str
    confirm_submit: bool = False


class AttemptRunRequest(BaseModel):
    passphrase: str = ""
    confirm_submit: bool = False


class AttemptResponse(BaseModel):
    id: int
    job_id: int
    status: str
    created_at: str
    updated_at: str | None = None
    result: dict | None = None


class AttemptListResponse(BaseModel):
    attempts: list[AttemptResponse]


class PipelineRunRequest(BaseModel):
    source_names: list[str] | None = None
    import_first: bool = False
    threshold: float = 0.4
    max_jobs: int = 50
    apply: bool = False
    passphrase: str = ""


class PipelineJobResult(BaseModel):
    job_id: int
    title: str
    company: str
    score: float
    scoring_mode: str
    summary: str
    attempt_id: int | None = None
    applied: bool = False
    apply_status: str | None = None


class PipelineStepResult(BaseModel):
    step: str
    status: str
    detail: str


class PipelineRunResponse(BaseModel):
    status: str
    total_jobs_scored: int
    jobs_above_threshold: int
    attempts_queued: int
    attempts_applied: int
    threshold: float
    steps: list[PipelineStepResult]
    results: list[PipelineJobResult]
