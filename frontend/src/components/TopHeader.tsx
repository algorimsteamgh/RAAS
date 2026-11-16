import { useState, useEffect, useRef } from 'react';

interface TopHeaderProps {
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  onSearchSubmit: () => void;
  openMobileNav: () => void;
  onUploadClick: () => void;
  userName?: string;
  navigateTo: (page: string) => void;
}

export default function TopHeader({
  searchQuery,
  setSearchQuery,
  onSearchSubmit,
  openMobileNav,
  userName = 'Tharun',
  navigateTo,
}: TopHeaderProps) {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  // Time-based greeting with "Good Evening" as default matching screenshot
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'Good Morning';
    if (hour >= 12 && hour < 17) return 'Good Afternoon';
    return 'Good Evening';
  };
  const greeting = getGreeting();

  // Listen for Cmd+K / Ctrl+K keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        const input = document.getElementById('global-search-input');
        input?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Click outside and Escape key to close popovers
  useEffect(() => {
    if (!showNotifications && !showProfileMenu) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setShowProfileMenu(false);
      }
    };
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowNotifications(false);
        setShowProfileMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [showNotifications, showProfileMenu]);

  return (
    <header className="app-top-header" role="banner">
      {/* Left: Mobile toggle & Greeting */}
      <div className="top-header-left">
        <button
          className="mobile-toggle-btn hidden-desktop"
          onClick={openMobileNav}
          aria-label="Toggle navigation menu"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>

        <div className="greeting-wrapper">
          <h1 className="greeting-title">
            <span className="greeting-time">{greeting}, </span>
            <span className="greeting-name">{userName}</span>
            <span className="greeting-wave"> 👋</span>
          </h1>
          <p className="greeting-subtitle">Here's your candidate intelligence overview.</p>
        </div>
      </div>

      {/* Middle/Right Controls matching screenshot */}
      <div className="top-header-right-group">
        {/* Global Search Bar */}
        <div className="top-header-search-bar">
          <div className="global-search-box">
            <svg
              className="search-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#64748B"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>

            <input
              id="global-search-input"
              type="text"
              className="global-search-input"
              placeholder="Search candidates, jobs, or resumes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onSearchSubmit();
                }
              }}
              aria-label="Search candidates, jobs, or resumes"
            />

            <kbd className="search-shortcut" title="Press ⌘K to search">
              ⌘K
            </kbd>
          </div>
        </div>

        {/* Notification Bell */}
        <div className="header-control-wrapper" ref={notifRef}>
          <button
            className="control-icon-btn"
            onClick={() => {
              setShowNotifications(!showNotifications);
              setShowProfileMenu(false);
            }}
            aria-label="View notifications"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#172554" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            <span className="notification-dot" />
          </button>

          {showNotifications && (
            <div className="popover-dropdown notifications-dropdown">
              <div className="popover-header">
                <span className="popover-title">Notifications</span>
                <span className="popover-badge">3 New</span>
              </div>
              <div className="notification-list">
                <div className="notification-item">
                  <div className="notif-dot blue" />
                  <div className="notif-text">
                    <p className="notif-msg"><strong>CAND-001</strong> screened against Senior Python Backend Engineer.</p>
                    <span className="notif-time">10 mins ago</span>
                  </div>
                </div>
                <div className="notification-item">
                  <div className="notif-dot green" />
                  <div className="notif-text">
                    <p className="notif-msg">AI inference engine active on <strong>qwen2.5:1.5b</strong>.</p>
                    <span className="notif-time">1 hour ago</span>
                  </div>
                </div>
                <div className="notification-item">
                  <div className="notif-dot blue" />
                  <div className="notif-text">
                    <p className="notif-msg">Screened candidates pool synchronized with SQLite.</p>
                    <span className="notif-time">2 hours ago</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Profile Avatar KT matching screenshot */}
        <div className="header-control-wrapper" ref={profileRef}>
          <button
            className="profile-avatar-btn"
            onClick={() => {
              setShowProfileMenu(!showProfileMenu);
              setShowNotifications(false);
            }}
            aria-label="User profile menu"
          >
            <span className="avatar-initials">KT</span>
          </button>

          {showProfileMenu && (
            <div className="popover-dropdown profile-dropdown">
              <div className="profile-dropdown-user">
                <div className="avatar-preview-circle">KT</div>
                <div className="profile-text-block">
                  <span className="user-name">{userName}</span>
                  <span className="user-email">tharun@raashiring.enterprise</span>
                </div>
              </div>

              <div className="dropdown-divider" />

              <div className="dropdown-menu-list">
                <button
                  className="dropdown-menu-item"
                  onClick={() => {
                    navigateTo('settings');
                    setShowProfileMenu(false);
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                  <span>System Settings</span>
                </button>
                <button
                  className="dropdown-menu-item"
                  onClick={() => {
                    navigateTo('evaluation');
                    setShowProfileMenu(false);
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="20" x2="18" y2="10" />
                    <line x1="12" y1="20" x2="12" y2="4" />
                    <line x1="6" y1="20" x2="6" y2="14" />
                  </svg>
                  <span>Benchmarks &amp; Gold Sets</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
