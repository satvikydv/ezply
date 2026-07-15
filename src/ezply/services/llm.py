import json
from dataclasses import dataclass

from ezply.settings import get_settings


@dataclass(frozen=True)
class FitScoreResult:
    score: float
    summary: str
    reasoning: str
    matched_keywords: list[str]
    missing_keywords: list[str]
    suggestions: list[str]


_FIT_SYSTEM_PROMPT = """You are an expert career coach and technical recruiter. Analyze how well the candidate's resume matches the job description.

Return a JSON object with these fields:
- score: float between 0 and 1 (overall fit)
- summary: str (one-line summary of fit)
- reasoning: str (2-3 sentence explanation)
- matched_keywords: list[str] (skills/terms present in both)
- missing_keywords: list[str] (important skills in the job but missing from resume)
- suggestions: list[str] (actionable suggestions to improve fit)

Be honest and critical. A score of 0.7+ means strong match, 0.4-0.7 means moderate, below 0.4 means weak."""


def _user_message(resume_text: str, job_text: str) -> str:
    return f"<resume>\n{resume_text}\n</resume>\n\n<job_description>\n{job_text}\n</job_description>"


def _parse_response(raw: str | None) -> FitScoreResult | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return FitScoreResult(
            score=float(data.get("score", 0)),
            summary=data.get("summary", ""),
            reasoning=data.get("reasoning", ""),
            matched_keywords=data.get("matched_keywords", []),
            missing_keywords=data.get("missing_keywords", []),
            suggestions=data.get("suggestions", []),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _score_openai(resume_text: str, job_text: str) -> FitScoreResult | None:
    from openai import OpenAI

    s = get_settings()
    if not s.llm_api_key:
        return None
    kwargs = {"api_key": s.llm_api_key}
    if s.llm_base_url:
        kwargs["base_url"] = s.llm_base_url
    try:
        client = OpenAI(**kwargs)
        resp = client.chat.completions.create(
            model=s.llm_model,
            messages=[
                {"role": "system", "content": _FIT_SYSTEM_PROMPT},
                {"role": "user", "content": _user_message(resume_text, job_text)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1000,
        )
        return _parse_response(resp.choices[0].message.content)
    except Exception:
        return None


def _score_gemini(resume_text: str, job_text: str) -> FitScoreResult | None:
    from google import genai

    s = get_settings()
    if not s.llm_api_key:
        return None
    try:
        client = genai.Client(api_key=s.llm_api_key)
        resp = client.models.generate_content(
            model=s.llm_model,
            contents=f"{_FIT_SYSTEM_PROMPT}\n\n{_user_message(resume_text, job_text)}",
            config={"response_mime_type": "application/json", "temperature": 0.3, "max_output_tokens": 1000},
        )
        return _parse_response(resp.text)
    except Exception:
        return None


def score_fit(resume_text: str, job_text: str) -> FitScoreResult | None:
    s = get_settings()
    if not s.llm_api_key:
        return None
    if s.llm_provider == "gemini":
        return _score_gemini(resume_text, job_text)
    return _score_openai(resume_text, job_text)
