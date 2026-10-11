// frontend/src/modules/ingesta/IngestaPage.jsx
import { useRef, useState } from 'react';
import { sessionName } from '../../shared/sessionNames';
import './IngestaPage.css';

const API_BASE = "http://localhost:8000/api/v1";

const PIPELINE_STEPS = [
    { key: "select", label: "Archivo seleccionado" },
    { key: "validate_file", label: "Validando archivo" },
    { key: "extract", label: "Extrayendo datos" },
    { key: "validate_data", label: "Validando información" },
    { key: "clean", label: "Limpiando datos" },
    { key: "normalize", label: "Normalizando datos" },
    { key: "structure", label: "Generando dataset" },
    { key: "done", label: "Procesamiento completado" },
];

/** Ícono de visto (paso completado). */
function IconCheck() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
        </svg>
    );
}

/** Ícono de equis (paso fallido). */
function IconCross() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
    );
}

/** Ícono de subida (zona para arrastrar archivos). */
function IconUpload() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
            <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
    );
}

/** Ícono de alerta (mensaje de error). */
function IconAlert() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
    );
}

/** Ícono de descarga (botón del dataset limpio). */
function IconDownload() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 4v12M12 16l-4-4M12 16l4-4" />
            <path d="M4 18v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
        </svg>
    );
}

/**
 * Convierte un tamaño en bytes a un texto legible (B, KB o MB).
 *
 * @param {number} bytes - tamaño del archivo en bytes.
 * @returns {string} tamaño formateado, ej. "12.4 KB".
 */
function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Genera un identificador único para un archivo seleccionado.
 *
 * @param {File} file - archivo elegido por el usuario.
 * @param {number} index - posición del archivo dentro de la selección.
 * @returns {string} identificador único.
 */
function makeId(file, index) {
    return `${file.name}-${file.size}-${Date.now()}-${index}`;
}

/**
 * Indica si el archivo tiene una extensión soportada (.csv).
 *
 * @param {File} file - archivo elegido por el usuario.
 * @returns {boolean} true si el archivo es .csv.
 */
function isSupportedFile(file) {
    const name = file.name.toLowerCase();
    return name.endsWith(".csv");
}

/**
 * Crea el estado inicial de un archivo en la lista de procesamiento.
 *
 * @param {File} file - archivo elegido por el usuario.
 * @param {number} index - posición del archivo dentro de la selección.
 * @returns {object} estado inicial del archivo (sin procesar).
 */
function newItem(file, index) {
    return {
        id: makeId(file, index),
        file,
        isProcessing: false,
        completedSteps: [],
        failedStep: null,
        result: null,
        error: null,
    };
}

/**
 * Página del módulo de ingesta: permite seleccionar uno o varios CSV,
 * subirlos y ejecutar el pipeline ETL, mostrando el progreso y el
 * resultado de cada archivo.
 */
