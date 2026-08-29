const fileInput = document.getElementById("file-input");
const fileNameLabel = document.getElementById("file-name");
const uploadBtn = document.getElementById("upload-btn");
const statusList = document.getElementById("status-list");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");
const errorMessage = document.getElementById("error-message");

function addStatus(text, kind) {
    const item = document.createElement("li");
    item.textContent = text;
    if (kind) {
        item.classList.add(`status-${kind}`);
    }
    statusList.appendChild(item);
}

function resetPanels() {
    statusList.innerHTML = "";
    resultSection.classList.add("hidden");
    errorSection.classList.add("hidden");
}

fileInput.addEventListener("change", () => {
    resetPanels();
    const file = fileInput.files[0];
    if (file) {
        fileNameLabel.textContent = file.name;
        uploadBtn.disabled = false;
        addStatus("Archivo seleccionado");
    } else {
        fileNameLabel.textContent = "Ningún archivo seleccionado";
        uploadBtn.disabled = true;
    }
});

uploadBtn.addEventListener("click", async () => {
    const file = fileInput.files[0];
    if (!file) {
        return;
    }

    uploadBtn.disabled = true;
    resetPanels();
    addStatus("Archivo seleccionado");

    try {
        const uploadData = await uploadFile(file);
        addStatus("Validando archivo", "success");
        addStatus(`Extrayendo datos (${uploadData.sheets.length} hoja(s) detectada(s))`, "success");

        const result = await processFile(uploadData);
        addStatus("Validando información", "success");
        addStatus("Limpiando datos", "success");
        addStatus("Normalizando datos", "success");
        addStatus("Generando dataset", "success");

        if (result.status === "completed") {
            addStatus("Procesamiento completado", "success");
        } else {
            addStatus("Procesamiento finalizado con errores", "error");
        }
        renderResult(result);
    } catch (error) {
        addStatus("Error durante el procesamiento", "error");
        errorMessage.textContent = error.message;
        errorSection.classList.remove("hidden");
    } finally {
        uploadBtn.disabled = false;
    }
});

async function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/v1/ingestion/upload", {
        method: "POST",
        body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.detail || "Error desconocido al subir el archivo.");
    }
    return data;
}

async function processFile(uploadData) {
    const response = await fetch("/api/v1/ingestion/process", {
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
}

function renderResult(result) {
    document.getElementById("result-execution-id").textContent = result.execution_id;
    document.getElementById("result-filename").textContent = result.filename;
    document.getElementById("result-read").textContent = result.records_read;
    document.getElementById("result-valid").textContent = result.records_valid;
    document.getElementById("result-rejected").textContent = result.records_rejected;
    document.getElementById("result-time").textContent = `${result.processing_time_seconds} s`;

    renderList("result-warnings", result.warnings, "Sin advertencias");
    renderList("result-errors", result.errors, "Sin errores");

    resultSection.classList.remove("hidden");
}

function renderList(elementId, items, emptyText) {
    const list = document.getElementById(elementId);
    list.innerHTML = "";
    if (!items || items.length === 0) {
        const li = document.createElement("li");
        li.textContent = emptyText;
        li.classList.add("muted");
        list.appendChild(li);
        return;
    }
    for (const item of items) {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
    }
}
