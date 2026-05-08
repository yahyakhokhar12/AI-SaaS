import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import FileUpload from "./FileUpload";

export default function ChatUI({
  activeConversation,
  messages,
  loading,
  error,
  remainingDaily,
  mode,
  privacyMode,
  inferenceMode,
  input,
  isListening,
  attachments,
  endRef,
  onSetMode,
  onTogglePrivacyMode,
  onInputChange,
  onSend,
  onStop,
  onCopyMessage,
  onRegenerateMessage,
  onAddImage,
  onAddFile,
  onAddCamera,
  onToggleVoice,
  onRemoveAttachment,
}) {
  function downloadArtifact(artifact) {
    let bytes;
    if (artifact.encoding === "hex") {
      const hex = artifact.content_base64 || "";
      const chunkCount = Math.floor(hex.length / 2);
      const numberArray = new Array(chunkCount);
      for (let index = 0; index < chunkCount; index += 1) {
        numberArray[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
      }
      bytes = new Uint8Array(numberArray);
    } else {
      const byteCharacters = atob(artifact.content_base64 || "");
      const byteNumbers = new Array(byteCharacters.length);
      for (let index = 0; index < byteCharacters.length; index += 1) {
        byteNumbers[index] = byteCharacters.charCodeAt(index);
      }
      bytes = new Uint8Array(byteNumbers);
    }
    const blob = new Blob([bytes], { type: artifact.mime_type || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = artifact.name || "artifact.bin";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="panel min-w-0 flex min-h-0 flex-col">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <p className="truncate text-sm font-medium text-slate-200">Chat: {activeConversation?.title || "Conversation"}</p>
          {remainingDaily !== null ? (
            <p className="text-xs text-slate-400">Limit remaining: {remainingDaily}</p>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="mx-auto mt-16 max-w-xl text-center">
            <h3 className="text-lg font-semibold text-slate-100">Ask anything</h3>
            <p className="mt-2 text-sm text-slate-400">
              Conversations are encrypted in your browser and stored only on your device.
            </p>
          </div>
        ) : null}

        {messages.map((message, index) => (
          <div key={`${message.ts}-${index}`} className={message.role === "user" ? "text-right" : ""}>
            <div
              className={`inline-block max-w-[90%] rounded-xl border px-3 py-2 text-left ${
                message.role === "user"
                  ? "border-accent/30 bg-accent/10 text-slate-50"
                  : "border-line bg-panelSoft text-slate-100"
              }`}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              {message.imageDataUrl ? (
                <img
                  src={message.imageDataUrl}
                  alt="Generated"
                  className="mt-3 w-full max-w-md rounded-lg border border-line object-cover"
                  loading="lazy"
                />
              ) : null}
              {Array.isArray(message.artifacts) && message.artifacts.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {message.artifacts.map((artifact) => (
                    <button
                      key={artifact.name}
                      type="button"
                      onClick={() => downloadArtifact(artifact)}
                      className="rounded-md border border-line bg-slate-900/60 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800/80"
                    >
                      Download {artifact.name}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
            {message.role === "assistant" && !message.imageDataUrl ? (
              <div className="mt-1 flex gap-3 text-xs text-slate-400">
                <button type="button" onClick={() => void onCopyMessage(message.content)}>
                  Copy
                </button>
                <button type="button" onClick={() => void onRegenerateMessage(index - 1)}>
                  Regenerate
                </button>
              </div>
            ) : null}
          </div>
        ))}

        {loading ? <p className="text-sm text-slate-400">Assistant is typing...</p> : null}
        <div ref={endRef} />
      </div>

      <form
        className="border-t border-line p-3"
        onSubmit={(event) => {
          event.preventDefault();
          onSend();
        }}
      >
        <div className="rounded-2xl border border-line bg-slate-900/80 px-2 py-2">
          <div className="flex items-center gap-2">
            <FileUpload
              compact
              showAttachments={false}
              attachments={attachments}
              isListening={isListening}
              onAddImage={onAddImage}
              onAddFile={onAddFile}
              onAddCamera={onAddCamera}
              onToggleVoice={onToggleVoice}
              onRemoveAttachment={onRemoveAttachment}
            />
            <textarea
              value={input}
              onChange={(event) => onInputChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  if (!loading) {
                    onSend();
                  }
                }
              }}
              className="h-10 max-h-24 min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-400"
              placeholder={mode === "image" ? "Describe an image..." : "Ask anything"}
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black disabled:opacity-60"
            >
              {mode === "image" ? "Generate" : "Send"}
            </button>
            <button
              type="button"
              onClick={onToggleVoice}
              className={`inline-flex h-8 w-8 items-center justify-center rounded-lg border ${
                isListening ? "border-rose-400 text-rose-300" : "border-line text-slate-300"
              } hover:bg-slate-800/50`}
              aria-label={isListening ? "Stop voice input" : "Start voice input"}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 4.5a2.5 2.5 0 0 1 2.5 2.5v5a2.5 2.5 0 1 1-5 0V7A2.5 2.5 0 0 1 12 4.5Z" stroke="currentColor" strokeWidth="1.8" />
                <path d="M7.5 11.5a4.5 4.5 0 0 0 9 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M12 16v3.5M9.5 19.5h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </div>

        {attachments.length ? (
          <div className="mt-2 flex flex-wrap gap-2">
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
        {attachments.some((attachment) => attachment.type === "image") ? (
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
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

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => onSetMode("image")}
            className="inline-flex items-center gap-2 rounded-full border border-line bg-black/30 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800/60"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
              <circle cx="9" cy="10" r="1.6" stroke="currentColor" strokeWidth="1.7" />
              <path d="M6 16l4-3 2.2 1.8L15.5 12 18 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Create an image
          </button>
          <button
            type="button"
            onClick={() => onSetMode("chat")}
            className="inline-flex items-center gap-2 rounded-full border border-line bg-black/30 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800/60"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M4 16.5V20l3.5-1.5H18A2 2 0 0 0 20 16.5V6.5a2 2 0 0 0-2-2H6A2 2 0 0 0 4 6.5v10Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
              <path d="M8 9.5h8M8 13h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            </svg>
            Write or edit
          </button>
          <button
            type="button"
            onClick={() => {
              onSetMode("chat");
              if (!input.trim()) {
                onInputChange("Look up ");
              }
            }}
            className="inline-flex items-center gap-2 rounded-full border border-line bg-black/30 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800/60"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
              <path d="M3 12h18M12 3c2.4 2.4 2.4 15.6 0 18M12 3c-2.4 2.4-2.4 15.6 0 18" stroke="currentColor" strokeWidth="1.4" />
            </svg>
            Look something up
          </button>
          <button
            type="button"
            onClick={onTogglePrivacyMode}
            className={`rounded-full border px-3 py-1.5 text-xs ${
              privacyMode === "strict" ? "border-emerald-400 text-emerald-300" : "border-line text-slate-300"
            }`}
          >
            {privacyMode === "strict" ? "Privacy: Strict" : "Privacy: Context"}
          </button>
        </div>

        <div className="mt-2 flex items-center justify-between gap-3">
          {error ? (
            <p className="max-w-[60%] truncate text-sm text-rose-300">{error}</p>
          ) : (
            <span className="text-xs text-slate-500">
              {inferenceMode === "device"
                ? "Private Device mode: prompts stay on your machine (local Ollama)."
                : privacyMode === "strict"
                  ? "Only current prompt is sent"
                  : "Recent local context is sent"}
            </span>
          )}
          <div className="flex gap-2">
            {loading && mode === "chat" ? (
              <button
                type="button"
                onClick={onStop}
                className="rounded-lg border border-line px-3 py-2 text-sm text-slate-200"
              >
                Stop
              </button>
            ) : null}
          </div>
        </div>
      </form>
    </div>
  );
}
