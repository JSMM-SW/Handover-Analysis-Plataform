// frontend/src/modules/ingesta/IngestaPage.jsx
import { useState } from 'react';

const API_BASE = "http://localhost:8000/api/v1";

export default function IngestaPage() {
    const [file, setFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [statusList, setStatusList] = useState([]);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handleFileChange = (e) => {
        const selectedFile = e.target.files[0];
        setFile(selectedFile || null);
        setStatusList(selectedFile ? [{ text: "Archivo seleccionado", kind: "" }] : []);
        setResult(null);
        setError(null);
    };

    const pushStatus = (text, kind = "") => {
        setStatusList(prev => [...prev, { text, kind }]);
    };

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

    const handleUpload = async () => {
        if (!file) return;

        setIsUploading(true);
        setResult(null);
        setError(null);
        setStatusList([{ text: "Archivo seleccionado", kind: "" }]);

        try {
            const uploadData = await uploadFile();
            pushStatus("Validando archivo", "success");
            pushStatus(`Extrayendo datos (${uploadData.sheets.length} hoja(s) detectada(s))`, "success");

            const processData = await processFile(uploadData);
            pushStatus("Validando información", "success");
            pushStatus("Limpiando datos", "success");
            pushStatus("Normalizando datos", "success");
            pushStatus("Generando dataset", "success");

            if (processData.status === "completed") {
                pushStatus("Procesamiento completado", "success");
            } else {
                pushStatus("Procesamiento finalizado con errores", "error");
            }
            setResult(processData);
        } catch (err) {
            pushStatus("Error durante el procesamiento", "error");
            setError(err.message);
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className="container mx-auto p-4">
            <div className="card bg-white shadow-md rounded p-6 mb-4">
                <h2 className="text-xl font-bold mb-4">Carga de datos de handover</h2>

                <div className="flex items-center gap-4 mb-4">
                    <input type="file" accept=".xlsx" onChange={handleFileChange} />
                    <span className="text-gray-500">
                        {file ? file.name : "Ningún archivo seleccionado"}
                    </span>
                </div>

                <button
                    onClick={handleUpload}
                    disabled={!file || isUploading}
                    className="bg-blue-600 text-white px-4 py-2 rounded disabled:bg-gray-400"
                >
                    {isUploading ? "Procesando..." : "Procesar archivo"}
                </button>

                <ul className="mt-4">
                    {statusList.map((status, index) => (
                        <li key={index} className={
                            status.kind === 'success' ? 'text-green-600' :
                            status.kind === 'error' ? 'text-red-600' : 'text-gray-600'
                        }>
                            {status.text}
                        </li>
                    ))}
                </ul>
            </div>

            {error && (
                <div className="card bg-red-50 border border-red-200 text-red-700 p-6 rounded">
                    <h2 className="font-bold">Error</h2>
                    <p>{error}</p>
                </div>
            )}

            {result && (
                <div className="card bg-white shadow-md rounded p-6">
                    <h2 className="text-xl font-bold mb-4">Resultado</h2>
                    <dl className="grid grid-cols-2 gap-4 mb-6">
                        <dt className="text-gray-500">Identificador de ejecución</dt>
                        <dd className="font-semibold">{result.execution_id}</dd>

                        <dt className="text-gray-500">Archivo</dt>
                        <dd className="font-semibold">{result.filename}</dd>

                        <dt className="text-gray-500">Registros leídos</dt>
                        <dd className="font-semibold">{result.records_read}</dd>

                        <dt className="text-gray-500">Registros válidos</dt>
                        <dd className="font-semibold">{result.records_valid}</dd>

                        <dt className="text-gray-500">Registros rechazados</dt>
                        <dd className="font-semibold">{result.records_rejected}</dd>

                        <dt className="text-gray-500">Tiempo de procesamiento</dt>
                        <dd className="font-semibold">{result.processing_time_seconds} s</dd>
                    </dl>

                    <h3 className="font-bold mb-2">Advertencias</h3>
                    <ul className="mb-6">
                        {result.warnings.length === 0 ? (
                            <li className="text-gray-400 italic">Sin advertencias</li>
                        ) : (
                            result.warnings.map((warning, index) => <li key={index}>{warning}</li>)
                        )}
                    </ul>

                    <h3 className="font-bold mb-2">Errores</h3>
                    <ul>
                        {result.errors.length === 0 ? (
                            <li className="text-gray-400 italic">Sin errores</li>
                        ) : (
                            result.errors.map((err, index) => <li key={index}>{err}</li>)
                        )}
                    </ul>
                </div>
            )}
        </div>
    );
}
