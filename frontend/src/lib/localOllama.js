const ollamaUrl = import.meta.env.VITE_OLLAMA_URL || "http://127.0.0.1:11434";
const ollamaTextModel = import.meta.env.VITE_OLLAMA_TEXT_MODEL || "llama3.2:1b";
const ollamaVisionModel = import.meta.env.VITE_OLLAMA_VISION_MODEL || "moondream";

function buildMessages(messages, attachments) {
  const base = messages.map((message) => ({
    role: message.role || "user",
    content: String(message.content || ""),
  }));

  const imageAttachments = (attachments || []).filter((item) => item.type === "image" && item.data_base64);
  const textAttachments = (attachments || []).filter((item) => item.type === "file_text" && item.text);

  if (textAttachments.length > 0) {
    const contextBlock = textAttachments
      .map((item) => `[${item.name || "attachment"}]\n${String(item.text || "").slice(0, 30000)}`)
      .join("\n\n");
    base.unshift({
      role: "system",
      content: `Local attachment context:\n${contextBlock}`,
    });
  }

  if (imageAttachments.length > 0) {
    base.push({
      role: "user",
      content: "Analyze the attached image(s) and answer the user request accurately.",
      images: imageAttachments.map((item) => item.data_base64),
    });
  }

  return base;
}

function resolveModel(attachments) {
  const hasImage = (attachments || []).some((item) => item.type === "image");
  return hasImage ? ollamaVisionModel : ollamaTextModel;
}

export async function streamLocalOllama(messages, attachments, onDelta, signal) {
  const payload = {
    model: resolveModel(attachments),
    stream: true,
    messages: buildMessages(messages, attachments),
  };

  const response = await fetch(`${ollamaUrl}/api/chat`, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`Local Ollama request failed (${response.status}). ${body || ""}`.trim());
  }
  if (!response.body) {
    throw new Error("Streaming unsupported in this browser");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const text = line.trim();
      if (!text) {
        continue;
      }
      let payloadLine;
      try {
        payloadLine = JSON.parse(text);
      } catch {
        continue;
      }
      const delta = payloadLine?.message?.content;
      if (delta) {
        onDelta(delta);
      }
    }
  }
}
