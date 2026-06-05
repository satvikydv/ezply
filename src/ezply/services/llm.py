import json
from dataclasses import dataclass

from openai import OpenAI

from ezply.settings import get_settings


@dataclass(frozen=True)
class FitScoreResult:
    score: float
    summary: str
    reasoning: str
    matched_keywords: list[str]
    missing_keywords: list[str]
    suggestions: list[str]


def _build_client() -> OpenAI | None:
    s = get_settings()
    if not s.llm_api_key:
        return None
    kwargs = {"api_key": s.llm_api_key}
    if s.llm_base_url:
        kwargs["base_url"] = s.llm_base_url
    return OpenAI(**kwargs)


_FIT_SYSTEM_PROMPT = """You are an expert career coach and technical recruiter. Analyze how well the candidate's resume matches the job description.

Return a JSON object with these fields:
- score: float between 0 and 1 (overall fit)
- summary: str (one-line summary of fit)
- reasoning: str (2-3 sentence explanation)
- matched_keywords: list[str] (skills/terms present in both)
- missing_keywords: list[str] (important skills in the job but missing from resume)
- suggestions: list[str] (actionable suggestions to improve fit)

Be honest and critical. A score of 0.7+ means strong match, 0.4-0.7 means moderate, below 0.4 means weak."""


def score_fit(resume_text: str, job_text: str) -> FitScoreResult | None:
    client = _build_client()
    if client is None:
        return None

    try:
        resp = client.chat.completions.create(
            model=get_settings().llm_model,
            messages=[
                {"role": "system", "content": _FIT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"<resume>\n{resume_text}\n</resume>\n\n<job_description>\n{job_text}\n</job_description>",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1000,
        )
        raw = resp.choices[0].message.content
        if not raw:
            return None
        data = json.loads(raw)
        return FitScoreResult(
            score=float(data.get("score", 0)),
            summary=data.get("summary", ""),
            reasoning=data.get("reasoning", ""),
            matched_keywords=data.get("matched_keywords", []),
            missing_keywords=data.get("missing_keywords", []),
            suggestions=data.get("suggestions", []),
        )
    except Exception:
        return None
