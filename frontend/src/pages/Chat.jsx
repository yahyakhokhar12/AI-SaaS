import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import ChatUI from "../components/ChatUI";
import NeuroVaultLogo from "../components/NeuroVaultLogo";
import { getOrCreateLocalKey, resetLocalKey } from "../lib/crypto";
import { getPrivacyStatus, streamAssistant } from "../lib/api";
import { streamLocalOllama } from "../lib/localOllama";
import { embedText, selectRelevantMessages } from "../lib/memory";
import {
  deleteConversation,
  listConversations,
  loadMessages,
  resetEncryptedWorkspace,
  saveConversation,
  saveMessages,
} from "../lib/storage";

function createConversationId() {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function createAttachmentId() {
  return `att_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function isTextLikeFile(file) {
  const name = file.name.toLowerCase();
  if (name.endsWith(".txt") || name.endsWith(".md") || name.endsWith(".json") || name.endsWith(".csv") || name.endsWith(".log")) {
    return true;
  }
  return file.type.startsWith("text/") || file.type === "application/json";
}

function toBase64Payload(dataUrl) {
  const parts = String(dataUrl || "").split(",");
  return parts.length > 1 ? parts[1] : "";
}

function looksLikeImageIntent(text) {
  const normalized = text.toLowerCase();
  return ["image", "photo", "picture", "draw", "illustration", "render"].some((hint) => normalized.includes(hint));
}

export default function Chat({ user, onLogout }) {
  const location = useLocation();
  const storageScope = user?.id ? `user:${user.id}` : `email:${String(user?.email || "").toLowerCase()}`;
  const [cryptoKey, setCryptoKey] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [messages, setMessages] = useState([]);
  const [booting, setBooting] = useState(true);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState("chat");
  const [privacyMode, setPrivacyMode] = useState(() => localStorage.getItem("privacy_mode") || "strict");
  const [inferenceMode, setInferenceMode] = useState(() => localStorage.getItem("inference_mode") || "device");
  const [cloudOptIn, setCloudOptIn] = useState(() => localStorage.getItem("cloud_opt_in") === "true");
  const [privacyStatus, setPrivacyStatus] = useState(null);
  const [conversationSearch, setConversationSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [remainingDaily, setRemainingDaily] = useState(null);
  const [streamAbortController, setStreamAbortController] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => (typeof window !== "undefined" ? window.innerWidth >= 768 : true));
  const [attachments, setAttachments] = useState([]);
  const [isListening, setIsListening] = useState(false);
  const endRef = useRef(null);
  const fileInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const speechRecognitionRef = useRef(null);
  const speechBaseInputRef = useRef("");
  const voiceRetriedLocalRef = useRef(false);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) || null,
    [conversations, activeConversationId],
  );

  const filteredConversations = useMemo(() => {
    const query = conversationSearch.trim().toLowerCase();
    if (!query) {
      return conversations;
    }
    return conversations.filter((conversation) => String(conversation.title || "").toLowerCase().includes(query));
  }, [conversations, conversationSearch]);

  useEffect(() => {
    async function boot() {
      try {
        const key = await getOrCreateLocalKey();
        setCryptoKey(key);
        const loadedConversations = await listConversations(key, storageScope);
        setConversations(loadedConversations);

        if (loadedConversations.length === 0) {
          const conversation = { id: createConversationId(), title: "New chat", updatedAt: Date.now() };
          await saveConversation(conversation, key, storageScope);
          setConversations([conversation]);
          setActiveConversationId(conversation.id);
        } else {
          setActiveConversationId(loadedConversations[0].id);
        }
      } catch (bootError) {
        try {
          await resetLocalKey();
          await resetEncryptedWorkspace(storageScope);
          const recoveredKey = await getOrCreateLocalKey();
          setCryptoKey(recoveredKey);
          const conversation = { id: createConversationId(), title: "New chat", updatedAt: Date.now() };
          await saveConversation(conversation, recoveredKey, storageScope);
          setConversations([conversation]);
          setActiveConversationId(conversation.id);
          setError("");
        } catch (recoveryError) {
          setError(recoveryError.message || bootError.message || "Failed to initialize encrypted workspace");
        }
      } finally {
        setBooting(false);
      }
    }
    setBooting(true);
    setConversations([]);
    setActiveConversationId("");
    setMessages([]);
    setAttachments([]);
    void boot();
  }, [storageScope]);

  useEffect(() => {
    if (!cryptoKey || !activeConversationId) {
      return;
    }
    async function hydrateMessages() {
      const localMessages = await loadMessages(activeConversationId, cryptoKey, storageScope);
      setMessages(localMessages);
      setAttachments([]);
    }
    void hydrateMessages();
  }, [cryptoKey, activeConversationId, storageScope]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    localStorage.setItem("privacy_mode", privacyMode);
  }, [privacyMode]);

  useEffect(() => {
    localStorage.setItem("inference_mode", inferenceMode);
  }, [inferenceMode]);

  useEffect(() => {
    localStorage.setItem("cloud_opt_in", cloudOptIn ? "true" : "false");
  }, [cloudOptIn]);

  useEffect(() => {
    async function loadPrivacyStatus() {
      try {
        const status = await getPrivacyStatus();
        setPrivacyStatus(status);
      } catch {
        setPrivacyStatus(null);
      }
    }
    void loadPrivacyStatus();
  }, []);

  useEffect(
    () => () => {
      if (speechRecognitionRef.current) {
        speechRecognitionRef.current.stop();
      }
    },
    [],
  );

  async function persistMessages(nextMessages) {
    if (!cryptoKey || !activeConversationId) {
      return;
    }
    await saveMessages(activeConversationId, nextMessages, cryptoKey, storageScope);
  }

  async function startNewChat() {
    if (!cryptoKey) {
      return;
    }
    const conversation = { id: createConversationId(), title: "New chat", updatedAt: Date.now() };
    await saveConversation(conversation, cryptoKey, storageScope);
    setConversations((previous) => [conversation, ...previous.filter((item) => item.id !== conversation.id)]);
    setActiveConversationId(conversation.id);
    setMessages([]);
    setAttachments([]);
    if (window.innerWidth < 768) {
      setSidebarOpen(false);
    }
  }

  async function renameConversation(conversationId) {
    if (!cryptoKey) {
      return;
    }
    const target = conversations.find((conversation) => conversation.id === conversationId);
    if (!target) {
      return;
    }
    const title = window.prompt("Rename conversation", target.title);
    if (!title?.trim()) {
      return;
    }
    const updated = { ...target, title: title.trim(), updatedAt: Date.now() };
    await saveConversation(updated, cryptoKey, storageScope);
    setConversations((previous) =>
      previous.map((conversation) => (conversation.id === conversationId ? updated : conversation)),
    );
  }

  async function removeConversation(conversationId) {
    if (!cryptoKey) {
      return;
    }
    await deleteConversation(conversationId, storageScope);
    const next = conversations.filter((conversation) => conversation.id !== conversationId);
    if (next.length === 0) {
      const conversation = { id: createConversationId(), title: "New chat", updatedAt: Date.now() };
      await saveConversation(conversation, cryptoKey, storageScope);
      setConversations([conversation]);
      setActiveConversationId(conversation.id);
      setMessages([]);
      setAttachments([]);
      return;
    }
    setConversations(next);
    if (conversationId === activeConversationId) {
      setActiveConversationId(next[0].id);
    }
  }

  async function updateConversationMetaFromMessages(nextMessages) {
    if (!cryptoKey || !activeConversationId) {
      return;
    }
    const firstUser = nextMessages.find((message) => message.role === "user");
    const title = firstUser ? firstUser.content.slice(0, 48) : "New chat";
    const nextMeta = { id: activeConversationId, title, updatedAt: Date.now() };
    await saveConversation(nextMeta, cryptoKey, storageScope);
    setConversations((previous) => [nextMeta, ...previous.filter((conversation) => conversation.id !== activeConversationId)]);
  }

  async function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
      reader.readAsDataURL(file);
    });
  }

  async function extractVideoMetadata(file) {
    return new Promise((resolve, reject) => {
      const objectUrl = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadedmetadata = () => {
        const payload = {
          duration_seconds: Number(video.duration || 0).toFixed(2),
          width: video.videoWidth || 0,
          height: video.videoHeight || 0,
          size_bytes: file.size || 0,
          mime_type: file.type || "video/unknown",
        };
        URL.revokeObjectURL(objectUrl);
        resolve(payload);
      };
      video.onerror = () => {
        URL.revokeObjectURL(objectUrl);
        reject(new Error(`Unable to read video metadata for ${file.name}`));
      };
      video.src = objectUrl;
    });
  }

  async function extractAudioMetadata(file) {
    return new Promise((resolve, reject) => {
      const objectUrl = URL.createObjectURL(file);
      const audio = document.createElement("audio");
      audio.preload = "metadata";
      audio.onloadedmetadata = () => {
        const payload = {
          duration_seconds: Number(audio.duration || 0).toFixed(2),
          size_bytes: file.size || 0,
          mime_type: file.type || "audio/unknown",
        };
        URL.revokeObjectURL(objectUrl);
        resolve(payload);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(objectUrl);
        reject(new Error(`Unable to read audio metadata for ${file.name}`));
      };
      audio.src = objectUrl;
    });
  }

  async function addFilesToAttachments(fileList) {
    const picked = Array.from(fileList || []);
    if (!picked.length) {
      return;
    }
    setError("");

    try {
      const builtAttachments = [];
      for (const file of picked) {
        if (file.type.startsWith("image/")) {
          const dataUrl = await readFileAsDataUrl(file);
          builtAttachments.push({
            id: createAttachmentId(),
            type: "image",
            name: file.name || "image",
            mimeType: file.type || "image/png",
            size: file.size || 0,
            dataUrl,
          });
          continue;
        }

        if (file.type.startsWith("video/")) {
          const meta = await extractVideoMetadata(file);
          builtAttachments.push({
            id: createAttachmentId(),
            type: "file_text",
            name: file.name,
            mimeType: file.type || "video/mp4",
            size: file.size || 0,
            text: [
              `Video analysis (local metadata)`,
              `file_name: ${file.name}`,
              `duration_seconds: ${meta.duration_seconds}`,
              `resolution: ${meta.width}x${meta.height}`,
              `size_bytes: ${meta.size_bytes}`,
              `mime_type: ${meta.mime_type}`,
            ].join("\n"),
          });
          continue;
        }

        if (file.type.startsWith("audio/")) {
          const meta = await extractAudioMetadata(file);
          builtAttachments.push({
            id: createAttachmentId(),
            type: "file_text",
            name: file.name,
            mimeType: file.type || "audio/mpeg",
            size: file.size || 0,
            text: [
              `Voice/audio analysis (local metadata)`,
              `file_name: ${file.name}`,
              `duration_seconds: ${meta.duration_seconds}`,
              `size_bytes: ${meta.size_bytes}`,
              `mime_type: ${meta.mime_type}`,
            ].join("\n"),
          });
          continue;
        }

        const lowerName = file.name.toLowerCase();
        if (lowerName.endsWith(".pdf") || lowerName.endsWith(".xlsx") || lowerName.endsWith(".xls") || lowerName.endsWith(".csv")) {
          const dataUrl = await readFileAsDataUrl(file);
          builtAttachments.push({
            id: createAttachmentId(),
            type: "file_binary",
            name: file.name,
            mimeType: file.type || "application/octet-stream",
            size: file.size || 0,
            dataUrl,
          });
          continue;
        }

        if (lowerName.endsWith(".docx")) {
          const module = await import("https://esm.sh/mammoth@1.9.0/mammoth.browser?bundle");
          const arrayBuffer = await file.arrayBuffer();
          const extracted = await module.extractRawText({ arrayBuffer });
          builtAttachments.push({
            id: createAttachmentId(),
            type: "file_text",
            name: file.name,
            mimeType: file.type || "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size: file.size || 0,
            text: String(extracted?.value || "").slice(0, 50000),
          });
          continue;
        }

        if (isTextLikeFile(file)) {
          const text = await file.text();
          builtAttachments.push({
            id: createAttachmentId(),
            type: "file_text",
            name: file.name,
            mimeType: file.type || "text/plain",
            size: file.size || 0,
            text: text.slice(0, 50000),
          });
          continue;
        }

        throw new Error(`Unsupported file type: ${file.name}`);
      }
      setAttachments((previous) => [...previous, ...builtAttachments].slice(-10));
    } catch (attachmentError) {
      setError(attachmentError.message || "Unable to add attachment");
    }
  }

  function removeAttachment(attachmentId) {
    setAttachments((previous) => previous.filter((attachment) => attachment.id !== attachmentId));
  }

  function buildAttachmentPayload() {
    return attachments.map((attachment) => {
      if (attachment.type === "image") {
        return {
          type: "image",
          name: attachment.name,
          mime_type: attachment.mimeType,
          data_base64: toBase64Payload(attachment.dataUrl),
        };
      }
      if (attachment.type === "file_binary") {
        return {
          type: "file_binary",
          name: attachment.name,
          mime_type: attachment.mimeType,
          data_base64: toBase64Payload(attachment.dataUrl),
        };
      }
      return {
        type: "file_text",
        name: attachment.name,
        mime_type: attachment.mimeType,
        text: attachment.text || "",
      };
    });
  }

  function toggleVoiceInput() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser.");
      return;
    }
    if (isListening && speechRecognitionRef.current) {
      speechRecognitionRef.current.stop();
      setIsListening(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    if ("processLocally" in recognition) {
      recognition.processLocally = false;
    }
    voiceRetriedLocalRef.current = false;

    recognition.onstart = () => {
      speechBaseInputRef.current = input;
      setIsListening(true);
      setError("");
    };
    recognition.onresult = (event) => {
      let finalTranscript = "";
      let interimTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const chunk = event.results[index][0].transcript || "";
        if (event.results[index].isFinal) {
          finalTranscript += chunk;
        } else {
          interimTranscript += chunk;
        }
      }
      const merged = `${speechBaseInputRef.current} ${finalTranscript} ${interimTranscript}`.replace(/\s+/g, " ").trim();
      setInput(merged);
    };
    recognition.onerror = (event) => {
      setIsListening(false);
      const reason = event?.error || "unknown";
      if (reason === "aborted") {
        return;
      }
      if (reason === "not-allowed" || reason === "service-not-allowed") {
        setError("Microphone permission was denied. Please allow mic access and try again.");
        return;
      }
      if (reason === "audio-capture") {
        setError("No microphone was found. Check your audio device and try again.");
        return;
      }
      if (reason === "no-speech") {
        setError("No speech detected. Please speak clearly and try again.");
        return;
      }
      if (reason === "network") {
        if ("processLocally" in recognition && !voiceRetriedLocalRef.current) {
          voiceRetriedLocalRef.current = true;
          try {
            recognition.processLocally = true;
            recognition.start();
            setError("Voice service was unreachable. Retrying with local recognition...");
            return;
          } catch {
          }
        }
        setError(
          "Voice recognition network error. Browser voice service is unavailable. Try Chrome/Edge with internet, or use typed input."
        );
        return;
      }
      setError(`Voice input failed (${reason}). Please try again.`);
    };
    recognition.onend = () => {
      setIsListening(false);
      speechRecognitionRef.current = null;
    };
    speechRecognitionRef.current = recognition;
    recognition.start();
  }

  function latestUserQuery(workingMessages, draft) {
    if (draft?.trim()) {
      return draft.trim();
    }
    return [...workingMessages].reverse().find((message) => message.role === "user")?.content || "";
  }

  async function sendMessage(regenerateFromIndex = null) {
    if (!input.trim() && attachments.length === 0 && regenerateFromIndex === null) {
      return;
    }
    if (!cryptoKey || loading) {
      return;
    }
    if (inferenceMode === "cloud" && !cloudOptIn) {
      const accepted = window.confirm(
        "Cloud mode sends your prompt and attachments for transient processing. Continue and enable cloud mode?",
      );
      if (!accepted) {
        return;
      }
      setCloudOptIn(true);
    }

    setError("");
    setLoading(true);
    const controller = new AbortController();
    setStreamAbortController(controller);

    const rawDraft = input.trim();
    const hasImageAttachment = attachments.some((attachment) => attachment.type === "image");
    const hasBinaryAttachment = attachments.some((attachment) => attachment.type === "file_binary");
    const hasTextAttachment = attachments.some((attachment) => attachment.type === "file_text");
    const fallbackDraft = hasImageAttachment
      ? "Please analyze the attached image."
      : hasBinaryAttachment
        ? "Please analyze the attached file."
        : hasTextAttachment
          ? "Please analyze the attached text."
          : "";
    const effectiveDraft = rawDraft || fallbackDraft;
    const draft =
      mode === "image" && effectiveDraft && !looksLikeImageIntent(effectiveDraft)
        ? `Generate an image: ${effectiveDraft}`
        : effectiveDraft;
    const localUnsupportedBinary = inferenceMode === "device" && attachments.some((attachment) => attachment.type === "file_binary");
    if (mode === "image" && inferenceMode === "device") {
      setLoading(false);
      setStreamAbortController(null);
      setError("Image generation is unavailable in Private Device mode. Switch to Local Server mode.");
      return;
    }
    if (localUnsupportedBinary) {
      setLoading(false);
      setStreamAbortController(null);
      setError("Local Device mode cannot parse binary files (PDF/Excel/CSV) directly. Switch to Local Server mode.");
      return;
    }
    let workingMessages = messages;
    if (regenerateFromIndex !== null) {
      workingMessages = messages.slice(0, regenerateFromIndex + 1);
      setMessages(workingMessages);
    } else {
      const userMessage = { role: "user", content: draft, ts: Date.now(), embedding: embedText(draft) };
      workingMessages = [...messages, userMessage];
      setMessages(workingMessages);
      setInput("");
    }

    const assistantMessage = {
      id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      role: "assistant",
      content: "",
      ts: Date.now(),
      embedding: null,
    };
    let streamedMessages = [...workingMessages, assistantMessage];
    setMessages(streamedMessages);
    const attachmentPayload = buildAttachmentPayload();
    const artifactsFromServer = [];
    let uploadMeta = null;

    try {
      const query = latestUserQuery(workingMessages, draft);
      const relevant = selectRelevantMessages(workingMessages, query, 6);
      const latestWindow = workingMessages.slice(-6);
      const composedContext = [...relevant, ...latestWindow]
        .filter((message, index, array) => array.findIndex((candidate) => candidate.ts === message.ts) === index)
        .map((message) => ({ role: message.role, content: message.content }));

      const outboundMessages =
        privacyMode === "strict"
          ? [{ role: "user", content: query }]
          : composedContext;
      if (!outboundMessages[0]?.content?.trim()) {
        throw new Error("Message is empty. Please try again.");
      }

      if (inferenceMode === "device") {
        await streamLocalOllama(outboundMessages, attachmentPayload, (delta) => {
          assistantMessage.content += delta;
          streamedMessages = [...workingMessages, { ...assistantMessage }];
          setMessages(streamedMessages);
        }, controller.signal);
      } else {
        await streamAssistant(
          outboundMessages,
          (event) => {
            if (event.type === "delta") {
              assistantMessage.content += event.content;
              streamedMessages = [...workingMessages, { ...assistantMessage }];
              setMessages(streamedMessages);
            }
            if (event.type === "image") {
              assistantMessage.imageDataUrl = `data:${event.mime_type};base64,${event.image_base64}`;
              streamedMessages = [...workingMessages, { ...assistantMessage }];
              setMessages(streamedMessages);
            }
            if (event.type === "artifact" && event.artifact) {
              artifactsFromServer.push(event.artifact);
            }
            if (event.type === "meta" && event.upload_result) {
              uploadMeta = event.upload_result;
            }
            if (event.type === "done") {
              setRemainingDaily(event.remaining_daily ?? null);
            }
            if (event.type === "error") {
              throw new Error(event.message || "Streaming failed");
            }
          },
          controller.signal,
          attachmentPayload,
          inferenceMode === "cloud" ? "cloud" : "local",
        );
      }

      if (artifactsFromServer.length > 0) {
        const artifactText = artifactsFromServer.map((artifact) => `- ${artifact.name}`).join("\n");
        assistantMessage.content = `${assistantMessage.content}\n\nArtifacts generated:\n${artifactText}`.trim();
        assistantMessage.artifacts = artifactsFromServer;
      }
      if (uploadMeta?.enabled) {
        const uploadLine = uploadMeta.uploaded
          ? `Power BI upload status: success (dataset id: ${uploadMeta.dataset_id || "n/a"}).`
          : `Power BI upload status: failed (${uploadMeta.message || "unknown error"}).`;
        assistantMessage.content = `${assistantMessage.content}\n\n${uploadLine}`.trim();
      }
      assistantMessage.embedding = embedText(assistantMessage.content || "artifact response");
      await persistMessages(streamedMessages);
      await updateConversationMetaFromMessages(streamedMessages);
      setAttachments([]);
    } catch (streamError) {
      if (controller.signal.aborted) {
        if (assistantMessage.content.trim()) {
          assistantMessage.embedding = embedText(assistantMessage.content);
          await persistMessages(streamedMessages);
          setMessages(streamedMessages);
        } else {
          await persistMessages(workingMessages);
          setMessages(workingMessages);
        }
      } else {
        setError(streamError.message);
        if (assistantMessage.content.trim()) {
          assistantMessage.embedding = embedText(assistantMessage.content);
          await persistMessages(streamedMessages);
          setMessages(streamedMessages);
        } else {
          await persistMessages(workingMessages);
          setMessages(workingMessages);
        }
      }
    } finally {
      setLoading(false);
      setStreamAbortController(null);
    }
  }

  function stopGeneration() {
    streamAbortController?.abort();
  }

  async function copyMessage(content) {
    await navigator.clipboard.writeText(content);
  }

  async function regenerateMessage(index) {
    await sendMessage(index);
  }

  function triggerFileInput(ref) {
    ref.current?.click();
  }

  function changeInferenceMode(nextMode) {
    if (nextMode === "cloud" && !cloudOptIn) {
      const accepted = window.confirm(
        "Cloud mode can send prompt/attachments to external API providers for transient inference. Continue?",
      );
      if (!accepted) {
        return;
      }
      setCloudOptIn(true);
    }
    setInferenceMode(nextMode);
  }

  if (booting) {
    return (
      <section className="flex h-[calc(100vh-2rem)] items-center justify-center">
        <p className="text-sm text-slate-300">Loading encrypted workspace...</p>
      </section>
    );
  }

  return (
    <section className="h-screen overflow-hidden p-3 md:p-4">
      <div
        className={`grid h-full grid-cols-1 gap-3 ${
          sidebarOpen ? "md:grid-cols-[320px_minmax(0,1fr)]" : "md:grid-cols-[0px_minmax(0,1fr)]"
        }`}
      >
        <aside
          className={`panel z-20 flex min-h-0 flex-col p-3 transition-all duration-200 md:relative md:translate-x-0 ${
            sidebarOpen
              ? "fixed inset-y-3 left-3 right-12 translate-x-0 md:relative md:inset-auto md:right-auto md:left-auto md:w-auto md:translate-x-0 md:opacity-100"
              : "fixed -translate-x-[120%] md:relative md:w-0 md:translate-x-0 md:overflow-hidden md:border-0 md:p-0 md:opacity-0 md:pointer-events-none"
          }`}
        >
          <div className="mb-2 flex items-center justify-between">
            <NeuroVaultLogo compact showName />
            <button
              type="button"
              className="rounded-lg border border-line p-2 text-slate-300 hover:bg-slate-800/50"
              onClick={() => setSidebarOpen((previous) => !previous)}
              aria-label="Toggle workspace sidebar"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M2 4H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                <path d="M2 8H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                <path d="M2 12H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <Link
              to="/chat"
              className={`rounded-lg border px-3 py-2 text-center text-sm ${
                location.pathname.startsWith("/chat")
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-line text-slate-300 hover:bg-slate-800/50"
              }`}
            >
              Chat
            </Link>
            <Link
              to="/billing"
              className={`rounded-lg border px-3 py-2 text-center text-sm ${
                location.pathname.startsWith("/billing")
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-line text-slate-300 hover:bg-slate-800/50"
              }`}
            >
              Billing
            </Link>
            <button
              type="button"
              onClick={onLogout}
              className="rounded-lg border border-line px-3 py-2 text-sm text-slate-300 hover:bg-slate-800/50"
            >
              Logout
            </button>
          </div>

          <button
            type="button"
            className="mt-3 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-black"
            onClick={() => void startNewChat()}
          >
            + New chat
          </button>

          <div className="mt-3 grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => changeInferenceMode("device")}
              className={`rounded-lg border px-2 py-2 text-xs ${
                inferenceMode === "device" ? "border-emerald-400 text-emerald-300" : "border-line text-slate-300"
              }`}
            >
              Device
            </button>
            <button
              type="button"
              onClick={() => changeInferenceMode("local")}
              className={`rounded-lg border px-2 py-2 text-xs ${
                inferenceMode === "local" ? "border-accent text-accent" : "border-line text-slate-300"
              }`}
            >
              Local
            </button>
            <button
              type="button"
              onClick={() => changeInferenceMode("cloud")}
              className={`rounded-lg border px-2 py-2 text-xs ${
                inferenceMode === "cloud" ? "border-amber-400 text-amber-300" : "border-line text-slate-300"
              }`}
            >
              Cloud
            </button>
          </div>

          <input
            value={conversationSearch}
            onChange={(event) => setConversationSearch(event.target.value)}
            placeholder="Search conversations..."
            className="mt-3 w-full rounded-lg border border-line bg-slate-900/70 px-3 py-2 text-xs text-slate-100 outline-none focus:border-accent"
          />

          <div className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
            <div className="space-y-2">
              {filteredConversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`rounded-lg border px-3 py-2 ${
                    conversation.id === activeConversationId ? "border-accent bg-accent/10" : "border-line bg-panelSoft"
                  }`}
                >
                  <button
                    type="button"
                    className="w-full truncate text-left text-sm text-slate-100"
                    onClick={() => {
                      setActiveConversationId(conversation.id);
                      setAttachments([]);
                      if (window.innerWidth < 768) {
                        setSidebarOpen(false);
                      }
                    }}
                  >
                    {conversation.title}
                  </button>
                  <div className="mt-2 flex gap-3 text-xs text-slate-400">
                    <button type="button" onClick={() => void renameConversation(conversation.id)}>
                      Rename
                    </button>
                    <button type="button" onClick={() => void removeConversation(conversation.id)}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {filteredConversations.length === 0 ? (
                <p className="rounded-lg border border-line bg-panelSoft px-3 py-2 text-xs text-slate-400">
                  No conversations match your search.
                </p>
              ) : null}
            </div>
          </div>

          <div className="mt-3 shrink-0 rounded-xl border border-line bg-panelSoft/70 p-3">
            <p className="mt-1 truncate text-sm font-medium text-slate-100">{user?.email}</p>
            <p className="mt-1 text-xs text-slate-400">Plan: {user?.plan?.toUpperCase()}</p>
            <p className="mt-1 text-xs text-slate-400">Zero-knowledge local encrypted history</p>
            <p className="mt-1 text-xs text-emerald-300">
              {inferenceMode === "device"
                ? "Mode: Private Device"
                : inferenceMode === "local"
                  ? "Mode: Local Server"
                  : "Mode: Cloud Opt-In"}
            </p>
            {privacyStatus ? (
              <p className="mt-1 truncate text-xs text-emerald-300" title={privacyStatus.server_content_storage}>
                {privacyStatus.server_content_storage}
              </p>
            ) : null}
          </div>
        </aside>

        {sidebarOpen && window.innerWidth < 768 ? (
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-10 bg-black/50 md:hidden"
            aria-label="Close sidebar"
          />
        ) : null}

        {!sidebarOpen ? (
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="fixed left-3 top-3 z-30 rounded-lg border border-line bg-panel px-3 py-2 text-slate-200 md:left-4 md:top-4"
            aria-label="Open workspace sidebar"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M2 4H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              <path d="M2 8H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              <path d="M2 12H14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        ) : null}

        <ChatUI
          activeConversation={activeConversation}
          messages={messages}
          loading={loading}
          error={error}
          remainingDaily={remainingDaily}
          mode={mode}
          privacyMode={privacyMode}
          inferenceMode={inferenceMode}
          input={input}
          isListening={isListening}
          attachments={attachments}
          endRef={endRef}
          onSetMode={setMode}
          onTogglePrivacyMode={() => setPrivacyMode((previous) => (previous === "strict" ? "context" : "strict"))}
          onInputChange={setInput}
          onSend={() => void sendMessage()}
          onStop={stopGeneration}
          onCopyMessage={copyMessage}
          onRegenerateMessage={regenerateMessage}
          onAddImage={() => triggerFileInput(imageInputRef)}
          onAddFile={() => triggerFileInput(fileInputRef)}
          onAddCamera={() => triggerFileInput(cameraInputRef)}
          onToggleVoice={toggleVoiceInput}
          onRemoveAttachment={removeAttachment}
        />

        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(event) => {
            void addFilesToAttachments(event.target.files);
            event.target.value = "";
          }}
        />
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(event) => {
            void addFilesToAttachments(event.target.files);
            event.target.value = "";
          }}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept=".docx,.txt,.md,.json,.csv,.log,.pdf,.xlsx,.xls,image/*,video/*,audio/*"
          multiple
          className="hidden"
          onChange={(event) => {
            void addFilesToAttachments(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
    </section>
  );
}
