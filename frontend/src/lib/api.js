export function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
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
  });
}
