export function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

const jsonCache = new Map();
const DEFAULT_GET_CACHE_TTL = 45000;

function clonePayload(payload) {
  if (typeof structuredClone === 'function') {
    return structuredClone(payload);
  }
  return JSON.parse(JSON.stringify(payload));
}

function requestCacheKey(url) {
  return new URL(url, window.location.origin).toString();
}

export function clearJsonCache() {
  jsonCache.clear();
}

export async function fetchJson(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const cacheTtl = options.cacheTtl ?? DEFAULT_GET_CACHE_TTL;
  const canCache = method === 'GET' && !options.body && cacheTtl > 0;
  const cacheKey = canCache ? requestCacheKey(url) : '';
  const cached = canCache ? jsonCache.get(cacheKey) : null;

  if (cached && cached.expiresAt > Date.now()) {
    return clonePayload(cached.payload);
  }

  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    method,
    headers: {
      Accept: 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...(options.body ? { 'X-CSRFToken': csrfToken() } : {}),
      ...(options.headers || {}),
    },
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || 'Запрос не выполнен.');
  }

  if (canCache) {
    jsonCache.set(cacheKey, {
      expiresAt: Date.now() + cacheTtl,
      payload: clonePayload(data),
    });
  }

  return data;
}

export function postForm(url, values) {
  const formData = new FormData();
  Object.entries(values).forEach(([key, value]) => {
    formData.append(key, value);
  });

  return fetchJson(url, {
    method: 'POST',
    body: formData,
  }).then((data) => {
    clearJsonCache();
    return data;
  });
}
