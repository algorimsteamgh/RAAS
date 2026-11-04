# Raashiring Enterprise AI Platform — Frontend Architecture

> **Modern Enterprise UI • Corporate Blue Design System • React 18 + TypeScript + Vite**  
> High-performance candidate intelligence dashboard, interactive candidate inspector, automated screening, and recruiter analytics.

---

## 1. Overview & Design Philosophy

The Raashiring frontend is engineered as a responsive, high-contrast, corporate enterprise application. It replaces previous prototype designs with a polished **Corporate Blue** color palette inspired by enterprise leaders (Azure, Linear, GitHub Enterprise, Workday):

- **Primary Colors:**
  - Corporate Navy (`#0B192C`, `#1E3E62`)
  - Accent / Brand Blue (`#008DDA`, `#00A9FF`, `#2563EB`)
  - Crisp Enterprise White (`#FFFFFF`, `#F8FAFC`, `#F1F5F9`)
  - Muted Borders & Dividers (`#E2E8F0`, `#CBD5E1`)
  - Semantic Status Colors: Emerald green (`#10B981` Shortlist), Amber (`#F59E0B` Review), Rose (`#EF4444` Do Not Shortlist).
- **Typography:** Plus Jakarta Sans for UI headers and body, JetBrains Mono for candidate hashes, evidence offsets, and code metrics.

---

## 2. Directory Structure

```
frontend/
├── index.html                   # HTML entry point with Raashiring favicon & Google Fonts
├── package.json                 # React, Lucide Icons, Vite, TypeScript, Tailwind
├── vite.config.ts               # Vite bundler configuration
├── tsconfig.json                # Strict TypeScript configuration
├── nginx.conf                   # Production Nginx reverse proxy configuration
├── public/
│   ├── logo.png                 # Raashiring corporate badge
│   ├── raashiring-logo.png      # Primary high-res logo
│   ├── raashiring-icon.png      # Icon mark
│   └── favicon-32.png / 64.png  # Enterprise browser favicons
└── src/
    ├── main.tsx                 # React DOM mount point & ErrorBoundary wrapper
    ├── App.tsx                  # Master application orchestrator, state store, & modal flows
    ├── index.css                # Corporate Blue CSS design system & utility classes
    ├── assets/                  # Bundled logos and brand assets
    └── components/
        ├── TopHeader.tsx        # Global enterprise navbar, status badge, search & controls
        ├── Sidebar.tsx          # Navigation sidebar (Dashboard, Candidates, Match, Automation, Settings)
        ├── DashboardView.tsx    # Executive KPIs, analytics charts, recent candidate pipelines
        ├── AutomationView.tsx   # Automated ingestion rules, triggers, and scheduled evaluations
        ├── SettingsView.tsx     # LLM model selection, Ollama endpoints, scoring weights
        ├── ErrorBoundary.tsx    # Production error boundary with recovery actions
        ├── IsometricCube.tsx    # 3D animated platform visual
        ├── TechIcons.tsx        # High-res SVG tech stack badges
        └── jobIconUtils.tsx     # Role-specific badge and icon mapping
```

---

## 3. Key Views & Navigation Modules

### 1. Executive Dashboard (`DashboardView.tsx`)
- **Key Metrics Overview**: Total candidates, screened resumes, average match score, active jobs, and shortlist conversion rate.
- **Dynamic Filters**: Filter metrics by Target Job Description (`job_id`) and Candidate Source (`ALL`, `UPLOADED`, `MOCK`).
- **Score Distribution Charts**: Interactive distribution breakdown across `SHORTLIST` (≥75%), `REVIEW` (50–74%), and `DO_NOT_SHORTLIST` (<50%).
- **Recent Candidate Feed**: Quick-inspection cards showing candidate skills, experience years, and recommendation pills.

### 2. Candidates Inspector & Resume Library (`App.tsx`)
- **Multi-Source Switching**: Toggle between `[All Resumes]`, `[Uploaded]`, and synthetic evaluation cohorts.
- **Candidate Detail Inspector**:
  - Full candidate contact details, verified skills, and experience timeline.
  - **4-Pillar Score Breakdown**: Mandatory skills, technical core, experience depth, and domain fit.
  - **Evidence Verifier**: Exact quote highlights and character offsets matching the original PDF/DOCX resume.
  - **Original Document Viewer**: Byte-level document streaming and preview.

### 3. Match & Screen Engine (`App.tsx`)
- Multi-candidate or single-candidate batch matching against enterprise Job Descriptions.
- Explainable AI reasoning generated deterministically with Ollama LLM extraction.

### 4. Automation Hub (`AutomationView.tsx`)
- Configure automated resume ingestion pipelines, automated email notifications, and webhook triggers.

### 5. Settings & LLM Engine Config (`SettingsView.tsx`)
- Switch active inference models (`qwen2.5:1.5b`, `qwen3.5`, `qwen3:8b`, or Azure OpenAI endpoints).
- Adjust deterministic scoring weights (Mandatory 40%, Technical 25%, Experience 20%, Domain 10%, Preferred 5%).

---

## 4. Local Development

### Prerequisites
- Node.js 18+ (Node 20+ recommended)
- npm or pnpm

### Installation & Run
```bash
cd frontend

# Install dependencies
npm install

# Start Vite hot-reload development server
npm run dev
```

The dev server will run on `http://localhost:5173` and proxy API calls to `http://localhost:8000`.

### Production Build & Linting
```bash
# Type check and build optimized static assets into dist/
npm run build

# Run linter
npm run lint

# Preview production build locally
npm run preview
```

---

## 5. Production Nginx Deployment

When containerized via `Dockerfile.frontend`:
1. Multi-stage build compiles TypeScript and bundles assets via Vite.
2. Nginx serves the compiled static files from `/usr/share/nginx/html`.
3. Nginx proxies `/api/*` requests internally to the backend container app on port 8000 with a 300-second read timeout for LLM inference streams.
4. Liveness probe is available at `/healthz`.
