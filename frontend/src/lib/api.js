const apiUrl =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000";
const simulationToken = import.meta.env.VITE_PAYMENT_SIMULATION_TOKEN || "";

async function parseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

export async function signup(email, password) {
  const response = await fetch(`${apiUrl}/auth/signup`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJson(response);
}

export async function login(email, password) {
  const response = await fetch(`${apiUrl}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJson(response);
}

export async function logout() {
  await fetch(`${apiUrl}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function me() {
  const response = await fetch(`${apiUrl}/auth/me`, {
    credentials: "include",
  });
  return parseJson(response);
}

export async function createPayment(method, amountPkr = 2000) {
  const response = await fetch(`${apiUrl}/create-payment`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method, amount_pkr: amountPkr }),
  });
  return parseJson(response);
}

export async function simulatePaymentSuccess(method, reference = null) {
  const headers = { "Content-Type": "application/json" };
  if (simulationToken) {
    headers["X-Simulation-Token"] = simulationToken;
  }
  const response = await fetch(`${apiUrl}/payments/simulate-success`, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify({ method, reference, status: "success" }),
  });
  return parseJson(response);
}

export async function streamAssistant(messages, onDelta, signal, attachments = [], inferenceMode = "local") {
  const response = await fetch(`${apiUrl}/chat/stream`, {
    method: "POST",
    credentials: "include",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, attachments, inference_mode: inferenceMode }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Streaming request failed");
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
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const eventChunk of events) {
      const line = eventChunk
        .split("\n")
        .find((candidate) => candidate.startsWith("data:"));
      if (!line) {
        continue;
      }
      const payload = JSON.parse(line.replace(/^data:\s*/, ""));
      onDelta(payload);
    }
  }
}

export async function generateImage(prompt) {
  const response = await fetch(`${apiUrl}/chat/image`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  return parseJson(response);
}

export async function getPrivacyStatus() {
  const response = await fetch(`${apiUrl}/chat/privacy-status`, {
    credentials: "include",
  });
  return parseJson(response);
}
