/**
 * Cliente HTTP del Módulo 2.
 *
 * Propio del módulo a propósito: `src/services/api.js` instancia axios, que **no está instalado**
 * en el proyecto, así que importarlo rompe la compilación (BLQ-04). Aquí se usa `fetch` nativo,
 * que es además lo que ya usa el módulo de ingesta.
 *
 * Responsabilidad única: hablar HTTP. Nada de lógica de presentación ni de dominio.
 */

/**
 * Base de la API. Se puede sobreescribir con `VITE_API_BASE_URL` en un `.env.local` para apuntar
 * a otro backend sin tocar el código.
 */
export const API_BASE =
  import.meta.env?.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

export const BASE_MODULO = `${API_BASE}/visualizacion-temporal`;

/** Milisegundos antes de abandonar una petición. Las series de 24 h pueden tardar. */
const TIMEOUT_MS = 30000;

/**
 * Error de API con el mensaje ya listo para mostrar.
 *
 * El backend responde `{"detail": "..."}` en español, así que se usa tal cual en lugar de
 * inventar un texto genérico que perdería la explicación.
 */
export class ErrorApi extends Error {
  constructor(mensaje, { status = 0, detalle = null } = {}) {
    super(mensaje);
    this.name = 'ErrorApi';
    this.status = status;
    this.detalle = detalle;
  }

  /** `true` cuando el recurso no existe: la interfaz lo trata como estado vacío, no como fallo. */
  get esNoEncontrado() {
    return this.status === 404;
  }
}

/**
 * Convierte un objeto de parámetros al query string del backend.
 *
 * Dos reglas que importan:
 * - Los valores `null`, `undefined` y `''` **se omiten**: enviarlos vacíos haría fallar la
 *   validación de FastAPI en lugar de significar "sin filtro".
 * - Los arrays se repiten (`?tecnologia=LTE&tecnologia=GSM`), que es como FastAPI espera las
 *   listas en query.
 *
 * @param {Record<string, unknown>} parametros
 * @returns {string} query string con `?` inicial, o cadena vacía
 */
export function construirQuery(parametros = {}) {
  const query = new URLSearchParams();

  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor === null || valor === undefined || valor === '') continue;

    if (Array.isArray(valor)) {
      valor.filter((v) => v !== null && v !== undefined && v !== '').forEach((v) => query.append(clave, v));
    } else {
      query.append(clave, valor);
    }
  }

  const texto = query.toString();
  return texto ? `?${texto}` : '';
}

async function extraerMensajeDeError(respuesta) {
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo?.detail === 'string') return cuerpo.detail;
    // FastAPI devuelve una lista de errores cuando falla la validación de tipos.
    if (Array.isArray(cuerpo?.detail)) {
      return cuerpo.detail.map((e) => e.msg ?? JSON.stringify(e)).join('; ');
    }
  } catch {
    // El cuerpo no era JSON; se cae al mensaje genérico de abajo.
  }
  return `Error ${respuesta.status} al consultar el servidor.`;
}

/**
 * Realiza una petición al módulo y devuelve el JSON ya parseado.
 *
 * @param {string} ruta      Ruta relativa al módulo, p. ej. '/sesiones'
 * @param {{method?: string, body?: unknown, signal?: AbortSignal}} [opciones]
 */
export async function peticion(ruta, { method = 'GET', body, signal } = {}) {
  const controlador = new AbortController();
  const temporizador = setTimeout(() => controlador.abort(), TIMEOUT_MS);

  // Se respeta la cancelación que hace TanStack Query al cambiar de filtro.
  if (signal) signal.addEventListener('abort', () => controlador.abort(), { once: true });

  try {
    const respuesta = await fetch(`${BASE_MODULO}${ruta}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controlador.signal,
    });

    if (!respuesta.ok) {
      const mensaje = await extraerMensajeDeError(respuesta);
      throw new ErrorApi(mensaje, { status: respuesta.status, detalle: mensaje });
    }

    return await respuesta.json();
  } catch (error) {
    if (error instanceof ErrorApi) throw error;

    if (error?.name === 'AbortError') {
      throw new ErrorApi(
        'La consulta tardó demasiado y se canceló. Prueba a acotar el rango temporal.',
        { status: 0 },
      );
    }

    throw new ErrorApi(
      'No se pudo contactar con el servidor. Comprueba que el backend esté arrancado.',
      { status: 0 },
    );
  } finally {
    clearTimeout(temporizador);
  }
}
