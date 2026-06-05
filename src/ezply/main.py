import io
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from ezply.db import async_session_factory, init_db
from ezply.models import Job, ResumeProfile
from ezply.schemas import (
    FitScoreRequest,
    FitScoreResponse,
    ImportJobsResponse,
    JobListResponse,
    JobRankRequest,
    JobRankResponse,
    JobResponse,
    RankedJobResponse,
    ResumeProfileRequest,
    ResumeProfileResponse,
    ResumeProfileUpsertResponse,
    AutofillProfileRequest,
    AutofillProfileResponse,
    AutofillExportRequest,
    AutofillExportResponse,
    AssistedApplyRequest,
    AssistedApplyResponse,
    AttemptCreateRequest,
    AttemptRunRequest,
    AttemptResponse,
    AttemptListResponse,
    SourceListResponse,
    SourceResponse,
)
from ezply.services.ingestion import ingest_source
from ezply.services.fitting import FitScorer
from ezply.services.registry import get_supported_sources, resolve_source
from ezply.settings import get_settings
from ezply.services.autofill import save_autofill_profile, load_autofill_profile
from ezply.services.assisted_apply import assisted_apply_greenhouse, PlaywrightNotAvailable
from ezply.services.apply_queue import create_attempt, list_attempts, get_attempt, update_attempt_result
from ezply.services.resume_parser import extract_autofill, parse_pdf

app = FastAPI(title="Ezply", version="0.1.0")
fit_scorer = FitScorer()


def _serialize_resume(resume: ResumeProfile) -> ResumeProfileResponse:
    return ResumeProfileResponse(id=resume.id, display_name=resume.display_name, resume_text=resume.resume_text)


def _serialize_autofill(autofill: "AutofillProfile") -> AutofillProfileResponse:
    return AutofillProfileResponse(id=autofill.id, display_name=autofill.display_name, created_at=autofill.created_at.isoformat())


def _serialize_job(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        seniority=job.seniority,
        source=job.source,
        source_url=job.source_url,
        description=job.description,
        posted_at=job.posted_at.isoformat() if job.posted_at else None,
    )


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "environment": settings.environment}


@app.get("/sources", response_model=SourceListResponse)
def list_sources() -> SourceListResponse:
    return SourceListResponse(
        sources=[
            SourceResponse(name=s.name, display_name=s.display_name, category=s.category)
            for s in get_supported_sources()
        ]
    )


@app.post("/jobs/import/{source_name}", response_model=ImportJobsResponse)
async def import_jobs(source_name: str) -> ImportJobsResponse:
    source = resolve_source(source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Unsupported source: {source_name}")

    return await ingest_source(source)


@app.get("/jobs", response_model=JobListResponse)
async def list_jobs() -> JobListResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(Job).order_by(Job.posted_at.desc().nulls_last(), Job.id.desc()))
        jobs = result.scalars().all()

    return JobListResponse(
        jobs=[_serialize_job(job) for job in jobs]
    )


@app.get("/jobs/search", response_model=JobListResponse)
async def search_jobs(role: str | None = None, location: str | None = None, limit: int = 100) -> JobListResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(Job).order_by(Job.posted_at.desc().nulls_last(), Job.id.desc()).limit(limit))
        jobs = result.scalars().all()

    if not role and not location:
        return JobListResponse(jobs=[_serialize_job(job) for job in jobs])

    role_terms = [t.strip().lower() for t in role.split(",") if t.strip()] if role else []

    def matches(job):
        text = " ".join([job.title or "", job.company or "", job.description or ""]).lower()
        if location and job.location:
            if location.lower() not in (job.location or "").lower():
                return False
        if not role_terms:
            return True
        return any(term in text for term in role_terms)

    filtered = [job for job in jobs if matches(job)]

    return JobListResponse(jobs=[_serialize_job(job) for job in filtered])


