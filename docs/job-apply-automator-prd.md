# PRD: Job Apply Automator v1

## Summary
Build a job application copilot that saves time by finding relevant jobs from multiple reliable sources, tailoring application materials, and autofilling common portal fields while keeping the user in control of final submission.

The v1 should reduce application time from roughly 15-25 minutes to 3-5 minutes for a relevant role.

## Problem
Job hunting has three repetitive steps that consume most of the time:
1. Finding relevant roles across multiple job boards.
2. Adapting a resume and cover letter to each JD.
3. Re-entering the same personal details on every portal.

Users often waste time on low-fit jobs or on repetitive submission work instead of focusing on interviews and high-signal applications.

## Goals
- Surface relevant jobs from a small number of job sources.
- Rank jobs by fit against a saved resume and user preferences.
- Generate a tailored resume version for each JD.
- Autofill common application fields and personal details.
- Keep the user in the loop before submission.
- Make the workflow fast enough that applying to good matches feels lightweight.

## Non-Goals for v1
- Fully autonomous mass applying.
- Bypassing CAPTCHA, anti-bot protections, or portal security controls.
- Supporting every job board and every ATS from day one.
- Writing deceptive screening answers or fabricating qualifications.
- Managing the entire job search lifecycle, including interview scheduling or offer negotiation.

## Primary User
- A job seeker applying to multiple roles per week who wants to save time without losing control over what gets submitted.

## User Needs
- I want to find jobs that match my background.
- I want each application to feel tailored without rewriting everything manually.
- I want my repetitive personal information filled in automatically.
- I want to review what will be submitted before anything is sent.
- I want a simple history of jobs I applied to and what version was used.

## Core Workflow
1. User uploads a resume and sets preferences.
2. System imports jobs from selected sources.
3. System scores and filters jobs by relevance.
4. User opens a job card and reviews the match.
5. System generates tailored resume content and optional cover letter draft.
6. System pre-fills portal fields from stored profile data.
7. User reviews, edits, and submits manually or via assisted apply where supported.
8. System stores application status and generated artifacts.

## v1 Scope
### Job Discovery
- Pull jobs from a limited set of reliable sources.
- Use multiple source types from day one, not a single board.
- Prefer ATS-backed company career pages and fresher-friendly sources with stable structure.
- Store job title, company, location, seniority, description, source URL, and date found.
- Deduplicate repeated listings.
- Allow manual keyword and location filters.

### Fit Scoring
- Compare job descriptions with the uploaded resume.
- Produce a simple relevance score and short explanation.
- Flag strong matches, weak matches, and missing skill signals.

### Resume Tailoring
- Generate a role-specific resume variant from the original resume.
- Emphasize relevant experience, keywords, and accomplishments.
- Keep a human-review step before export.

### Profile Autofill
- Store basic personal details once.
- Autofill common fields such as name, email, phone, location, work authorization, education, links, and salary expectations if provided.
- Allow user overrides per application.

### Application Tracking
- Track saved jobs, drafted applications, submitted applications, and skipped jobs.
- Preserve generated resume version and notes for each application.

## Source Strategy
Start with a small set of sources that balance signal quality and scrape reliability.

### Primary Sources
- Company career pages backed by ATS platforms such as Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Teamtailor, Breezy, and Recruitee.
- Internship and graduate-program portals.
- LinkedIn Jobs for assisted ingestion and manual review.

### Secondary Sources
- Fresher-focused boards relevant to the target region.
- Startup job boards such as Wellfound.
- Broad aggregators such as Indeed and Glassdoor when they add coverage without too much noise.

### Source Selection Rules
- Prefer sources with stable page structure and low duplication.
- Prefer sources that are current, recruiter-controlled, and close to the employer.
- Prefer sources that produce higher conversion for freshers over raw volume.
- Expand source coverage only after the initial pipeline is reliable.

## v1 Out of Scope
- Direct integration with every ATS.
- Browser automation for all portals.
- Multi-account support.
- Team or recruiter workflows.
- Analytics beyond basic application history and status.

## Product Principles
- Human in control: no submission without review.
- Relevance over volume: optimize for fit, not spam.
- Portable data: resume, profile, and application history should be easy to export.
- Safe automation: stay within reasonable platform and compliance boundaries.

## Success Metrics
- Median time from job opening to ready-to-submit application is under 5 minutes.
- At least 70 percent of surfaced jobs are marked relevant or worth reviewing.
- At least 50 percent of started applications reach a review-ready state.
- Users complete more applications per week with less manual effort.
- Users report the tailored materials are better than generic copy.

## Risks and Constraints
- Job boards and ATS portals vary widely, so coverage will be inconsistent.
- Scraping may be limited by terms of service, rate limits, or anti-bot controls.
- Tailoring can drift into inaccurate claims if not constrained.
- Autofill can fail when portal field names are inconsistent.
- Over-automation can reduce trust if users cannot easily inspect or edit content.

## Guardrails
- Never invent experience, degrees, certifications, or employment dates.
- Always show the user the final generated resume text before export or submission.
- Prefer officially available feeds, APIs, or permitted extraction methods.
- Respect site rules and rate limits.
- Require explicit user confirmation before any application is submitted.

## Architecture Confirmation Policy
Any decision that materially affects data sources, scraping method, resume-tailoring behavior, sensitive data storage, or submission automation must be confirmed with the user before implementation.

Examples of decisions that require confirmation:
- Which sources are included in the initial scrape set.
- Whether browser automation is allowed for any portal.
- Whether personal data is stored locally or remotely.
- Whether tailoring may rewrite bullets or only re-rank existing content.
- Whether to support cover letters in v1.

## MVP Deliverables
- Resume upload and profile setup.
- Job ingestion from 2-3 sources.
- Relevance scoring and filters.
- Tailored resume draft export.
- Autofill-ready personal profile.
- Application queue with status tracking.

## Post-v1 Upgrade Ideas
- Direct browser-assisted apply for common portals.
- Support for more job boards and ATS patterns.
- Better ranking using outcome feedback from user behavior.
- Cover letter generation.
- Interview prep based on job descriptions.
- Auto-fill question suggestions based on prior answers.

## Open Questions
- Which job sources should v1 support first?
- Should the initial output be resume-only or resume plus cover letter?
- What level of browser automation is acceptable for the first release?
- Should tailoring be limited to keyword alignment, or also rewrite bullet points?
- How should the product handle sensitive data storage and export?

## Suggested Build Order
1. Resume and profile ingestion.
2. Job import and deduplication.
3. Fit scoring and shortlist UI.
4. Tailored resume generation.
5. Profile autofill and export.
6. Application tracking.
7. Portal automation experiments for the highest-value targets.
