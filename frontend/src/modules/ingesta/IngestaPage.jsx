// frontend/src/modules/ingesta/IngestaPage.jsx
import { useRef, useState } from 'react';
import { sessionName } from '../../shared/sessionNames';
import './IngestaPage.css';

const API_BASE = "http://localhost:8000/api/v1";
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 30 * 60 * 1000;
const POLL_MAX_FAILURES = 5;
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

const MSG_CANCELLED = "Procesamiento cancelado. No se guardó ningún dato.";
const MSG_DISCARDED = "Descartado de la cola. No se subió ni se procesó.";

// Etapas reales que informa el backend en GET /status (campo `etapa`), en orden.
const BACKEND_STAGES = [
    { key: "en_cola", label: "En cola" },
    { key: "extract", label: "Extrayendo datos" },
    { key: "validate", label: "Validando información" },
    { key: "clean", label: "Limpiando datos" },
    { key: "normalize", label: "Normalizando datos" },
    { key: "structure", label: "Generando dataset" },
    { key: "load", label: "Guardando en la base de datos" },
    { key: "verify", label: "Verificando la carga" },
];

function IconCheck() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
        </svg>
    );
}

function IconUpload() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
            <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
    );
}

function IconAlert() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
    );
}

function IconDownload() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 4v12M12 16l-4-4M12 16l4-4" />
            <path d="M4 18v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
        </svg>
    );
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function makeId(file, index) {
    return `${file.name}-${file.size}-${Date.now()}-${index}`;
}

function isSupportedFile(file) {
    const name = file.name.toLowerCase();
    return name.endsWith(".csv");
}

// Misma clave que el backend (sin ruta, sin espacios en los extremos, en
// minúsculas): dos archivos con la misma clave son el mismo archivo.
function filenameKey(name) {
    return name.split(/[\\/]/).pop().replace(/^ +| +$/g, "").toLowerCase();
}

// Desenlaces que no son errores del sistema ni éxitos: cada uno se muestra
// con su propio mensaje.
class DuplicateRejection extends Error {}   // ya cargado / repetido en la selección
class UploadFailure extends Error {}        // no se subió (red, 413, timeout, subida incompleta)
class NotProcessed extends Error {}         // se subió pero no se procesó (con motivo)
class UserCancelled extends Error {}        // el usuario canceló
class StatusUnknown extends Error {}        // se perdió la conexión durante el polling

function newItem(file, index, rejection = null) {
    return {
        id: makeId(file, index),
        file,
        phase: rejection ? "rejected" : "pending",
        message: rejection,
        etapa: null,
        progreso: 0,
        executionId: null,
        cancelRequested: false,
        result: null,
    };
}

async function readJson(response) {
    try {
        return await response.json();
    } catch {
        return null;
    }
}

