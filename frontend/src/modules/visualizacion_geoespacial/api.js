const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');
export async function getGeo(path, params = {}, signal) {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
  const response = await fetch(`${BASE}/geoespacial/${path}?${query}`, { signal });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `No se pudo consultar los datos (${response.status}).`);
  return data;
}
