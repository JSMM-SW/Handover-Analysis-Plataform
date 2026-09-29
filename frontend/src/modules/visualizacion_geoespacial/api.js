const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');
export async function getGeo(path, params = {}, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((item) => query.append(key, item));
    else if (value !== '' && value != null) query.set(key, value);
  }
  let response;
  try {
    response = await fetch(`${BASE}/geoespacial/${path}?${query}`, { signal });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('No se pudo contactar con la API. Comprueba el backend y su terminal: puede ser un problema de conexión o una respuesta bloqueada por CORS.', { cause: error });
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `No se pudo consultar los datos (${response.status}).`);
  return data;
}
