export default function IsometricCube() {
  return (
    <div className="isometric-cube-container" aria-hidden="true">
      <svg
        width="160"
        height="140"
        viewBox="0 0 160 140"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="isometric-cube-svg"
      >
        <defs>
          <linearGradient id="corp-top-face" x1="40" y1="20" x2="120" y2="70" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#155EEF" />
            <stop offset="100%" stopColor="#1D4ED8" />
          </linearGradient>

          <linearGradient id="corp-left-face" x1="20" y1="50" x2="80" y2="90" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#1E40AF" />
            <stop offset="100%" stopColor="#172554" />
          </linearGradient>

          <linearGradient id="corp-right-face" x1="80" y1="50" x2="140" y2="90" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#1D4ED8" />
            <stop offset="100%" stopColor="#1E3A8A" />
          </linearGradient>

          <linearGradient id="corp-mid-top" x1="40" y1="20" x2="120" y2="70" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#3B82F6" />
            <stop offset="100%" stopColor="#2563EB" />
          </linearGradient>

          <linearGradient id="corp-bot-top" x1="40" y1="20" x2="120" y2="70" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#60A5FA" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
        </defs>

        {/* Ambient Subtle Shadow on White Surface */}
        <ellipse cx="80" cy="118" rx="56" ry="18" fill="#E2E8F0" />

        {/* ================= LAYER 1: BASE COMPUTE LAYER ================= */}
        <g transform="translate(0, 40)">
          {/* Left Side */}
          <path d="M 28 50 L 80 80 L 80 92 L 28 62 Z" fill="#1E3A8A" />
          {/* Right Side */}
          <path d="M 80 80 L 132 50 L 132 62 L 80 92 Z" fill="#172554" />
          {/* Top Face */}
          <path d="M 80 20 L 132 50 L 80 80 L 28 50 Z" fill="url(#corp-bot-top)" stroke="#DBEAFE" strokeWidth="1" />
          {/* Front Status Indicator Dot */}
          <circle cx="80" cy="86" r="2.5" fill="#16845B" />
        </g>

        {/* ================= LAYER 2: LOCAL AI MODEL (QWEN) ================= */}
        <g transform="translate(0, 20)">
          {/* Left Side */}
          <path d="M 28 46 L 80 76 L 80 86 L 28 56 Z" fill="#1E40AF" />
          {/* Right Side */}
          <path d="M 80 76 L 132 46 L 132 56 L 80 86 Z" fill="#1E3A8A" />
          {/* Top Face */}
          <path d="M 80 16 L 132 46 L 80 76 L 28 46 Z" fill="url(#corp-mid-top)" stroke="#BFDBFE" strokeWidth="1" />
          {/* Front Status Indicator Dot */}
          <circle cx="80" cy="81" r="2.5" fill="#16845B" />
        </g>

        {/* ================= LAYER 3: INTELLIGENCE & SCORING RUNTIME ================= */}
        <g transform="translate(0, 0)">
          {/* Left Side */}
          <path d="M 28 42 L 80 72 L 80 84 L 28 54 Z" fill="url(#corp-left-face)" />
          {/* Right Side */}
          <path d="M 80 72 L 132 42 L 132 54 L 80 84 Z" fill="url(#corp-right-face)" />
          {/* Top Face */}
          <path d="M 80 12 L 132 42 L 80 72 L 28 42 Z" fill="url(#corp-top-face)" stroke="#93C5FD" strokeWidth="1" />
          {/* Front Status Indicator Dot */}
          <circle cx="80" cy="78" r="2.5" fill="#16845B" />

          {/* Clean Flat Monogram "R" on Top Face */}
          <g transform="translate(80, 42) rotate(30) skewX(-30) scale(0.85)">
            <path
              d="M -14 -14 L -4 -14 C 1 -14, 5 -11, 5 -5 C 5 1, 1 5, -4 5 L -8 5 L -8 14 L -14 14 Z M -8 -9 L -4 -9 C -1 -9, 0 -7, 0 -5 C 0 -3, -1 -1, -4 -1 L -8 -1 Z"
              fill="#FFFFFF"
            />
            <path
              d="M -2 4 L 7 14 L 1 14 L -7 5 Z"
              fill="#FFFFFF"
            />
          </g>
        </g>
      </svg>
    </div>
  );
}
