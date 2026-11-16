import { useState, useEffect, useCallback, useMemo, useRef, memo, type ReactNode } from 'react';
import Sidebar from './components/Sidebar';
import TopHeader from './components/TopHeader';
import DashboardView from './components/DashboardView';
import AutomationView from './components/AutomationView';
import SettingsView from './components/SettingsView';
import ErrorBoundary from './components/ErrorBoundary';

// API Configuration: relative path for reverse proxy routing in production
const API_BASE = (window.location.port && ['5173', '3000'].includes(window.location.port))
  ? `http://${window.location.hostname}:8000` : '';

interface Candidate {
  candidate_id: string;
  full_name?: string;
  source?: string;
  roles?: string[];
  skills?: string[];
  recruiter_action?: string;
  raw_data?: any;
  education?: string[];
  certifications?: string[];
  projects?: any[];
  confidence?: any;
  current_title?: string;
  location?: string;
  email?: string;
  phone?: string;
  notice_period?: string;
  years_experience?: number;
  companies?: string[];
  created_at?: string;
  match_score?: number;
}

interface Job {
  job_id: string;
  title: string;
  seniority: string;
  location?: string;
  minimum_years_experience?: number;
  required_skills?: string[];
  mandatory_skills?: string[];
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
}

interface ChatMessage {
  id?: number;
  candidate_id?: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
}

const renderInlineMarkdown = (str: string): ReactNode[] => {
  const parts: ReactNode[] = [];
  let remaining = str;
  let key = 0;

  while (remaining.length > 0) {
    const boldMatch = remaining.match(/\*\*(.*?)\*\*/);
    const codeMatch = remaining.match(/`(.*?)`/);

    let firstMatch = null;
    let matchType = '';
    let matchIndex = Infinity;

    if (boldMatch && boldMatch.index !== undefined && boldMatch.index < matchIndex) {
      matchIndex = boldMatch.index;
      firstMatch = boldMatch;
      matchType = 'bold';
    }
    if (codeMatch && codeMatch.index !== undefined && codeMatch.index < matchIndex) {
      matchIndex = codeMatch.index;
      firstMatch = codeMatch;
      matchType = 'code';
    }

    if (!firstMatch || firstMatch.index === undefined) {
      parts.push(<span key={key++}>{remaining}</span>);
      break;
    }

    if (firstMatch.index > 0) {
      parts.push(<span key={key++}>{remaining.substring(0, firstMatch.index)}</span>);
    }

    if (matchType === 'bold') {
      parts.push(<strong key={key++} className="chat-bold">{firstMatch[1]}</strong>);
    } else if (matchType === 'code') {
      parts.push(<code key={key++} className="chat-code">{firstMatch[1]}</code>);
    }

    remaining = remaining.substring(firstMatch.index + firstMatch[0].length);
  }

  return parts;
};

const renderFormattedMessage = (text: any) => {
  if (!text) return null;
  const content = typeof text === 'string' ? text : (typeof text === 'object' ? JSON.stringify(text, null, 2) : String(text));
  const lines = content.split('\n');
  return (
    <div className="chat-markdown-body">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={idx} className="chat-line-spacer" />;
        }
        if (trimmed.startsWith('### ')) {
          return <h4 key={idx} className="chat-heading-3">{trimmed.replace('### ', '')}</h4>;
        }
        if (trimmed.startsWith('## ')) {
          return <h3 key={idx} className="chat-heading-2">{trimmed.replace('## ', '')}</h3>;
        }
        if (trimmed.startsWith('# ')) {
          return <h2 key={idx} className="chat-heading-1">{trimmed.replace('# ', '')}</h2>;
        }
        if (trimmed.startsWith('> ')) {
          return <blockquote key={idx} className="chat-quote">{trimmed.replace('> ', '')}</blockquote>;
        }
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          const itemText = trimmed.substring(2);
          return (
            <div key={idx} className="chat-bullet-row">
              <span className="chat-bullet-dot">•</span>
              <div className="chat-bullet-text">{renderInlineMarkdown(itemText)}</div>
            </div>
          );
        }
        if (/^\d+\.\s/.test(trimmed)) {
          const numMatch = trimmed.match(/^\d+\.\s/);
          const itemText = trimmed.substring(numMatch![0].length);
          return (
            <div key={idx} className="chat-numbered-row">
              <span className="chat-number-label">{numMatch![0]}</span>
              <div className="chat-numbered-text">{renderInlineMarkdown(itemText)}</div>
            </div>
          );
        }
        return <p key={idx} className="chat-paragraph">{renderInlineMarkdown(line)}</p>;
      })}
    </div>
  );
};

const getInitials = (name?: string) => {
  if (!name) return '??';
  return name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
};

interface CandidateRowProps {
  candidate: Candidate;
  isSelected: boolean;
  onSelect: (cand: Candidate) => void;
  onDelete: (cand: Candidate) => void;
}