export default function IngestaPage() {
    const [items, setItems] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const [isRunning, setIsRunning] = useState(false);
    const inputRef = useRef(null);
    // Estado de control de la cola (no necesita re-render).
    const control = useRef({ currentId: null, abort: null, cancelledIds: new Set(), cancelAll: false });

    const updateItem = (id, patch) => {
        setItems((prev) =>
            prev.map((item) => (item.id === id ? { ...item, ...(typeof patch === "function" ? patch(item) : patch) } : item))
        );
    };

    const addFiles = (fileList) => {
        const files = Array.from(fileList).filter(isSupportedFile);
        if (files.length === 0) return;
        const seen = new Set();
        setItems(files.map((file, index) => {
            const key = filenameKey(file.name);
            const repeated = seen.has(key);
            seen.add(key);
            return newItem(
                file,
                index,
                repeated ? `El archivo '${file.name}' está repetido en esta selección; solo se procesa una vez.` : null
            );
        }));
    };

    const handleFileInput = (e) => addFiles(e.target.files);

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        if (!isRunning) addFiles(e.dataTransfer.files);
    };

    const clearAll = () => {
        setItems([]);
        if (inputRef.current) inputRef.current.value = "";
    };

    const uploadFile = async (file) => {
        const formData = new FormData();
        formData.append("files", file);
        // El backend compara los bytes recibidos contra este tamaño.
        formData.append("declared_sizes", String(file.size));

        const abort = new AbortController();
        control.current.abort = abort;
        let timedOut = false;
        const timer = setTimeout(() => { timedOut = true; abort.abort(); }, UPLOAD_TIMEOUT_MS);

        let response;
        try {
            response = await fetch(`${API_BASE}/ingestion/upload`, { method: "POST", body: formData, signal: abort.signal });
        } catch (err) {
            if (timedOut) {
                throw new UploadFailure("La subida tardó demasiado y se interrumpió. Revisa tu conexión y vuelve a intentarlo.");
            }
            if (err.name === "AbortError") throw new UserCancelled();
            throw new UploadFailure("No se pudo conectar con el servidor. Revisa tu conexión y vuelve a intentarlo.");
        } finally {
            clearTimeout(timer);
            control.current.abort = null;
        }

        if (response.status === 413) {
            throw new UploadFailure("El archivo es demasiado grande para subirse.");
        }
        const data = await readJson(response);
        const item = Array.isArray(data) ? data[0] : null;
        // 409: todos los archivos de la carga se rechazaron por duplicado; el
        // cuerpo trae igual el resultado por archivo.
        if ((!response.ok && response.status !== 409) || !item) {
            throw new UploadFailure("El servidor no pudo recibir el archivo. Vuelve a intentarlo.");
        }
        if (!item.ok) {
            const message = item.error || "El archivo no se pudo recibir.";
            if (item.error_code === "duplicado" || item.error_code === "duplicado_en_seleccion") {
                throw new DuplicateRejection(message);
            }
            if (item.error_code === "subida_incompleta") throw new UploadFailure(message);
            throw new NotProcessed(message);
        }
        return item.upload;
    };

    const startProcessing = async (uploadData) => {
        let response;
        try {
            response = await fetch(`${API_BASE}/ingestion/process`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    stored_filename: uploadData.stored_filename,
                    original_filename: uploadData.original_filename,
                }),
            });
        } catch {
            throw new NotProcessed("El archivo se subió, pero no se pudo iniciar el procesamiento (sin conexión con el servidor). Vuelve a intentarlo.");
        }
        const data = await readJson(response);
        if (response.status === 409) {
            throw new DuplicateRejection(data?.detail || "El archivo ya fue cargado. No se volvió a procesar.");
        }
        if (!response.ok || !data?.execution_id) {
            throw new NotProcessed(data?.detail || "El archivo se subió, pero el servidor no pudo iniciar el procesamiento.");
        }
        return data.execution_id;
    };

    // Consulta /status hasta que la ejecución deje de estar en "processing".
    // Nunca asume éxito ni fallo: si no puede confirmar, lanza StatusUnknown.
    const pollExecution = async (id, executionId) => {
        const deadline = Date.now() + POLL_TIMEOUT_MS;
        let consecutiveFailures = 0;
        while (Date.now() < deadline) {
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
            try {
                const response = await fetch(`${API_BASE}/ingestion/status/${executionId}`);
                const data = await readJson(response);
                if (!response.ok || !data) throw new Error("status no disponible");
                consecutiveFailures = 0;
                if (data.status !== "processing") return data;
                updateItem(id, {
                    etapa: data.etapa,
                    progreso: data.progreso ?? 0,
                    cancelRequested: Boolean(data.cancel_requested),
                });
            } catch {
                // Un fallo de red aislado no aborta: el procesamiento sigue en el servidor.
                consecutiveFailures += 1;
                if (consecutiveFailures >= POLL_MAX_FAILURES) throw new StatusUnknown();
            }
        }
        throw new StatusUnknown();
    };

    const applyFinalStatus = (id, data) => {
        if (data.status === "completed") {
            updateItem(id, { phase: "completed", result: data, progreso: 100, message: null });
        } else if (data.status === "cancelled") {
            updateItem(id, { phase: "cancelled", result: null, message: MSG_CANCELLED });
        } else {
            updateItem(id, {
                phase: "failed",
                result: data,
                message: (data.errors && data.errors[0]) || "El archivo se subió, pero no se pudo procesar.",
            });
        }
    };

    const followExecution = async (id, executionId) => {
        try {
            applyFinalStatus(id, await pollExecution(id, executionId));
        } catch (err) {
            if (!(err instanceof StatusUnknown)) throw err;
            updateItem(id, {
                phase: "unknown",
                message: "No se pudo confirmar el estado del procesamiento (se perdió la conexión con el servidor). El archivo puede seguir procesándose.",
            });
        }
    };

    const processItem = async (id, file) => {
        const wasCancelled = () => control.current.cancelledIds.has(id);
        control.current.currentId = id;
        updateItem(id, { phase: "uploading", message: null, etapa: null, progreso: 0, result: null });

        try {
            const uploadData = await uploadFile(file);
            if (wasCancelled()) throw new UserCancelled();

            const executionId = await startProcessing(uploadData);
            updateItem(id, { phase: "processing", executionId, etapa: "en_cola", progreso: 0 });
            // Si se canceló justo mientras se creaba la ejecución, se cancela ya en el servidor.
            if (wasCancelled()) await requestServerCancel(id, executionId);
            await followExecution(id, executionId);
        } catch (err) {
            if (err instanceof UserCancelled) {
                updateItem(id, { phase: "cancelled", message: MSG_CANCELLED });
            } else if (err instanceof DuplicateRejection) {
                updateItem(id, { phase: "rejected", message: err.message });
            } else if (err instanceof UploadFailure) {
                updateItem(id, { phase: "upload_failed", message: err.message });
            } else if (err instanceof NotProcessed) {
                updateItem(id, { phase: "failed", message: err.message });
            } else {
                updateItem(id, { phase: "failed", message: "Ocurrió un problema inesperado. Vuelve a intentarlo." });
            }
        } finally {
            control.current.currentId = null;
        }
    };

    const handleProcessAll = async () => {
        if (isRunning) return;
        control.current.cancelAll = false;
        control.current.cancelledIds = new Set();
        setIsRunning(true);
        try {
            // Uno por uno, en orden: así "Cancelar archivo actual" y "Cancelar
            // todo" tienen un significado claro.
            for (const item of items.filter((candidate) => candidate.phase === "pending")) {
                if (control.current.cancelAll) {
                    updateItem(item.id, { phase: "discarded", message: MSG_DISCARDED });
                    continue;
                }
                await processItem(item.id, item.file);
            }
        } finally {
            setIsRunning(false);
        }
    };

    const requestServerCancel = async (id, executionId) => {
        updateItem(id, { cancelRequested: true });
        try {
            const response = await fetch(`${API_BASE}/ingestion/cancel/${executionId}`, { method: "POST" });
            // 409: ya terminó (p. ej. "ya completada"): el polling mostrará el estado real.
            if (!response.ok && response.status !== 409) updateItem(id, { cancelRequested: false });
        } catch {
            updateItem(id, { cancelRequested: false });
        }
    };

    const cancelItem = (item) => {
        control.current.cancelledIds.add(item.id);
        if (item.phase === "uploading") {
            control.current.abort?.abort();
        } else if (item.phase === "processing" && item.executionId) {
            requestServerCancel(item.id, item.executionId);
        }
    };

    const currentItem = items.find((item) => item.phase === "uploading" || item.phase === "processing");
    const pendingCount = items.filter((item) => item.phase === "pending").length;

    const handleCancelCurrent = () => {
        if (!currentItem) return;
        if (!window.confirm(`¿Cancelar el procesamiento de '${currentItem.file.name}'? No se guardará ningún dato de este archivo.`)) return;
        cancelItem(currentItem);
    };

    const handleCancelAll = () => {
        if (!window.confirm("¿Cancelar todo? Se cancelará el archivo actual y se descartarán los archivos pendientes de la cola.")) return;
        control.current.cancelAll = true;
        if (currentItem) cancelItem(currentItem);
    };

    const handleRecheck = async (item) => {
        updateItem(item.id, { phase: "processing", message: null });
        await followExecution(item.id, item.executionId);
    };

    return (
        <div className="ingesta-page">
            <div className="ingesta-shell">
                <header className="ingesta-header">
                    <span className="ingesta-eyebrow">Módulo de ingesta</span>
                    <h1 className="ingesta-title">Carga de datos de handover</h1>
                    <p className="ingesta-subtitle">
                        Sube uno o varios archivos CSV con mediciones de handover para
                        validarlos, limpiarlos y estructurarlos como dataset listo para análisis.
                    </p>
                </header>

                <section className="ingesta-card">
                    <h2 className="ingesta-card-title">Archivos</h2>
                    <p className="ingesta-card-hint">Formatos soportados: .csv — puedes seleccionar varios a la vez</p>

                    <label
                        className={`ingesta-dropzone ${isDragging ? "is-dragging" : ""} ${items.length > 0 ? "has-file" : ""}`}
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={handleDrop}
                    >
                        <input
                            ref={inputRef}
                            type="file"
                            accept=".csv"
                            multiple
                            onChange={handleFileInput}
                            disabled={isRunning}
                        />
                        <span className="ingesta-dropzone-icon"><IconUpload /></span>
                        {items.length > 0 ? (
                            <>
                                <span className="ingesta-dropzone-filename">
                                    {items.length === 1 ? items[0].file.name : `${items.length} archivos seleccionados`}
                                </span>
                                <span className="ingesta-dropzone-hint">clic para cambiar la selección</span>
                            </>
                        ) : (
                            <>
                                <span className="ingesta-dropzone-text">Arrastra tus archivos aquí, o haz clic para seleccionarlos</span>
                                <span className="ingesta-dropzone-hint">Session_5.csv, Session_14.csv, etc.</span>
                            </>
                        )}
                    </label>

                    <button
                        className="ingesta-btn"
                        onClick={handleProcessAll}
                        disabled={pendingCount === 0 || isRunning}
                    >
                        {isRunning && <span className="ingesta-spinner" />}
                        {isRunning
                            ? "Procesando…"
                            : `Procesar archivo${pendingCount > 1 ? "s" : ""}`}
                    </button>

                    {isRunning && (
                        <div className="ingesta-cancel-row">
                            <button type="button" className="ingesta-btn-secondary" onClick={handleCancelCurrent} disabled={!currentItem || currentItem.cancelRequested}>
                                {items.length > 1 ? "Cancelar archivo actual" : "Cancelar"}
                            </button>
                            {items.length > 1 && (
                                <button type="button" className="ingesta-btn-secondary is-danger" onClick={handleCancelAll}>
                                    Cancelar todo
                                </button>
                            )}
                        </div>
                    )}

                    {items.length > 0 && !isRunning && (
                        <button type="button" className="ingesta-link-btn" onClick={clearAll}>
                            Quitar selección
                        </button>
                    )}
                </section>

                {items.map((item) => (
                    <FileResultCard key={item.id} item={item} onRecheck={handleRecheck} />
                ))}
            </div>
        </div>
    );
}