export default function IngestaPage() {
    const [items, setItems] = useState([]);
    const [isDragging, setIsDragging] = useState(false);
    const inputRef = useRef(null);

    const isProcessingAny = items.some((item) => item.isProcessing);

    /**
     * Actualiza parcialmente el estado de un archivo de la lista.
     *
     * @param {string} id - identificador del archivo.
     * @param {object|Function} patch - cambios a aplicar, o función que los
     *   calcula a partir del estado actual del archivo.
     */
    const updateItem = (id, patch) => {
        setItems((prev) =>
            prev.map((item) => (item.id === id ? { ...item, ...(typeof patch === "function" ? patch(item) : patch) } : item))
        );
    };

    /**
     * Reemplaza la selección actual por los archivos .csv recibidos.
     *
     * @param {FileList} fileList - archivos del input o del drag & drop.
     */
    const addFiles = (fileList) => {
        const files = Array.from(fileList).filter(isSupportedFile);
        if (files.length === 0) return;
        setItems(files.map((file, index) => newItem(file, index)));
    };

    /**
     * Maneja la selección de archivos desde el input.
     *
     * @param {Event} e - evento change del input de archivos.
     */
    const handleFileInput = (e) => addFiles(e.target.files);

    /**
     * Maneja los archivos soltados sobre la zona de carga.
     *
     * @param {DragEvent} e - evento drop.
     */
    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        addFiles(e.dataTransfer.files);
    };

    /** Limpia la selección y reinicia el input de archivos. */
    const clearAll = () => {
        setItems([]);
        if (inputRef.current) inputRef.current.value = "";
    };

    /**
     * Sube el archivo al backend (POST /ingestion/upload).
     *
     * @param {File} file - archivo a subir.
     * @returns {Promise<object>} metadatos del archivo almacenado.
     * @throws {Error} si el backend rechaza el archivo.
     */
    const uploadFile = async (file) => {
        const formData = new FormData();
        formData.append("files", file);

        const response = await fetch(`${API_BASE}/ingestion/upload`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();
        const item = Array.isArray(data) ? data[0] : null;
        if (!response.ok || !item) {
            throw new Error("Error desconocido al subir el archivo.");
        }
        if (!item.ok) {
            throw new Error(item.error || "Error desconocido al subir el archivo.");
        }
        return item.upload;
    };

    /**
     * Ejecuta el pipeline ETL sobre un archivo ya subido (POST /ingestion/process).
     *
     * @param {object} uploadData - metadatos devueltos por uploadFile.
     * @returns {Promise<object>} resultado de la ejecución del pipeline.
     * @throws {Error} si el procesamiento falla.
     */
    const processFile = async (uploadData) => {
        const response = await fetch(`${API_BASE}/ingestion/process`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                stored_filename: uploadData.stored_filename,
                original_filename: uploadData.original_filename,
            }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Error desconocido al procesar el archivo.");
        }
        return data;
    };

    /**
     * Sube y procesa un archivo, marcando cada paso del pipeline a medida
     * que avanza y registrando el paso en el que falló, si falla.
     *
     * @param {string} id - identificador del archivo en la lista.
     * @param {File} file - archivo a procesar.
     */
    const processItem = async (id, file) => {
        updateItem(id, {
            isProcessing: true,
            completedSteps: ["select"],
            failedStep: null,
            result: null,
            error: null,
        });

        const advance = (key) =>
            updateItem(id, (item) => ({ completedSteps: [...item.completedSteps, key] }));

        try {
            const uploadData = await uploadFile(file);
            advance("validate_file");
            advance("extract");

            const processData = await processFile(uploadData);
            advance("validate_data");
            advance("clean");
            advance("normalize");
            advance("structure");
            advance("done");

            if (processData.status !== "completed") {
                updateItem(id, { failedStep: "done" });
            }
            updateItem(id, { result: processData });
        } catch (err) {
            updateItem(id, (item) => {
                const nextStepIndex = PIPELINE_STEPS.findIndex(
                    (step) => !item.completedSteps.includes(step.key)
                );
                return {
                    failedStep: PIPELINE_STEPS[nextStepIndex]?.key ?? "done",
                    error: err.message,
                };
            });
        } finally {
            updateItem(id, { isProcessing: false });
        }
    };

    /** Procesa todos los archivos que aún no tienen resultado. */
    const handleProcessAll = () => {
        items.forEach((item) => {
            if (!item.isProcessing && !item.result) {
                processItem(item.id, item.file);
            }
        });
    };

    return (
        <div className="ingesta-page">
            <div className="ingesta-shell">
                <header className="ingesta-header">
                    <h2 className="ingesta-title">Carga de datos de handover</h2>
                    <p className="ingesta-subtitle">
                        Sube uno o varios archivos CSV con mediciones de handover para
                        validarlos, limpiarlos y estructurarlos como dataset listo para análisis.
                    </p>
                </header>

                <section className="ingesta-card">
                    <h3 className="ingesta-card-title">Archivos</h3>
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
                            disabled={isProcessingAny}
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

                    <div className="ingesta-actions">
                        <button
                            className="ingesta-btn"
                            onClick={handleProcessAll}
                            disabled={items.length === 0 || isProcessingAny}
                        >
                            {isProcessingAny && <span className="ingesta-spinner" />}
                            {isProcessingAny
                                ? "Procesando…"
                                : `Procesar archivo${items.length > 1 ? "s" : ""}`}
                        </button>

                        {items.length > 0 && !isProcessingAny && (
                            <button type="button" className="ingesta-btn-link" onClick={clearAll}>
                                Quitar selección
                            </button>
                        )}
                    </div>
                </section>

                {items.map((item) => (
                    <FileResultCard key={item.id} item={item} />
                ))}
            </div>
        </div>
    );
}

/**
 * Tarjeta con el progreso y el resultado del procesamiento de un archivo.
 *
 * @param {object} props
 * @param {object} props.item - estado del archivo (ver newItem).
 */
function FileResultCard({ item }) {
    const { file, completedSteps, failedStep, result, error } = item;
    const hasStarted = completedSteps.length > 0 || failedStep;

    const stepsToShow = hasStarted
        ? PIPELINE_STEPS.filter((step, index) => {
            const failedIndex = PIPELINE_STEPS.findIndex((s) => s.key === failedStep);
            return failedIndex === -1 || index <= failedIndex;
        })
        : [];

    return (
        <section className="ingesta-card">
            <div className="ingesta-result-header">
                <h3 className="ingesta-file-name">{file.name}</h3>
                <span className="ingesta-dropzone-hint">{formatBytes(file.size)}</span>
            </div>

            {stepsToShow.length > 0 && (
                <ul className="ingesta-steps">
                    {stepsToShow.map((step) => {
                        const isDone = completedSteps.includes(step.key);
                        const isFailed = failedStep === step.key;
                        const state = isFailed ? "is-error" : isDone ? "is-success" : "is-pending";
                        return (
                            <li key={step.key} className={`ingesta-step ${state}`}>
                                <span className="ingesta-step-icon">
                                    {isFailed ? <IconCross /> : isDone ? <IconCheck /> : null}
                                </span>
                                {step.label}
                            </li>
                        );
                    })}
                </ul>
            )}

            {error && (
                <div className="ingesta-alert is-error">
                    <span className="ingesta-alert-icon"><IconAlert /></span>
                    <div>
                        <p className="ingesta-alert-title">No se pudo completar el procesamiento</p>
                        <p>{error}</p>
                    </div>
                </div>
            )}

            {result && (
                <div className="ingesta-result">
                    <div className="ingesta-result-header">
                        <span className={`ingesta-status-pill ${result.status === "completed" ? "is-completed" : "is-failed"}`}>
                            {result.status === "completed" ? "Completado" : "Con errores"}
                        </span>
                        {result.status === "completed" && (
                            <a
                                className="ingesta-btn"
                                href={`${API_BASE}/ingestion/export?execution_id=${result.execution_id}`}
                            >
                                <IconDownload />
                                Descargar dataset limpio
                            </a>
                        )}
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
                        <h4 className="ingesta-section-title">Advertencias</h4>
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

                    <div className="ingesta-section">
                        <h4 className="ingesta-section-title">Errores</h4>
                        {result.errors.length === 0 ? (
                            <p className="ingesta-note is-empty">Sin errores</p>
                        ) : (
                            <ul className="ingesta-note-list">
                                {result.errors.map((err) => (
                                    <li key={err} className="ingesta-note is-error">{err}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
}
