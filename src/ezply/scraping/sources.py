from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ezply.scraping.base import JobRecord, JobSource
from ezply.settings import get_settings


@dataclass(frozen=True)
class GreenhouseJobBoard:
    slug: str
    company_name: str


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


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "Ezply/0.1.0"})
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def __init__(self) -> None:
        settings = get_settings()
        self._boards = [GreenhouseJobBoard(slug=board, company_name=board.replace("-", " ").title()) for board in settings.greenhouse_board_list()]

    async def fetch_jobs(self) -> list[JobRecord]:
        jobs: list[JobRecord] = []

        for board in self._boards:
            jobs.extend(self._fetch_board_jobs(board))

        return jobs

    def _fetch_board_jobs(self, board: GreenhouseJobBoard) -> list[JobRecord]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board.slug}/jobs?content=true"
        try:
            payload = _fetch_json(url)
        except (HTTPError, URLError, json.JSONDecodeError):
            return []

        records: list[JobRecord] = []
        for job in payload.get("jobs", []):
            content = job.get("content", {}) or {}
            location = content.get("location", {}) or {}
            title = _clean_text(job.get("title"))
            job_url = _clean_text(job.get("absolute_url"))
            if not title or not job_url:
                continue

            records.append(
                JobRecord(
                    title=title,
                    company=board.company_name,
                    location=_clean_text(location.get("name")) or None,
                    seniority=self._infer_seniority(title),
                    source=board.slug,
                    source_url=job_url,
                    description=_strip_html(_clean_text(content.get("description"))),
                )
            )

        return records

    def _infer_seniority(self, title: str) -> str | None:
        lowered = title.lower()
        if any(keyword in lowered for keyword in ["intern", "internship", "graduate", "new grad", "fresher", "entry level"]):
            return "entry"
        return None


class LeverSource(JobSource):
    name = "lever"

    async def fetch_jobs(self) -> list[JobRecord]:
        return []


class AshbySource(JobSource):
    name = "ashby"

    async def fetch_jobs(self) -> list[JobRecord]:
        return []


class WorkableSource(JobSource):
    name = "workable"

    async def fetch_jobs(self) -> list[JobRecord]:
        return []


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
