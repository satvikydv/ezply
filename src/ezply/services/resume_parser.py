import io
import re
from typing import IO

from pdfminer.high_level import extract_text


def parse_pdf(file: IO[bytes]) -> str:
    return extract_text(file)


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{3,4}(?:\s?(?:ext|x)\s?\d+)?",
)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", re.IGNORECASE)
_URL_RE = re.compile(r"(?:https?://)?[\w-]+\.(?:com|org|io|dev|app|ai|co|net)(?:/[\w-]*)?", re.IGNORECASE)


def extract_autofill(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    emails = list(set(_EMAIL_RE.findall(text)))
    phones = list(set(_PHONE_RE.findall(text)))
    phones = [p for p in phones if len(p) >= 7]
    linkedins = list(set(_LINKEDIN_RE.findall(text)))
    githubs = list(set(_GITHUB_RE.findall(text)))

    profile: dict[str, str] = {}

    if emails:
        profile["email"] = emails[0]
    if phones:
        cleaned = re.sub(r"[^\d+]", "", phones[0])
        if len(cleaned) >= 7:
            profile["phone"] = cleaned
    if linkedins:
        profile["linkedin"] = linkedins[0]
    if githubs:
        profile["github"] = githubs[0]

    # Name heuristic: first meaningful line that isn't an email/phone/URL
    for line in lines:
        line = line.strip()
        if not line or len(line) > 60 or len(line) < 3:
            continue
        if _EMAIL_RE.match(line) or _LINKEDIN_RE.match(line) or _URL_RE.match(line):
            continue
        if re.search(r"\d{7,}", line):
            continue
        if line[0].isupper() or all(w[0].isupper() for w in line.split() if w):
            profile["name"] = line
            break

    # Location heuristic: look for patterns like "City, State" or "City, Country"
    location_patterns = [
        re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s[A-Z]{2}(?:\s\d{5})?)"),
        re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)"),
    ]
    for pat in location_patterns:
        match = pat.search(text)
        if match:
            profile["location"] = match.group(1)
            break

    return profile
