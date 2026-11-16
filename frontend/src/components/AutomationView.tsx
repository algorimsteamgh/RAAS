import { useState } from 'react';

interface AutomationViewProps {
  onStartBatch: () => void;
  systemHealth: any;
}

export default function AutomationView({ onStartBatch, systemHealth }: AutomationViewProps) {
  const [autoMatchThreshold, setAutoMatchThreshold] = useState(80);
  const [enableAutoShortlist, setEnableAutoShortlist] = useState(true);
  const [enableDuplicateSkip, setEnableDuplicateSkip] = useState(true);

  return (
    <div className="automation-page-container">
      <div className="page-header-block">
        <div>
          <h2 className="view-title">Automated Candidate Intelligence &amp; Workflows</h2>
          <p className="view-subtitle">
            Configure AI automated screening rules, batch parsing queues, and autonomous scoring thresholds.
          </p>
        </div>
        <button className="btn-primary" onClick={onStartBatch}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>Batch Upload Resumes</span>
        </button>
      </div>

      <div className="automation-grid">
        {/* Pipeline Queue Card */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box blue">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <h3 className="dash-card-title">Active AI Extraction Pipeline</h3>
            </div>
            <span className="badge-tag green">Engine Ready</span>
          </div>

          <div className="pipeline-stats-row">
            <div className="pipeline-stat-box">
              <span className="stat-num">0</span>
              <span className="stat-lbl">Queued</span>
            </div>
            <div className="pipeline-stat-box">
              <span className="stat-num">{systemHealth.ollama_status === 'connected' ? '1' : '0'}</span>
              <span className="stat-lbl">Active Workers</span>
            </div>
            <div className="pipeline-stat-box">
              <span className="stat-num">100%</span>
              <span className="stat-lbl">Parser Uptime</span>
            </div>
          </div>

          <p className="pipeline-desc">
            AI worker is ready for async batch parsing. Resumes are processed without leaving this machine.
          </p>
        </div>

        {/* Screening Rules Card */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box blue">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                </svg>
              </div>
              <h3 className="dash-card-title">Autonomous Screening Triggers</h3>
            </div>
          </div>

          <div className="rule-toggles-list">
            <div className="rule-toggle-row">
              <div className="rule-meta">
                <span className="rule-name">Auto-Shortlist Score Threshold</span>
                <span className="rule-desc">Automatically tag candidates scoring ≥ {autoMatchThreshold} as Shortlisted.</span>
              </div>
              <input
                type="range"
                min="50"
                max="95"
                value={autoMatchThreshold}
                onChange={(e) => setAutoMatchThreshold(Number(e.target.value))}
                className="range-slider"
              />
            </div>

            <div className="rule-toggle-row">
              <div className="rule-meta">
                <span className="rule-name">SHA-256 Duplicate File Prevention</span>
                <span className="rule-desc">Instantly reject byte-identical duplicate CVs before running AI extraction.</span>
              </div>
              <input
                type="checkbox"
                checked={enableDuplicateSkip}
                onChange={(e) => setEnableDuplicateSkip(e.target.checked)}
                className="toggle-checkbox"
              />
            </div>

            <div className="rule-toggle-row">
              <div className="rule-meta">
                <span className="rule-name">Auto-Generate Verification Interview Questions</span>
                <span className="rule-desc">Synthesize evidence-probing technical questions during initial candidate parse.</span>
              </div>
              <input
                type="checkbox"
                checked={enableAutoShortlist}
                onChange={(e) => setEnableAutoShortlist(e.target.checked)}
                className="toggle-checkbox"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
