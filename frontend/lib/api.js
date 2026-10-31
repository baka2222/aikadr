export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    cache: 'no-store',
    ...options,
    headers: options.body instanceof FormData
      ? options.headers
      : { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!response.ok) {
    let message = `Ошибка ${response.status}`;
    try {
      const payload = await response.json();
      message = typeof payload.detail === 'string' ? payload.detail : message;
    } catch { /* response without JSON */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const seriesUrl = (id) => `/series/${encodeURIComponent(id)}`;
export const watchUrl = (seriesId, episodeId) =>
  `/watch/${encodeURIComponent(seriesId)}/${encodeURIComponent(episodeId)}`;

export function uploadWithProgress(path, body, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', `/api${path}`);
    request.withCredentials = true;
    request.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
    request.onerror = () => reject(new Error('Соединение прервано. Повторите загрузку.'));
    request.onload = () => {
      let result;
      try { result = JSON.parse(request.responseText); } catch { reject(new Error(`Ошибка загрузки ${request.status}`)); return; }
      if (request.status >= 200 && request.status < 300) resolve(result);
      else reject(new Error(typeof result.detail === 'string' ? result.detail : 'Не удалось загрузить файл'));
    };
    request.send(body);
  });
}
