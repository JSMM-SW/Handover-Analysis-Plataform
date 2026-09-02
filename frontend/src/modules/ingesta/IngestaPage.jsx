// frontend/src/modules/ingesta/IngestaPage.jsx
import { useRef, useState } from 'react';
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

function IconCheck() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
        </svg>
    );
}

function IconCross() {
    return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
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

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function IngestaPage() {
    const [file, setFile] = useState(null);
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [completedSteps, setCompletedSteps] = useState([]);
    const [failedStep, setFailedStep] = useState(null);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const inputRef = useRef(null);

    const resetOutcome = () => {
        setResult(null);
        setError(null);
        setFailedStep(null);
    };

    const pickFile = (selected) => {
        if (!selected) return;
        setFile(selected);
        setCompletedSteps(["select"]);
        resetOutcome();
    };

    const handleFileInput = (e) => pickFile(e.target.files[0]);

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        const dropped = e.dataTransfer.files?.[0];
        if (dropped && dropped.name.toLowerCase().endsWith(".xlsx")) {
            pickFile(dropped);
        }
    };

    const advance = (key) => setCompletedSteps((prev) => [...prev, key]);

    const uploadFile = async () => {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${API_BASE}/ingestion/upload`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Error desconocido al subir el archivo.");
        }
        return data;
    };

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

    const handleProcess = async () => {
        if (!file) return;

        setIsUploading(true);
        resetOutcome();
        setCompletedSteps(["select"]);

        try {
            const uploadData = await uploadFile();
            advance("validate_file");
            advance("extract");

            const processData = await processFile(uploadData);
            advance("validate_data");
            advance("clean");
            advance("normalize");
            advance("structure");

            if (processData.status === "completed") {
                advance("done");
            } else {
                setFailedStep("done");
            }
            setResult(processData);
        } catch (err) {
            const nextStepIndex = PIPELINE_STEPS.findIndex(
                (step) => !completedSteps.includes(step.key)
            );
            setFailedStep(PIPELINE_STEPS[nextStepIndex]?.key ?? "done");
            setError(err.message);
        } finally {
            setIsUploading(false);
        }
    };

    const clearFile = () => {
        setFile(null);
        setCompletedSteps([]);
        resetOutcome();
        if (inputRef.current) inputRef.current.value = "";
    };

    const stepsToShow = completedSteps.length > 0 || failedStep
        ? PIPELINE_STEPS.filter((step, index) => {
            const failedIndex = PIPELINE_STEPS.findIndex((s) => s.key === failedStep);
            return failedIndex === -1 || index <= failedIndex;
        })
        : [];

    return (
        <div className="ingesta-page">
            <div className="ingesta-shell">
                <header className="ingesta-header">
                    <span className="ingesta-eyebrow">Módulo de ingesta</span>
                    <h1 className="ingesta-title">Carga de datos de handover</h1>
                    <p className="ingesta-subtitle">
                        Sube un archivo Excel con mediciones de handover para validarlo,
                        limpiarlo y estructurarlo como dataset listo para análisis.
                    </p>
                </header>

                <section className="ingesta-card">
                    <h2 className="ingesta-card-title">Archivo</h2>
                    <p className="ingesta-card-hint">Formato soportado: .xlsx</p>

                    <label
                        className={`ingesta-dropzone ${isDragging ? "is-dragging" : ""} ${file ? "has-file" : ""}`}
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={handleDrop}
                    >
                        <input
                            ref={inputRef}
                            type="file"
                            accept=".xlsx"
                            onChange={handleFileInput}
                            disabled={isUploading}
                        />
                        <span className="ingesta-dropzone-icon"><IconUpload /></span>
                        {file ? (
                            <>
                                <span className="ingesta-dropzone-filename">{file.name}</span>
                                <span className="ingesta-dropzone-hint">{formatBytes(file.size)} — clic para cambiar de archivo</span>
                            </>
                        ) : (
                            <>
                                <span className="ingesta-dropzone-text">Arrastra tu archivo aquí, o haz clic para seleccionarlo</span>
                                <span className="ingesta-dropzone-hint">Datos_Tesis.xlsx, mediciones de campo, etc.</span>
                            </>
                        )}
                    </label>

                    <button
                        className="ingesta-btn"
                        onClick={handleProcess}
                        disabled={!file || isUploading}
                    >
                        {isUploading && <span className="ingesta-spinner" />}
                        {isUploading ? "Procesando…" : "Procesar archivo"}
                    </button>

                    {file && !isUploading && !result && (
                        <button
                            type="button"
                            onClick={clearFile}
                            style={{
                                marginTop: 10,
                                background: "none",
                                border: "none",
                                color: "var(--color-text-faint)",
                                fontSize: 12.5,
                                cursor: "pointer",
                                padding: 0,
                            }}
                        >
                            Quitar archivo
                        </button>
                    )}

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
                </section>

                {error && (
                    <section className="ingesta-card">
                        <div className="ingesta-alert is-error">
                            <span className="ingesta-alert-icon"><IconAlert /></span>
                            <div>
                                <p className="ingesta-alert-title">No se pudo completar el procesamiento</p>
                                <p>{error}</p>
                            </div>
                        </div>
                    </section>
                )}

                {result && (
                    <section className="ingesta-card">
                        <div className="ingesta-result-header">
                            <h2 className="ingesta-card-title">Resultado</h2>
                            <span className={`ingesta-status-pill ${result.status === "completed" ? "is-completed" : "is-failed"}`}>
                                {result.status === "completed" ? "Completado" : "Con errores"}
                            </span>
                        </div>
                        <p className="ingesta-result-meta">
                            {result.filename} · {result.execution_id}
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

                        <div className="ingesta-section">
                            <h3 className="ingesta-section-title">Errores</h3>
                            {result.errors.length === 0 ? (
                                <p className="ingesta-note is-empty">Sin errores</p>
                            ) : (
                                <ul className="ingesta-note-list">
                                    {result.errors.map((err) => (
                                        <li key={err} className="ingesta-note is-warning" style={{ color: "var(--color-error)", background: "var(--color-error-soft)" }}>
                                            {err}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
}
