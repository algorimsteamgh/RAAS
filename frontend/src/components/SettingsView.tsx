import { useState } from 'react';

interface SettingsViewProps {
  systemHealth?: any;
  userName: string;
  setUserName: (n: string) => void;
  onClearUploaded: () => void;
  onReloadMock: () => void;
  showToast: (msg: string, type: 'success' | 'info' | 'error') => void;
}

export default function SettingsView({
  userName,
  setUserName,
  onClearUploaded,
  onReloadMock,
  showToast,
}: SettingsViewProps) {
  const [tempUserName, setTempUserName] = useState(userName);

  const handleSaveProfile = () => {
    setUserName(tempUserName);
    showToast('Profile updated successfully!', 'success');
  };

  return (
    <div className="settings-page-container">
      <div className="page-header-block">
        <div>
          <h2 className="view-title">System Settings &amp; Configuration</h2>
          <p className="view-subtitle">Manage recruiter profile credentials and enterprise database storage.</p>
        </div>
      </div>

      <div className="settings-cards-grid">
        {/* Official Brand Identity Banner */}
        <div className="dash-card about-brand-card" style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '20px', padding: '24px', background: '#EFF6FF', border: '1px solid #BFDBFE', borderRadius: '12px' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '14px', background: '#155EEF', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 4px 12px rgba(21, 94, 239, 0.25)' }}>
            <svg width="36" height="36" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M9 7h8.2c3.2 0 5.8 2.2 5.8 5.2s-2.6 5.2-5.8 5.2H13.5v7.6H9V7zm4.5 7.2h3.7c1.4 0 2.5-.9 2.5-2s-1.1-2-2.5-2H13.5v4zm4.2 3.2L23 25h-4.8l-4.6-7.2h4.1z"
                fill="#FFFFFF"
              />
            </svg>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#172554', letterSpacing: '-0.02em', margin: 0 }}>Raashiring</h3>
              <span className="job-status-pill" style={{ fontSize: '11px', padding: '2px 8px', background: '#DBEAFE', color: '#155EEF', borderColor: '#BFDBFE' }}>v3.0.0 Enterprise</span>
            </div>
            <p style={{ fontSize: '13px', color: '#155EEF', fontWeight: 600, margin: '0 0 6px 0' }}>AI-Powered Hiring &amp; Candidate Intelligence</p>
            <p style={{ fontSize: '12.5px', color: '#64748B', margin: 0, maxWidth: '680px', lineHeight: 1.5 }}>
              Enterprise candidate ranking, resume parsing, and ground-truth evaluation running with zero cloud telemetry. Powered by AI inference and high-fidelity deterministic matching.
            </p>
          </div>
        </div>

        {/* User Profile Settings */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box blue">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>
              <h3 className="dash-card-title">User Profile &amp; Recruiter Greeting</h3>
            </div>
          </div>

          <div className="settings-form">
            <div className="form-group">
              <label className="form-label">Recruiter Name</label>
              <input
                type="text"
                className="form-input"
                value={tempUserName}
                onChange={(e) => setTempUserName(e.target.value)}
                placeholder="e.g. Tharun"
              />
              <span className="form-help">Displayed in the personalized top header greeting.</span>
            </div>

            <div className="form-group">
              <label className="form-label">Profile Avatar</label>
              <div className="avatar-preview-row">
                <div className="profile-avatar-lg">KT</div>
                <span className="avatar-meta">Primary Admin · Tharun (KT)</span>
              </div>
            </div>

            <button className="btn-primary" onClick={handleSaveProfile}>
              Save Profile
            </button>
          </div>
        </div>

        {/* Data & Privacy Governance */}
        <div className="dash-card">
          <div className="dash-card-header">
            <div className="card-title-group">
              <div className="header-icon-box red">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <h3 className="dash-card-title">Data Privacy &amp; Enterprise Storage</h3>
            </div>
          </div>

          <p className="settings-section-desc">
            Candidate resumes and extraction records are stored securely with SHA-256 integrity validation.
          </p>

          <div className="danger-actions-row">
            <button className="btn-secondary" onClick={onReloadMock}>
              Reset Candidate Pool (500)
            </button>
            <button className="btn-danger" onClick={onClearUploaded}>
              Delete All Uploaded Resumes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
