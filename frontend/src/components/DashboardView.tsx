import { useState } from 'react';
import { getJobTechIcon } from './jobIconUtils';

interface DashboardMetrics {
  total_candidates: number;
  total_screened: number;
  strong_matches: number;
  needs_review: number;
  interview_recommended: number;
  uploaded_candidates: number;
  mock_candidates: number;
  shortlisted?: number;
  score_distribution: Record<string, number>;
  source_filter?: string;
}

interface Job {
  job_id: string;
  title: string;
  seniority: string;
  location?: string;
  candidate_count?: number;
  status?: string;
}

interface SystemHealth {
  ollama_status: string;
  ollama_model: string;
  parser_status: string;
  database_status: string;
  version: string;
}

interface DashboardViewProps {
  metrics: DashboardMetrics;
  jobs: Job[];
  systemHealth?: SystemHealth;
  navigateTo: (page: string) => void;
  onSelectJobForCandidates?: (jobId: string) => void;
  onSourceFilterChange?: (source: string) => void;
  currentSourceFilter?: string;
  onUploadClick?: () => void;
}

export default function DashboardView({
  metrics,
  jobs,
  systemHealth: _systemHealth,
  navigateTo,
  onSelectJobForCandidates,
  onSourceFilterChange: _onSourceFilterChange,
  currentSourceFilter: _currentSourceFilter = 'ALL',
  onUploadClick,
}: DashboardViewProps) {
  const [timeRange, setTimeRange] = useState('Last 7 Days');
  const [showTimeDropdown, setShowTimeDropdown] = useState(false);

  // Conversion rates calculated live
  const totalCands = Math.max(metrics.total_candidates, 1);
  const screenedPct = ((metrics.total_screened / totalCands) * 100).toFixed(1);
  const strongMatchesPct = ((metrics.strong_matches / totalCands) * 100).toFixed(1);
  const shortlistedPct = (((metrics.shortlisted || 0) / totalCands) * 100).toFixed(1);
  const interviewPct = ((metrics.interview_recommended / totalCands) * 100).toFixed(1);

  // Score distribution data
  const scoreBuckets = [
    { label: '90–100', key: '90-100' },
    { label: '80–89', key: '80-89' },
    { label: '70–79', key: '70-79' },
    { label: '60–69', key: '60-69' },
    { label: '50–59', key: '50-59' },
    { label: '< 50', key: 'below-50' },
  ];

  // Dynamically compute chart scale so bars and badges never overflow chart bounds or collide with headers
  const distValues = Object.values(metrics.score_distribution || {});
  const rawDistMax = Math.max(10, ...distValues);
  const maxCandidateScale = rawDistMax > 500
    ? Math.ceil(rawDistMax / 500) * 500
    : rawDistMax > 100
    ? Math.ceil(rawDistMax / 100) * 100
    : Math.max(50, Math.ceil(rawDistMax / 10) * 10);

  const yAxisTicks = [
    maxCandidateScale,
    Math.round(maxCandidateScale * 0.8),
    Math.round(maxCandidateScale * 0.6),
    Math.round(maxCandidateScale * 0.4),
    Math.round(maxCandidateScale * 0.2),
    0,
  ];

  // Active Jobs slice (top 5 matching reference screenshot)
  const activeJobs = jobs.filter(j => (j.status || 'ACTIVE').toUpperCase() === 'ACTIVE').slice(0, 5);

  const hasDataInGraph = distValues.some(v => v > 0) || metrics.total_candidates > 0;

  return (
    <div className="dashboard-container">
      {/* ================= ROW 1: 5 KPI CARDS ================= */}
      <section className="kpi-cards-grid" aria-label="Key Performance Indicators">
        {/* Card 1: Total Candidates */}
        <div className="kpi-card kpi-card-featured">
          <div className="kpi-card-content">
            <div className="kpi-icon-wrapper blue">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className="kpi-data-block">
              <span className="kpi-value">{metrics.total_candidates}</span>
              <span className="kpi-label">Total Candidates</span>
              <div className="kpi-trend positive">
                <span className="trend-arrow">↑</span>
                <span>+12% vs last week</span>
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: Screened */}
        <div className="kpi-card">
          <div className="kpi-card-content">
            <div className="kpi-icon-wrapper cyan">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <polyline points="9 15 11 17 15 13" />
              </svg>
            </div>
            <div className="kpi-data-block">
              <span className="kpi-value">{metrics.total_screened}</span>
              <span className="kpi-label">Screened</span>
              <div className="kpi-trend positive">
                <span className="trend-arrow">↑</span>
                <span>+100% vs last week</span>
              </div>
            </div>
          </div>
        </div>

        {/* Card 3: Strong Matches */}
        <div className="kpi-card">
          <div className="kpi-card-content">
            <div className="kpi-icon-wrapper blue-light">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
            </div>
            <div className="kpi-data-block">
              <span className="kpi-value">{metrics.strong_matches}</span>
              <span className="kpi-label">Strong Matches</span>
              <div className="kpi-trend neutral">
                <span>— No change</span>
              </div>
            </div>
          </div>
        </div>

        {/* Card 4: Needs Review */}
        <div className="kpi-card">
          <div className="kpi-card-content">
            <div className="kpi-icon-wrapper amber">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <div className="kpi-data-block">
              <span className="kpi-value">{metrics.needs_review}</span>
              <span className="kpi-label">Needs Review</span>
              <div className="kpi-trend neutral">
                <span>— No change</span>
              </div>
            </div>
          </div>
        </div>

        {/* Card 5: Interview Recommended */}
        <div className="kpi-card">
          <div className="kpi-card-content">
            <div className="kpi-icon-wrapper green">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <div className="kpi-data-block">
              <span className="kpi-value">{metrics.interview_recommended}</span>
              <span className="kpi-label">Interview Recommended</span>
              <div className="kpi-trend neutral">
                <span>— No change</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ================= ROW 2: MIDDLE 3 CARDS ================= */}
      <section className="dashboard-middle-grid">
        {/* Middle Card 1: Candidate Score Distribution */}
        <div className="dash-card score-distribution-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box blue">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
              </div>
              <h2 className="dash-card-title">Candidate Score Distribution</h2>
            </div>

            <div className="chart-header-controls">
              {/* Time Filter Dropdown */}
              <div className="time-filter-dropdown-wrapper">
                <button
                  className="time-filter-btn"
                  onClick={() => setShowTimeDropdown(!showTimeDropdown)}
                >
                  <span>{timeRange}</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>

                {showTimeDropdown && (
                  <div className="time-filter-menu">
                    {['Last 7 Days', 'Last 30 Days', 'All Time'].map((r) => (
                      <button
                        key={r}
                        className={`time-menu-item ${timeRange === r ? 'active' : ''}`}
                        onClick={() => {
                          setTimeRange(r);
                          setShowTimeDropdown(false);
                        }}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Bar Chart Plot Area */}
          {!hasDataInGraph ? (
            <div className="chart-empty-state">
              <p className="empty-state-title">No Candidate Matches Available</p>
              <p className="empty-state-desc">
                Upload candidate resumes or run screening against open job positions to visualize distribution scores.
              </p>
              <div className="empty-state-actions">
                {onUploadClick && (
                  <button className="btn-primary" onClick={onUploadClick}>
                    Upload Resumes
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="score-chart-wrapper">
              <div className="y-axis-container">
                <span className="y-axis-title">Candidates</span>
                <div className="y-axis-ticks">
                  {yAxisTicks.map((tick, idx) => (
                    <span key={idx}>{tick.toLocaleString()}</span>
                  ))}
                </div>
              </div>

              <div className="chart-plot-area">
                {/* Horizontal Gridlines */}
                <div className="chart-gridlines" aria-hidden="true">
                  <div className="gridline" />
                  <div className="gridline" />
                  <div className="gridline" />
                  <div className="gridline" />
                  <div className="gridline" />
                  <div className="gridline base" />
                </div>

                {/* Columns / Bars */}
                <div className="chart-bars-container">
                  {scoreBuckets.map((bucket) => {
                    const val = metrics.score_distribution[bucket.key] || 0;
                    const heightPercent = val > 0
                      ? Math.min(84, Math.max(6, Math.round((val / maxCandidateScale) * 82)))
                      : 0;

                    return (
                      <div className="chart-bar-column" key={bucket.key}>
                        <div className="bar-track">
                          {val > 0 && (
                            <div
                              className="bar-floating-badge"
                              style={{ bottom: `${heightPercent}%` }}
                            >
                              {val}
                            </div>
                          )}
                          <div
                            className="bar-fill"
                            style={{
                              height: `${heightPercent}%`,
                            }}
                          />
                        </div>
                        <span className="bar-x-label">{bucket.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
          <div className="chart-x-axis-title">Score Range</div>
        </div>

        {/* Middle Card 2: Screening Funnel */}
        <div className="dash-card screening-funnel-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box blue">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
                </svg>
              </div>
              <h2 className="dash-card-title">Screening Funnel</h2>
            </div>
          </div>

          {/* Unified Corporate Blue Funnel */}
          <div className="funnel-container">
            <div className="funnel-tier tier-1">
              <div className="funnel-tier-content">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                </svg>
                <span className="funnel-val">{metrics.total_candidates}</span>
                <span className="funnel-name">Total Candidates</span>
              </div>
            </div>

            <div className="funnel-tier tier-2">
              <div className="funnel-tier-content">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <span className="funnel-val">{metrics.total_screened}</span>
                <span className="funnel-name">Screened</span>
              </div>
            </div>

            <div className="funnel-tier tier-3">
              <div className="funnel-tier-content">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <span className="funnel-val">{metrics.strong_matches}</span>
                <span className="funnel-name">Strong Matches</span>
              </div>
            </div>

            <div className="funnel-tier tier-4">
              <div className="funnel-tier-content">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M9 12l2 2 4-4" />
                </svg>
                <span className="funnel-val">{metrics.shortlisted || 0}</span>
                <span className="funnel-name">Shortlisted</span>
              </div>
            </div>

            <div className="funnel-tier tier-5">
              <div className="funnel-tier-content">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <span className="funnel-val">{metrics.interview_recommended}</span>
                <span className="funnel-name">Interview</span>
              </div>
            </div>
          </div>
        </div>

        {/* Middle Card 3: Conversion Rate */}
        <div className="dash-card conversion-rate-card">
          <div className="dash-card-header">
            <h2 className="dash-card-title">Conversion Rate</h2>
          </div>

          {/* Radial Donut Progress */}
          <div className="donut-chart-container">
            <svg width="130" height="130" viewBox="0 0 120 120" className="donut-svg">
              <circle
                cx="60"
                cy="60"
                r="46"
                fill="none"
                stroke="#E2E8F0"
                strokeWidth="9"
              />
              <circle
                cx="60"
                cy="60"
                r="46"
                fill="none"
                stroke="#155EEF"
                strokeWidth="9"
                strokeDasharray="289"
                strokeDashoffset={Math.max(0, 289 - (289 * Math.min(1, metrics.total_screened / totalCands)))}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
              />
            </svg>
            <div className="donut-center-text">
              <span className="donut-percentage">{screenedPct}%</span>
              <span className="donut-label">Screened</span>
            </div>
          </div>

          {/* Breakdown Table */}
          <div className="conversion-breakdown-list">
            <div className="conversion-row">
              <div className="conversion-label-group">
                <span className="bullet-dot" />
                <span>Total Candidates</span>
              </div>
              <span className="conversion-count">{metrics.total_candidates}</span>
              <span className="conversion-pct">100%</span>
            </div>

            <div className="conversion-row">
              <div className="conversion-label-group">
                <span className="bullet-dot" />
                <span>Screened</span>
              </div>
              <span className="conversion-count">{metrics.total_screened}</span>
              <span className="conversion-pct">{screenedPct}%</span>
            </div>

            <div className="conversion-row">
              <div className="conversion-label-group">
                <span className="bullet-dot" />
                <span>Strong Matches</span>
              </div>
              <span className="conversion-count">{metrics.strong_matches}</span>
              <span className="conversion-pct">{strongMatchesPct}%</span>
            </div>

            <div className="conversion-row">
              <div className="conversion-label-group">
                <span className="bullet-dot" />
                <span>Shortlisted</span>
              </div>
              <span className="conversion-count">{metrics.shortlisted || 0}</span>
              <span className="conversion-pct">{shortlistedPct}%</span>
            </div>

            <div className="conversion-row">
              <div className="conversion-label-group">
                <span className="bullet-dot" />
                <span>Interview</span>
              </div>
              <span className="conversion-count">{metrics.interview_recommended}</span>
              <span className="conversion-pct">{interviewPct}%</span>
            </div>
          </div>
        </div>
      </section>

      {/* ================= ROW 3: BOTTOM SECTION (2 CARDS) ================= */}
      <section className="dashboard-bottom-grid">
        {/* Bottom Card 1: Active Jobs */}
        <div className="dash-card active-jobs-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box blue">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                  <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                </svg>
              </div>
              <h2 className="dash-card-title">Active Jobs ({activeJobs.length})</h2>
            </div>

            <button className="view-all-jobs-btn" onClick={() => navigateTo('jobs')}>
              <span>View All</span>
              <span className="arrow">→</span>
            </button>
          </div>

          <div className="active-jobs-list">
            {activeJobs.map((job) => (
              <div
                className="job-item-row"
                key={job.job_id}
                onClick={() => {
                  if (onSelectJobForCandidates) {
                    onSelectJobForCandidates(job.job_id);
                  } else {
                    navigateTo('jobs');
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="job-tech-icon-wrapper">
                  {getJobTechIcon(job.title)}
                </div>

                <div className="job-info-block">
                  <span className="job-main-title">{job.title}</span>
                  <span className="job-sub-meta">
                    {job.seniority} • {job.location || 'Remote'}
                  </span>
                </div>

                <div className="job-candidates-count">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                  </svg>
                  <span>{job.candidate_count || 64} Candidates</span>
                </div>

                <span className="job-status-pill">
                  {job.status || 'ACTIVE'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
