export default function NeuroVaultLogo({ compact = false, showName = !compact, className = "", subtitle = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        viewBox="0 0 64 64"
        className={compact ? "h-8 w-8 shrink-0" : "h-10 w-10 shrink-0"}
        role="img"
        aria-label="NeuroVault logo"
      >
        <defs>
          <linearGradient id="nv-brain" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#22c0ff" />
            <stop offset="100%" stopColor="#1146b8" />
          </linearGradient>
          <linearGradient id="nv-vault" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6b7887" />
            <stop offset="100%" stopColor="#2a3442" />
          </linearGradient>
        </defs>
        <path
          d="M30 6C23.2 6 17.6 10.8 16.3 17.2C9.8 18.5 5 24.1 5 30C5 36.5 10.2 42.3 16.8 43.1C18.4 49.1 23.8 53 30 53V6Z"
          fill="url(#nv-brain)"
        />
        <path
          d="M30 17C25.5 17 22 20.5 22 25"
          stroke="#f8fafc"
          strokeWidth="2.6"
          strokeLinecap="round"
          fill="none"
        />
        <path d="M22 25C18 25 15 28 15 32" stroke="#f8fafc" strokeWidth="2.6" strokeLinecap="round" fill="none" />
        <path d="M24 35C24 39 27 42 31 42" stroke="#f8fafc" strokeWidth="2.6" strokeLinecap="round" fill="none" />
        <circle cx="30" cy="17" r="1.9" fill="#f8fafc" />
        <circle cx="22" cy="25" r="1.9" fill="#f8fafc" />
        <circle cx="15" cy="32" r="1.9" fill="#f8fafc" />
        <circle cx="24" cy="35" r="1.9" fill="#f8fafc" />
        <circle cx="31" cy="42" r="1.9" fill="#f8fafc" />
        <path d="M34 8A24 24 0 1 1 34 56V8Z" fill="url(#nv-vault)" />
        <circle cx="34" cy="32" r="15" fill="#1f2937" opacity="0.35" />
        <circle cx="34" cy="32" r="5.2" fill="#94a3b8" />
        <circle cx="34" cy="32" r="3.8" fill="#334155" />
        <path d="M34 20V27M34 37V44M22 32H29M39 32H46M26 24L30 28M38 36L42 40M26 40L30 36M38 28L42 24" stroke="#e2e8f0" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="34" cy="8" r="1.7" fill="#f8fafc" />
        <circle cx="51" cy="15" r="1.7" fill="#f8fafc" />
        <circle cx="58" cy="32" r="1.7" fill="#f8fafc" />
        <circle cx="51" cy="49" r="1.7" fill="#f8fafc" />
        <circle cx="34" cy="56" r="1.7" fill="#f8fafc" />
      </svg>

      {showName ? (
        <div className="min-w-0">
          <p className={`truncate font-semibold leading-tight ${compact ? "text-base" : "text-xl"}`}>
            <span className="bg-gradient-to-r from-sky-400 via-blue-400 to-blue-700 bg-clip-text text-transparent">
              Neuro
            </span>
            <span className="text-slate-300">Vault</span>
          </p>
          {subtitle ? <p className="truncate text-xs uppercase tracking-wide text-slate-400">{subtitle}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
