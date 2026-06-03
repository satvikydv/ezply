from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ezply.scraping.base import JobRecord, JobSource
from ezply.settings import get_settings


@dataclass(frozen=True)
class CompanyBoard:
    slug: str
    company_name: str


_CONCURRENCY_LIMIT = 10


async def _run_parallel(board_fetches: list[tuple[CompanyBoard, Any]]) -> list[JobRecord]:
    sem = asyncio.Semaphore(_CONCURRENCY_LIMIT)

    async def _fetch_one(board: CompanyBoard, fetch_fn) -> list[JobRecord]:
        async with sem:
            return await asyncio.to_thread(fetch_fn, board)

    results = await asyncio.gather(*[_fetch_one(b, f) for b, f in board_fetches], return_exceptions=True)
    jobs: list[JobRecord] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        jobs.extend(r)
    return jobs


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _strip_html(value: str) -> str:
    if not value:
        return ""
    result: list[str] = []
    in_tag = False
    for character in value:
        if character == "<":
            in_tag = True
            continue
        if character == ">":
            in_tag = False
            continue
        if not in_tag:
            result.append(character)
    return " ".join("".join(result).split())


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "Ezply/0.1.0"})
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _fetch_json_array(url: str) -> list[Any]:
    request = Request(url, headers={"User-Agent": "Ezply/0.1.0"})
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _parse_timestamp_ms(ts: int | None) -> datetime | None:
    if ts is None or ts == 0:
        return None
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)


def _parse_date_str(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────────────
# Greenhouse
# ──────────────────────────────────────────────


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def __init__(self) -> None:
        settings = get_settings()
        self._boards = [CompanyBoard(slug=board, company_name=_slug_to_name(board)) for board in settings.greenhouse_board_list()]

    async def fetch_jobs(self) -> list[JobRecord]:
        return await _run_parallel([(b, self._fetch_board_jobs) for b in self._boards])

    def _fetch_board_jobs(self, board: CompanyBoard) -> list[JobRecord]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board.slug}/jobs?content=true"
        try:
            payload = _fetch_json(url)
        except (HTTPError, URLError, json.JSONDecodeError):
            return []

        records: list[JobRecord] = []
        for job in payload.get("jobs", []):
            title = _clean_text(job.get("title"))
            job_url = _clean_text(job.get("absolute_url"))
            if not title or not job_url:
                continue

            location_obj = job.get("location") or {}
            location_name = _clean_text(location_obj.get("name")) if isinstance(location_obj, dict) else _clean_text(location_obj) or None

            content_raw = job.get("content", "") or ""
            description = _strip_html(_clean_text(content_raw))

            first_published = job.get("first_published")
            posted_at = _parse_date_str(first_published) if first_published else None

            records.append(
                JobRecord(
                    title=title,
                    company=board.company_name,
                    location=location_name,
                    seniority=self._infer_seniority(title),
                    source=board.slug,
                    source_url=job_url,
                    description=description,
                    posted_at=posted_at,
                )
            )
        return records

    def _infer_seniority(self, title: str) -> str | None:
        lowered = title.lower()
        if any(keyword in lowered for keyword in ["intern", "internship", "graduate", "new grad", "fresher", "entry level"]):
            return "entry"
        return None


# ──────────────────────────────────────────────
# Lever  (api.lever.co/v0/postings/{slug}?mode=json)
# ──────────────────────────────────────────────


class LeverSource(JobSource):
    name = "lever"

    def __init__(self) -> None:
        settings = get_settings()
        self._boards = [CompanyBoard(slug=board, company_name=_slug_to_name(board)) for board in settings.lever_board_list()]

    async def fetch_jobs(self) -> list[JobRecord]:
        return await _run_parallel([(b, self._fetch_board_jobs) for b in self._boards])

    def _fetch_board_jobs(self, board: CompanyBoard) -> list[JobRecord]:
        url = f"https://api.lever.co/v0/postings/{board.slug}?mode=json"
        try:
            payload = _fetch_json_array(url)
        except (HTTPError, URLError, json.JSONDecodeError):
            return []

        records: list[JobRecord] = []
        for job in payload:
            title = _clean_text(job.get("text"))
            if not title:
                continue
            categories = job.get("categories", {}) or {}
            location = _clean_text(categories.get("location")) or None
            apply_url = _clean_text(job.get("applyUrl")) or ""
            hosted_url = _clean_text(job.get("hostedUrl")) or ""
            source_url = apply_url or hosted_url
            if not source_url:
                continue
            desc_plain = _clean_text(job.get("descriptionPlain", ""))
            desc_body = _strip_html(_clean_text(job.get("descriptionBody", "")))
            description = desc_plain or desc_body

            created_ms = job.get("createdAt")
            posted_at = _parse_timestamp_ms(created_ms) if isinstance(created_ms, (int, float)) else None

            records.append(
                JobRecord(
                    title=title,
                    company=board.company_name,
                    location=location,
                    seniority=self._infer_seniority(title),
                    source=board.slug,
                    source_url=source_url,
                    description=description,
                    posted_at=posted_at,
                )
            )
        return records

    def _infer_seniority(self, title: str) -> str | None:
        lowered = title.lower()
        if any(keyword in lowered for keyword in ["intern", "internship", "graduate", "new grad", "fresher", "entry level"]):
            return "entry"
        if any(keyword in lowered for keyword in ["senior", "sr", "staff", "lead", "principal", "head", "director", "chief", "vp", "vice president", "manager"]):
            return "senior"
        return None


