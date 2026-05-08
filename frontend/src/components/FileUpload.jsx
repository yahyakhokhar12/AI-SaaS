import { useEffect, useRef, useState } from "react";

export default function FileUpload({
  attachments,
  isListening,
  onAddImage,
  onAddFile,
  onAddCamera,
  onToggleVoice,
  onRemoveAttachment,
  compact = false,
  className = "",
  showAttachments = true,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    function onOutsideClick(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, []);

  return (
    <div className={`${compact ? "mb-0" : "mb-2"} ${className}`}>
      <div ref={menuRef} className="relative flex items-center gap-2">
        <button
          type="button"
          onClick={() => setMenuOpen((previous) => !previous)}
          className={`${
            compact
              ? "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line text-xl leading-none text-slate-200 hover:bg-slate-800/50"
              : "rounded-md border border-line px-3 py-1 text-base font-semibold text-slate-200 hover:bg-slate-800/50"
          }`}
          aria-label="Open attachment menu"
          aria-expanded={menuOpen}
        >
          +
        </button>
        {!compact ? <p className="text-xs text-slate-400">Attach image, doc, video, audio, camera, or voice input</p> : null}

        {menuOpen ? (
          <div className={`absolute left-0 ${compact ? "top-11" : "top-10"} z-30 w-44 rounded-lg border border-line bg-panel p-1 shadow-xl`}>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onAddImage();
              }}
              className="w-full rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/60"
            >
              Add image
            </button>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onAddFile();
              }}
              className="w-full rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/60"
            >
              Add file/doc/video/audio
            </button>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onAddCamera();
              }}
              className="w-full rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/60"
            >
              Camera
            </button>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onToggleVoice();
              }}
              className={`w-full rounded-md px-3 py-2 text-left text-xs ${
                isListening ? "text-rose-300 hover:bg-rose-500/10" : "text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              {isListening ? "Stop voice" : "Voice to text"}
            </button>
          </div>
        ) : null}
      </div>

      {showAttachments && attachments.length ? (
        <div className={`${compact ? "mt-3" : "mt-2"} flex flex-wrap gap-2`}>
          {attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="inline-flex items-center gap-2 rounded-md border border-line bg-panelSoft px-2 py-1 text-xs text-slate-200"
            >
              <span className="max-w-[180px] truncate">{attachment.name}</span>
              <button
                type="button"
                onClick={() => onRemoveAttachment(attachment.id)}
                className="text-slate-400 hover:text-rose-300"
              >
                x
              </button>
            </div>
          ))}
        </div>
      ) : null}

      {showAttachments && attachments.some((attachment) => attachment.type === "image") ? (
        <div className={`${compact ? "mt-3" : "mt-2"} flex gap-2 overflow-x-auto pb-1`}>
          {attachments
            .filter((attachment) => attachment.type === "image")
            .map((attachment) => (
              <img
                key={attachment.id}
                src={attachment.dataUrl}
                alt={attachment.name}
                className="h-16 w-16 rounded-md border border-line object-cover"
              />
            ))}
        </div>
      ) : null}
    </div>
  );
}
