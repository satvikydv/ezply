from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class JobRecord:
    title: str
    company: str
    location: str | None
    seniority: str | None
    source: str
    source_url: str
    description: str


class JobSource(ABC):
    name: str

    @abstractmethod
    async def fetch_jobs(self) -> list[JobRecord]:
        raise NotImplementedError