# ──────────────────────────────────────────────
# Ashby  (api.ashbyhq.com/posting-api/job-board/{slug})
# ──────────────────────────────────────────────


class AshbySource(JobSource):
    name = "ashby"

    def __init__(self) -> None:
        settings = get_settings()
        self._boards = [CompanyBoard(slug=board, company_name=_slug_to_name(board)) for board in settings.ashby_board_list()]

    async def fetch_jobs(self) -> list[JobRecord]:
        return await _run_parallel([(b, self._fetch_board_jobs) for b in self._boards])

    def _fetch_board_jobs(self, board: CompanyBoard) -> list[JobRecord]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board.slug}?includeCompensation=false"
        try:
            payload = _fetch_json(url)
        except (HTTPError, URLError, json.JSONDecodeError):
            return []

        records: list[JobRecord] = []
        for job in payload.get("jobs", []):
            if not job.get("isListed", True):
                continue
            title = _clean_text(job.get("title"))
            if not title:
                continue
            location = _clean_text(job.get("location")) or None
            apply_url = _clean_text(job.get("applyUrl")) or ""
            job_url = _clean_text(job.get("jobUrl")) or ""
            source_url = apply_url or job_url
            if not source_url:
                continue
            desc = _clean_text(job.get("descriptionPlain", "")) or _strip_html(_clean_text(job.get("descriptionHtml", "")))

            published = job.get("publishedDate")
            posted_at = _parse_date_str(published) if published else None

            records.append(
                JobRecord(
                    title=title,
                    company=board.company_name,
                    location=location,
                    seniority=self._infer_seniority(title),
                    source=board.slug,
                    source_url=source_url,
                    description=desc,
                    posted_at=posted_at,
                )
            )
        return records

    def _infer_seniority(self, title: str) -> str | None:
        lowered = title.lower()
        if any(keyword in lowered for keyword in ["intern", "internship", "graduate", "new grad", "fresher", "entry level"]):
            return "entry"
        if any(keyword in lowered for keyword in ["senior", "sr", "staff", "lead", "principal", "head", "director", "chief", "vp", "vice president", "manager"]):
            return "senior"
        return None


# ──────────────────────────────────────────────
# Workable  — cross-customer meta search
# Queries run against 170k+ live postings across ALL Workable customers
# ──────────────────────────────────────────────


class WorkableSource(JobSource):
    name = "workable"

    def __init__(self, query: str = "software engineer", max_pages: int = 5):
        self.query = query
        self.max_pages = max_pages

    async def fetch_jobs(self) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        seen_urls: set[str] = set()
        next_token: str | None = None

        for _ in range(self.max_pages):
            url = f"https://jobs.workable.com/api/v1/jobs?query={quote(self.query)}&limit=20"
            if next_token:
                url += f"&nextPageToken={quote(next_token)}"
            try:
                payload = _fetch_json(url)
            except (HTTPError, URLError, json.JSONDecodeError):
                break

            for job in payload.get("jobs", []):
                title = _clean_text(job.get("title"))
                company_obj = job.get("company", {}) or {}
                company_name = _clean_text(company_obj.get("title", "")) if isinstance(company_obj, dict) else _clean_text(str(company_obj))
                if not title or not company_name:
                    continue
                source_url = _clean_text(job.get("url") or "")
                if not source_url or source_url in seen_urls:
                    continue
                seen_urls.add(source_url)

                loc_obj = job.get("location") or {}
                location = None
                if isinstance(loc_obj, dict):
                    parts = [loc_obj.get("city", ""), loc_obj.get("subregion", ""), loc_obj.get("countryName", "")]
                    location = ", ".join(p for p in parts if p) or None
                if not location:
                    locs = job.get("locations") or []
                    location = _clean_text(locs[0]) if locs else None

                job_id = _clean_text(job.get("id", ""))
                apply_url = f"https://jobs.workable.com/view/{job_id}" if job_id else source_url

                desc = _strip_html(_clean_text(job.get("description", "")))
                created = job.get("created")
                posted_at = _parse_date_str(created) if created else None
                department = _clean_text(job.get("department", ""))
                company_label = f"{company_name} [{department}]" if department else company_name

                jobs.append(
                    JobRecord(
                        title=title,
                        company=company_label,
                        location=location,
                        seniority=self._infer_seniority(title),
                        source="workable",
                        source_url=apply_url,
                        description=desc,
                        posted_at=posted_at,
                    )
                )

            next_token = payload.get("nextPageToken")
            if not next_token:
                break

        return jobs

    def _infer_seniority(self, title: str) -> str | None:
        lowered = title.lower()
        if any(keyword in lowered for keyword in ["intern", "internship", "graduate", "new grad", "fresher", "entry level"]):
            return "entry"
        if any(keyword in lowered for keyword in ["senior", "sr", "staff", "lead", "principal", "head", "director", "chief", "vp", "vice president", "manager"]):
            return "senior"
        return None


