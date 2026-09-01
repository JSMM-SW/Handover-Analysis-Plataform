// frontend/src/modules/ingesta/IngestaPage.jsx
import { useState } from 'react';

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

    const handleUpload = async () => {
        if (!file) return;

        setIsUploading(true);
        setResult(null);
        setError(null);
        setStatusList([
            { text: "Archivo seleccionado", kind: "" },
            { text: "Subiendo y validando archivo...", kind: "" }
        ]);

        const formData = new FormData();
        formData.append("file", file);

        try {
            // Nota: Aquí se usa la URL de tu backend
            const response = await fetch("http://localhost:8000/api/v1/ingestion/upload", {
                method: "POST",
                body: formData,
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || "Error desconocido al procesar el archivo.");
            }

            setStatusList(prev => [...prev, { text: "Procesamiento completado", kind: "success" }]);
            setResult(data);
        } catch (err) {
            setStatusList(prev => [...prev, { text: "Error durante el procesamiento", kind: "error" }]);
            setError(err.message);
        } finally {
            setIsUploading(false);
        }
    };

    const formatBytes = (bytes) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
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
                        <dd className="font-semibold">{result.original_filename}</dd>
                        <dt className="text-gray-500">Tamaño</dt>
                        <dd className="font-semibold">{formatBytes(result.file_size_bytes)}</dd>
                        <dt className="text-gray-500">Tiempo de procesamiento</dt>
                        <dd className="font-semibold">{result.processing_time_seconds} s</dd>
                    </dl>

                    <h3 className="font-bold mb-2">Hojas detectadas</h3>
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="border-b">
                                <th className="py-2">Hoja</th>
                                <th className="py-2">Filas</th>
                                <th className="py-2">Columnas</th>
                                <th className="py-2">Encabezados</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.sheets.map((sheet, index) => (
                                <tr key={index} className="border-b">
                                    <td className="py-2">{sheet.name}</td>
                                    <td className="py-2">{sheet.num_rows}</td>
                                    <td className="py-2">{sheet.num_cols}</td>
                                    <td className="py-2">{sheet.headers.join(", ")}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}