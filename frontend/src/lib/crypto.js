const KEY_DB_NAME = "zk-chat-crypto";
const KEY_STORE_NAME = "keys";
const KEY_ID = "primary-aes-key";

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function fromBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function openKeyDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(KEY_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(KEY_STORE_NAME)) {
        db.createObjectStore(KEY_STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Failed to open key database"));
  });
}

function getStoredKey() {
  return openKeyDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(KEY_STORE_NAME, "readonly");
        const store = transaction.objectStore(KEY_STORE_NAME);
        const request = store.get(KEY_ID);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error || new Error("Failed to read encryption key"));
      }),
  );
}

function storeKey(base64RawKey) {
  return openKeyDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(KEY_STORE_NAME, "readwrite");
        const store = transaction.objectStore(KEY_STORE_NAME);
        const request = store.put(base64RawKey, KEY_ID);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error || new Error("Failed to persist encryption key"));
      }),
  );
}

function clearStoredKey() {
  return openKeyDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(KEY_STORE_NAME, "readwrite");
        const store = transaction.objectStore(KEY_STORE_NAME);
        const request = store.delete(KEY_ID);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error || new Error("Failed to clear encryption key"));
      }),
  );
}

export async function resetLocalKey() {
  await clearStoredKey();
}

async function exportKeyToBase64(key) {
  const raw = await crypto.subtle.exportKey("raw", key);
  return toBase64(raw);
}

async function importKeyFromBase64(base64RawKey) {
  const raw = fromBase64(base64RawKey);
  return crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, true, ["encrypt", "decrypt"]);
}

export async function generateKey() {
  return crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
}

export async function generateEncryptionKey() {
  return generateKey();
}

export async function encrypt(text, key) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(text);
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);
  return {
    iv: toBase64(iv.buffer),
    ciphertext: toBase64(ciphertext),
  };
}

export async function encryptData(data, key) {
  const serialized = typeof data === "string" ? data : JSON.stringify(data);
  return encrypt(serialized, key);
}

export async function decrypt(payload, key) {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: new Uint8Array(fromBase64(payload.iv)) },
    key,
    fromBase64(payload.ciphertext),
  );
  return new TextDecoder().decode(plaintext);
}

export async function decryptData(payload, key) {
  const plain = await decrypt(payload, key);
  try {
    return JSON.parse(plain);
  } catch {
    return plain;
  }
}

export async function getOrCreateLocalKey() {
  try {
    const existing = await getStoredKey();
    if (typeof existing === "string" && existing.length > 0) {
      try {
        return await importKeyFromBase64(existing);
      } catch {
        await clearStoredKey();
      }
    }

    const key = await generateKey();
    const keyBase64 = await exportKeyToBase64(key);
    await storeKey(keyBase64);
    return key;
  } catch (error) {
    throw new Error(`Unable to initialize local encryption key: ${error?.message || String(error)}`);
  }
}
