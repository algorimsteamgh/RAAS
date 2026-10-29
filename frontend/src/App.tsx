import React, { useState, useEffect, useCallback, useRef } from 'react';

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
  notice_period?: string;
}

interface Job {
  job_id: string;
  title: string;
  seniority: string;
  location?: string;
  minimum_years_experience?: number;
  required_skills?: string[];
  mandatory_skills?: string[];
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

const renderInlineMarkdown = (str: string): React.ReactNode[] => {
  const parts: React.ReactNode[] = [];
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

const renderFormattedMessage = (text: string) => {
  if (!text) return null;
  const lines = text.split('\n');
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

export default function App() {
  // Navigation & Page State
  const [activePage, setActivePage] = useState<string>('dashboard');
  const [selectedTab, setSelectedTab] = useState<string>('why');
  const [showMobileNav, setShowMobileNav] = useState<boolean>(false);

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

  // --- HEALTH CHECK ---
  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/system/health`);
      if (res.ok) {
        const data = await res.json();
        setSystemHealth(data);
      }
    } catch (e) {
      setSystemHealth(prev => ({ ...prev, ollama_status: 'disconnected' }));
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  // --- DASHBOARD METRICS ---
  const loadDashboard = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dashboard/metrics`);
      if (res.ok) {
        const data = await res.json();
        setDashboardMetrics(data);
      }
    } catch (e) {
      console.error('Failed to load dashboard metrics:', e);
    }
  }, []);

  // --- CANDIDATES LIST ---
  const fetchCandidates = useCallback(async (selectFirst = false) => {
    try {
      const res = await fetch(`${API_BASE}/api/candidates`);
      if (res.ok) {
        const data = await res.json();
        setAllCandidates(data);
        if (selectFirst && data.length > 0) {
          selectCandidate(data[0]);
        }
      }
    } catch (e) {
      console.error('Failed to fetch candidates:', e);
    }
  }, []);

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

  useEffect(() => {
    if (toastMessage) {
      const timer = setTimeout(() => setToastMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toastMessage]);

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

  // --- HERO & EVIDENCE GRAPH DETAILS ---
  const fetchHeroData = async (candId: string, jobId?: string) => {
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
      console.warn('Evidence graph fetch failed:', e);
    }
  };

  // --- HR CHAT ACTIONS ---
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

  const sendChatMessage = async (msgText?: string) => {
    const textToSend = (msgText !== undefined ? msgText : chatInput).trim();
    if (!textToSend || !selectedCandidate || chatLoading) return;

    const userMsg: ChatMessage = {
      role: 'user',
      content: textToSend,
      created_at: new Date().toISOString()
    };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/candidates/${selectedCandidate.candidate_id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: textToSend,
          job_id: chatJobId || undefined,
          save_history: true
        })
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: data.reply,
          created_at: new Date().toISOString()
        };
        setChatMessages(prev => [...prev, assistantMsg]);
        if (data.suggested_followups && data.suggested_followups.length > 0) {
          setSuggestedFollowups(data.suggested_followups);
        }
      } else {
        const errData = await res.json().catch(() => ({ detail: 'Error communicating with assistant' }));
        setChatMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `⚠️ Error: ${errData.detail || 'Could not process query.'}`,
            created_at: new Date().toISOString()
          }
        ]);
      }
    } catch (e: any) {
      setChatMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ Connection error: Unable to contact local AI backend (${e.message || 'offline'}).`,
          created_at: new Date().toISOString()
        }
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const clearChatHistory = () => {
    if (!selectedCandidate) return;
    setDeleteConfirmTarget({
      type: 'chat',
      candidateId: selectedCandidate.candidate_id,
      candidateName: selectedCandidate.full_name || selectedCandidate.candidate_id
    });
  };

  const selectCandidate = async (cand: Candidate) => {
    setSelectedCandidate(cand);
    setMobileDetailView(true);
    setHeroData(null); // Clear previous to show loading/skeleton
    await fetchHeroData(cand.candidate_id, activeMatchedJobId || undefined);
    fetchChatHistory(cand.candidate_id, chatJobId || activeMatchedJobId || undefined);
  };

  useEffect(() => {
    if (selectedCandidate && selectedTab === 'chat') {
      fetchChatHistory(selectedCandidate.candidate_id, chatJobId);
    }
  }, [selectedCandidate?.candidate_id, chatJobId, selectedTab, fetchChatHistory]);

  useEffect(() => {
    if (selectedTab === 'chat') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, chatLoading, selectedTab]);

  // --- RECRUITER ACTIONS ---
  const doAction = async (action: string) => {
    if (!selectedCandidate) return;
    try {
      const res = await fetch(`${API_BASE}/api/candidates/${selectedCandidate.candidate_id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      if (res.ok) {
        // Update local candidates state
        setAllCandidates(prev => prev.map(c =>
          c.candidate_id === selectedCandidate.candidate_id
            ? { ...c, recruiter_action: action }
            : c
        ));
      }
    } catch (e) {
      console.error('Recruiter action failed:', e);
    }
  };

  // --- DELETE CANDIDATES & MODAL ACTIONS ---
  const promptDeleteCandidate = (candidate?: any) => {
    const cand = candidate || selectedCandidate;
    if (!cand) return;
    setDeleteConfirmTarget({
      type: 'single',
      candidateId: cand.candidate_id,
      candidateName: cand.full_name || cand.candidate_id
    });
  };

  const deleteCandidate = () => promptDeleteCandidate();
  const deleteSpecificCandidate = (candidate: any) => promptDeleteCandidate(candidate);
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
          setDeleteConfirmTarget(null);
          showToast(`Candidate ${candName} deleted successfully`, 'info');
          setAllCandidates(prev => prev.filter(c => c.candidate_id !== candId));
          if (selectedCandidate?.candidate_id === candId) {
            setSelectedCandidate(null);
            setHeroData(null);
            setMobileDetailView(false);
          }
          fetchCandidates();
          loadDashboard();
        } else {
          const errData = await res.json().catch(() => ({}));
          showToast(errData.detail || 'Delete failed', 'error');
        }
      } else if (deleteConfirmTarget.type === 'all') {
        const res = await fetch(`${API_BASE}/api/candidates/uploaded/all`, {
          method: 'DELETE'
        });
        if (res.ok) {
          setDeleteConfirmTarget(null);
          const resData = await res.json().catch(() => ({ count: 0 }));
          showToast(`Deleted ${resData.count || 'all'} uploaded resumes`, 'info');
          setAllCandidates(prev => prev.filter(c => c.source !== 'UPLOADED'));
          setSelectedCandidate(null);
          setHeroData(null);
          setMobileDetailView(false);
          fetchCandidates();
          loadDashboard();
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
          setDeleteConfirmTarget(null);
          setChatMessages([]);
          showToast('Chat history cleared', 'info');
        } else {
          showToast('Failed to clear chat history', 'error');
        }
      }
    } catch (e: any) {
      showToast('Action failed: ' + (e.message || 'unknown error'), 'error');
    } finally {
      setDeleteInProgress(false);
    }
  };

  // --- JOB MATCH IN MODAL ---
  const runJobMatch = async () => {
    const targetJobId = selectedJobIdForMatch || (jobs.length > 0 ? jobs[0].job_id : '');
    if (!selectedCandidate || !targetJobId) return;
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
        setShowMatchModal(false);
        setActiveMatchedJobId(targetJobId);
        setChatJobId(targetJobId);
        await fetchHeroData(selectedCandidate.candidate_id, targetJobId);
      } else {
        showToast('Match failed.', 'error');
      }
    } catch (e: any) {
      showToast('Match failed: ' + e.message, 'error');
    } finally {
      setMatchingInProgress(false);
    }
  };

  // --- EXTRACT JD WITH AI ---
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
          minimum_years_experience: data.minimum_years_experience || prev.minimum_years_experience,
          required_skills: (data.required_skills || []).join(', '),
          preferred_skills: (data.preferred_skills || []).join(', '),
          education_requirements: (data.education_requirements || []).join(', '),
        }));
      }
    } catch (e: any) {
      showToast('JD extraction failed: ' + e.message, 'error');
    } finally {
      setExtractingJd(false);
    }
  };

  // --- SAVE MANUAL / EXTRACTED JOB ---
  const saveJob = async () => {
    if (!newJob.title.trim()) {
      showToast('Job title is required.', 'error');
      return;
    }
    const body = {
      ...newJob,
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
        setShowCreateJobModal(false);
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
        loadJobs();
      }
    } catch (e: any) {
      showToast('Failed to create job: ' + e.message, 'error');
    }
  };

  // --- BATCH UPLOAD ---
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
    if (!uploadQueue.length) return;
    setUploadStatus({
      processing: true,
      completed: 0,
      failed: 0,
      total: uploadQueue.length
    });

    let completed = 0;
    let failed = 0;

    for (let i = 0; i < uploadQueue.length; i++) {
      const file = uploadQueue[i];
      setCurrentProcessingFile(file.name);
      setUploadStage('Reading document and extracting text...');

      try {
        const fd = new FormData();
        fd.append('file', file);

        const stage1 = setTimeout(() => {
          setUploadStage('Local AI analyzing skills, employment history & dates (~15-25s)...');
        }, 1200);

        const stage2 = setTimeout(() => {
          setUploadStage('Deterministic evidence verification & calculating timeline...');
        }, 18000);

        const res = await fetch(`${API_BASE}/api/upload-cv`, {
          method: 'POST',
          body: fd
        });
        clearTimeout(stage1);
        clearTimeout(stage2);

        if (res.ok) {
          completed++;
          setUploadStage('✓ Verified candidate profile extracted successfully!');
          const createdCand = await res.json();
          setToastMessage({
            text: `✓ Uploaded ${createdCand.full_name || file.name}`,
            type: 'success'
          });
        } else {
          failed++;
          const errData = await res.json().catch(() => ({ detail: 'Upload error' }));
          setUploadStage(`✕ Issue: ${errData.detail || 'Failed'}`);
          setToastMessage({
            text: `Upload failed: ${errData.detail || file.name}`,
            type: 'error'
          });
        }
      } catch (e: any) {
        failed++;
        setUploadStage(`✕ Connection error: ${e.message}`);
        setToastMessage({
          text: `Upload failed: ${e.message}`,
          type: 'error'
        });
      }

      setUploadStatus(prev => ({
        ...prev,
        completed,
        failed,
      }));
    }

    setUploadQueue([]);
    setTimeout(() => {
      setShowUploadModal(false);
      setUploadStatus({ processing: false, completed: 0, failed: 0, total: 0 });
      setCurrentProcessingFile('');
      setUploadStage('');
      fetchCandidates(true);
      loadDashboard();
    }, 1500);
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
  const initials = (name?: string) => {
    if (!name) return '??';
    return name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
  };

  const copyToClipboard = (text: string, btnId: string) => {
    navigator.clipboard.writeText(text);
    const btn = document.getElementById(btnId);
    if (btn) {
      const originalText = btn.textContent;
      btn.textContent = '✓ Copied!';
      setTimeout(() => { btn.textContent = originalText; }, 2000);
    }
  };

  // Filter Logic
  const filteredCandidates = allCandidates.filter(c => {
    if (currentFilter !== 'ALL' && c.source !== currentFilter) return false;
    if (searchQuery) {
      const text = `${c.full_name || ''} ${(c.roles || []).join(' ')} ${(c.skills || []).join(' ')}`.toLowerCase();
      if (!text.includes(searchQuery.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div className="app-shell">
      {/* HEADER */}
      <header className="app-header" role="banner">
        <div className="header-left">
          <button className="mobile-menu-btn hidden-desktop" onClick={() => setShowMobileNav(!showMobileNav)} aria-label="Open navigation menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <div className="brand">
            <div className="brand-icon" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <div>
              <h1>CV Screening AI Agent</h1>
              <p className="subtitle">Evidence-backed candidate intelligence, running locally.</p>
            </div>
          </div>
        </div>

        <nav className="top-nav" role="navigation" aria-label="Main navigation">
          <button className={`nav-btn ${activePage === 'dashboard' ? 'active' : ''}`} onClick={() => navigateTo('dashboard')}>Dashboard</button>
          <button className={`nav-btn ${activePage === 'jobs' ? 'active' : ''}`} onClick={() => navigateTo('jobs')}>Jobs</button>
          <button className={`nav-btn ${activePage === 'library' ? 'active' : ''}`} onClick={() => navigateTo('library')}>Resume Library</button>
          <button className={`nav-btn ${activePage === 'evaluation' ? 'active' : ''}`} onClick={() => navigateTo('evaluation')}>Benchmarks</button>
        </nav>

        <div className="header-right">
          <div className="system-status" aria-live="polite">
            <span className={`status-dot ${systemHealth.ollama_status === 'connected' ? 'connected' : systemHealth.ollama_status === 'connected_model_missing' ? 'partial' : 'disconnected'}`}></span>
            <span className="status-text">
              {systemHealth.ollama_status === 'connected' ? `${systemHealth.ollama_model} · Local AI` : systemHealth.ollama_status === 'connected_model_missing' ? 'Model not found' : 'Ollama Offline'}
            </span>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => setShowUploadModal(true)} aria-label="Upload Resumes">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Upload
          </button>
        </div>
      </header>

      {/* DASHBOARD PAGE */}
      {activePage === 'dashboard' && (
        <main className="page-view active" role="main">
          <div className="page-content">
            <div className="page-header">
              <h2>Dashboard</h2>
              <p className="page-desc">Overview of your candidate intelligence pipeline.</p>
            </div>

            <div className="metrics-row">
              <div className="metric-card">
                <span className="metric-val">{dashboardMetrics.total_candidates}</span>
                <span className="metric-label">Candidates</span>
              </div>
              <div className="metric-card">
                <span className="metric-val">{dashboardMetrics.total_screened}</span>
                <span className="metric-label">Screened</span>
              </div>
              <div className="metric-card accent">
                <span className="metric-val">{dashboardMetrics.strong_matches}</span>
                <span className="metric-label">Strong Matches</span>
              </div>
              <div className="metric-card warn">
                <span className="metric-val">{dashboardMetrics.needs_review}</span>
                <span className="metric-label">Needs Review</span>
              </div>
              <div className="metric-card success">
                <span className="metric-val">{dashboardMetrics.interview_recommended}</span>
                <span className="metric-label">Interview Recommended</span>
              </div>
            </div>

            <div className="dash-grid">
              <div className="card">
                <h3>Score Distribution</h3>
                <div className="score-dist-chart">
                  {Object.entries(dashboardMetrics.score_distribution || {}).map(([range, count]) => {
                    const maxDist = Math.max(1, ...Object.values(dashboardMetrics.score_distribution));
                    const colors: Record<string, string> = { '90-100': '#22c55e', '80-89': '#4ade80', '70-79': '#6366f1', '60-69': '#eab308', '50-59': '#f97316', 'below-50': '#ef4444' };
                    return (
                      <div className="dist-bar-row" key={range}>
                        <span className="dist-bar-label">{range}</span>
                        <div className="dist-bar-track">
                          <div className="dist-bar-fill" style={{ width: `${(count / maxDist) * 100}%`, background: colors[range] || 'var(--accent)' }}></div>
                        </div>
                        <span className="dist-bar-val">{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="card">
                <h3>Screening Funnel</h3>
                <div className="funnel-chart">
                  {[
                    { label: 'Total Candidates', count: dashboardMetrics.total_candidates, color: 'var(--text-0)' },
                    { label: 'Screened', count: dashboardMetrics.total_screened, color: 'var(--accent-text)' },
                    { label: 'Strong Matches', count: dashboardMetrics.strong_matches, color: 'var(--success-text)' },
                    { label: 'Shortlisted', count: dashboardMetrics.shortlisted || 0, color: '#4ade80' },
                    { label: 'Interview', count: dashboardMetrics.interview_recommended, color: 'var(--info)' },
                  ].map(f => (
                    <div className="funnel-row" key={f.label}>
                      <span className="funnel-count" style={{ color: f.color }}>{f.count}</span>
                      <span className="funnel-label">{f.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card">
                <h3>Active Jobs</h3>
                <div className="dash-job-list">
                  {jobs.length > 0 ? (
                    jobs.slice(0, 5).map(j => (
                      <div className="dash-job-item" key={j.job_id} onClick={() => navigateTo('jobs')}>
                        <div>
                          <span className="dash-job-title">{j.title}</span>
                          <br />
                          <span className="dash-job-meta">{j.seniority} · {j.location || 'Remote'}</span>
                        </div>
                        <span className="badge status-pass">{j.status || 'ACTIVE'}</span>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state-sm">
                      No jobs created yet.{' '}
                      <button className="btn-link" onClick={() => setShowCreateJobModal(true)}>Create a job</button>
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <h3>System Info</h3>
                <div className="system-info-list">
                  {[
                    ['AI Engine', systemHealth.ollama_status === 'connected' ? '● Connected' : '○ Disconnected'],
                    ['Model', systemHealth.ollama_model],
                    ['Parser', systemHealth.parser_status],
                    ['Database', systemHealth.database_status],
                    ['Version', systemHealth.version],
                    ['Uploaded', `${dashboardMetrics.uploaded_candidates} resumes`],
                    ['Mock Data', `${dashboardMetrics.mock_candidates} candidates`],
                  ].map(([label, val]) => (
                    <div className="sys-info-row" key={label}>
                      <span className="sys-info-label">{label}</span>
                      <span className="sys-info-val">{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </main>
      )}

      {/* JOBS PAGE */}
      {activePage === 'jobs' && (
        <main className="page-view active">
          <div className="page-content">
            <div className="page-header">
              <div>
                <h2>Jobs</h2>
                <p className="page-desc">Create and manage job descriptions with editable requirements.</p>
              </div>
              <button className="btn btn-primary" onClick={() => setShowCreateJobModal(true)}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Create Job
              </button>
            </div>

            <div className="jobs-grid">
              {jobs.length > 0 ? (
                jobs.map(j => {
                  const skills = j.required_skills || j.mandatory_skills || [];
                  return (
                    <div className="card job-card" key={j.job_id}>
                      <div className="job-card-header">
                        <span className="job-card-title">{j.title}</span>
                        <span className="badge status-pass">{j.status || 'ACTIVE'}</span>
                      </div>
                      <div className="job-card-meta">
                        <span className="badge source-badge">{j.seniority}</span>
                        <span className="badge source-badge">{j.location || 'Remote'}</span>
                        <span className="badge source-badge">{j.minimum_years_experience || 0}+ yrs</span>
                      </div>
                      <div className="job-card-skills">
                        {skills.slice(0, 6).map(s => (
                          <span className="skill-pill" key={s}>{s}</span>
                        ))}
                        {skills.length > 6 && (
                          <span className="skill-pill">+{skills.length - 6}</span>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="empty-state" style={{ gridColumn: '1/-1' }}>
                  <div className="empty-icon">📋</div>
                  <h3>No jobs yet</h3>
                  <p>Create a job with requirements to start evidence-based screening.</p>
                  <button className="btn btn-primary" onClick={() => setShowCreateJobModal(true)}>Create Job</button>
                </div>
              )}
            </div>
          </div>
        </main>
      )}

      {/* RESUME LIBRARY PAGE */}
      {activePage === 'library' && (
        <main className="page-view active">
          <div className={`library-layout ${mobileDetailView ? 'mobile-show-detail' : 'mobile-show-list'}`}>
            <aside className="sidebar">
              <div className="card sidebar-card">
                <div className="card-header">
                  <h2>Candidates</h2>
                  <span className="count-badge">{filteredCandidates.length}</span>
                </div>

                <div className="library-controls">
                  <input
                    type="text"
                    className="search-input"
                    placeholder="Search name, skill, role..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    aria-label="Search candidates"
                  />
                  <div className="filter-pills">
                    {['ALL', 'UPLOADED', 'MOCK'].map(f => (
                      <button
                        className={`filter-btn ${currentFilter === f ? 'active' : ''}`}
                        key={f}
                        onClick={() => setCurrentFilter(f)}
                      >
                        {f.charAt(0) + f.slice(1).toLowerCase()}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="candidate-list-wrapper">
                  <div className="candidate-list">
                    {filteredCandidates.length > 0 ? (
                      filteredCandidates.map(c => {
                        const name = c.full_name || 'Unknown';
                        const isActive = selectedCandidate?.candidate_id === c.candidate_id;
                        const action = c.recruiter_action;
                        const actionBadge = action ? (
                          <span className={`badge status-${action === 'SHORTLIST' ? 'pass' : action === 'REJECT' ? 'fail' : 'verify'}`}>
                            {action}
                          </span>
                        ) : null;

                        return (
                          <div className={`cand-item ${isActive ? 'active' : ''}`} key={c.candidate_id} onClick={() => selectCandidate(c)}>
                            <div className="cand-avatar-sm">{initials(name)}</div>
                            <div className="cand-info">
                              <div className="cand-name">{name}</div>
                              <div className="cand-role">{c.roles?.length ? c.roles[0] : 'Professional'}</div>
                            </div>
                            <div className="cand-badges">
                              {actionBadge}
                              <span className={`badge source-badge ${c.source === 'MOCK' ? 'mock' : ''}`}>{c.source || 'UPLOADED'}</span>
                              <button
                                className="cand-delete-btn"
                                title={`Delete ${name}`}
                                aria-label={`Delete ${name}`}
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  deleteSpecificCandidate(c);
                                }}
                              >
                                ✕
                              </button>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="loading-state">No candidates matching criteria.</div>
                    )}
                  </div>
                </div>

                <div className="sidebar-footer">
                  <button className="btn btn-sm btn-ghost-danger" onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    deleteUploadedAll();
                  }}>Delete All Uploaded</button>
                </div>
              </div>
            </aside>

            <section className="workspace">
              {!selectedCandidate && (
                <div className="empty-state">
                  <div className="empty-icon">📂</div>
                  <h3>No Candidate Selected</h3>
                  <p>Select a candidate from the list or upload resumes to begin evidence-based screening.</p>
                  <button className="btn btn-primary" onClick={() => setShowUploadModal(true)}>Upload Resumes</button>
                </div>
              )}

              {selectedCandidate && (
                <div className="candidate-inspector">
                  {/* Mobile Back Button Header */}
                  <div className="mobile-back-header hidden-desktop">
                    <button className="btn btn-secondary btn-sm" onClick={() => setMobileDetailView(false)}>
                      ← Back to Candidates
                    </button>
                    <span className="mobile-cand-label">{selectedCandidate.full_name || 'Candidate Details'}</span>
                  </div>

                  {/* Hero */}
                  <div className="hero-section">
                    <div className="hero-left">
                      <div className="hero-avatar">{initials(selectedCandidate.full_name)}</div>
                      <div className="hero-info">
                        <div className="hero-name-row">
                          <h2>{selectedCandidate.full_name || 'Unknown'}</h2>
                          <span className={`badge source-badge ${selectedCandidate.source === 'MOCK' ? 'mock' : ''}`}>{selectedCandidate.source || 'UPLOADED'}</span>
                        </div>
                        <p className="hero-role">{selectedCandidate.roles?.length ? selectedCandidate.roles.join(', ') : selectedCandidate.current_title || 'Professional'}</p>
                        {heroData?.matched_job && (
                          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(99, 102, 241, 0.12)', border: '1px solid rgba(99, 102, 241, 0.3)', padding: '2px 10px', borderRadius: '14px', fontSize: '12px', margin: '4px 0 8px 0', width: 'fit-content' }}>
                            <span>🎯 Target JD: <strong>{heroData.matched_job.title}</strong> ({heroData.matched_job.seniority})</span>
                            <button
                              style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: '0 2px', fontSize: '13px', lineHeight: 1 }}
                              onClick={() => {
                                setActiveMatchedJobId('');
                                fetchHeroData(selectedCandidate.candidate_id);
                              }}
                              title="Reset to general score"
                            >✕</button>
                          </div>
                        )}
                        <div className="hero-meta">
                          <span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                              <circle cx={12} cy={10} r={3} />
                            </svg>
                            {selectedCandidate.location || 'Not specified'}
                          </span>
                          <span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                              <polyline points="22,6 12,13 2,6" />
                            </svg>
                            {selectedCandidate.email || 'N/A'}
                          </span>
                          <span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                              <circle cx={12} cy={12} r={10} />
                              <polyline points="12 6 12 12 16 14" />
                            </svg>
                            {selectedCandidate.notice_period || 'Not specified'}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="hero-right">
                      {heroData && (
                        <>
                          <div className="score-ring">
                            <svg viewBox="0 0 120 120" className="score-svg">
                              <circle className="score-bg" cx={60} cy="60" r="52" />
                              <circle
                                className="score-fill"
                                cx={60}
                                cy="60"
                                r="52"
                                style={{
                                  strokeDasharray: 2 * Math.PI * 52,
                                  strokeDashoffset: (2 * Math.PI * 52) - ((heroData.overall_score || 0) / 100) * (2 * Math.PI * 52),
                                  stroke: (heroData.overall_score || 0) >= 85 ? '#22c55e' : (heroData.overall_score || 0) >= 70 ? '#6366f1' : (heroData.overall_score || 0) >= 55 ? '#eab308' : '#ef4444'
                                }}
                              />
                              <text x={60} y={55} className="score-num">{Math.round(heroData.overall_score || 0)}</text>
                              <text x={60} y={72} className="score-label">{heroData.recommendation || 'SCORE'}</text>
                            </svg>
                          </div>
                          <div className="hero-exp">
                            <span className="exp-value">{heroData.experience_truth?.calculated_professional_experience || '0 months'}</span>
                            <span className="exp-label">Verified Experience</span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="action-bar">
                    <div className="action-bar-left">
                      <button className="btn btn-sm btn-success" onClick={() => doAction('SHORTLIST')}>✓ Shortlist</button>
                      <button className="btn btn-sm btn-secondary" onClick={() => doAction('MAYBE')}>? Maybe</button>
                      <button className="btn btn-sm btn-ghost-danger" onClick={() => doAction('REJECT')}>✕ Reject</button>
                      <button className="btn btn-sm btn-secondary" onClick={() => doAction('INTERVIEW')}>📞 Interview</button>
                    </div>
                    <div className="action-bar-right">
                      <button className="btn btn-sm btn-secondary" onClick={() => window.open(`${API_BASE}/api/candidates/${selectedCandidate.candidate_id}/original-file`, '_blank')}>📄 Original</button>
                      <button className="btn btn-sm btn-primary" onClick={() => {
                        if (!selectedJobIdForMatch && jobs.length > 0) {
                          setSelectedJobIdForMatch(activeMatchedJobId || jobs[0].job_id);
                        }
                        setShowMatchModal(true);
                      }}>🎯 Match JD</button>
                      <button className="btn btn-sm btn-ghost-danger" title="Delete Candidate" aria-label="Delete Candidate" onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        deleteCandidate();
                      }}>🗑️ Delete</button>
                    </div>
                  </div>

                  {/* Inspector Tabs */}
                  <div className="tab-bar" role="tablist">
                    {[
                      { id: 'why', label: 'Why This Candidate?' },
                      { id: 'chat', label: '💬 HR Chat' },
                      { id: 'missing', label: 'What Is Missing?' },
                      { id: 'exptruth', label: 'Experience Truth' },
                      { id: 'requirements', label: 'Requirements' },
                      { id: 'interview', label: 'Interview Questions' },
                      { id: 'evidence', label: `Evidence (${heroData?.evidence_graph?.all_evidence_nodes?.length || 0})` },
                      { id: 'overview', label: 'Overview' },
                      { id: 'json', label: 'Raw JSON' },
                    ].map(tab => (
                      <button
                        className={`tab-btn ${selectedTab === tab.id ? 'active' : ''}`}
                        role="tab"
                        aria-selected={selectedTab === tab.id}
                        onClick={() => setSelectedTab(tab.id)}
                        key={tab.id}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {/* Tab Panes */}
                  <div className="tab-content">
                    {/* WHY TAB */}
                    {selectedTab === 'why' && (
                      <div className="tab-pane active" role="tabpanel">
                        {heroData ? (
                          <>
                            <div className="score-explanation">
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                <div>
                                  <span style={{ fontSize: '24px', fontWeight: '800' }}>{Math.round(heroData.overall_score || 0)}</span>
                                  <span style={{ fontSize: '14px', color: 'var(--text-2)' }}> / 100</span>
                                </div>
                                <span className={`badge status-${(heroData.recommendation || '').includes('Strong') ? 'pass' : (heroData.recommendation || '').includes('Match') ? 'partial' : 'verify'}`} style={{ fontSize: '12px', padding: '4px 10px' }}>
                                  {heroData.recommendation}
                                </span>
                              </div>
                              <div className="score-breakdown-grid">
                                {Object.entries(heroData.score_breakdown?.factor_scores || {}).map(([key, f]: [string, any]) => {
                                  const pct = f.max > 0 ? (f.score / f.max) * 100 : 0;
                                  return (
                                    <div className="score-factor" key={key}>
                                      <span className="sf-label">{f.label || key}</span>
                                      <span className="sf-value">{Math.round(f.score)} <span style={{ fontSize: '11px', color: 'var(--text-3)' }}>/ {f.max}</span></span>
                                      <div className="sf-bar"><div className="sf-bar-fill" style={{ width: `${pct}%` }}></div></div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="why-list">
                              {(heroData.why_this_candidate || []).length > 0 ? (
                                (heroData.why_this_candidate || []).map((f: any, i: number) => (
                                  <div className="evidence-item" key={i}>
                                    <div className="ei-header">
                                      <span className="ei-title">✓ {f.factor}</span>
                                      <span className="badge status-pass">{f.confidence}</span>
                                    </div>
                                    <div className="ei-detail">{f.detail}</div>
                                    {f.evidence && <div className="ei-evidence">{f.evidence}</div>}
                                  </div>
                                ))
                              ) : (
                                <div className="empty-state-sm">No match factors available. Run a job match to see results.</div>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="loading-state">Loading candidate insights...</div>
                        )}
                      </div>
                    )}

                    {/* HR CHAT TAB */}
                    {selectedTab === 'chat' && (
                      <div className="tab-pane active" role="tabpanel">
                        <div className="chat-container">
                          {/* Chat Header Bar */}
                          <div className="chat-header-bar">
                            <div>
                              <div className="chat-header-title">
                                <span>💬</span>
                                <span>HR Intelligence Chat</span>
                                <span className="badge status-pass" style={{ fontSize: '11px', padding: '2px 8px' }}>
                                  Local Zero-Cloud AI
                                </span>
                              </div>
                              <div className="chat-header-meta">
                                Grounded in verified CV extraction & deterministic scoring • Zero cloud leakage
                              </div>
                            </div>

                            <div className="chat-header-actions">
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <label style={{ fontSize: '11px', color: 'var(--text-2)' }}>Job Context:</label>
                                <select
                                  className="chat-jd-select"
                                  value={chatJobId}
                                  onChange={(e) => setChatJobId(e.target.value)}
                                >
                                  <option value="">General (No Job Filter)</option>
                                  {jobs.map(j => (
                                    <option key={j.job_id} value={j.job_id}>
                                      {j.title} ({j.seniority})
                                    </option>
                                  ))}
                                </select>
                              </div>

                              {chatMessages.length > 0 && (
                                <button
                                  className="btn btn-sm btn-ghost-danger"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    clearChatHistory();
                                  }}
                                  title="Clear conversation history"
                                >
                                  🗑️ Clear
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Chat Messages Scroll Area */}
                          <div className="chat-messages-area">
                            {chatMessages.length === 0 ? (
                              <div className="chat-welcome-box">
                                <div style={{ fontSize: '36px', marginBottom: '8px' }}>🤖</div>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-0)', marginBottom: '6px' }}>
                                  Candidate Intelligence Assistant
                                </h3>
                                <p style={{ fontSize: '13px', color: 'var(--text-2)', maxWidth: '520px', margin: '0 auto 16px', lineHeight: 1.5 }}>
                                  Ask me any questions about <strong>{selectedCandidate?.full_name || 'this candidate'}</strong>.
                                  I can analyze skill alignment, explain score penalties, identify career gaps, draft outreach emails, and generate tailored interview verification questions.
                                </p>
                                <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                  <span className="badge status-pass">🔒 100% Local Inference</span>
                                  <span className="badge status-pass">🛡️ Evidence Grounded</span>
                                  <span className="badge status-pass">⚡ Zero Hallucination Guardrails</span>
                                </div>
                              </div>
                            ) : (
                              chatMessages.map((msg, idx) => {
                                const isUser = msg.role === 'user';
                                return (
                                  <div key={idx} className={`chat-message-row ${isUser ? 'user' : 'assistant'}`}>
                                    <div className={`chat-avatar ${isUser ? 'user' : 'assistant'}`}>
                                      {isUser ? '👤' : '🤖'}
                                    </div>
                                    <div className={`chat-bubble ${isUser ? 'user' : 'assistant'}`}>
                                      {isUser ? (
                                        <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                                      ) : (
                                        renderFormattedMessage(msg.content)
                                      )}
                                      {msg.created_at && (
                                        <div className="chat-bubble-time">
                                          {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })
                            )}

                            {chatLoading && (
                              <div className="chat-message-row assistant">
                                <div className="chat-avatar assistant">🤖</div>
                                <div className="chat-bubble assistant">
                                  <div className="chat-typing-indicator">
                                    <div className="typing-dot" style={{ animationDelay: '0ms' }}></div>
                                    <div className="typing-dot" style={{ animationDelay: '200ms' }}></div>
                                    <div className="typing-dot" style={{ animationDelay: '400ms' }}></div>
                                    <span style={{ marginLeft: '4px' }}>Agent synthesizing candidate evidence...</span>
                                  </div>
                                </div>
                              </div>
                            )}

                            <div ref={chatEndRef} />
                          </div>

                          {/* Quick Suggested Followup Chips */}
                          {suggestedFollowups.length > 0 && (
                            <div className="chat-chips-container">
                              <span className="chat-chip-label">Quick Prompts:</span>
                              {suggestedFollowups.slice(0, 4).map((prompt, pIdx) => (
                                <button
                                  key={pIdx}
                                  type="button"
                                  className="chat-chip-btn"
                                  onClick={() => sendChatMessage(prompt)}
                                  disabled={chatLoading}
                                >
                                  {prompt}
                                </button>
                              ))}
                            </div>
                          )}

                          {/* Input Bar */}
                          <form
                            className="chat-input-container"
                            onSubmit={(e) => {
                              e.preventDefault();
                              sendChatMessage();
                            }}
                          >
                            <input
                              type="text"
                              className="chat-textarea"
                              placeholder={`Ask about ${selectedCandidate?.full_name || 'candidate'} (e.g. 'Draft phone screen invite', 'Explain score')...`}
                              value={chatInput}
                              onChange={(e) => setChatInput(e.target.value)}
                              disabled={chatLoading}
                            />
                            <button
                              type="submit"
                              className="chat-send-btn"
                              disabled={!chatInput.trim() || chatLoading}
                            >
                              <span>Send</span>
                              <span>💬</span>
                            </button>
                          </form>
                        </div>
                      </div>
                    )}

                    {/* MISSING TAB */}
                    {selectedTab === 'missing' && (
                      <div className="tab-pane active" role="tabpanel">
                        {heroData ? (
                          <div className="missing-list">
                            {(heroData.what_is_missing || []).length > 0 ? (
                              (heroData.what_is_missing || []).map((m: any, i: number) => {
                                if (m.requirement === 'None') {
                                  return (
                                    <div className="evidence-item" key={i}>
                                      <div className="ei-title">✓ All requirements met</div>
                                      <div className="ei-detail">{m.evidence}</div>
                                    </div>
                                  );
                                }
                                const cls = m.status === 'MISSING' ? 'missing' : 'verify';
                                const icon = m.status === 'MISSING' ? '✕' : '⚠';
                                return (
                                  <div className={`evidence-item ${cls}`} key={i}>
                                    <div className="ei-header">
                                      <span className="ei-title">{icon} {m.requirement}</span>
                                      <span className={`status-badge status-${m.status === 'MISSING' ? 'fail' : 'verify'}`}>{m.status}</span>
                                    </div>
                                    <div className="ei-detail">{m.evidence}</div>
                                    <div className="ei-meta"><span>📋 {m.recommendation}</span></div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="empty-state-sm">No missing requirements detected.</div>
                            )}
                          </div>
                        ) : (
                          <div className="loading-state">Loading...</div>
                        )}
                      </div>
                    )}

                    {/* EXPERIENCE TRUTH TAB */}
                    {selectedTab === 'exptruth' && (
                      <div className="tab-pane active" role="tabpanel">
                        {heroData ? (
                          <div className="exp-truth-container">
                            <div className="truth-summary">
                              <div className="truth-stat">
                                <span className="ts-label">Candidate Claim</span>
                                <span className="ts-value amber">{heroData.experience_truth?.claimed_experience || 'N/A'}</span>
                              </div>
                              <div className="truth-stat">
                                <span className="ts-label">Calculated Professional</span>
                                <span className="ts-value green">{heroData.experience_truth?.calculated_professional_experience || '0 months'}</span>
                              </div>
                              <div className="truth-stat">
                                <span className="ts-label">Difference</span>
                                <span className={`ts-value ${heroData.experience_truth?.discrepancy_status === 'Consistent' ? 'green' : 'amber'}`}>
                                  {heroData.experience_truth?.difference || 'N/A'}
                                </span>
                              </div>
                              <div className="truth-stat">
                                <span className="ts-label">Status</span>
                                <span className={`ts-value ${heroData.experience_truth?.discrepancy_status === 'Consistent' ? 'green' : 'amber'}`}>
                                  {heroData.experience_truth?.discrepancy_status || 'N/A'}
                                </span>
                              </div>
                              <div className="truth-stat">
                                <span className="ts-label">Internship</span>
                                <span className="ts-value">{heroData.experience_truth?.calculated_internship_experience || '0 months'}</span>
                              </div>
                              <div className="truth-stat">
                                <span className="ts-label">Current Role</span>
                                <span className="ts-value">
                                  {heroData.experience_truth?.current_title || 'N/A'}
                                  <br />
                                  <span style={{ fontSize: '12px', color: 'var(--text-3)' }}>{heroData.experience_truth?.current_company || ''}</span>
                                </span>
                              </div>
                            </div>

                            {heroData.experience_truth?.discrepancy_status !== 'Consistent' ? (
                              <div className="truth-alert warn">
                                <strong>Timeline Discrepancy:</strong> The candidate's stated experience differs from the calculated employment timeline. This is a review flag, not a fraud determination.
                              </div>
                            ) : (
                              <div className="truth-alert ok">✓ Experience claim is consistent with the calculated employment timeline.</div>
                            )}

                            {/* Overlaps */}
                            {(heroData.experience_truth?.overlap_details || []).length > 0 && (
                              (heroData.experience_truth.overlap_details || []).map((o: any, idx: number) => (
                                <div className="truth-alert warn" key={idx}>⚠ Concurrent employment detected: {o.note}</div>
                              ))
                            )}

                            {/* Gaps */}
                            {(heroData.experience_truth?.career_gaps || []).length > 0 && (
                              <div style={{ marginTop: '8px' }}>
                                <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-2)', marginBottom: '6px' }}>
                                  Career Gaps ({(heroData.experience_truth.career_gaps || []).length})
                                </h4>
                                {(heroData.experience_truth.career_gaps || []).map((g: any, idx: number) => (
                                  <div className="truth-alert warn" key={idx}>📅 {g.duration_formatted} gap — {g.between}</div>
                                ))}
                              </div>
                            )}

                            {/* Timeline */}
                            {(heroData.employment_timeline || []).length > 0 && (
                              <div style={{ marginTop: '12px' }}>
                                <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-2)', marginBottom: '8px' }}>Employment Timeline</h4>
                                <div className="timeline-visual">
                                  {(heroData.employment_timeline || []).map((entry: any, idx: number) => (
                                    <div className="timeline-entry" key={idx}>
                                      <div className="te-info">
                                        <div className="te-role">{entry.title || entry.role || 'Role'}</div>
                                        <div className="te-company">{entry.company || 'Company'} <span className="te-type">{entry.employment_type || 'Full-time'}</span></div>
                                        <div className="te-dates">
                                          {entry.start_date && entry.start_date !== 'Unknown' ? (
                                            `${entry.start_date} → ${entry.is_current || !entry.end_date || entry.end_date === 'Present' ? 'Present' : entry.end_date}`
                                          ) : (
                                            'Date not verified'
                                          )}
                                        </div>
                                        <div className="te-duration">{entry.duration || '0 months'}</div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="loading-state">Loading...</div>
                        )}
                      </div>
                    )}

                    {/* REQUIREMENTS TAB */}
                    {selectedTab === 'requirements' && (
                      <div className="tab-pane active" role="tabpanel">
                        {heroData ? (
                          <div className="req-match-container">
                            {(heroData.requirement_analysis || []).length > 0 ? (
                              <div className="table-wrapper">
                                <table className="data-table">
                                  <thead>
                                    <tr>
                                      <th>Requirement</th>
                                      <th>Evidence</th>
                                      <th>Experience</th>
                                      <th>Status</th>
                                      <th>Confidence</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(heroData.requirement_analysis || []).map((r: any, i: number) => {
                                      const statusCls = r.status === 'PASS' ? 'pass' : r.status === 'PARTIAL' ? 'partial' : r.status === 'UNKNOWN' ? 'verify' : 'fail';
                                      return (
                                        <tr key={i}>
                                          <td><strong>{r.requirement}</strong></td>
                                          <td style={{ maxWidth: '300px', fontSize: '12px', color: 'var(--text-2)' }}>{r.evidence_summary || ''}</td>
                                          <td>{r.calculated_experience || 'N/A'}</td>
                                          <td><span className={`status-badge status-${statusCls}`}>{r.status}</span></td>
                                          <td><span className="badge source-badge">{String(r.confidence || '')}</span></td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            ) : (
                              <div className="empty-state-sm">No requirements analysis available. Match against a job description first.</div>
                            )}
                          </div>
                        ) : (
                          <div className="loading-state">Loading...</div>
                        )}
                      </div>
                    )}

                    {/* INTERVIEW TAB */}
                    {selectedTab === 'interview' && (
                      <div className="tab-pane active" role="tabpanel">
                        {heroData ? (
                          <div className="interview-container">
                            {(heroData.interview_questions || []).length > 0 ? (
                              (heroData.interview_questions || []).map((q: any, i: number) => (
                                <div className="interview-card" key={i}>
                                  <div className="iq-header">
                                    <span className="iq-requirement">
                                      <span className={`status-badge status-${q.status === 'MISSING' ? 'fail' : 'verify'}`}>{q.status}</span>
                                      &nbsp;{q.requirement}
                                    </span>
                                    <span className="badge source-badge">{q.priority}</span>
                                  </div>
                                  <div className="iq-reason">{q.reason}</div>
                                  <div className="iq-question">"{q.question}"</div>
                                  <div className="iq-footer">
                                    <button className="btn btn-sm btn-secondary" id={`copy-q-${i}`} onClick={() => copyToClipboard(q.question, `copy-q-${i}`)}>
                                      📋 Copy Question
                                    </button>
                                  </div>
                                </div>
                              ))
                            ) : (
                              <div className="empty-state-sm">No verification questions generated. All requirements appear to be well-evidenced.</div>
                            )}
                          </div>
                        ) : (
                          <div className="loading-state">Loading...</div>
                        )}
                      </div>
                    )}

                    {/* EVIDENCE TAB */}
                    {selectedTab === 'evidence' && (
                      <div className="tab-pane active" role="tabpanel">
                        {heroData ? (
                          <div className="evidence-container">
                            {(() => {
                              const skillGraphs = heroData.evidence_graph?.skill_graphs || {};
                              const high: any[] = [], medium: any[] = [], low: any[] = [];
                              Object.entries(skillGraphs).forEach(([skill, sg]: [string, any]) => {
                                const conf = sg.confidence || 'UNKNOWN';
                                const entry = { skill, ...sg };
                                if (conf === 'HIGH') high.push(entry);
                                else if (conf === 'MEDIUM') medium.push(entry);
                                else low.push(entry);
                              });

                              if (high.length === 0 && medium.length === 0 && low.length === 0) {
                                  return <div className="empty-state-sm">No evidence nodes available.</div>;
                              }

                              const renderSection = (title: string, items: any[], labelClass: string) => {
                                if (!items.length) return null;
                                return (
                                  <div style={{ marginBottom: '16px' }} key={title}>
                                    <div className="ev-section-title">{title} ({items.length})</div>
                                    <div className="ev-grid">
                                      {items.map(item => {
                                        const nodes = item.evidence_nodes || [];
                                        return (
                                          <div className="ev-card" key={item.skill}>
                                            <div className="ev-card-header">
                                              <span className="ev-skill">{item.skill}</span>
                                              <span className={`ev-source-label ${labelClass}`}>{item.confidence || 'UNKNOWN'}</span>
                                            </div>
                                            <div style={{ fontSize: '12px', color: 'var(--text-2)', margin: '2px 0' }}>{item.total_calculated_duration || '0 months'}</div>
                                            {nodes.slice(0, 2).map((n: any, idx: number) => (
                                              <div className="ev-quote" key={idx}>"{n.source_text || ''}"</div>
                                            ))}
                                            <div className="ev-card-footer">
                                              <span>{item.reasoning || ''}</span>
                                              <span className={`ev-source-label ${nodes[0]?.evidence_type === 'EMPLOYMENT' ? 'employment' : nodes[0]?.evidence_type === 'PROJECT' ? 'project' : 'skills'}`}>
                                                {nodes[0]?.evidence_type || 'SOURCE'}
                                              </span>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                );
                              };

                              return [
                                renderSection('High Confidence Evidence', high, 'employment'),
                                renderSection('Medium Confidence Evidence', medium, 'project'),
                                renderSection('Low Confidence — Skills Section Only', low, 'skills')
                              ];
                            })()}
                          </div>
                        ) : (
                          <div className="loading-state">Loading...</div>
                        )}
                      </div>
                    )}

                    {/* OVERVIEW TAB */}
                    {selectedTab === 'overview' && (
                      <div className="tab-pane active" role="tabpanel">
                        {selectedCandidate ? (
                          <div className="overview-grid">
                            <div className="card overview-section">
                              <h3>Skills ({(selectedCandidate.skills || []).length})</h3>
                              <div className="skills-cloud">
                                {(selectedCandidate.skills || []).length > 0 ? (
                                  (selectedCandidate.skills || []).map(s => <span className="skill-pill" key={s}>{s}</span>)
                                ) : (
                                  <span className="text-muted">None listed</span>
                                )}
                              </div>
                            </div>
                            <div className="card overview-section">
                              <h3>Extraction Confidence</h3>
                              <div className="conf-list">
                                {['skills', 'years_experience', 'roles', 'education', 'overall'].map(k => {
                                  const confObj = selectedCandidate.confidence || {};
                                  const val = confObj[k] !== undefined ? Math.round(confObj[k] * 100) : 80;
                                  return (
                                    <div className="conf-item" key={k}>
                                      <div className="conf-row">
                                        <span>{k.replace(/_/g, ' ')}</span>
                                        <span>{val}%</span>
                                      </div>
                                      <div className="conf-bar"><div className="conf-fill" style={{ width: `${val}%` }}></div></div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="card overview-section">
                              <h3>Education & Credentials</h3>
                              {(selectedCandidate.education || []).length > 0 ? (
                                (selectedCandidate.education || []).map((e, idx) => (
                                  <div style={{ padding: '6px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '13px' }} key={idx}>{e}</div>
                                ))
                              ) : (
                                <div className="text-muted">No education details</div>
                              )}
                              {(selectedCandidate.certifications || []).length > 0 && (
                                <div style={{ marginTop: '8px' }}>
                                  <strong style={{ fontSize: '12px', color: 'var(--text-3)' }}>Certifications</strong>
                                  {(selectedCandidate.certifications || []).map((c, idx) => (
                                    <div style={{ fontSize: '13px', padding: '4px 0' }} key={idx}>{c}</div>
                                  ))}
                                </div>
                              )}
                            </div>
                            <div className="card overview-section">
                              <h3>Projects ({(selectedCandidate.projects || []).length})</h3>
                              {(selectedCandidate.projects || []).length > 0 ? (
                                (selectedCandidate.projects || []).slice(0, 5).map((p, idx) => (
                                  <div style={{ padding: '6px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '13px' }} key={idx}>{String(p)}</div>
                                ))
                              ) : (
                                <div className="text-muted">No projects listed</div>
                              )}
                            </div>
                          </div>
                        ) : (
                          <div className="loading-state">Loading...</div>
                        )}
                      </div>
                    )}

                    {/* JSON TAB */}
                    {selectedTab === 'json' && (
                      <div className="tab-pane active" role="tabpanel">
                        {selectedCandidate && (
                          <div className="json-panel">
                            <div className="json-header-bar">
                              <h3>Candidate JSON</h3>
                              <button className="btn btn-sm btn-secondary" id="btn-copy-json" onClick={() => copyToClipboard(JSON.stringify(selectedCandidate.raw_data || selectedCandidate, null, 2), 'btn-copy-json')}>
                                Copy JSON
                              </button>
                            </div>
                            <pre className="json-code">{JSON.stringify(selectedCandidate.raw_data || selectedCandidate, null, 2)}</pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </section>
          </div>
        </main>
      )}

      {/* BENCHMARKS / EVALUATION PAGE */}
      {activePage === 'evaluation' && (
        <main className="page-view active">
          <div className="page-content">
            <div className="page-header">
              <div>
                <h2>Benchmark & Evaluation</h2>
                <p className="page-desc">Local Ollama extraction and deterministic matching performance evaluated against ground truth labels.</p>
              </div>
              <button className="btn btn-primary btn-sm" onClick={runEvaluation} disabled={evalLoading}>
                {evalLoading ? 'Calculating...' : 'Run Benchmark'}
              </button>
            </div>

            {evalMetrics && (
              <div className="metrics-row">
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.extraction_metrics?.skill_precision * 100).toFixed(1)}%</span>
                  <span className="metric-label">Skill Precision</span>
                </div>
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.extraction_metrics?.skill_recall * 100).toFixed(1)}%</span>
                  <span className="metric-label">Skill Recall</span>
                </div>
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.extraction_metrics?.skill_f1 * 100).toFixed(1)}%</span>
                  <span className="metric-label">Skill F1</span>
                </div>
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.matching_metrics?.accuracy * 100).toFixed(1)}%</span>
                  <span className="metric-label">Match Accuracy</span>
                </div>
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.matching_metrics?.precision_at_5 * 100).toFixed(1)}%</span>
                  <span className="metric-label">P@5</span>
                </div>
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.matching_metrics?.ndcg_at_10 * 100).toFixed(1)}%</span>
                  <span className="metric-label">NDCG@10</span>
                </div>
                <div className="metric-card">
                  <span className="metric-val">{(evalMetrics.matching_metrics?.mrr * 100).toFixed(1)}%</span>
                  <span className="metric-label">MRR</span>
                </div>
              </div>
            )}

            <div className="card">
              <h3>Sample Benchmark Results</h3>
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th>Job</th>
                      <th>Ground Truth</th>
                      <th>AI Recommendation</th>
                      <th>Score</th>
                      <th>Match</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalMetrics?.sample_evaluations ? (
                      (evalMetrics.sample_evaluations || []).map((s: any, idx: number) => (
                        <tr key={idx}>
                          <td><strong>{s.candidate_id}</strong></td>
                          <td>{s.job_id}</td>
                          <td><span className="badge source-badge">SHORTLIST</span></td>
                          <td><span className={`status-badge status-${s.recommendation === 'SHORTLIST' ? 'pass' : 'verify'}`}>{s.recommendation}</span></td>
                          <td><strong>{s.score}%</strong></td>
                          <td>
                            <span className={`status-badge status-${s.recommendation === 'SHORTLIST' ? 'pass' : 'fail'}`}>
                              {s.recommendation === 'SHORTLIST' ? 'MATCH' : 'MISMATCH'}
                            </span>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6} className="text-center text-muted" style={{ padding: '24px' }}>
                          {evalLoading ? 'Running evaluation benchmark, please wait...' : 'Click "Run Benchmark" to evaluate.'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </main>
      )}

      {/* UPLOAD MODAL */}
      {showUploadModal && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Upload Resumes"
          onClick={(e) => {
            if (e.target === e.currentTarget && !uploadStatus.processing) {
              setShowUploadModal(false);
            }
          }}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '18px' }}>📤</span>
                <h3>Upload Resumes</h3>
              </div>
              <button className="btn-icon" onClick={() => setShowUploadModal(false)} aria-label="Close">✕</button>
            </div>
            <div className="modal-body">
              {!uploadStatus.processing ? (
                <>
                  <div
                    className="drop-zone"
                    onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('dragover'); }}
                    onDragLeave={(e) => e.currentTarget.classList.remove('dragover')}
                    onDrop={handleFileDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <input type="file" ref={fileInputRef} onChange={handleFileChange} accept=".pdf,.docx,.txt" multiple hidden />
                    <div className="drop-zone-content">
                      <div className="upload-icon">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="17 8 12 3 7 8" />
                          <line x1="12" y1="3" x2="12" y2="15" />
                        </svg>
                      </div>
                      <p className="drop-title">Drag & drop resume files here</p>
                      <p className="drop-sub">or <button className="btn-link" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>browse files</button></p>
                      <span className="file-limits">PDF, DOCX, TXT · Up to 500 files</span>
                    </div>
                  </div>

                  {uploadQueue.length > 0 && (
                    <div className="file-queue">
                      <div className="queue-header">
                        <h4>Queue ({uploadQueue.length} {uploadQueue.length === 1 ? 'file' : 'files'})</h4>
                        <button className="btn-link" style={{ fontSize: '11px' }} onClick={() => setUploadQueue([])}>Clear</button>
                      </div>
                      <div className="queue-list">
                        {uploadQueue.map((f, i) => (
                          <div className="queue-item" key={i}>
                            <span className="queue-item-name">{f.name}</span>
                            <span className="queue-item-meta">{(f.size / 1024).toFixed(1)} KB</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="upload-active-progress">
                  <div className="upload-spinner-ring">
                    <div className="spinner-orbit"></div>
                    <span className="spinner-center-icon">⚡</span>
                  </div>

                  <h4 className="upload-stage-title">{uploadStage || 'Processing with Local AI...'}</h4>
                  {currentProcessingFile && (
                    <div className="upload-current-file">
                      <span>📄</span>
                      <span className="file-name">{currentProcessingFile}</span>
                    </div>
                  )}

                  <div className="progress-bar-bg" style={{ marginTop: '16px' }}>
                    <div
                      className="progress-bar-fill animated-shimmer"
                      style={{
                        width: `${Math.max(15, (uploadStatus.completed / uploadStatus.total) * 100)}%`
                      }}
                    ></div>
                  </div>

                  <div className="progress-stats" style={{ justifyContent: 'space-between', marginTop: '8px' }}>
                    <span>{uploadStatus.completed} of {uploadStatus.total} completed</span>
                    <span style={{ color: 'var(--accent-text)', fontWeight: 600 }}>Zero Cloud Leakage • Local AI</span>
                  </div>

                  <div className="upload-notice-box">
                    <p>💡 <strong>Local AI Verification:</strong> The model reads the full CV, calculates employment timelines, and verifies claims locally without sending private data to external clouds.</p>
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              {!uploadStatus.processing ? (
                <>
                  <button className="btn btn-secondary" onClick={() => { setUploadQueue([]); setShowUploadModal(false); }}>Cancel</button>
                  <button className="btn btn-primary" onClick={startBatchUpload} disabled={uploadQueue.length === 0}>
                    Upload & Process
                  </button>
                </>
              ) : (
                <>
                  <button className="btn btn-secondary" onClick={() => setShowUploadModal(false)}>
                    Run in Background
                  </button>
                  <span className="btn btn-primary disabled" style={{ opacity: 0.7, cursor: 'wait' }}>
                    ⚡ Processing...
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* JOB MATCH MODAL */}
      {showMatchModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Match Against Job">
          <div className="modal-content sm">
            <div className="modal-header">
              <h3>Match Against Job Description</h3>
              <button className="btn-icon" onClick={() => setShowMatchModal(false)} aria-label="Close">✕</button>
            </div>
            <div className="modal-body">
              <label className="form-label" htmlFor="jobSelectInput">Select Job:</label>
              <select
                className="form-select"
                id="jobSelectInput"
                value={selectedJobIdForMatch}
                onChange={(e) => setSelectedJobIdForMatch(e.target.value)}
                aria-label="Select Job"
              >
                {jobs.length > 0 ? (
                  jobs.map(j => (
                    <option value={j.job_id} key={j.job_id}>{j.title} ({j.seniority})</option>
                  ))
                ) : (
                  <option value="">No jobs available</option>
                )}
              </select>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowMatchModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={runJobMatch} disabled={matchingInProgress}>
                {matchingInProgress ? 'Scoring...' : 'Run Matching'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CREATE JOB MODAL */}
      {showCreateJobModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Create Job">
          <div className="modal-content lg">
            <div className="modal-header">
              <h3>Create Job</h3>
              <button className="btn-icon" onClick={() => setShowCreateJobModal(false)} aria-label="Close">✕</button>
            </div>
            <div className="modal-body">
              <div className="form-section">
                <label className="form-label">Paste Job Description (optional — AI will extract requirements)</label>
                <textarea
                  className="form-textarea"
                  rows={6}
                  placeholder="Paste the full job description here..."
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                ></textarea>
                <button className="btn btn-sm btn-secondary" id="btnExtractJD" onClick={extractJD} disabled={extractingJd}>
                  {extractingJd ? '🔄 Extracting...' : '🤖 Extract Requirements with AI'}
                </button>
              </div>

              <div className="form-divider"><span>or fill manually</span></div>

              <div className="form-grid">
                <div className="form-group">
                  <label className="form-label" htmlFor="jobTitle">Job Title *</label>
                  <input
                    className="form-input"
                    id="jobTitle"
                    placeholder="e.g. Senior React Engineer"
                    value={newJob.title}
                    onChange={(e) => setNewJob({ ...newJob, title: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="jobSeniority">Seniority</label>
                  <select
                    className="form-select"
                    id="jobSeniority"
                    value={newJob.seniority}
                    onChange={(e) => setNewJob({ ...newJob, seniority: e.target.value })}
                  >
                    <option value="Junior">Junior</option>
                    <option value="Mid-level">Mid-level</option>
                    <option value="Senior">Senior</option>
                    <option value="Lead">Lead</option>
                    <option value="Staff">Staff</option>
                    <option value="Principal">Principal</option>
                    <option value="Manager">Manager</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="jobLocation">Location</label>
                  <input
                    className="form-input"
                    id="jobLocation"
                    placeholder="e.g. Austin, TX"
                    value={newJob.location}
                    onChange={(e) => setNewJob({ ...newJob, location: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="jobMinExp">Min. Experience (years)</label>
                  <input
                    className="form-input"
                    id="jobMinExp"
                    type="number"
                    min="0"
                    step="0.5"
                    value={newJob.minimum_years_experience}
                    onChange={(e) => setNewJob({ ...newJob, minimum_years_experience: parseFloat(e.target.value) || 0 })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="jobReqSkills">Required Skills (comma-separated)</label>
                <input
                  className="form-input"
                  id="jobReqSkills"
                  placeholder="React, Node.js, AWS, Python"
                  value={newJob.required_skills}
                  onChange={(e) => setNewJob({ ...newJob, required_skills: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="jobPrefSkills">Preferred Skills (comma-separated)</label>
                <input
                  className="form-input"
                  id="jobPrefSkills"
                  placeholder="Docker, Kubernetes, GraphQL"
                  value={newJob.preferred_skills}
                  onChange={(e) => setNewJob({ ...newJob, preferred_skills: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="jobEdu">Education Requirements (comma-separated)</label>
                <input
                  className="form-input"
                  id="jobEdu"
                  placeholder="BS Computer Science"
                  value={newJob.education_requirements}
                  onChange={(e) => setNewJob({ ...newJob, education_requirements: e.target.value })}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowCreateJobModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={saveJob}>Create Job</button>
            </div>
          </div>
        </div>
      )}

      {/* MOBILE NAV OVERLAY */}
      {showMobileNav && (
        <div className="mobile-nav-overlay" onClick={() => setShowMobileNav(false)}>
          <nav className="mobile-nav" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-nav-header">
              <span className="mobile-nav-title">Navigation</span>
              <button className="btn-icon" onClick={() => setShowMobileNav(false)} aria-label="Close menu">✕</button>
            </div>
            <button className={`mobile-nav-btn ${activePage === 'dashboard' ? 'active' : ''}`} onClick={() => navigateTo('dashboard')}>
              📊 Dashboard
            </button>
            <button className={`mobile-nav-btn ${activePage === 'jobs' ? 'active' : ''}`} onClick={() => navigateTo('jobs')}>
              💼 Jobs
            </button>
            <button className={`mobile-nav-btn ${activePage === 'library' ? 'active' : ''}`} onClick={() => navigateTo('library')}>
              👥 Resume Library
            </button>
            <button className={`mobile-nav-btn ${activePage === 'evaluation' ? 'active' : ''}`} onClick={() => navigateTo('evaluation')}>
              📈 Benchmarks
            </button>
          </nav>
        </div>
      )}

      {/* DELETE CONFIRMATION MODAL */}
      {deleteConfirmTarget && (
        <div 
          className="modal-backdrop" 
          role="dialog" 
          aria-modal="true" 
          aria-labelledby="delete-dialog-title"
          onClick={() => !deleteInProgress && setDeleteConfirmTarget(null)}
        >
          <div 
            className="modal-content sm delete-modal" 
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 id="delete-dialog-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: 'var(--danger)' }}>⚠️</span>
                {deleteConfirmTarget.type === 'single' && 'Delete Candidate'}
                {deleteConfirmTarget.type === 'all' && 'Delete All Uploaded Resumes'}
                {deleteConfirmTarget.type === 'chat' && 'Clear Chat History'}
              </h3>
              <button 
                className="btn-icon" 
                disabled={deleteInProgress}
                onClick={() => setDeleteConfirmTarget(null)} 
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              {deleteConfirmTarget.type === 'single' && (
                <div>
                  <p style={{ marginBottom: '10px', fontSize: '14px', color: 'var(--text-0)' }}>
                    Are you sure you want to permanently delete candidate{' '}
                    <strong style={{ color: 'var(--accent-text)' }}>{deleteConfirmTarget.candidateName}</strong>?
                  </p>
                  <p style={{ fontSize: '12px', color: 'var(--text-3)', lineHeight: 1.5 }}>
                    ID: <code>{deleteConfirmTarget.candidateId}</code><br />
                    All extracted skills, evidence graphs, match scores, and uploaded resume files will be permanently deleted from the database.
                  </p>
                </div>
              )}
              {deleteConfirmTarget.type === 'all' && (
                <div>
                  <p style={{ marginBottom: '10px', fontSize: '14px', color: 'var(--text-0)' }}>
                    Are you sure you want to delete <strong style={{ color: 'var(--danger-text)' }}>ALL uploaded resumes</strong>?
                  </p>
                  <p style={{ fontSize: '12px', color: 'var(--text-3)', lineHeight: 1.5 }}>
                    This action will purge all uploaded candidate files, extractions, and scores. Mock benchmark candidates will be preserved. This cannot be undone.
                  </p>
                </div>
              )}
              {deleteConfirmTarget.type === 'chat' && (
                <div>
                  <p style={{ marginBottom: '10px', fontSize: '14px', color: 'var(--text-0)' }}>
                    Are you sure you want to clear the conversation history for{' '}
                    <strong style={{ color: 'var(--accent-text)' }}>{deleteConfirmTarget.candidateName}</strong>?
                  </p>
                  <p style={{ fontSize: '12px', color: 'var(--text-3)', lineHeight: 1.5 }}>
                    All past messages exchanged with the AI Recruiter will be cleared.
                  </p>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button 
                className="btn btn-secondary" 
                disabled={deleteInProgress}
                onClick={() => setDeleteConfirmTarget(null)}
              >
                Cancel
              </button>
              <button 
                className="btn btn-danger" 
                disabled={deleteInProgress}
                onClick={handleExecuteDelete}
              >
                {deleteInProgress ? 'Deleting...' : (
                  deleteConfirmTarget.type === 'chat' ? 'Yes, Clear History' : 'Yes, Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* FLOATING BACKGROUND PROGRESS PILL */}
      {uploadStatus.processing && !showUploadModal && (
        <div className="floating-progress-pill" onClick={() => setShowUploadModal(true)} role="status">
          <div className="pill-pulse-dot"></div>
          <span className="pill-text">Extracting resume with Local AI ({uploadStatus.completed}/{uploadStatus.total})...</span>
          <span className="pill-action">View</span>
        </div>
      )}

      {/* TOAST NOTIFICATION */}
      {toastMessage && (
        <div className={`app-toast toast-${toastMessage.type}`} role="alert">
          <span className="toast-text">{toastMessage.text}</span>
          <button className="toast-close" onClick={() => setToastMessage(null)} aria-label="Dismiss">✕</button>
        </div>
      )}
    </div>
  );
}