function StageList({ item }) {
    const stageIndex = BACKEND_STAGES.findIndex((stage) => stage.key === item.etapa);
    const steps = [
        { key: "upload", label: "Subiendo archivo", done: item.phase !== "uploading", active: item.phase === "uploading" },
        ...BACKEND_STAGES.slice(1).map((stage, index) => ({
            key: stage.key,
            label: stage.label,
            done: item.phase === "processing" && stageIndex > index + 1,
            active: item.phase === "processing" && stageIndex === index + 1,
        })),
    ];
    return (
        <>
            <ul className="ingesta-steps">
                {steps.map((step) => (
                    <li key={step.key} className={`ingesta-step ${step.done ? "is-success" : step.active ? "is-active" : "is-pending"}`}>
                        <span className="ingesta-step-icon">{step.done ? <IconCheck /> : null}</span>
                        {step.label}
                    </li>
                ))}
            </ul>
            {item.phase === "processing" && (
                <div className="ingesta-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={item.progreso}>
                    <div className="ingesta-progress-bar" style={{ width: `${item.progreso}%` }} />
                    <span className="ingesta-progress-label">
                        {item.cancelRequested ? "Cancelando…" : `${item.progreso}%`}
                    </span>
                </div>
            )}
        </>
    );
}

function Notice({ kind, title, children }) {
    return (
        <div className={`ingesta-alert ${kind}`} style={{ marginTop: 16 }}>
            <span className="ingesta-alert-icon"><IconAlert /></span>
            <div>
                <p className="ingesta-alert-title">{title}</p>
                {children}
            </div>
        </div>
    );
}

