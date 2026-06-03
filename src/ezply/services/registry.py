from dataclasses import dataclass

from ezply.scraping.base import JobSource
from ezply.scraping.sources import (
    AshbySource,
    GreenhouseSource,
    InternshalaSource,
    LeverSource,
    WellfoundSource,
    WorkableSearchSource,
    WorkableSource,
)


@dataclass(frozen=True)
class SupportedSource:
    name: str
    display_name: str
    category: str
    source: JobSource


SUPPORTED_SOURCES: list[SupportedSource] = [
    SupportedSource(name="greenhouse", display_name="Greenhouse", category="ats", source=GreenhouseSource()),
    SupportedSource(name="lever", display_name="Lever", category="ats", source=LeverSource()),
    SupportedSource(name="ashby", display_name="Ashby", category="ats", source=AshbySource()),
    SupportedSource(name="workable", display_name="Workable", category="ats", source=WorkableSource()),
    SupportedSource(name="workable-search", display_name="Workable Search (all companies)", category="meta_search", source=WorkableSearchSource()),
    SupportedSource(name="internshala", display_name="Internshala", category="fresher_board", source=InternshalaSource()),
    SupportedSource(name="wellfound", display_name="Wellfound", category="startup_board", source=WellfoundSource()),
]


def get_supported_sources() -> list[SupportedSource]:
    return SUPPORTED_SOURCES


def resolve_source(source_name: str):
    for supported_source in SUPPORTED_SOURCES:
        if supported_source.name == source_name:
            return supported_source.source
    return None