@app.get("/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    html = """
        <!doctype html>
        <html>
            <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>Ezply — Dashboard</title>
                <style>
                    :root {
                        --bg: #0b1020;
                        --panel: #111833;
                        --panel-2: #162044;
                        --text: #e8eefc;
                        --muted: #96a3c7;
                        --accent: #74c0fc;
                        --accent-2: #63e6be;
                        --danger: #ff8787;
                        --border: rgba(148, 163, 184, 0.22);
                    }
                    * { box-sizing: border-box; }
                    body {
                        margin: 0;
                        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
                        color: var(--text);
                        background: radial-gradient(circle at top left, #17203f, var(--bg) 40%);
                    }
                    .shell { max-width: 1240px; margin: 0 auto; padding: 24px; }
                    .hero {
                        display: flex; justify-content: space-between; align-items: start; gap: 16px; margin-bottom: 20px;
                        padding: 24px; border: 1px solid var(--border); border-radius: 20px;
                        background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
                        backdrop-filter: blur(10px);
                    }
                    .hero h1 { margin: 0 0 6px; font-size: 30px; }
                    .hero p { margin: 0; color: var(--muted); }
                    .badge { display:inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(116, 192, 252, 0.14); color: var(--accent); font-size: 12px; }
                    nav { display:flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 20px; }
                    nav button, button.primary, button.secondary, button.ghost {
                        border: 1px solid var(--border); border-radius: 12px; color: var(--text);
                        background: var(--panel); padding: 10px 14px; cursor: pointer; transition: transform .12s ease, border-color .12s ease, background .12s ease;
                    }
                    nav button:hover, button.primary:hover, button.secondary:hover, button.ghost:hover { transform: translateY(-1px); border-color: rgba(116,192,252,.5); }
                    button.primary { background: linear-gradient(135deg, #228be6, #0ea5e9); border-color: transparent; }
                    button.secondary { background: var(--panel-2); }
                    button.ghost { background: transparent; }
                    .grid { display: grid; grid-template-columns: 1.35fr .9fr; gap: 16px; align-items: start; }
                    .card {
                        background: rgba(17,24,51,0.95); border: 1px solid var(--border); border-radius: 18px; padding: 18px;
                        box-shadow: 0 20px 60px rgba(0,0,0,.18);
                    }
                    .panel-title { display:flex; align-items:center; justify-content:space-between; gap: 12px; margin-bottom: 14px; }
                    .panel-title h2 { margin: 0; font-size: 18px; }
                    .muted { color: var(--muted); font-size: 13px; }
                    label { display:block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
                    input, textarea, select {
                        width: 100%; border-radius: 12px; border: 1px solid var(--border); background: rgba(10,15,30,.82);
                        color: var(--text); padding: 11px 12px; outline: none;
                    }
                    textarea { min-height: 140px; resize: vertical; }
                    .row { display:grid; grid-template-columns: 1fr 1fr; gap: 10px; }
                    .stack { display:grid; gap: 10px; }
                    .actions { display:flex; flex-wrap: wrap; gap: 8px; align-items:center; margin-top: 10px; }
                    .status {
                        margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: rgba(22,32,68,.8); border: 1px solid var(--border);
                        color: var(--muted); min-height: 20px;
                    }
                    .error { color: var(--danger); }
                    .success { color: var(--accent-2); }
                    .job, .attempt {
                        border: 1px solid var(--border); border-radius: 16px; padding: 14px; margin-top: 12px; background: rgba(255,255,255,.03);
                    }
                    .job h3, .attempt h3 { margin: 0 0 6px; }
                    .meta { color: var(--muted); font-size: 12px; }
                    .tabs > section { display:none; }
                    .tabs > section.active { display:block; }
                    pre { white-space: pre-wrap; word-break: break-word; }
                    @media (max-width: 980px) { .grid { grid-template-columns: 1fr; } .hero { flex-direction: column; } .row { grid-template-columns: 1fr; } }
                </style>
            </head>
            <body>
                <div class="shell">
                    <div class="hero">
                        <div>
                            <span class="badge">Ezply dashboard</span>
                            <h1>Job search, filtering, and assisted apply</h1>
                            <p>Use the backend APIs directly through a functional UI. Save your resume and autofill profile, search matching jobs, enqueue attempts, and run assisted applies.</p>
                        </div>
                        <div class="stack" style="min-width: 260px;">
                            <button class="primary" id="refreshAll" type="button">Refresh Everything</button>
                            <button class="secondary" id="loadAllProfiles" type="button">Load Resume + Autofill</button>
                        </div>
                    </div>

                    <nav>
                        <button class="ghost tab-btn" data-tab="search" type="button">Search</button>
                        <button class="ghost tab-btn" data-tab="resume" type="button">Resume</button>
                        <button class="ghost tab-btn" data-tab="autofill" type="button">Autofill</button>
                        <button class="ghost tab-btn" data-tab="attempts" type="button">Attempts</button>
                        <button class="ghost tab-btn" data-tab="import" type="button">Import</button>
                        <button class="ghost tab-btn" data-tab="fit" type="button">Fit Score</button>
                    </nav>

                    <div class="tabs">
                        <section id="tab-search" class="active">
                            <div class="grid">
                                <div class="card">
                                    <div class="panel-title">
                                        <h2>Search jobs</h2>
                                        <span class="muted">Keyword match against title, company, and description</span>
                                    </div>
                                    <div class="row">
                                        <div>
                                            <label for="role">Role keywords</label>
                                            <input id="role" placeholder="data engineer, frontend, platform" />
                                        </div>
                                        <div>
                                            <label for="location">Location</label>
                                            <input id="location" placeholder="remote, san francisco, india" />
                                        </div>
                                    </div>
                                    <div class="actions">
                                        <button class="primary" id="searchBtn" type="button">Search jobs</button>
                                        <button class="secondary" id="clearResults" type="button">Clear results</button>
                                    </div>
                                    <div class="status" id="searchStatus">Ready.</div>
                                    <div id="results"></div>
                                </div>

                                <div class="card">
                                    <div class="panel-title">
                                        <h2>Quick actions</h2>
                                        <span class="muted">Queue and execute from a job card</span>
                                    </div>
                                    <div class="stack">
                                        <div>
                                            <label for="applyPassphrase">Passphrase for autofill</label>
                                            <input id="applyPassphrase" type="password" placeholder="required for assisted apply" />
                                        </div>
                                        <div>
                                            <label for="confirmSubmit">Submit after fill</label>
                                            <select id="confirmSubmit">
                                                <option value="false">No, just fill and review</option>
                                                <option value="true">Yes, if portal permits</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="status" id="quickStatus">Tip: load your autofill profile first.</div>
                                </div>
                            </div>
                        </section>

                        <section id="tab-resume">
                            <div class="card">
                                <div class="panel-title">
                                    <h2>Resume</h2>
                                    <span class="muted">Saved to backend via /resume</span>
                                </div>
                                <div class="row">
                                    <div>
                                        <label for="resume_name">Display name</label>
                                        <input id="resume_name" placeholder="Primary Resume" />
                                    </div>
                                    <div class="actions" style="align-items:end; justify-content:flex-end;">
                                        <button class="secondary" id="load_resume" type="button">Load</button>
                                        <button class="primary" id="save_resume" type="button">Save resume</button>
                                    </div>
                                </div>
                                <label for="resume_text">Resume text</label>
                                <textarea id="resume_text" placeholder="Paste the resume text used for ranking and tailoring"></textarea>
                                <div class="stack" style="margin-top:10px;">
                                    <div class="row">
                                        <div>
                                            <label for="resume_pdf">Upload PDF to parse</label>
                                            <input id="resume_pdf" type="file" accept=".pdf" />
                                        </div>
                                        <div class="actions" style="align-items:end; justify-content:flex-end;">
                                            <button class="secondary" id="upload_resume_btn" type="button">Parse PDF</button>
                                        </div>
                                    </div>
                                    <div id="extracted_autofill" style="display:none;">
                                        <label>Extracted autofill fields</label>
                                        <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:8px 0;">
                                            <span id="af_name_display" class="badge"></span>
                                            <span id="af_email_display" class="badge"></span>
                                            <span id="af_phone_display" class="badge"></span>
                                            <span id="af_location_display" class="badge"></span>
                                            <span id="af_linkedin_display" class="badge"></span>
                                            <span id="af_github_display" class="badge"></span>
                                        </div>
                                        <div class="actions">
                                            <button class="secondary" id="apply_extracted_autofill" type="button">Use as autofill</button>
                                        </div>
                                    </div>
                                </div>
                                <div class="status" id="resume_status">No resume loaded.</div>
                            </div>
                        </section>

                        <section id="tab-autofill">
                            <div class="card">
                                <div class="panel-title">
                                    <h2>Autofill profile</h2>
                                    <span class="muted">Encrypted with your passphrase</span>
                                </div>
                                <div class="row">
                                    <div>
                                        <label for="af_name">Display name</label>
                                        <input id="af_name" placeholder="Primary Autofill" />
                                    </div>
                                    <div>
                                        <label for="af_pass">Passphrase</label>
                                        <input id="af_pass" type="password" placeholder="required to save/load/export" />
                                    </div>
                                </div>
                                <label for="af_json">Profile JSON</label>
                                <textarea id="af_json" placeholder='{"name":"...","email":"...","phone":"..."}'></textarea>
                                <div class="actions">
                                    <button class="secondary" id="load_autofill" type="button">Load</button>
                                    <button class="secondary" id="export_autofill" type="button">Export / Verify</button>
                                    <button class="primary" id="save_autofill" type="button">Save autofill</button>
                                </div>
                                <div class="status" id="autofill_status">No autofill loaded.</div>
                                <pre id="autofill_export"></pre>
                            </div>
                        </section>

                        <section id="tab-attempts">
                            <div class="card">
                                <div class="panel-title">
                                    <h2>Attempts</h2>
                                    <span class="muted">Queued and executed applications</span>
                                </div>
                                <div class="actions">
                                    <button class="primary" id="refresh_attempts" type="button">Refresh attempts</button>
                                </div>
                                <div class="status" id="attempts_status">Waiting for attempts.</div>
                                <div id="attempts_list"></div>
                            </div>
                        </section>

                        <section id="tab-import">
                            <div class="card">
                                <div class="panel-title">
                                    <h2>Import jobs</h2>
                                    <span class="muted">Pull from configured sources</span>
                                </div>
                                <div class="stack">
                                    <div>
                                        <label for="importSource">Source</label>
                                        <select id="importSource">
                                            <option value="greenhouse">Greenhouse</option>
                                            <option value="lever">Lever</option>
                                            <option value="ashby">Ashby</option>
                                            <option value="workable">Workable</option>
                                            <option value="workable-search">Workable Search (all companies)</option>
                                        </select>
                                    </div>
                                    <div class="actions">
                                        <button class="primary" id="importSourceBtn" type="button">Import source</button>
                                    </div>
                                </div>
                                <div class="status" id="import_status">Import will use the backend source registry.</div>
                            </div>
                        </section>

                        <section id="tab-fit">
                            <div class="card">
                                <div class="panel-title">
                                    <h2>Fit score</h2>
                                    <span class="muted">Compare your resume to any job description</span>
                                </div>
                                <div class="row">
                                    <div>
                                        <label for="fitLimit">Rank jobs limit</label>
                                        <input id="fitLimit" type="number" min="1" max="100" value="25" />
                                    </div>
                                    <div class="actions" style="align-items:end; justify-content:flex-end;">
                                        <button class="secondary" id="rankJobsBtn" type="button">Rank jobs</button>
                                        <button class="primary" id="scoreFitBtn" type="button">Score text</button>
                                    </div>
                                </div>
                                <div class="row">
                                    <div>
                                        <label for="fitResume">Resume text</label>
                                        <textarea id="fitResume" placeholder="Used for scoring and ranking"></textarea>
                                    </div>
                                    <div>
                                        <label for="fitJob">Job text</label>
                                        <textarea id="fitJob" placeholder="Paste a job description"></textarea>
                                    </div>
                                </div>
                                <div class="status" id="fit_status">Use the loaded resume or paste fresh text.</div>
                                <pre id="fit_result"></pre>
                                <div id="ranked_jobs"></div>
                            </div>
                        </section>
                    </div>
                </div>

                <script>
                    const state = {
                        lastSearchJobs: [],
                        selectedJob: null,
                    };

                    function setStatus(id, text, kind = '') {
                        const el = document.getElementById(id);
                        el.textContent = text;
                        el.className = 'status' + (kind ? ' ' + kind : '');
                    }

                    function showTab(name) {
                        document.querySelectorAll('.tabs > section').forEach(section => section.classList.remove('active'));
                        const active = document.getElementById('tab-' + name);
                        if (active) active.classList.add('active');
                    }

                    async function api(path, options = {}) {
                        const res = await fetch(path, {
                            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
                            ...options,
                        });
                        const text = await res.text();
                        let body = null;
                        try { body = text ? JSON.parse(text) : null; } catch (e) { body = { raw: text }; }
                        if (!res.ok) {
                            const detail = body && body.detail ? body.detail : (body && body.raw ? body.raw : res.statusText);
                            throw new Error(detail || 'Request failed');
                        }
                        return body;
                    }

                    function formatDate(d) {
                        if (!d) return '';
                        const date = new Date(d);
                        if (isNaN(date)) return d;
                        const now = new Date();
                        const diff = (now - date) / 1000;
                        if (diff < 86400) return 'Today';
                        if (diff < 172800) return 'Yesterday';
                        if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
                        return date.toLocaleDateString();
                    }

                    function renderJob(job) {
                        const card = document.createElement('div');
                        card.className = 'job';
                        const postedLabel = job.posted_at ? formatDate(job.posted_at) : '';
                        card.innerHTML = `
                            <h3>${job.title}</h3>
                            <div class="meta">${job.company} • ${job.location || 'No location'} • ${job.source}${postedLabel ? ' • ' + postedLabel : ''}</div>
                            <p>${(job.description || '').slice(0, 260).replace(/\\n/g, ' ')}${job.description && job.description.length > 260 ? '…' : ''}</p>
                        `;
                        const actions = document.createElement('div');
                        actions.className = 'actions';

                        const queueBtn = document.createElement('button');
                        queueBtn.type = 'button';
                        queueBtn.className = 'secondary';
                        queueBtn.textContent = 'Enqueue';
                        queueBtn.onclick = async () => {
                            try {
                                setStatus('quickStatus', `Queueing job ${job.id}...`);
                                const passphrase = document.getElementById('applyPassphrase').value || '';
                                await api('/apply/queue', {
                                    method: 'POST',
                                    body: JSON.stringify({ job_id: job.id, passphrase, confirm_submit: false }),
                                });
                                setStatus('quickStatus', `Queued job ${job.id}.`, 'success');
                                await refreshAttempts();
                            } catch (err) {
                                setStatus('quickStatus', err.message, 'error');
                            }
                        };

                        const runBtn = document.createElement('button');
                        runBtn.type = 'button';
                        runBtn.className = 'primary';
                        runBtn.textContent = 'Run assisted apply';
                        runBtn.onclick = async () => {
                            try {
                                setStatus('quickStatus', `Queueing and running job ${job.id}...`);
                                const passphrase = document.getElementById('applyPassphrase').value || '';
                                const confirmSubmit = document.getElementById('confirmSubmit').value === 'true';
                                const queued = await api('/apply/queue', {
                                    method: 'POST',
                                    body: JSON.stringify({ job_id: job.id, passphrase, confirm_submit: confirmSubmit }),
                                });
                                const attempt = await api(`/apply/attempts/${queued.id}/run`, {
                                    method: 'POST',
                                    body: JSON.stringify({ passphrase, confirm_submit: confirmSubmit }),
                                });
                                setStatus('quickStatus', `Attempt ${attempt.id} is ${attempt.status}.`, 'success');
                                await refreshAttempts();
                            } catch (err) {
                                setStatus('quickStatus', err.message, 'error');
                            }
                        };

                        const viewBtn = document.createElement('button');
                        viewBtn.type = 'button';
                        viewBtn.className = 'ghost';
                        viewBtn.textContent = 'Use for fit score';
                        viewBtn.onclick = () => {
                            document.getElementById('fitJob').value = job.description || '';
                            showTab('fit');
                            setStatus('fit_status', `Loaded job ${job.id} into fit scoring.`);
                        };

                        actions.appendChild(queueBtn);
                        actions.appendChild(runBtn);
                        actions.appendChild(viewBtn);
                        card.appendChild(actions);
                        return card;
                    }

                    async function searchJobs() {
                        try {
                            const role = document.getElementById('role').value.trim();
                            const location = document.getElementById('location').value.trim();
                            const params = new URLSearchParams();
                            if (role) params.set('role', role);
                            if (location) params.set('location', location);
                            setStatus('searchStatus', 'Searching jobs...');
                            const data = await api(`/jobs/search?${params.toString()}`);
                            state.lastSearchJobs = data.jobs || [];
                            const results = document.getElementById('results');
                            results.innerHTML = '';
                            if (!state.lastSearchJobs.length) {
                                setStatus('searchStatus', 'No matches found.');
                                return;
                            }
                            state.lastSearchJobs.forEach(job => results.appendChild(renderJob(job)));
                            setStatus('searchStatus', `Found ${state.lastSearchJobs.length} jobs.`, 'success');
                        } catch (err) {
                            setStatus('searchStatus', err.message, 'error');
                        }
                    }

                    async function loadResume() {
                        try {
                            const data = await api('/resume');
                            document.getElementById('resume_name').value = data.display_name || '';
                            document.getElementById('resume_text').value = data.resume_text || '';
                            document.getElementById('fitResume').value = data.resume_text || '';
                            setStatus('resume_status', 'Resume loaded.', 'success');
                        } catch (err) {
                            setStatus('resume_status', err.message, 'error');
                        }
                    }

                    async function saveResume() {
                        try {
                            const payload = {
                                display_name: document.getElementById('resume_name').value.trim() || 'Primary Resume',
                                resume_text: document.getElementById('resume_text').value || '',
                            };
                            await api('/resume', { method: 'PUT', body: JSON.stringify(payload) });
                            document.getElementById('fitResume').value = payload.resume_text;
                            setStatus('resume_status', 'Resume saved.', 'success');
                        } catch (err) {
                            setStatus('resume_status', err.message, 'error');
                        }
                    }

                    async function loadAutofill() {
                        try {
                            const passphrase = document.getElementById('af_pass').value || '';
                            const data = await api('/autofill/export', { method: 'POST', body: JSON.stringify({ passphrase }) });
                            document.getElementById('af_json').value = JSON.stringify(data.profile || {}, null, 2);
                            setStatus('autofill_status', 'Autofill loaded.', 'success');
                        } catch (err) {
                            setStatus('autofill_status', err.message, 'error');
                        }
                    }

                    async function saveAutofill() {
                        try {
                            const passphrase = document.getElementById('af_pass').value || '';
                            if (!passphrase) throw new Error('Enter a passphrase before saving autofill.');
                            const profile = JSON.parse(document.getElementById('af_json').value || '{}');
                            const payload = {
                                display_name: document.getElementById('af_name').value.trim() || 'Primary Autofill',
                                profile,
                                passphrase,
                            };
                            await api('/autofill', { method: 'PUT', body: JSON.stringify(payload) });
                            setStatus('autofill_status', 'Autofill saved.', 'success');
                        } catch (err) {
                            setStatus('autofill_status', err.message, 'error');
                        }
                    }

                    async function exportAutofill() {
                        try {
                            const passphrase = document.getElementById('af_pass').value || '';
                            const data = await api('/autofill/export', { method: 'POST', body: JSON.stringify({ passphrase }) });
                            document.getElementById('autofill_export').textContent = JSON.stringify(data.profile || {}, null, 2);
                            setStatus('autofill_status', 'Autofill exported and verified.', 'success');
                        } catch (err) {
                            setStatus('autofill_status', err.message, 'error');
                        }
                    }

                    async function refreshAttempts() {
                        try {
                            const data = await api('/apply/attempts');
                            const container = document.getElementById('attempts_list');
                            container.innerHTML = '';
                            const attempts = data.attempts || [];
                            if (!attempts.length) {
                                setStatus('attempts_status', 'No attempts yet. Search jobs and enqueue one.', '');
                                return;
                            }
                            attempts.forEach(attempt => {
                                const card = document.createElement('div');
                                card.className = 'attempt';
                                card.innerHTML = `
                                    <h3>Attempt ${attempt.id}</h3>
                                    <div class="meta">Job ${attempt.job_id} • ${attempt.status} • ${attempt.created_at}${attempt.updated_at ? ' • ' + attempt.updated_at : ''}</div>
                                `;
                                if (attempt.result) {
                                    const pre = document.createElement('pre');
                                    pre.textContent = JSON.stringify(attempt.result, null, 2);
                                    card.appendChild(pre);
                                }
                                const actions = document.createElement('div');
                                actions.className = 'actions';
                                const runBtn = document.createElement('button');
                                runBtn.type = 'button';
                                runBtn.className = 'primary';
                                runBtn.textContent = 'Run / retry';
                                runBtn.onclick = async () => {
                                    try {
                                        setStatus('attempts_status', `Running attempt ${attempt.id}...`);
                                        const passphrase = document.getElementById('af_pass').value || document.getElementById('applyPassphrase').value || '';
                                        const confirmSubmit = document.getElementById('confirmSubmit').value === 'true';
                                        const updated = await api(`/apply/attempts/${attempt.id}/run`, {
                                            method: 'POST',
                                            body: JSON.stringify({ passphrase, confirm_submit: confirmSubmit }),
                                        });
                                        setStatus('attempts_status', `Attempt ${updated.id} is ${updated.status}.`, 'success');
                                        await refreshAttempts();
                                    } catch (err) {
                                        setStatus('attempts_status', err.message, 'error');
                                    }
                                };
                                actions.appendChild(runBtn);
                                card.appendChild(actions);
                                container.appendChild(card);
                            });
                            setStatus('attempts_status', `Loaded ${attempts.length} attempts.`, 'success');
                        } catch (err) {
                            setStatus('attempts_status', err.message, 'error');
                        }
                    }

                    async function importSource() {
                        try {
                            const source = document.getElementById('importSource').value || 'greenhouse';
                            setStatus('import_status', `Importing ${source}...`);
                            const data = await api(`/jobs/import/${source}`, { method: 'POST' });
                            setStatus('import_status', `Imported ${data.imported_count} jobs, skipped ${data.skipped_count}.`, 'success');
                            await searchJobs();
                        } catch (err) {
                            setStatus('import_status', err.message, 'error');
                        }
                    }

                    async function scoreFit() {
                        try {
                            const resume_text = document.getElementById('fitResume').value || '';
                            const job_text = document.getElementById('fitJob').value || '';
                            if (!resume_text.trim() || !job_text.trim()) throw new Error('Paste both resume and job text first.');
                            const data = await api('/fit/score', { method: 'POST', body: JSON.stringify({ resume_text, job_text }) });
                            document.getElementById('fit_result').textContent = JSON.stringify(data, null, 2);
                            setStatus('fit_status', `Score: ${Math.round(data.score)}.`, 'success');
                        } catch (err) {
                            setStatus('fit_status', err.message, 'error');
                        }
                    }

                    async function rankJobs() {
                        try {
                            const limit = Number(document.getElementById('fitLimit').value || 25);
                            const resume_text = document.getElementById('fitResume').value || '';
                            const data = await api('/jobs/rank', { method: 'POST', body: JSON.stringify({ resume_text: resume_text.trim() || null, limit }) });
                            const ranked = data.ranked_jobs || [];
                            const container = document.getElementById('ranked_jobs');
                            container.innerHTML = '';
                            ranked.forEach(entry => {
                                const card = document.createElement('div');
                                card.className = 'job';
                                card.innerHTML = `
                                    <h3>${entry.job.title}</h3>
                                    <div class="meta">${entry.job.company} • ${entry.job.location || 'No location'} • score ${entry.fit_score.score.toFixed(1)}</div>
                                    <p>${entry.fit_score.summary}</p>
                                `;
                                const useBtn = document.createElement('button');
                                useBtn.type = 'button';
                                useBtn.className = 'secondary';
                                useBtn.textContent = 'Use in search';
                                useBtn.onclick = () => {
                                    document.getElementById('role').value = entry.job.title;
                                    document.getElementById('location').value = entry.job.location || '';
                                    showTab('search');
                                    setStatus('searchStatus', `Loaded ranked job ${entry.job.id} into search filters.`);
                                };
                                card.appendChild(useBtn);
                                container.appendChild(card);
                            });
                            setStatus('fit_status', `Ranked ${ranked.length} jobs.`, 'success');
                        } catch (err) {
                            setStatus('fit_status', err.message, 'error');
                        }
                    }

                    async function uploadResume() {
                        const fileInput = document.getElementById('resume_pdf');
                        const file = fileInput.files[0];
                        if (!file) { setStatus('resume_status', 'Select a PDF file first.', 'error'); return; }
                        try {
                            setStatus('resume_status', 'Uploading and parsing PDF...');
                            const form = new FormData();
                            form.append('file', file);
                            const res = await fetch('/resume/upload', { method: 'POST', body: form });
                            const body = await res.json();
                            if (!res.ok) throw new Error(body.detail || 'Upload failed');
                            document.getElementById('resume_text').value = body.resume_text;
                            document.getElementById('fitResume').value = body.resume_text;
                            const af = body.autofill || {};
                            const displayEls = {
                                name: 'af_name_display', email: 'af_email_display', phone: 'af_phone_display',
                                location: 'af_location_display', linkedin: 'af_linkedin_display', github: 'af_github_display',
                            };
                            for (const [key, id] of Object.entries(displayEls)) {
                                document.getElementById(id).textContent = af[key] ? `${key}: ${af[key]}` : '';
                            }
                            document.getElementById('extracted_autofill').style.display = 'block';
                            setStatus('resume_status', `Parsed ${body.filename}. Text and autofill extracted.`, 'success');
                        } catch (err) {
                            setStatus('resume_status', err.message, 'error');
                        }
                    }

                    function applyExtractedAutofill() {
                        const afEls = ['name', 'email', 'phone', 'location', 'linkedin', 'github'];
                        const profile = {};
                        for (const key of afEls) {
                            const text = document.getElementById('af_' + key + '_display').textContent;
                            if (text) {
                                const val = text.includes(': ') ? text.split(': ').slice(1).join(': ') : text;
                                if (val.trim()) profile[key] = val.trim();
                            }
                        }
                        if (Object.keys(profile).length) {
                            document.getElementById('af_json').value = JSON.stringify(profile, null, 2);
                            showTab('autofill');
                            setStatus('autofill_status', 'Loaded parsed autofill from resume. Save with a passphrase.', 'success');
                        } else {
                            setStatus('resume_status', 'No autofill fields to apply.', 'error');
                        }
                    }

                    async function refreshEverything() {
                        await Promise.allSettled([searchJobs(), refreshAttempts()]);
                        setStatus('resume_status', 'Click Load to fetch the saved resume.', '');
                        setStatus('autofill_status', 'Click Load to fetch the encrypted autofill profile.', '');
                    }

                    document.addEventListener('DOMContentLoaded', () => {
                        document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => showTab(btn.dataset.tab)));
                        document.getElementById('searchBtn').addEventListener('click', searchJobs);
                        document.getElementById('clearResults').addEventListener('click', () => {
                            document.getElementById('results').innerHTML = '';
                            setStatus('searchStatus', 'Results cleared.');
                        });
                        document.getElementById('save_resume').addEventListener('click', saveResume);
                        document.getElementById('load_resume').addEventListener('click', loadResume);
                        document.getElementById('upload_resume_btn').addEventListener('click', uploadResume);
                        document.getElementById('apply_extracted_autofill').addEventListener('click', applyExtractedAutofill);
                        document.getElementById('save_autofill').addEventListener('click', saveAutofill);
                        document.getElementById('load_autofill').addEventListener('click', loadAutofill);
                        document.getElementById('export_autofill').addEventListener('click', exportAutofill);
                        document.getElementById('refresh_attempts').addEventListener('click', refreshAttempts);
                        document.getElementById('importSourceBtn').addEventListener('click', importSource);
                        document.getElementById('scoreFitBtn').addEventListener('click', scoreFit);
                        document.getElementById('rankJobsBtn').addEventListener('click', rankJobs);
                        document.getElementById('refreshAll').addEventListener('click', refreshEverything);
                        document.getElementById('loadAllProfiles').addEventListener('click', async () => {
                            await Promise.allSettled([loadResume(), loadAutofill()]);
                        });
                        refreshEverything();
                    });
                </script>
            </body>
        </html>
        """
    return HTMLResponse(content=html)


@app.get("/resume", response_model=ResumeProfileResponse)
async def get_resume() -> ResumeProfileResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
        resume = result.scalar_one_or_none()

    if resume is None:
        raise HTTPException(status_code=404, detail="No resume profile saved yet")

    return _serialize_resume(resume)


@app.put("/resume", response_model=ResumeProfileUpsertResponse)
async def upsert_resume(request: ResumeProfileRequest) -> ResumeProfileUpsertResponse:
    async with async_session_factory() as session:
        result = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
        resume = result.scalar_one_or_none()

        if resume is None:
            resume = ResumeProfile(display_name=request.display_name, resume_text=request.resume_text)
            session.add(resume)
        else:
            resume.display_name = request.display_name
            resume.resume_text = request.resume_text

        await session.commit()
        await session.refresh(resume)

    return ResumeProfileUpsertResponse(resume=_serialize_resume(resume))


@app.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        content = await file.read()
        text = parse_pdf(io.BytesIO(content))
        autofill = extract_autofill(text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {str(e)}")

    return {"resume_text": text, "autofill": autofill, "filename": file.filename}


@app.put("/autofill", response_model=AutofillProfileResponse)
async def upsert_autofill(request: AutofillProfileRequest) -> AutofillProfileResponse:
    try:
        autofill = await save_autofill_profile(request.display_name, request.profile, request.passphrase)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _serialize_autofill(autofill)


@app.post("/autofill/export", response_model=AutofillExportResponse)
async def export_autofill(request: AutofillExportRequest) -> AutofillExportResponse:
    try:
        profile = await load_autofill_profile(request.passphrase)
    except ValueError:
        raise HTTPException(status_code=404, detail="No autofill profile saved")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid passphrase or corrupt data")

    return AutofillExportResponse(profile=profile)


@app.post("/fit/score", response_model=FitScoreResponse)
def score_fit(request: FitScoreRequest) -> FitScoreResponse:
    result = fit_scorer.score(request.resume_text, request.job_text)
    return FitScoreResponse(
        score=result.score,
        summary=result.summary,
        matched_keywords=result.matched_keywords,
        missing_keywords=result.missing_keywords,
    )


@app.post("/jobs/rank", response_model=JobRankResponse)
async def rank_jobs(request: JobRankRequest) -> JobRankResponse:
    resume_text = request.resume_text
    if resume_text is None or not resume_text.strip():
        async with async_session_factory() as session:
            result = await session.execute(select(ResumeProfile).order_by(ResumeProfile.id.desc()).limit(1))
            saved_resume = result.scalar_one_or_none()

        if saved_resume is None:
            raise HTTPException(status_code=400, detail="Provide resume_text or save a resume profile first")

        resume_text = saved_resume.resume_text

    async with async_session_factory() as session:
        result = await session.execute(select(Job).order_by(Job.id.desc()).limit(request.limit))
        jobs = result.scalars().all()

    ranked_jobs = []
    for job in jobs:
        result = fit_scorer.score(resume_text, job.description)
        ranked_jobs.append(
            RankedJobResponse(
                job=_serialize_job(job),
                fit_score=FitScoreResponse(
                    score=result.score,
                    summary=result.summary,
                    matched_keywords=result.matched_keywords,
                    missing_keywords=result.missing_keywords,
                ),
            )
        )

    ranked_jobs.sort(key=lambda item: item.fit_score.score, reverse=True)
    return JobRankResponse(ranked_jobs=ranked_jobs)


@app.post("/apply/assist", response_model=AssistedApplyResponse)
async def assist_apply(request: AssistedApplyRequest) -> AssistedApplyResponse:
    async with async_session_factory() as session:
        job = await session.get(Job, request.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    try:
        result = await assisted_apply_greenhouse(job.source_url, request.passphrase, confirm_submit=request.confirm_submit)
    except PlaywrightNotAvailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AssistedApplyResponse(job_id=request.job_id, job_url=job.source_url, filled=result.get("filled", {}), ready_to_submit=result.get("ready_to_submit", False))


@app.post("/apply/queue", response_model=AttemptResponse)
async def enqueue_apply(request: AttemptCreateRequest) -> AttemptResponse:
    async with async_session_factory() as session:
        job = await session.get(Job, request.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    attempt = await create_attempt(request.job_id)
    parsed = None
    if attempt.result:
        try:
            parsed = json.loads(attempt.result)
        except Exception:
            parsed = {"raw": attempt.result}

    return AttemptResponse(
        id=attempt.id,
        job_id=attempt.job_id,
        status=attempt.status,
        created_at=attempt.created_at.isoformat(),
        updated_at=attempt.updated_at.isoformat() if attempt.updated_at else None,
        result=parsed,
    )


@app.get("/apply/attempts", response_model=AttemptListResponse)
async def list_apply_attempts() -> AttemptListResponse:
    attempts = await list_attempts()
    return AttemptListResponse(
        attempts=[
            (lambda a: AttemptResponse(
                id=a.id,
                job_id=a.job_id,
                status=a.status,
                created_at=a.created_at.isoformat(),
                updated_at=a.updated_at.isoformat() if a.updated_at else None,
                result=(lambda r: (json.loads(r) if r else None))(a.result) if a.result else None,
            ))(a)
            for a in attempts
        ]
    )


@app.post("/apply/attempts/{attempt_id}/run", response_model=AttemptResponse)
async def run_attempt(attempt_id: int, request: AttemptRunRequest) -> AttemptResponse:
    attempt = await get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    async with async_session_factory() as session:
        job = await session.get(Job, attempt.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    try:
        # run assisted apply and persist result
        result = await assisted_apply_greenhouse(job.source_url, request.passphrase, confirm_submit=request.confirm_submit)
        result_text = str(result)
        updated = await update_attempt_result(attempt.id, "completed", result_text)
    except PlaywrightNotAvailable as e:
        updated = await update_attempt_result(attempt.id, "error", str(e))
    except Exception as e:
        updated = await update_attempt_result(attempt.id, "failed", str(e))

    parsed = None
    if updated.result:
        try:
            parsed = json.loads(updated.result)
        except Exception:
            parsed = {"raw": updated.result}

    return AttemptResponse(
        id=updated.id,
        job_id=updated.job_id,
        status=updated.status,
        created_at=updated.created_at.isoformat(),
        updated_at=updated.updated_at.isoformat() if updated.updated_at else None,
        result=parsed,
    )