# ──────────────────────────────────────────────
# Workable Search  — query-based meta search (alternative queries)
# ──────────────────────────────────────────────


class WorkableSearchSource(JobSource):
    name = "workable-search"

    def __init__(self, queries: list[str] | None = None, max_pages_per_query: int = 2):
        self.queries = queries or [
            "software engineer", "frontend", "backend", "data",
            "product manager", "devops", "designer", "full stack",
        ]
        self.max_pages_per_query = max_pages_per_query

    async def _fetch_query(self, query: str, seen_urls: set[str]) -> list[JobRecord]:
        records: list[JobRecord] = []
        next_token: str | None = None
        for _ in range(self.max_pages_per_query):
            url = f"https://jobs.workable.com/api/v1/jobs?query={quote(query)}&limit=20"
            if next_token:
                url += f"&nextPageToken={quote(next_token)}"
            try:
                payload = await asyncio.to_thread(_fetch_json, url)
            except (HTTPError, URLError, json.JSONDecodeError):
                break

            for job in payload.get("jobs", []):
                title = _clean_text(job.get("title"))
                company_obj = job.get("company", {}) or {}
                company_name = _clean_text(company_obj.get("title", "")) if isinstance(company_obj, dict) else _clean_text(str(company_obj))
                if not title or not company_name:
                    continue
                source_url = _clean_text(job.get("url") or "")
                if not source_url or source_url in seen_urls:
                    continue
                seen_urls.add(source_url)

                loc_obj = job.get("location") or {}
                location = None
                if isinstance(loc_obj, dict):
                    parts = [loc_obj.get("city", ""), loc_obj.get("subregion", ""), loc_obj.get("countryName", "")]
                    location = ", ".join(p for p in parts if p) or None
                if not location:
                    locs = job.get("locations") or []
                    location = _clean_text(locs[0]) if locs else None

                job_id = _clean_text(job.get("id", ""))
                apply_url = f"https://jobs.workable.com/view/{job_id}" if job_id else source_url
                desc = _strip_html(_clean_text(job.get("description", "")))
                created = job.get("created")
                posted_at = _parse_date_str(created) if created else None
                department = _clean_text(job.get("department", ""))
                company_label = f"{company_name} [{department}]" if department else company_name

                records.append(
                    JobRecord(
                        title=title,
                        company=company_label,
                        location=location,
                        seniority=self._infer_seniority(title),
                        source="workable-search",
                        source_url=apply_url,
                        description=desc,
                        posted_at=posted_at,
                    )
                )

            next_token = payload.get("nextPageToken")
            if not next_token:
                break
        return records

    async def fetch_jobs(self) -> list[JobRecord]:
        seen_urls: set[str] = set()
        sem = asyncio.Semaphore(5)

        async def _run(q: str) -> list[JobRecord]:
            async with sem:
                return await self._fetch_query(q, seen_urls)

        results = await asyncio.gather(*[_run(q) for q in self.queries], return_exceptions=True)
        all_jobs: list[JobRecord] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            all_jobs.extend(r)
        return all_jobs

    def _infer_seniority(self, title: str) -> str | None:
        lowered = title.lower()
        if any(keyword in lowered for keyword in ["intern", "internship", "graduate", "new grad", "fresher", "entry level"]):
            return "entry"
        if any(keyword in lowered for keyword in ["senior", "sr", "staff", "lead", "principal", "head", "director", "chief", "vp", "vice president", "manager"]):
            return "senior"
        return None


# ──────────────────────────────────────────────
# Internshala, Wellfound, LinkedIn (stubs)
# ──────────────────────────────────────────────


class InternshalaSource(JobSource):
    name = "internshala"

    async def fetch_jobs(self) -> list[JobRecord]:
        return []


class WellfoundSource(JobSource):
    name = "wellfound"

    async def fetch_jobs(self) -> list[JobRecord]:
        return []


class LinkedInSource(JobSource):
    name = "linkedin"

    async def fetch_jobs(self) -> list[JobRecord]:
        return []
