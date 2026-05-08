import localforage from "localforage";
import { decryptData, encryptData } from "./crypto";

const conversationsStore = localforage.createInstance({
  name: "zk-chat",
  storeName: "conversations",
});

const messagesStore = localforage.createInstance({
  name: "zk-chat",
  storeName: "messages",
});

function resolveScope(scope) {
  const normalized = String(scope || "").trim();
  return normalized ? normalized : "";
}

function scopedKey(scope, conversationId) {
  const activeScope = resolveScope(scope);
  if (!activeScope) {
    return String(conversationId);
  }
  return `${activeScope}::${conversationId}`;
}

function scopedPrefix(scope) {
  const activeScope = resolveScope(scope);
  return activeScope ? `${activeScope}::` : "";
}

function stripScope(scope, key) {
  const prefix = scopedPrefix(scope);
  if (!prefix) {
    return String(key);
  }
  return String(key).startsWith(prefix) ? String(key).slice(prefix.length) : String(key);
}

async function getAll(store) {
  const items = [];
  await store.iterate((value, key) => {
    items.push({ key, value });
  });
  return items;
}

export async function listConversations(key, scope = "") {
  const prefix = scopedPrefix(scope);
  const encryptedItems = await getAll(conversationsStore);
  const decrypted = [];
  for (const item of encryptedItems) {
    if (prefix && !String(item.key).startsWith(prefix)) {
      continue;
    }
    try {
      const record = await decryptData(item.value, key);
      decrypted.push({ id: stripScope(scope, item.key), ...(record || {}) });
    } catch {
      await conversationsStore.removeItem(item.key);
      await messagesStore.removeItem(item.key);
    }
  }
  return decrypted.sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function saveConversation(conversation, key, scope = "") {
  const payload = await encryptData(
    {
      title: conversation.title,
      updatedAt: conversation.updatedAt,
    },
    key,
  );
  await conversationsStore.setItem(scopedKey(scope, conversation.id), payload);
}

export async function deleteConversation(conversationId, scope = "") {
  const key = scopedKey(scope, conversationId);
  await conversationsStore.removeItem(key);
  await messagesStore.removeItem(key);
}

export async function loadMessages(conversationId, key, scope = "") {
  const messageKey = scopedKey(scope, conversationId);
  const payload = await messagesStore.getItem(messageKey);
  if (!payload) {
    return [];
  }
  try {
    return await decryptData(payload, key);
  } catch {
    await messagesStore.removeItem(messageKey);
    return [];
  }
}

export async function saveMessages(conversationId, messages, key, scope = "") {
  const payload = await encryptData(messages, key);
  await messagesStore.setItem(scopedKey(scope, conversationId), payload);
}

export async function resetEncryptedWorkspace(scope = "") {
  const prefix = scopedPrefix(scope);
  if (!prefix) {
    await conversationsStore.clear();
    await messagesStore.clear();
    return;
  }
  const conversationItems = await getAll(conversationsStore);
  for (const item of conversationItems) {
    if (String(item.key).startsWith(prefix)) {
      await conversationsStore.removeItem(item.key);
    }
  }
  const messageItems = await getAll(messagesStore);
  for (const item of messageItems) {
    if (String(item.key).startsWith(prefix)) {
      await messagesStore.removeItem(item.key);
    }
  }
}
