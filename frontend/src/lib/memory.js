function tokenize(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

export function embedText(text) {
  const buckets = new Array(64).fill(0);
  const tokens = tokenize(text);
  for (const token of tokens) {
    let hash = 0;
    for (let i = 0; i < token.length; i += 1) {
      hash = (hash * 31 + token.charCodeAt(i)) >>> 0;
    }
    buckets[hash % buckets.length] += 1;
  }
  const norm = Math.sqrt(buckets.reduce((sum, value) => sum + value * value, 0)) || 1;
  return buckets.map((value) => value / norm);
}

function cosineSimilarity(a, b) {
  let value = 0;
  for (let index = 0; index < a.length; index += 1) {
    value += a[index] * b[index];
  }
  return value;
}

export function selectRelevantMessages(messages, query, topK = 6) {
  const queryEmbedding = embedText(query);
  const scored = messages
    .filter((message) => message.embedding && message.content)
    .map((message) => ({
      message,
      score: cosineSimilarity(queryEmbedding, message.embedding),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)
    .map((item) => item.message);
  return scored;
}
