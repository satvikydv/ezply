import { useEffect, useState } from 'react'
import './App.css'

interface Metrics {
  total_jobs_ingested: number
  total_jobs_scored: number
  total_jobs_applied: number
}

function App() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('http://localhost:8000/api/metrics')
      .then(res => res.json())
      .then(data => {
        setMetrics(data)
        setLoading(false)
      })
      .catch(err => {
        console.error("Failed to fetch metrics", err)
        setLoading(false)
      })
  }, [])

  return (
    <div className="dashboard-container">
      <header className="hero">
        <div className="hero-content">
          <span className="badge">Ezply Agent</span>
          <h1>Job Board Automation</h1>
          <p>Real-time detection and relevance scoring dashboard.</p>
        </div>
      </header>

      <main className="metrics-grid">
        <div className="metric-card">
          <h3>Jobs Ingested</h3>
          <div className="value">
            {loading ? <span className="skeleton" /> : metrics?.total_jobs_ingested ?? 0}
          </div>
        </div>
        <div className="metric-card highlight">
          <h3>Jobs Scored (High Fit)</h3>
          <div className="value">
            {loading ? <span className="skeleton" /> : metrics?.total_jobs_scored ?? 0}
          </div>
        </div>
        <div className="metric-card">
          <h3>Applications Sent</h3>
          <div className="value">
            {loading ? <span className="skeleton" /> : metrics?.total_jobs_applied ?? 0}
          </div>
        </div>
      </main>
      
      <section className="feed">
        <h2>Recent High Fit Jobs</h2>
        <div className="feed-placeholder">
          <p>Connect to the backend API to view the live feed of matching jobs.</p>
        </div>
      </section>
    </div>
  )
}

export default App