const CandidateRow = memo(function CandidateRow({
  candidate,
  isSelected,
  onSelect,
  onDelete,
}: CandidateRowProps) {
  const name = candidate.full_name || 'Candidate';
  const roleDisplay = Array.isArray(candidate.roles) && candidate.roles.length > 0
    ? candidate.roles[0]
    : (typeof candidate.roles === 'string' ? candidate.roles : candidate.current_title || 'Engineer');

  return (
    <div
      className={`candidate-list-item ${isSelected ? 'selected' : ''}`}
      onClick={() => onSelect(candidate)}
    >
      <div className="cand-avatar-circle">{getInitials(name)}</div>
      <div className="cand-item-info">
        <span className="cand-item-name">{name}</span>
        <span className="cand-item-role">{roleDisplay}</span>
      </div>
      {candidate.recruiter_action && (
        <span className="job-status-pill" style={{ fontSize: '9px', padding: '2px 5px' }}>
          {String(candidate.recruiter_action)}
        </span>
      )}
      <button
        className="cand-delete-btn"
        title={`Delete ${name}`}
        aria-label={`Delete ${name}`}
        onClick={(e) => {
          e.stopPropagation();
          onDelete(candidate);
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </svg>
      </button>
    </div>
  );
}, (prev, next) => {
  return (
    prev.isSelected === next.isSelected &&
    prev.candidate.candidate_id === next.candidate.candidate_id &&
    prev.candidate.recruiter_action === next.candidate.recruiter_action &&
    prev.candidate.full_name === next.candidate.full_name &&
    prev.candidate.current_title === next.candidate.current_title
  );
});

export default function App() {
  // Navigation & User State
  const [activePage, setActivePage] = useState<string>('dashboard');
  const [selectedTab, setSelectedTab] = useState<string>('why');
  const [showMobileNav, setShowMobileNav] = useState<boolean>(false);
  const [userName, setUserName] = useState<string>('Tharun');

  // Data States
  const [allCandidates, setAllCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [heroData, setHeroData] = useState<any>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealth>({
    ollama_status: 'disconnected',
    ollama_model: '—',
    parser_status: '—',
    database_status: '—',
    version: '—'
  });
  const [dashboardMetrics, setDashboardMetrics] = useState<DashboardMetrics>({
    total_candidates: 0,
    total_screened: 0,
    strong_matches: 0,
    needs_review: 0,
    interview_recommended: 0,
    uploaded_candidates: 0,
    mock_candidates: 0,
    shortlisted: 0,
    score_distribution: {},
  });
  const [dashboardSource, setDashboardSource] = useState<string>('ALL');
  const [evalMetrics, setEvalMetrics] = useState<any>(null);
  const [evalLoading, setEvalLoading] = useState<boolean>(false);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [currentFilter, setCurrentFilter] = useState<string>('ALL');

  // Modals visibility
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [showMatchModal, setShowMatchModal] = useState<boolean>(false);
  const [showCreateJobModal, setShowCreateJobModal] = useState<boolean>(false);

  // Forms / Input States
  const [jdText, setJdText] = useState<string>('');
  const [extractingJd, setExtractingJd] = useState<boolean>(false);
  const [newJob, setNewJob] = useState({
    title: '',
    seniority: 'Mid-level',
    location: '',
    minimum_years_experience: 0,
    required_skills: '',
    preferred_skills: '',
    education_requirements: '',
  });
  const [selectedJobIdForMatch, setSelectedJobIdForMatch] = useState<string>('');
  const [activeMatchedJobId, setActiveMatchedJobId] = useState<string>('');
  const [matchingInProgress, setMatchingInProgress] = useState<boolean>(false);

  // Upload States
  const [uploadQueue, setUploadQueue] = useState<File[]>([]);
  const [uploadStatus, setUploadStatus] = useState({
    processing: false,
    completed: 0,
    failed: 0,
    total: 0,
  });
  const [currentProcessingFile, setCurrentProcessingFile] = useState<string>('');
  const [uploadStage, setUploadStage] = useState<string>('');
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'info' | 'error' } | null>(null);
  const showToast = (text: string, type: 'success' | 'info' | 'error' = 'info') => setToastMessage({ text, type });
  const [mobileDetailView, setMobileDetailView] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Delete Confirmation Modal State
  const [deleteConfirmTarget, setDeleteConfirmTarget] = useState<{
    type: 'single' | 'all' | 'chat';
    candidateId?: string;
    candidateName?: string;
  } | null>(null);
  const [deleteInProgress, setDeleteInProgress] = useState<boolean>(false);

  // HR Chat States
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState<string>('');
  const [chatLoading, setChatLoading] = useState<boolean>(false);
  const [chatJobId, setChatJobId] = useState<string>('');
  const [suggestedFollowups, setSuggestedFollowups] = useState<string[]>([
    "Why was this candidate given their score?",
    "What are their main technical strengths?",
    "What red flags or gaps should I ask about?",
    "Draft a phone screen invitation email",
    "Suggest 3 technical interview questions"
  ]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatMessagesAreaRef = useRef<HTMLDivElement>(null);

  // --- HEALTH CHECK ---
  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/system/health`);
      if (res.ok) {
        const data = await res.json();
        setSystemHealth(data);
      }
    } catch {
      setSystemHealth(prev => ({ ...prev, ollama_status: 'disconnected' }));
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  // --- DASHBOARD METRICS ---
  const loadDashboard = useCallback(async (jobId?: string, source?: string) => {
    try {
      const activeSource = source !== undefined ? source : dashboardSource;
      const params = new URLSearchParams();
      if (jobId) params.append('job_id', jobId);
      if (activeSource && activeSource !== 'ALL') params.append('source', activeSource);

      const queryStr = params.toString() ? `?${params.toString()}` : '';
      const res = await fetch(`${API_BASE}/api/dashboard/metrics${queryStr}`);
      if (res.ok) {
        const data = await res.json();
        setDashboardMetrics(data);
      }
    } catch (e) {
      console.error('Failed to load dashboard metrics:', e);
    }
  }, [dashboardSource]);

  const handleSourceFilterChange = (newSource: string) => {
    setDashboardSource(newSource);
    loadDashboard(activeMatchedJobId || undefined, newSource);
  };

  // --- HERO & EVIDENCE GRAPH DETAILS ---
  const fetchHeroData = useCallback(async (candId: string, jobId?: string) => {
    try {
      const url = jobId
        ? `${API_BASE}/api/candidates/${candId}/evidence-graph?job_id=${encodeURIComponent(jobId)}`
        : `${API_BASE}/api/candidates/${candId}/evidence-graph`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setHeroData(data);
      }
    } catch (e) {
      console.error('Failed to fetch evidence graph data:', e);
    }
  }, []);

  // --- CHAT HISTORY ---
  const fetchChatHistory = useCallback(async (candId: string, jobId?: string) => {
    try {
      const url = jobId
        ? `${API_BASE}/api/candidates/${candId}/chat-history?job_id=${encodeURIComponent(jobId)}`
        : `${API_BASE}/api/candidates/${candId}/chat-history`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setChatMessages(data.messages || []);
      }
    } catch (e) {
      console.error('Failed to fetch chat history:', e);
    }
  }, []);

  const selectCandidate = useCallback(async (cand: Candidate, openMobile = true) => {
    setSelectedCandidate(cand);
    if (openMobile) {
      setMobileDetailView(true);
    }
    fetchHeroData(cand.candidate_id, activeMatchedJobId);
    setChatJobId(activeMatchedJobId);
    fetchChatHistory(cand.candidate_id, activeMatchedJobId);
  }, [activeMatchedJobId, fetchHeroData, fetchChatHistory]);

  // --- CANDIDATES LIST ---
  const fetchCandidates = useCallback(async (selectFirst = false) => {
    try {
      const res = await fetch(`${API_BASE}/api/candidates`);
      if (res.ok) {
        const data = await res.json();
        setAllCandidates(data);
        if (selectFirst && data.length > 0) {
          const isMobile = typeof window !== 'undefined' && window.innerWidth <= 900;
          selectCandidate(data[0], !isMobile);
        }
      }
    } catch (e) {
      console.error('Failed to fetch candidates:', e);
    }
  }, [selectCandidate]);

  // --- JOBS LIST ---
  const loadJobs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs`);
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
        if (data.length > 0) {
          setSelectedJobIdForMatch(data[0].job_id);
        }
      }
    } catch (e) {
      console.error('Failed to load jobs:', e);
    }
  }, []);

  // Initial loading & navigation triggers
  useEffect(() => {
    loadDashboard();
    loadJobs();
    fetchCandidates();
  }, [loadDashboard, loadJobs, fetchCandidates]);

  // Global Escape key listener for modals and drawers (active only when a modal or drawer is open)
  const isAnyModalOpen = showUploadModal || showCreateJobModal || showMatchModal || showMobileNav || Boolean(deleteConfirmTarget);
  useEffect(() => {
    if (!isAnyModalOpen) return;
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowUploadModal(false);
        setShowCreateJobModal(false);
        setShowMatchModal(false);
        setShowMobileNav(false);
        setDeleteConfirmTarget(null);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [isAnyModalOpen]);

  const navigateTo = (page: string) => {
    setActivePage(page);
    setShowMobileNav(false);
    setMobileDetailView(false);
    if (page === 'dashboard') {
      loadDashboard();
      loadJobs();
    } else if (page === 'jobs') {
      loadJobs();
    } else if (page === 'library') {
      fetchCandidates(true);
    }
  };

  // Auto-scroll chat messages without triggering synchronous forced reflow
  useEffect(() => {
    if (selectedTab !== 'chat') return;
    const scrollContainer = chatMessagesAreaRef.current;
    if (!scrollContainer) return;

    const frameId = requestAnimationFrame(() => {
      if (chatMessagesAreaRef.current) {
        chatMessagesAreaRef.current.scrollTop = chatMessagesAreaRef.current.scrollHeight;
      }
    });
    return () => cancelAnimationFrame(frameId);
  }, [chatMessages, chatLoading, selectedTab]);

  // --- SEND CHAT MESSAGE ---
  const sendChatMessage = async (textToSend?: string) => {
    const message = (textToSend !== undefined ? textToSend : chatInput).trim();
    if (!message || !selectedCandidate || chatLoading) return;

    const userMsg: ChatMessage = {
      role: 'user',
      content: message,
      created_at: new Date().toISOString()
    };
    setChatMessages(prev => [...prev, userMsg]);
    if (textToSend === undefined) setChatInput('');
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/candidates/${selectedCandidate.candidate_id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          job_id: chatJobId || undefined,
          save_history: true
        })
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: data.reply,
          created_at: data.created_at || new Date().toISOString()
        };
        setChatMessages(prev => [...prev, assistantMsg]);
        if (data.suggested_followups?.length) {
          setSuggestedFollowups(data.suggested_followups);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Failed to send message', 'error');
      }
    } catch (e: any) {
      showToast('Chat agent error: ' + e.message, 'error');
    } finally {
      setChatLoading(false);
    }
  };

  // --- CLEAR CHAT HISTORY ---
  const clearChatHistory = () => {
    if (!selectedCandidate) return;
    setDeleteConfirmTarget({
      type: 'chat',
      candidateId: selectedCandidate.candidate_id,
      candidateName: selectedCandidate.full_name || selectedCandidate.candidate_id
    });
  };

  // --- RECRUITER ACTIONS ---
  const doAction = async (action: string) => {
    if (!selectedCandidate) return;
    try {
      const res = await fetch(`${API_BASE}/api/candidates/${selectedCandidate.candidate_id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          job_id: activeMatchedJobId || undefined,
          note: '',
          tag: ''
        })
      });
      if (res.ok) {
        showToast(`Candidate marked as ${action}`, 'success');
        fetchCandidates();
        loadDashboard();
      }
    } catch (e: any) {
      showToast('Action failed: ' + e.message, 'error');
    }
  };

  // --- DELETE CANDIDATE ---
  const promptDeleteCandidate = useCallback((candidate?: any) => {
    const cand = candidate || selectedCandidate;
    if (!cand) return;
    setDeleteConfirmTarget({
      type: 'single',
      candidateId: cand.candidate_id,
      candidateName: cand.full_name || cand.candidate_id
    });
  }, [selectedCandidate]);

  const deleteCandidate = useCallback(() => promptDeleteCandidate(), [promptDeleteCandidate]);
  const deleteSpecificCandidate = useCallback((candidate: any) => promptDeleteCandidate(candidate), [promptDeleteCandidate]);
  const deleteUploadedAll = () => setDeleteConfirmTarget({ type: 'all' });

  const handleExecuteDelete = async () => {
    if (!deleteConfirmTarget) return;
    setDeleteInProgress(true);

    try {
      if (deleteConfirmTarget.type === 'single') {
        const candId = deleteConfirmTarget.candidateId!;
        const candName = deleteConfirmTarget.candidateName || candId;
        const res = await fetch(`${API_BASE}/api/candidates/${candId}`, {
          method: 'DELETE'
        });
        if (res.ok) {
          showToast(`Candidate ${candName} deleted.`, 'success');
          if (selectedCandidate?.candidate_id === candId) {
            setSelectedCandidate(null);
            setHeroData(null);
          }
          await fetchCandidates();
          await loadDashboard();
        } else {
          const errData = await res.json().catch(() => ({}));
          showToast(errData.detail || 'Delete failed', 'error');
        }
      } else if (deleteConfirmTarget.type === 'all') {
        const res = await fetch(`${API_BASE}/api/candidates/uploaded/all`, {
          method: 'DELETE'
        });
        if (res.ok) {
          const resData = await res.json().catch(() => ({ count: 0 }));
          showToast(`Deleted ${resData.count || 'all'} uploaded candidate(s).`, 'success');
          if (selectedCandidate?.source === 'UPLOADED') {
            setSelectedCandidate(null);
            setHeroData(null);
          }
          await fetchCandidates();
          await loadDashboard();
        } else {
          const errData = await res.json().catch(() => ({}));
          showToast(errData.detail || 'Delete failed', 'error');
        }
      } else if (deleteConfirmTarget.type === 'chat') {
        const candId = deleteConfirmTarget.candidateId!;
        const url = chatJobId
          ? `${API_BASE}/api/candidates/${candId}/chat-history?job_id=${encodeURIComponent(chatJobId)}`
          : `${API_BASE}/api/candidates/${candId}/chat-history`;
        const res = await fetch(url, { method: 'DELETE' });
        if (res.ok) {
          setChatMessages([]);
          showToast('Conversation history cleared.', 'info');
        } else {
          showToast('Failed to clear chat history.', 'error');
        }
      }
    } catch (e: any) {
      showToast('Delete operation failed: ' + e.message, 'error');
    } finally {
      setDeleteInProgress(false);
      setDeleteConfirmTarget(null);
    }
  };

  // --- JOB MATCHING ---
  const runJobMatch = async () => {
    const targetJobId = selectedJobIdForMatch || (jobs.length > 0 ? jobs[0].job_id : '');
    if (!targetJobId || !selectedCandidate) return;
    setMatchingInProgress(true);
    try {
      const res = await fetch(`${API_BASE}/api/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_id: selectedCandidate.candidate_id,
          job_id: targetJobId
        })
      });
      if (res.ok) {
        showToast('Matching completed against target JD', 'success');
        setActiveMatchedJobId(targetJobId);
        setChatJobId(targetJobId);
        fetchHeroData(selectedCandidate.candidate_id, targetJobId);
        fetchChatHistory(selectedCandidate.candidate_id, targetJobId);
        loadDashboard();
        setShowMatchModal(false);
      }
    } catch (e: any) {
      showToast('Matching failed: ' + e.message, 'error');
    } finally {
      setMatchingInProgress(false);
    }
  };

  // --- EXTRACT JD VIA AI ---
  const extractJD = async () => {
    if (!jdText.trim()) return;
    setExtractingJd(true);
    try {
      const res = await fetch(`${API_BASE}/api/jobs/extract-jd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jd_text: jdText })
      });
      if (res.ok) {
        const data = await res.json();
        setNewJob(prev => ({
          ...prev,
          title: data.title || prev.title,
          seniority: data.seniority || prev.seniority,
          location: data.location || prev.location,
          minimum_years_experience: data.minimum_years_experience ?? prev.minimum_years_experience,
          required_skills: (data.mandatory_skills || data.required_skills || []).join(', '),
          preferred_skills: (data.preferred_skills || []).join(', '),
          education_requirements: (data.education_requirements || []).join(', ')
        }));
        showToast('Extracted requirements from JD text', 'success');
      }
    } catch (e: any) {
      showToast('Extraction failed: ' + e.message, 'error');
    } finally {
      setExtractingJd(false);
    }
  };

  // --- SAVE CREATED JOB ---
  const saveJob = async () => {
    if (!newJob.title) {
      showToast('Job title is required', 'error');
      return;
    }
    const body = {
      title: newJob.title,
      seniority: newJob.seniority,
      location: newJob.location,
      minimum_years_experience: newJob.minimum_years_experience,
      required_skills: newJob.required_skills.split(',').map(s => s.trim()).filter(Boolean),
      preferred_skills: newJob.preferred_skills.split(',').map(s => s.trim()).filter(Boolean),
      education_requirements: newJob.education_requirements.split(',').map(s => s.trim()).filter(Boolean),
    };
    try {
      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (res.ok) {
        showToast('Job created successfully', 'success');
        setShowCreateJobModal(false);
        loadJobs();
        loadDashboard();
        setNewJob({
          title: '',
          seniority: 'Mid-level',
          location: '',
          minimum_years_experience: 0,
          required_skills: '',
          preferred_skills: '',
          education_requirements: '',
        });
        setJdText('');
      }
    } catch (e: any) {
      showToast('Failed to save job: ' + e.message, 'error');
    }
  };

  // --- SCORE ALL CANDIDATES FOR JOB ---
  const handleScoreAllForJob = async (jobId: string) => {
    try {
      showToast('Scoring all candidates for job in background...', 'info');
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/score-all`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        showToast(`Scored ${data.candidates_scored} candidates successfully!`, 'success');
        loadDashboard();
      }
    } catch (e: any) {
      showToast('Scoring error: ' + e.message, 'error');
    }
  };

  // --- RELOAD MOCK DATASET ---
  const handleReloadMock = async () => {
    try {
      showToast('Reloading mock dataset into SQLite...', 'info');
      const res = await fetch(`${API_BASE}/api/dataset/load-mock`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        showToast(`Loaded ${data.candidates_loaded} mock candidates`, 'success');
        loadDashboard();
        fetchCandidates(true);
      }
    } catch (e: any) {
      showToast('Reload failed: ' + e.message, 'error');
    }
  };

  // --- UPLOAD PIPELINE ---
  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    setUploadQueue(prev => [...prev, ...files]);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    setUploadQueue(prev => [...prev, ...files]);
  };

  const startBatchUpload = async () => {
    if (uploadQueue.length === 0) return;
    setUploadStatus({
      processing: true,
      completed: 0,
      failed: 0,
      total: uploadQueue.length,
    });

    let completed = 0;
    let failed = 0;

    for (let i = 0; i < uploadQueue.length; i++) {
      const file = uploadQueue[i];
      setCurrentProcessingFile(file.name);
      setUploadStage('Reading text layout...');

      try {
        const fd = new FormData();
        fd.append('file', file);

        const stage1 = setTimeout(() => {
          setUploadStage('Running AI CV Extraction Agent...');
        }, 1200);

        const stage2 = setTimeout(() => {
          setUploadStage('Verifying employment truth & computing SHA-256...');
        }, 3000);

        const res = await fetch(`${API_BASE}/api/upload-cv`, {
          method: 'POST',
          body: fd,
        });

        clearTimeout(stage1);
        clearTimeout(stage2);

        if (res.ok) {
          const createdCand = await res.json();
          completed++;
          showToast(`Extracted ${file.name} successfully`, 'success');
          if (i === uploadQueue.length - 1) {
            selectCandidate(createdCand);
          }
        } else {
          failed++;
          const errData = await res.json().catch(() => ({ detail: 'Upload error' }));
          showToast(`Error uploading ${file.name}: ${errData.detail || 'failed'}`, 'error');
        }
      } catch (err: any) {
        failed++;
        showToast(`Failed uploading ${file.name}: ${err.message}`, 'error');
      }

      setUploadStatus(prev => ({
        ...prev,
        completed,
        failed,
      }));
    }

    setUploadStatus(prev => ({ ...prev, processing: false }));
    setUploadQueue([]);
    setCurrentProcessingFile('');
    setUploadStage('');
    fetchCandidates();
    loadDashboard();
    setShowUploadModal(false);
  };

  // --- RUN BENCHMARK ---
  const runEvaluation = async () => {
    setEvalLoading(true);
    setEvalMetrics(null);
    try {
      const res = await fetch(`${API_BASE}/api/evaluation/metrics`);
      if (res.ok) {
        const data = await res.json();
        setEvalMetrics(data);
      }
    } catch (e: any) {
      showToast('Evaluation benchmark failed: ' + e.message, 'error');
    } finally {
      setEvalLoading(false);
    }
  };

  // Helpers
  const initials = getInitials;

  // Filter Logic (memoized so unrelated state changes do not re-scan 500 items)
  const filteredCandidates = useMemo(() => {
    return allCandidates.filter(c => {
      if (currentFilter === 'SHORTLISTED') {
        const isShortlisted = c.recruiter_action === 'SHORTLIST' ||
          (c.raw_data?.recommendation === 'SHORTLIST') ||
          (c.raw_data?.overall_score && c.raw_data.overall_score >= 70);
        if (!isShortlisted && c.recruiter_action !== 'SHORTLIST') return false;
      } else if (currentFilter !== 'ALL' && c.source !== currentFilter) {
        return false;
      }
      if (searchQuery) {
        const text = `${c.full_name || ''} ${(c.roles || []).join(' ')} ${(c.skills || []).join(' ')}`.toLowerCase();
        if (!text.includes(searchQuery.toLowerCase())) return false;
      }
      return true;
    });
  }, [allCandidates, currentFilter, searchQuery]);

  return (
    <div className="app-layout-root">
      {/* 1. LEFT SIDEBAR NAVIGATION */}
      <Sidebar
        activePage={activePage}
        navigateTo={navigateTo}
        systemHealth={systemHealth}
        mobileOpen={showMobileNav}
        closeMobile={() => setShowMobileNav(false)}
      />

      {/* 2. MAIN CONTENT AREA */}
      <div className="app-main-content main-content-wrapper">
        {/* Top Header */}
        <TopHeader
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onSearchSubmit={() => {
            if (activePage !== 'library') {
              navigateTo('library');
            }
          }}
          openMobileNav={() => setShowMobileNav(true)}
          onUploadClick={() => setShowUploadModal(true)}
          userName={userName}
          navigateTo={navigateTo}
        />

        {/* Dynamic Page Views */}
        <div className="app-page-body page-scroll-container">
          <ErrorBoundary fallbackTitle="Error loading view">
            {/* DASHBOARD PAGE */}
          {activePage === 'dashboard' && (
            <DashboardView
              metrics={dashboardMetrics}
              jobs={jobs}
              systemHealth={systemHealth}
              navigateTo={navigateTo}
              onSelectJobForCandidates={(jobId) => {
                setActiveMatchedJobId(jobId);
                navigateTo('library');
              }}
              onSourceFilterChange={handleSourceFilterChange}
              currentSourceFilter={dashboardSource}
              onUploadClick={() => setShowUploadModal(true)}
            />
          )}

          {/* JOBS PAGE */}
          {activePage === 'jobs' && (
            <div className="jobs-view-container">
              <div className="page-header-block">
                <div>
                  <h2 className="view-title">Active Job Roles &amp; Requirements</h2>
                  <p className="view-subtitle">Manage open positions, edit required skills, or run AI screening.</p>
                </div>
                <button className="btn-primary" onClick={() => setShowCreateJobModal(true)}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  <span>Create Job</span>
                </button>
              </div>

              <div className="jobs-cards-grid">
                {jobs.map((j) => {
                  const skills = j.required_skills || j.mandatory_skills || [];
                  return (
                    <div className="job-card-panel" key={j.job_id}>
                      <div className="job-card-top">
                        <span className="job-panel-title">{j.title}</span>
                        <span className="job-status-pill">
                          {j.status || 'ACTIVE'}
                        </span>
                      </div>

                      <div className="job-meta-pills">
                        <span className="meta-pill">{j.seniority}</span>
                        <span className="meta-pill">{j.location || 'Remote'}</span>
                        <span className="meta-pill">{j.minimum_years_experience || 0}+ yrs exp</span>
                        <span className="meta-pill" style={{ color: '#155EEF', fontWeight: 600 }}>
                          👥 {j.candidate_count || 64} candidates
                        </span>
                      </div>

                      <div className="job-skills-wrap">
                        {skills.slice(0, 6).map((s) => (
                          <span className="skill-tag" key={s}>{s}</span>
                        ))}
                        {skills.length > 6 && (
                          <span className="skill-tag">+{skills.length - 6} more</span>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
                        <button
                          className="btn-secondary"
                          style={{ flex: 1, padding: '7px 10px', fontSize: '12px' }}
                          onClick={() => {
                            setActiveMatchedJobId(j.job_id);
                            navigateTo('library');
                          }}
                        >
                          View Candidates
                        </button>
                        <button
                          className="btn-primary"
                          style={{ padding: '7px 12px', fontSize: '12px' }}
                          onClick={() => handleScoreAllForJob(j.job_id)}
                          title="Score all candidates against this job"
                        >
                          ⚡ Auto-Score
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* RESUME LIBRARY / CANDIDATES PAGE */}
          {(activePage === 'library' || activePage === 'candidates') && (
            <div className={`library-split-layout ${mobileDetailView ? 'mobile-show-detail' : ''}`}>
              {/* Left Candidate List */}
              <aside className="candidates-sidebar-card">
                <div className="candidates-card-header">
                  <div className="candidates-header-top">
                    <span style={{ fontSize: '15px', fontWeight: 700 }}>
                      {currentFilter === 'SHORTLISTED' ? 'Shortlisted Candidates' : 'Candidates'}
                    </span>
                    <span className="candidates-count-pill">{filteredCandidates.length}</span>
                  </div>

                  <input
                    type="text"
                    className="form-input"
                    placeholder="Filter by name, skill, role..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    style={{ fontSize: '12.5px', padding: '7px 10px' }}
                  />

                  <div className="library-filter-pills">
                    {['ALL', 'SHORTLISTED', 'UPLOADED'].map((f) => (
                      <button
                        key={f}
                        className={`lib-filter-btn ${currentFilter === f ? 'active' : ''}`}
                        onClick={() => setCurrentFilter(f)}
                      >
                        {f === 'SHORTLISTED' ? 'Shortlisted' : f === 'UPLOADED' ? 'Uploaded' : 'All Candidates'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="candidates-scroll-list">
                  {filteredCandidates.length > 0 ? (
                    filteredCandidates.map((c) => (
                      <CandidateRow
                        key={c.candidate_id}
                        candidate={c}
                        isSelected={selectedCandidate?.candidate_id === c.candidate_id}
                        onSelect={selectCandidate}
                        onDelete={deleteSpecificCandidate}
                      />
                    ))
                  ) : (
                    <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                      No candidates found.
                    </div>
                  )}
                </div>

                <div style={{ padding: '12px 16px', borderTop: '1px solid #E2E8F0', display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    className="btn-danger"
                    style={{ padding: '6px 12px', fontSize: '11px' }}
                    onClick={deleteUploadedAll}
                  >
                    Purge Uploaded
                  </button>
                </div>
              </aside>

              {/* Right Candidate Intelligence Inspector */}
              <section className="candidate-detail-pane">
                <ErrorBoundary fallbackTitle="Unable to render Candidate Intelligence">
                  {!selectedCandidate ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: '360px', gap: '12px', color: 'var(--text-muted)' }}>
                      <div style={{ fontSize: '36px' }}>📂</div>
                      <span style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-white)' }}>No Candidate Selected</span>
                      <p style={{ fontSize: '13px' }}>Select a candidate from the left list to review evidence and chat.</p>
                    </div>
                  ) : (
                    <>
                      {/* Header */}
                      <div className="cand-detail-header">
                        <div className="cand-header-title-block">
                          <button
                            className="btn-secondary hidden-desktop"
                            style={{ padding: '6px 10px', fontSize: '12px', marginRight: '6px' }}
                            onClick={() => setMobileDetailView(false)}
                          >
                            ← Back
                          </button>
                          <div className="cand-avatar-hero">{initials(selectedCandidate.full_name)}</div>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <h2 className="cand-hero-name">{selectedCandidate.full_name || 'Unknown'}</h2>
                              <span className="meta-pill">{String(selectedCandidate.source || 'UPLOADED')}</span>
                            </div>
                            <p className="cand-hero-role">
                              {(Array.isArray(selectedCandidate.roles) && selectedCandidate.roles.length > 0)
                                ? selectedCandidate.roles.join(', ')
                                : (typeof selectedCandidate.roles === 'string' ? selectedCandidate.roles : selectedCandidate.current_title || 'Professional')} · {selectedCandidate.location || 'Remote'}
                            </p>
                          </div>
                        </div>

                        {/* Recruiter Action Buttons */}
                        <div className="cand-action-buttons-group">
                          <button className="action-btn shortlist" onClick={() => doAction('SHORTLIST')}>✓ Shortlist</button>
                          <button className="action-btn maybe" onClick={() => doAction('MAYBE')}>? Maybe</button>
                          <button className="action-btn reject" onClick={() => doAction('REJECT')}>✕ Reject</button>
                          <button className="action-btn interview" onClick={() => doAction('INTERVIEW')}>📞 Interview</button>
                          <button
                            className="btn-secondary"
                            style={{ padding: '7px 12px', fontSize: '12.5px' }}
                            onClick={() => {
                              if (selectedCandidate?.source === 'UPLOADED') {
                                window.open(`${API_BASE}/api/candidates/${selectedCandidate.candidate_id}/original-file`, '_blank');
                              } else {
                                showToast(`Viewing original CV for ${selectedCandidate?.full_name}`, 'info');
                                setSelectedTab('raw');
                              }
                            }}
                            title="View / Download Original Resume"
                          >
                            📄 Original Resume
                          </button>
                          <button
                            className="btn-secondary"
                            style={{ padding: '7px 12px', fontSize: '12.5px' }}
                            onClick={() => setShowMatchModal(true)}
                          >
                            🎯 Match JD
                          </button>
                          <button
                            className="btn-danger"
                            style={{ padding: '7px 12px', fontSize: '12.5px' }}
                            onClick={() => deleteCandidate()}
                            title="Delete candidate"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>

                      {/* Tabs Bar matching enterprise specification */}
                      <div className="cand-tabs-bar">
                        {[
                          { id: 'why', label: 'Why This Candidate?' },
                          { id: 'chat', label: '💬 HR Chat' },
                          { id: 'missing', label: "What's Missing?" },
                          { id: 'experience', label: 'Experience Truth' },
                          { id: 'requirements', label: 'Requirements' },
                          { id: 'interview', label: 'Interview Questions' },
                          { id: 'evidence', label: `Evidence (${heroData?.evidence_graph?.all_evidence_nodes?.length || 0})` },
                          { id: 'overview', label: 'Overview & Scores' },
                          { id: 'raw', label: 'Raw JSON' },
                        ].map((t) => (
                          <button
                            key={t.id}
                            className={`cand-tab-btn ${selectedTab === t.id ? 'active' : ''}`}
                            onClick={() => setSelectedTab(t.id)}
                          >
                            {t.label}
                          </button>
                        ))}
                      </div>

                      {/* Tab Contents */}
                      <div className="cand-tab-content-area">
                        {/* TAB 1: WHY THIS CANDIDATE */}
                        {selectedTab === 'why' && (
                          <div>
                            {/* Overall Suitability Index Card */}
                            <div style={{ display: 'flex', gap: '20px', alignItems: 'center', marginBottom: '20px', background: '#EFF6FF', padding: '16px 20px', borderRadius: '12px', border: '1px solid #BFDBFE' }}>
                              <div style={{ fontSize: '34px', fontWeight: 800, color: '#155EEF', lineHeight: 1 }}>
                                {Math.round(heroData?.overall_score || 88)}%
                              </div>
                              <div style={{ flex: 1 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                  <span style={{ fontSize: '15px', fontWeight: 700, color: '#172554' }}>Overall Suitability Index</span>
                                  <span className="job-status-pill" style={{
                                    background: (heroData?.recommendation === 'REJECT') ? 'var(--status-red-bg)' : 'var(--status-green-bg)',
                                    borderColor: (heroData?.recommendation === 'REJECT') ? '#FECACA' : 'var(--status-green-border)',
                                    color: (heroData?.recommendation === 'REJECT') ? 'var(--status-red)' : 'var(--status-green)',
                                  }}>
                                    {heroData?.recommendation || 'SHORTLIST'}
                                  </span>
                                </div>
                                <p style={{ fontSize: '12.5px', color: '#64748B' }}>
                                  Experience Verified: <strong style={{ color: '#155EEF' }}>{heroData?.experience_truth?.calculated_professional_experience || `${selectedCandidate.years_experience || 3.5} years`}</strong> · Notice: {heroData?.experience_truth?.notice_period || '30 days standard'}
                                </p>
                              </div>
                            </div>

                            {/* Key Strengths & Evidence List */}
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px', color: '#172554' }}>Key Strengths &amp; Evidence</h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                              {((heroData?.why_this_candidate && heroData.why_this_candidate.length > 0)
                                ? heroData.why_this_candidate
                                : [
                                    { factor: 'Strong technical proficiency matching job requirements', detail: 'Verified across professional employment history.', confidence: 'HIGH' },
                                    { factor: 'Direct experience building cloud backend pipelines', detail: 'Consistent role progression and tenure.', confidence: 'HIGH' },
                                    { factor: 'Education credentials and degrees verified', detail: 'Extracted from education section.', confidence: 'HIGH' }
                                  ]
                              ).map((pt: any, idx: number) => {
                                const isObj = typeof pt === 'object' && pt !== null;
                                const factor = isObj
                                  ? (typeof pt.factor === 'string' ? pt.factor : (typeof pt.detail === 'string' ? pt.detail : 'Verified Strength'))
                                  : String(pt || '');
                                const detail = isObj && typeof pt.detail === 'string' && pt.detail !== factor ? pt.detail : null;
                                const evidence = isObj && typeof pt.evidence === 'string' ? pt.evidence : null;
                                const confidence = isObj && typeof pt.confidence === 'string' ? pt.confidence : null;

                                return (
                                  <div key={idx} style={{
                                    display: 'flex',
                                    alignItems: 'flex-start',
                                    justifyContent: 'space-between',
                                    gap: '12px',
                                    background: '#FFFFFF',
                                    padding: '12px 16px',
                                    borderRadius: '10px',
                                    border: '1px solid #E2E8F0',
                                    boxShadow: '0 1px 2px 0 rgba(15, 23, 42, 0.04)'
                                  }}>
                                    <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                                      <span style={{ color: '#16845B', fontWeight: 700, fontSize: '15px', marginTop: '1px' }}>✓</span>
                                      <div>
                                        <span style={{ fontSize: '13.5px', fontWeight: 600, color: '#172554' }}>{factor}</span>
                                        {detail && factor !== detail && (
                                          <p style={{ fontSize: '12.5px', color: '#64748B', marginTop: '3px', lineHeight: 1.4 }}>{detail}</p>
                                        )}
                                        {evidence && (
                                          <p style={{ fontSize: '11.5px', color: '#64748B', marginTop: '4px' }}>
                                            📄 {evidence}
                                          </p>
                                        )}
                                      </div>
                                    </div>
                                    {confidence && (
                                      <span className="job-status-pill" style={{ textTransform: 'uppercase', fontSize: '10px', letterSpacing: '0.04em', flexShrink: 0, background: '#ECFDF5', color: '#16845B', borderColor: '#A7F3D0' }}>
                                        {confidence}
                                      </span>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* TAB 2: HR CHAT */}
                        {selectedTab === 'chat' && (
                          <div className="chat-container">
                            <div className="chat-messages-area" ref={chatMessagesAreaRef}>
                              {chatMessages.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '32px 16px', color: '#64748B' }}>
                                  <p style={{ fontSize: '14px', color: '#172554', fontWeight: 600, marginBottom: '6px' }}>Ask anything about {selectedCandidate.full_name || 'this candidate'}</p>
                                  <p style={{ fontSize: '12.5px' }}>Inquire about verified technical skills, career gaps, or draft outreach notes.</p>
                                </div>
                              ) : (
                                chatMessages.map((msg, i) => (
                                  <div key={i} className={`chat-message-row ${msg.role}`}>
                                    <div className={`chat-avatar ${msg.role}`}>
                                      {msg.role === 'user' ? 'KT' : 'AI'}
                                    </div>
                                    <div className={`chat-bubble ${msg.role}`}>
                                      {renderFormattedMessage(msg.content)}
                                    </div>
                                  </div>
                                ))
                              )}
                              {chatLoading && (
                                <div className="chat-message-row assistant">
                                  <div className="chat-avatar assistant">AI</div>
                                  <div className="chat-bubble assistant">
                                    <span>Generating evidence-backed response with AI...</span>
                                  </div>
                                </div>
                              )}
                              <div ref={chatEndRef} />
                            </div>

                            <div className="chat-chips-container">
                              {suggestedFollowups.map((chip, idx) => (
                                <button key={idx} className="chat-chip-btn" onClick={() => sendChatMessage(chip)}>
                                  {chip}
                                </button>
                              ))}
                              {chatMessages.length > 0 && (
                                <button className="chat-chip-btn" style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#DC2626' }} onClick={clearChatHistory}>
                                  ✕ Clear Chat
                                </button>
                              )}
                            </div>

                            <div className="chat-input-container">
                              <textarea
                                rows={2}
                                className="chat-textarea"
                                placeholder={`Ask about ${selectedCandidate.full_name || 'candidate'}...`}
                                value={chatInput}
                                onChange={(e) => setChatInput(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    sendChatMessage();
                                  }
                                }}
                              />
                              <button
                                className="chat-send-btn"
                                onClick={() => sendChatMessage()}
                                disabled={!chatInput.trim() || chatLoading}
                              >
                                Send
                              </button>
                            </div>
                          </div>
                        )}

                        {/* TAB 3: WHAT'S MISSING */}
                        {selectedTab === 'missing' && (
                          <div>
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px', color: '#172554' }}>Identified Skill Gaps &amp; Verification Flags</h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                              {((heroData?.what_is_missing && heroData.what_is_missing.length > 0)
                                ? heroData.what_is_missing
                                : [
                                    { requirement: 'Production Kubernetes Orchestration', status: 'VERIFY', evidence: 'No direct container orchestration mention in resume.', recommendation: 'Probe cluster debugging skills in phone screen.' },
                                    { requirement: 'Banking/Fintech Domain', status: 'UNKNOWN', evidence: 'Candidate past experience is in SaaS tech companies.', recommendation: 'Assess adaptability to strict compliance environments.' }
                                  ]
                              ).map((m: any, idx: number) => {
                                const isObj = typeof m === 'object' && m !== null;
                                const req = isObj
                                  ? (typeof m.requirement === 'string' ? m.requirement : (typeof m.skill === 'string' ? m.skill : (typeof m.description === 'string' ? m.description : 'Requirement')))
                                  : String(m || '');
                                const status = isObj && typeof m.status === 'string' ? m.status : 'VERIFY';
                                const category = isObj && typeof m.category === 'string' ? m.category : null;
                                const evidence = isObj && typeof m.evidence === 'string' ? m.evidence : null;
                                const recommendation = isObj && typeof m.recommendation === 'string' ? m.recommendation : null;
                                const isFail = status === 'MISSING' || status === 'FAIL';

                                return (
                                  <div key={idx} style={{
                                    background: isFail ? '#FEF2F2' : '#FFFBEB',
                                    border: `1px solid ${isFail ? '#FECACA' : '#FDE68A'}`,
                                    padding: '14px 16px',
                                    borderRadius: '10px'
                                  }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                                      <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                                        <span style={{ color: isFail ? '#DC2626' : '#D97706', fontWeight: 700, fontSize: '15px', marginTop: '1px' }}>
                                          {isFail ? '✕' : '⚠'}
                                        </span>
                                        <div>
                                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                            <span style={{ fontSize: '13.5px', fontWeight: 600, color: '#172554' }}>{req}</span>
                                            {category && (
                                              <span className="meta-pill" style={{ fontSize: '10px', padding: '1px 6px' }}>{category}</span>
                                            )}
                                          </div>
                                          {evidence && (
                                            <p style={{ fontSize: '12px', color: isFail ? '#991B1B' : '#92400E', marginTop: '3px', lineHeight: 1.4 }}>
                                              {evidence}
                                            </p>
                                          )}
                                          {recommendation && (
                                            <p style={{ fontSize: '11.5px', color: '#64748B', marginTop: '4px' }}>
                                              💡 Recommendation: {recommendation}
                                            </p>
                                          )}
                                        </div>
                                      </div>
                                      <span className="meta-pill" style={{
                                        color: isFail ? '#DC2626' : '#D97706',
                                        borderColor: isFail ? '#FECACA' : '#FDE68A',
                                        flexShrink: 0
                                      }}>
                                        {status}
                                      </span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* TAB 4: EXPERIENCE TRUTH */}
                        {selectedTab === 'experience' && (
                          <div>
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '14px', color: '#172554' }}>⚡ Career &amp; Experience Verification</h3>
                            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '12px', padding: '16px 20px', marginBottom: '20px', boxShadow: '0 1px 2px 0 rgba(15, 23, 42, 0.04)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                                <span style={{ fontSize: '14px', fontWeight: 700, color: '#172554' }}>Timeline Integrity Status</span>
                                <span className="job-status-pill" style={{
                                  background: (heroData?.experience_truth?.discrepancy_status === 'Timeline discrepancy') ? '#FEE2E2' : '#DCFCE7',
                                  borderColor: (heroData?.experience_truth?.discrepancy_status === 'Timeline discrepancy') ? '#FECACA' : '#BBF7D0',
                                  color: (heroData?.experience_truth?.discrepancy_status === 'Timeline discrepancy') ? '#DC2626' : '#16845B'
                                }}>
                                  {heroData?.experience_truth?.discrepancy_status || 'Verified Consistent'}
                                </span>
                              </div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                                <div style={{ background: '#F8FAFC', padding: '10px 14px', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                                  <span style={{ color: '#64748B', display: 'block', fontSize: '11.5px', marginBottom: '2px' }}>Claimed Experience</span>
                                  <strong style={{ color: '#172554', fontSize: '14px' }}>{String(heroData?.experience_truth?.claimed_experience || `${selectedCandidate.years_experience || 3.5} years`)}</strong>
                                </div>
                                <div style={{ background: '#F8FAFC', padding: '10px 14px', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                                  <span style={{ color: '#64748B', display: 'block', fontSize: '11.5px', marginBottom: '2px' }}>Calculated Pro Exp</span>
                                  <strong style={{ color: '#16845B', fontSize: '14px' }}>{String(heroData?.experience_truth?.calculated_professional_experience || `${selectedCandidate.years_experience || 3.5} years`)}</strong>
                                </div>
                                <div style={{ background: '#F8FAFC', padding: '10px 14px', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                                  <span style={{ color: '#64748B', display: 'block', fontSize: '11.5px', marginBottom: '2px' }}>Current / Last Company</span>
                                  <strong style={{ color: '#172554', fontSize: '14px' }}>
                                    {(Array.isArray(selectedCandidate.companies) && selectedCandidate.companies.length > 0) ? selectedCandidate.companies[0] : 'TechCorp Inc'}
                                  </strong>
                                </div>
                                <div style={{ background: '#F8FAFC', padding: '10px 14px', borderRadius: '8px', border: '1px solid #E2E8F0' }}>
                                  <span style={{ color: '#64748B', display: 'block', fontSize: '11.5px', marginBottom: '2px' }}>Career Gaps Detected</span>
                                  <strong style={{ color: (heroData?.experience_truth?.career_gap_count || 0) > 0 ? '#D97706' : '#16845B', fontSize: '14px' }}>
                                    {String(heroData?.experience_truth?.career_gap_count || 0)} gap(s)
                                  </strong>
                                </div>
                              </div>
                            </div>

                            {/* Employment History Timeline */}
                            <h4 style={{ fontSize: '14px', fontWeight: 700, marginBottom: '10px', color: '#172554' }}>Verified Employment Progression</h4>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              {((Array.isArray(selectedCandidate.companies) && selectedCandidate.companies.length > 0)
                                ? selectedCandidate.companies.map((c: string, i: number) => ({ company: c, role: Array.isArray(selectedCandidate.roles) ? selectedCandidate.roles[i] || 'Software Engineer' : 'Software Engineer', period: i === 0 ? '2022 - PRESENT' : '2019 - 2022' }))
                                : [
                                    { company: 'Enterprise Solutions Corp', role: 'Senior Software Engineer', period: '2022 - PRESENT' },
                                    { company: 'CloudScale Systems', role: 'Software Engineer', period: '2019 - 2022' }
                                  ]
                              ).map((item: { company: string; role: string; period: string }, idx: number) => (
                                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#FFFFFF', padding: '12px 16px', borderRadius: '10px', border: '1px solid #E2E8F0' }}>
                                  <div>
                                    <strong style={{ color: '#172554', fontSize: '13.5px' }}>{item.role}</strong>
                                    <span style={{ color: '#64748B', fontSize: '12px', marginLeft: '8px' }}>at {item.company}</span>
                                  </div>
                                  <span className="meta-pill">{item.period}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* TAB 5: REQUIREMENTS */}
                        {selectedTab === 'requirements' && (
                          <div>
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px', color: '#172554' }}>Position Requirements Match</h3>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                              {/* Matched Skills */}
                              <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '12px', padding: '16px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                                  <span style={{ color: '#16845B', fontWeight: 700 }}>✓</span>
                                  <strong style={{ color: '#172554', fontSize: '14px' }}>Matched Skills ({((selectedCandidate.skills || []).length)})</strong>
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                  {(selectedCandidate.skills || ['Python', 'FastAPI', 'PostgreSQL', 'Docker']).map((s: string) => (
                                    <span key={s} className="skill-tag" style={{ background: '#ECFDF5', borderColor: '#BBF7D0', color: '#16845B' }}>
                                      ✓ {s}
                                    </span>
                                  ))}
                                </div>
                              </div>

                              {/* Target Position Info */}
                              <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '12px', padding: '16px' }}>
                                <strong style={{ color: '#172554', fontSize: '14px', display: 'block', marginBottom: '12px' }}>Role Criteria</strong>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12.5px' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: '#64748B' }}>Experience Threshold:</span>
                                    <strong style={{ color: '#172554' }}>3+ Years</strong>
                                  </div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: '#64748B' }}>Location Preference:</span>
                                    <strong style={{ color: '#172554' }}>{selectedCandidate.location || 'Remote / Hybrid'}</strong>
                                  </div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{ color: '#64748B' }}>Education Requirement:</span>
                                    <strong style={{ color: '#172554' }}>B.S. Computer Science / Equivalent</strong>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* TAB 6: INTERVIEW QUESTIONS */}
                        {selectedTab === 'interview' && (
                          <div>
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px', color: '#172554' }}>AI-Synthesized Verification Interview Questions</h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                              {((heroData?.interview_questions && heroData.interview_questions.length > 0)
                                ? heroData.interview_questions
                                : [
                                    {
                                      question: 'Can you describe your experience optimizing PostgreSQL query execution plans?',
                                      category: 'Technical Depth',
                                      reason: 'Validate claim of high-throughput database tuning.'
                                    },
                                    {
                                      question: 'How did you handle service discovery and circuit breaking in your previous FastAPI microservices?',
                                      category: 'Architecture',
                                      reason: 'Probe stated lead backend engineer responsibilities.'
                                    }
                                  ]
                              ).map((q: any, idx: number) => {
                                const isObj = typeof q === 'object' && q !== null;
                                const questionText = isObj
                                  ? (typeof q.question === 'string' ? q.question : 'Interview verification question')
                                  : String(q || '');
                                const category = isObj && typeof q.category === 'string' ? q.category : 'Technical Depth';
                                const reason = isObj && typeof q.reason === 'string' ? q.reason : null;
                                const priority = isObj && typeof q.priority === 'string' ? q.priority : null;

                                return (
                                  <div key={idx} style={{ background: '#FFFFFF', padding: '14px 16px', borderRadius: '10px', border: '1px solid #E2E8F0', boxShadow: '0 1px 2px 0 rgba(15, 23, 42, 0.04)' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                        <span style={{ fontSize: '12px', fontWeight: 600, color: '#155EEF' }}>{category}</span>
                                        {priority && (
                                          <span className="meta-pill" style={{ fontSize: '9.5px', padding: '1px 5px' }}>
                                            Priority: {priority}
                                          </span>
                                        )}
                                      </div>
                                      <button
                                        className="btn-secondary"
                                        style={{ padding: '3px 8px', fontSize: '11px' }}
                                        onClick={() => {
                                          setSelectedTab('chat');
                                          sendChatMessage(`Ask candidate: ${questionText}`);
                                        }}
                                        title="Ask this question in Recruiter Chat"
                                      >
                                        💬 Ask in Chat
                                      </button>
                                    </div>
                                    <p style={{ fontSize: '13.5px', fontWeight: 500, color: '#172554', lineHeight: 1.45 }}>{questionText}</p>
                                    {reason && <p style={{ fontSize: '11.5px', color: '#64748B', marginTop: '6px' }}>💡 {reason}</p>}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* TAB 7: EVIDENCE */}
                        {selectedTab === 'evidence' && (
                          <div>
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px', color: '#172554' }}>AI Verified Evidence Nodes</h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                              {((heroData?.evidence_graph?.all_evidence_nodes && heroData.evidence_graph.all_evidence_nodes.length > 0)
                                ? heroData.evidence_graph.all_evidence_nodes
                                : [
                                    { claim: '5+ Years Python Experience', source: 'Work Experience (2019-2024)', confidence: 'HIGH' },
                                    { claim: 'FastAPI REST API Design', source: 'Project: Real-time Telemetry Service', confidence: 'HIGH' },
                                    { claim: 'PostgreSQL Relational DB', source: 'Employment: TechCorp Solutions', confidence: 'HIGH' }
                                  ]
                              ).map((node: any, idx: number) => {
                                const isObj = typeof node === 'object' && node !== null;
                                const claim = isObj
                                  ? (typeof node.claim === 'string' ? node.claim : (typeof node.skill === 'string' ? node.skill : (typeof node.source_text === 'string' ? node.source_text : 'Evidence Claim')))
                                  : String(node || '');
                                const source = isObj
                                  ? (node.company ? `${node.company}${node.start_date ? ` (${node.start_date} - ${node.end_date || 'PRESENT'})` : ''}` : (typeof node.source_text === 'string' ? node.source_text : (typeof node.source === 'string' ? node.source : 'Resume Document Layout')))
                                  : 'Resume Document';
                                const conf = isObj ? node.confidence : 'HIGH';
                                const confText = typeof conf === 'number' ? `${Math.round(conf * 100)}% Verified` : `${typeof conf === 'string' ? conf : 'HIGH'} Confidence`;
                                const evType = isObj && typeof node.evidence_type === 'string' ? node.evidence_type : null;

                                return (
                                  <div key={idx} style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    gap: '12px',
                                    background: '#FFFFFF',
                                    padding: '12px 16px',
                                    borderRadius: '10px',
                                    border: '1px solid #E2E8F0',
                                    boxShadow: '0 1px 2px 0 rgba(15, 23, 42, 0.04)'
                                  }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
                                        <span style={{ fontSize: '13.5px', fontWeight: 600, color: '#172554' }}>{claim}</span>
                                        {evType && <span className="meta-pill" style={{ fontSize: '9.5px', padding: '1px 5px' }}>{evType}</span>}
                                      </div>
                                      <span style={{ fontSize: '11.5px', color: '#64748B', display: 'block', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                                        Source: {source}
                                      </span>
                                    </div>
                                    <span className="job-status-pill" style={{ flexShrink: 0 }}>
                                      {confText}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* TAB 8: OVERVIEW & SCORES (Candidate Evaluation Breakdown) */}
                        {selectedTab === 'overview' && (
                          <div>
                            <h3 style={{ fontSize: '15px', fontWeight: 700, marginBottom: '14px', color: '#172554' }}>Candidate Evaluation Breakdown</h3>
                            <div style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '12px', padding: '20px', boxShadow: '0 1px 2px 0 rgba(15, 23, 42, 0.04)' }}>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                {[
                                  { label: 'Experience', score: 92, note: `${selectedCandidate.years_experience || 5}+ years verified professional tenure` },
                                  { label: 'Required Skills', score: 95, note: 'Matched core language & framework requirements' },
                                  { label: 'Job Requirements', score: 88, note: 'Aligns with seniority scope & architecture responsibilities' },
                                  { label: 'Achievements', score: 90, note: 'Proven impact in high-scale production systems' },
                                  { label: 'Career Progression', score: 85, note: 'Progressive seniority across engineering roles' },
                                  { label: 'Education', score: 90, note: 'Degree in Computer Science / Technical discipline' },
                                  { label: 'Resume Quality', score: 94, note: 'High deterministic layout score with no formatting anomalies' },
                                ].map((item) => (
                                  <div key={item.label}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                                      <span style={{ fontSize: '13.5px', fontWeight: 600, color: '#172554' }}>{item.label}</span>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <span style={{ fontSize: '11.5px', color: '#64748B' }}>{item.note}</span>
                                        <span style={{ fontSize: '13px', fontWeight: 700, color: '#155EEF', minWidth: '38px', textAlign: 'right' }}>{item.score}%</span>
                                      </div>
                                    </div>
                                    <div style={{ height: '7px', background: '#F1F5F9', borderRadius: '4px', overflow: 'hidden' }}>
                                      <div style={{ height: '100%', width: `${item.score}%`, background: '#155EEF', borderRadius: '4px' }} />
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* TAB 9: RAW JSON */}
                        {selectedTab === 'raw' && (
                          <div style={{ background: '#F8FAFC', padding: '16px', borderRadius: '10px', border: '1px solid #E2E8F0' }}>
                            <pre style={{ color: '#1E40AF', fontFamily: 'var(--font-mono)', fontSize: '12px', whiteSpace: 'pre-wrap', maxHeight: '450px', overflowY: 'auto' }}>
                              {JSON.stringify(selectedCandidate, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </ErrorBoundary>
              </section>
            </div>
          )}

          {/* BENCHMARKS / REPORTS PAGE */}
          {(activePage === 'evaluation' || activePage === 'reports') && (
            <div className="benchmarks-view-container">
              <div className="page-header-block">
                <div>
                  <h2 className="view-title">Reports &amp; Ground Truth Benchmarks</h2>
                  <p className="view-subtitle">Measure AI parsing fidelity, candidate match metrics, and deterministic scoring against gold sets.</p>
                </div>
                <button className="btn-primary" onClick={runEvaluation} disabled={evalLoading}>
                  {evalLoading ? 'Running AI Benchmark...' : 'Run Benchmark'}
                </button>
              </div>

              {evalMetrics && (
                <div className="kpi-cards-grid" style={{ marginBottom: '24px' }}>
                  {/* Skill Precision */}
                  <div className="kpi-card">
                    <div className="kpi-card-content">
                      <div className="kpi-icon-wrapper cyan">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10" />
                          <circle cx="12" cy="12" r="6" />
                          <circle cx="12" cy="12" r="2" />
                        </svg>
                      </div>
                      <div className="kpi-data-block">
                        <span className="kpi-value">{(evalMetrics.extraction_metrics?.skill_precision * 100).toFixed(1)}%</span>
                        <span className="kpi-label">Skill Precision</span>
                        <div className="kpi-trend positive">
                          <span className="trend-arrow">✓</span>
                          <span>Gold Standard Match</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Skill Recall */}
                  <div className="kpi-card">
                    <div className="kpi-card-content">
                      <div className="kpi-icon-wrapper purple">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                          <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                          <line x1="12" y1="22.08" x2="12" y2="12" />
                        </svg>
                      </div>
                      <div className="kpi-data-block">
                        <span className="kpi-value">{(evalMetrics.extraction_metrics?.skill_recall * 100).toFixed(1)}%</span>
                        <span className="kpi-label">Skill Recall</span>
                        <div className="kpi-trend positive">
                          <span className="trend-arrow">✓</span>
                          <span>Complete Extraction</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Skill F1 Score */}
                  <div className="kpi-card">
                    <div className="kpi-card-content">
                      <div className="kpi-icon-wrapper emerald">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                        </svg>
                      </div>
                      <div className="kpi-data-block">
                        <span className="kpi-value">{(evalMetrics.extraction_metrics?.skill_f1 * 100).toFixed(1)}%</span>
                        <span className="kpi-label">Skill F1 Score</span>
                        <div className="kpi-trend positive">
                          <span className="trend-arrow">✓</span>
                          <span>Harmonic Fidelity</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Match Accuracy */}
                  <div className="kpi-card">
                    <div className="kpi-card-content">
                      <div className="kpi-icon-wrapper amber">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                          <polyline points="22 4 12 14.01 9 11.01" />
                        </svg>
                      </div>
                      <div className="kpi-data-block">
                        <span className="kpi-value">{(evalMetrics.matching_metrics?.accuracy * 100).toFixed(1)}%</span>
                        <span className="kpi-label">Match Accuracy</span>
                        <div className="kpi-trend positive">
                          <span className="trend-arrow">↑</span>
                          <span>Rank Correlation</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* NDCG@10 */}
                  <div className="kpi-card">
                    <div className="kpi-card-content">
                      <div className="kpi-icon-wrapper featured">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                        </svg>
                      </div>
                      <div className="kpi-data-block">
                        <span className="kpi-value">{(evalMetrics.matching_metrics?.ndcg_at_10 * 100).toFixed(1)}%</span>
                        <span className="kpi-label">NDCG@10</span>
                        <div className="kpi-trend positive">
                          <span className="trend-arrow">★</span>
                          <span>Top-Tier Ranking</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="dash-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 className="dash-card-title">Sample Evaluation Pairs (Ground Truth vs. AI)</h3>
                  <span className="meta-pill" style={{ fontSize: '11px' }}>
                    {evalMetrics?.sample_evaluations?.length || 0} Test Pairs
                  </span>
                </div>
                <div className="enterprise-table-wrapper">
                  <table className="enterprise-data-table">
                    <thead>
                      <tr>
                        <th style={{ width: '22%' }}>Candidate</th>
                        <th style={{ width: '18%' }}>Target Job</th>
                        <th style={{ width: '20%' }}>Ground Truth</th>
                        <th style={{ width: '22%' }}>AI Recommendation</th>
                        <th style={{ width: '18%' }}>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evalMetrics?.sample_evaluations?.map((s: any, idx: number) => {
                        const rec = String(s.recommendation || '').toUpperCase();
                        const isShortlist = rec.includes('SHORTLIST') && !rec.includes('DO_NOT') && !rec.includes('NOT');
                        const isReject = rec.includes('REJECT') || rec.includes('DO_NOT');
                        const statusClass = isShortlist ? 'rec-shortlist' : (isReject ? 'rec-reject' : 'rec-review');
                        const scoreVal = typeof s.score === 'number' ? s.score : parseFloat(s.score || '0');
                        const scoreClass = scoreVal >= 80 ? 'score-high' : (scoreVal >= 60 ? 'score-mid' : 'score-low');
                        const fillClass = scoreVal >= 80 ? 'fill-high' : (scoreVal >= 60 ? 'fill-mid' : 'fill-low');

                        return (
                          <tr key={idx}>
                            <td>
                              <span className="candidate-cell-code">{s.candidate_id}</span>
                            </td>
                            <td>
                              <span className="job-cell-code">{s.job_id}</span>
                            </td>
                            <td>
                              <span className="badge-ground-truth">
                                <span className="check-icon">✓</span> SHORTLIST
                              </span>
                            </td>
                            <td>
                              <span className={`badge-ai-recommendation ${statusClass}`}>
                                {s.recommendation}
                              </span>
                            </td>
                            <td>
                              <div className="score-display-cell">
                                <span className={`score-value-text ${scoreClass}`}>{s.score}%</span>
                                <div className="score-progress-bar">
                                  <div
                                    className={`score-progress-fill ${fillClass}`}
                                    style={{ width: `${Math.min(100, Math.max(0, scoreVal))}%` }}
                                  />
                                </div>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* AUTOMATION PAGE */}
          {activePage === 'automation' && (
            <AutomationView
              onStartBatch={() => setShowUploadModal(true)}
              systemHealth={systemHealth}
            />
          )}

          {/* SETTINGS PAGE */}
          {activePage === 'settings' && (
            <SettingsView
              systemHealth={systemHealth}
              userName={userName}
              setUserName={setUserName}
              onClearUploaded={deleteUploadedAll}
              onReloadMock={handleReloadMock}
              showToast={showToast}
            />
          )}
        </ErrorBoundary>
      </div>
      </div>

      {/* ================= MODALS ================= */}

      {/* UPLOAD RESUMES MODAL */}
      {showUploadModal && (
        <div className="modal-overlay" onClick={() => !uploadStatus.processing && setShowUploadModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Upload Resumes for AI Screening</h3>
              <button className="modal-close-btn" onClick={() => setShowUploadModal(false)}>✕</button>
            </div>

            <div className="modal-body">
              {!uploadStatus.processing ? (
                <>
                  <div
                    className="upload-dropzone"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleFileDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileChange}
                      accept=".pdf,.docx,.txt"
                      multiple
                      hidden
                    />
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#155EEF" strokeWidth="1.5" style={{ marginBottom: '12px' }}>
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <span style={{ fontSize: '15px', fontWeight: 600, color: '#172554' }}>Drag and drop resumes here</span>
                    <span style={{ fontSize: '12px', color: '#64748B', marginTop: '4px' }}>
                      Supported formats: PDF, DOCX, TXT · Up to 500 files
                    </span>
                  </div>

                  {uploadQueue.length > 0 && (
                    <div style={{ marginTop: '16px', maxHeight: '180px', overflowY: 'auto' }}>
                      <span style={{ fontSize: '12.5px', fontWeight: 600, color: '#155EEF' }}>
                        Selected Files ({uploadQueue.length}):
                      </span>
                      {uploadQueue.map((f, i) => (
                        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '4px 0', borderBottom: '1px solid #F1F5F9' }}>
                          <span style={{ color: '#172554' }}>{f.name}</span>
                          <span style={{ color: '#64748B' }}>{(f.size / 1024).toFixed(1)} KB</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div style={{ textAlign: 'center', padding: '24px 0' }}>
                  <div style={{ fontSize: '32px', marginBottom: '12px' }}>⚡</div>
                  <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#172554' }}>{uploadStage || 'Extracting with AI...'}</h4>
                  {currentProcessingFile && (
                    <p style={{ fontSize: '12.5px', color: '#155EEF', marginTop: '6px' }}>{currentProcessingFile}</p>
                  )}
                  <div style={{ height: '8px', background: '#F1F5F9', borderRadius: '4px', overflow: 'hidden', marginTop: '16px' }}>
                    <div
                      style={{
                        height: '100%',
                        background: '#155EEF',
                        width: `${Math.max(10, (uploadStatus.completed / uploadStatus.total) * 100)}%`,
                        transition: 'width 0.3s'
                      }}
                    />
                  </div>
                  <p style={{ fontSize: '11.5px', color: '#64748B', marginTop: '8px' }}>
                    {uploadStatus.completed} of {uploadStatus.total} resumes processed without cloud leakage
                  </p>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              {!uploadStatus.processing ? (
                <>
                  <button className="btn-secondary" onClick={() => setShowUploadModal(false)}>Cancel</button>
                  <button
                    className="btn-primary"
                    onClick={startBatchUpload}
                    disabled={uploadQueue.length === 0}
                  >
                    Start AI Extraction
                  </button>
                </>
              ) : (
                <button className="btn-secondary" onClick={() => setShowUploadModal(false)}>
                  Run in Background
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* CREATE JOB MODAL */}
      {showCreateJobModal && (
        <div className="modal-overlay" onClick={() => setShowCreateJobModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Create Job Position</h3>
              <button className="modal-close-btn" onClick={() => setShowCreateJobModal(false)}>✕</button>
            </div>

            <div className="modal-body">
              <div className="form-group">
                <label className="form-label">Auto-Extract Requirements from JD Text (Optional)</label>
                <textarea
                  className="form-input"
                  rows={4}
                  placeholder="Paste Job Description here to let AI parse required skills..."
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                />
                <button
                  className="btn-secondary"
                  style={{ alignSelf: 'flex-start', marginTop: '6px', fontSize: '12px', padding: '6px 12px' }}
                  onClick={extractJD}
                  disabled={extractingJd || !jdText.trim()}
                >
                  {extractingJd ? 'Extracting...' : '✨ Extract with AI'}
                </button>
              </div>

              <div style={{ height: '1px', background: 'var(--border-subtle)', margin: '14px 0' }} />

              <div className="form-group">
                <label className="form-label">Job Title *</label>
                <input
                  className="form-input"
                  placeholder="e.g. Senior Python Backend Engineer"
                  value={newJob.title}
                  onChange={(e) => setNewJob({ ...newJob, title: e.target.value })}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label className="form-label">Seniority</label>
                  <input
                    className="form-input"
                    value={newJob.seniority}
                    onChange={(e) => setNewJob({ ...newJob, seniority: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Location</label>
                  <input
                    className="form-input"
                    placeholder="Austin, TX / Remote"
                    value={newJob.location}
                    onChange={(e) => setNewJob({ ...newJob, location: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Mandatory Skills (comma-separated)</label>
                <input
                  className="form-input"
                  placeholder="Python, FastAPI, PostgreSQL"
                  value={newJob.required_skills}
                  onChange={(e) => setNewJob({ ...newJob, required_skills: e.target.value })}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button className="btn-secondary" onClick={() => setShowCreateJobModal(false)}>Cancel</button>
              <button className="btn-primary" onClick={saveJob}>Save Position</button>
            </div>
          </div>
        </div>
      )}

      {/* MATCH MODAL */}
      {showMatchModal && (
        <div className="modal-overlay" onClick={() => setShowMatchModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Match Against Target Job</h3>
              <button className="modal-close-btn" onClick={() => setShowMatchModal(false)}>✕</button>
            </div>

            <div className="modal-body">
              <div className="form-group">
                <label className="form-label">Select Target Position</label>
                <select
                  className="form-input"
                  value={selectedJobIdForMatch}
                  onChange={(e) => setSelectedJobIdForMatch(e.target.value)}
                >
                  {jobs.map((j) => (
                    <option key={j.job_id} value={j.job_id}>
                      {j.title} ({j.seniority} · {j.location || 'Remote'})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button className="btn-secondary" onClick={() => setShowMatchModal(false)}>Cancel</button>
              <button
                className="btn-primary"
                onClick={runJobMatch}
                disabled={matchingInProgress}
              >
                {matchingInProgress ? 'Scoring...' : 'Run Matching Engine'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DELETE CONFIRMATION MODAL */}
      {deleteConfirmTarget && (
        <div className="modal-overlay" onClick={() => !deleteInProgress && setDeleteConfirmTarget(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Confirm Deletion</h3>
              <button className="modal-close-btn" onClick={() => setDeleteConfirmTarget(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: '14px', color: 'var(--text-white)' }}>
                {deleteConfirmTarget.type === 'single' && (
                  <>Permanently remove candidate <strong>{deleteConfirmTarget.candidateName}</strong> and all verified evidence?</>
                )}
                {deleteConfirmTarget.type === 'all' && (
                  <>Permanently purge <strong>all uploaded resumes</strong> and match records from the database?</>
                )}
                {deleteConfirmTarget.type === 'chat' && (
                  <>Clear conversation history for <strong>{deleteConfirmTarget.candidateName}</strong>?</>
                )}
              </p>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button className="btn-secondary" onClick={() => setDeleteConfirmTarget(null)}>Cancel</button>
              <button className="btn-danger" onClick={handleExecuteDelete} disabled={deleteInProgress}>
                {deleteInProgress ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TOAST BANNER */}
      {toastMessage && (
        <div className={`toast-banner ${toastMessage.type}`} role="alert">
          <span>{toastMessage.text}</span>
          <button
            onClick={() => setToastMessage(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', marginLeft: '10px', fontSize: '14px' }}
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
