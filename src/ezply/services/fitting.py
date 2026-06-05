from dataclasses import dataclass
import re

from ezply.services.llm import score_fit as llm_score_fit

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True)
class FitResult:
    score: float
    summary: str
    matched_keywords: list[str]
    missing_keywords: list[str]
    reasoning: str = ""
    suggestions: list[str] = ()
    scoring_mode: str = "keyword"


class FitScorer:
    def score(self, resume_text: str, job_text: str, mode: str = "auto") -> FitResult:
        if not resume_text.strip() or not job_text.strip():
            return FitResult(score=0.0, summary="Missing resume or job text", matched_keywords=[], missing_keywords=[])

        fallback = self._keyword_score(resume_text, job_text)

        if mode == "keyword":
            return fallback

        if mode == "llm" or mode == "auto":
            llm_result = llm_score_fit(resume_text, job_text)
            if llm_result is not None:
                return FitResult(
                    score=llm_result.score,
                    summary=llm_result.summary,
                    matched_keywords=llm_result.matched_keywords,
                    missing_keywords=llm_result.missing_keywords,
                    reasoning=llm_result.reasoning,
                    suggestions=list(llm_result.suggestions),
                    scoring_mode="llm",
                )

        return fallback

    def _keyword_score(self, resume_text: str, job_text: str) -> FitResult:
        resume_keywords = self._extract_keywords(resume_text)
        job_keywords = self._extract_keywords(job_text)
        matched_keywords = sorted(resume_keywords & job_keywords)
        missing_keywords = sorted(job_keywords - resume_keywords)

        if not job_keywords:
            return FitResult(score=0.0, summary="No meaningful keywords found in job text", matched_keywords=[], missing_keywords=[])

        overlap_ratio = len(matched_keywords) / len(job_keywords)
        score = round(min(1.0, overlap_ratio), 2)

        if score >= 0.65:
            summary = "Strong keyword match"
        elif score >= 0.35:
            summary = "Moderate keyword match"
        else:
            summary = "Weak keyword match"

        return FitResult(score=score, summary=summary, matched_keywords=matched_keywords, missing_keywords=missing_keywords)

    def _extract_keywords(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())
        return {token for token in tokens if len(token) > 2 and token not in STOPWORDS}