function FileResultCard({ item, onRecheck }) {
    const { file, phase, message, result } = item;
    const inProgress = phase === "uploading" || phase === "processing";

    return (
        <section className="ingesta-card">
            <div className="ingesta-result-header">
                <h2 className="ingesta-card-title">{file.name}</h2>
                <span className="ingesta-dropzone-hint">{formatBytes(file.size)}</span>
            </div>

            {inProgress && <StageList item={item} />}

            {phase === "rejected" && (
                <Notice kind="is-warning" title="Archivo no procesado"><p>{message}</p></Notice>
            )}
            {(phase === "cancelled" || phase === "discarded") && (
                <Notice kind="is-neutral" title={phase === "cancelled" ? "Cancelado" : "Descartado"}><p>{message}</p></Notice>
            )}
            {phase === "upload_failed" && (
                <Notice kind="is-error" title="El archivo no se subió"><p>{message}</p></Notice>
            )}
            {phase === "failed" && (
                <Notice kind="is-error" title="El archivo se subió, pero no se procesó"><p>{message}</p></Notice>
            )}
            {phase === "unknown" && (
                <Notice kind="is-warning" title="No se pudo confirmar el estado">
                    <p>{message}</p>
                    <button type="button" className="ingesta-btn-secondary" style={{ marginTop: 10 }} onClick={() => onRecheck(item)}>
                        Volver a consultar
                    </button>
                </Notice>
            )}

            {/* Solo se muestra "Completado" con status=completed confirmado por el backend. */}
            {phase === "completed" && result?.status === "completed" && (
                <div style={{ marginTop: 16 }}>
                    <div className="ingesta-result-header">
                        <span className="ingesta-status-pill is-completed">Completado</span>
                        <a
                            className="ingesta-btn"
                            style={{ width: "auto", marginTop: 0, padding: "8px 16px", fontSize: 13 }}
                            href={`${API_BASE}/ingestion/export?execution_id=${result.execution_id}`}
                        >
                            <IconDownload />
                            Descargar dataset limpio
                        </a>
                    </div>
                    <p className="ingesta-result-meta">
                        {sessionName(result)}
                    </p>

                    <div className="ingesta-stat-grid">
                        <div className="ingesta-stat">
                            <div className="ingesta-stat-value">{result.records_read}</div>
                            <div className="ingesta-stat-label">Leídos</div>
                        </div>
                        <div className="ingesta-stat is-valid">
                            <div className="ingesta-stat-value">{result.records_valid}</div>
                            <div className="ingesta-stat-label">Válidos</div>
                        </div>
                        <div className="ingesta-stat is-rejected">
                            <div className="ingesta-stat-value">{result.records_rejected}</div>
                            <div className="ingesta-stat-label">Rechazados</div>
                        </div>
                        <div className="ingesta-stat">
                            <div className="ingesta-stat-value">{result.processing_time_seconds}s</div>
                            <div className="ingesta-stat-label">Tiempo</div>
                        </div>
                    </div>

                    <div className="ingesta-section">
                        <h3 className="ingesta-section-title">Advertencias</h3>
                        {result.warnings.length === 0 ? (
                            <p className="ingesta-note is-empty">Sin advertencias</p>
                        ) : (
                            <ul className="ingesta-note-list">
                                {result.warnings.map((warning) => (
                                    <li key={warning} className="ingesta-note is-warning">{warning}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
}
