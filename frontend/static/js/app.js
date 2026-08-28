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
    addStatus("Subiendo y validando archivo...");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch("/api/v1/ingestion/upload", {
            method: "POST",
            body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Error desconocido al procesar el archivo.");
        }

        addStatus("Procesamiento completado", "success");
        renderResult(data);
    } catch (error) {
        addStatus("Error durante el procesamiento", "error");
        errorMessage.textContent = error.message;
        errorSection.classList.remove("hidden");
    } finally {
        uploadBtn.disabled = false;
    }
});

function renderResult(result) {
    document.getElementById("result-execution-id").textContent = result.execution_id;
    document.getElementById("result-filename").textContent = result.original_filename;
    document.getElementById("result-size").textContent = formatBytes(result.file_size_bytes);
    document.getElementById("result-time").textContent = `${result.processing_time_seconds} s`;

    const tbody = document.getElementById("sheets-table-body");
    tbody.innerHTML = "";
    for (const sheet of result.sheets) {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${escapeHtml(sheet.name)}</td>
            <td>${sheet.num_rows}</td>
            <td>${sheet.num_cols}</td>
            <td>${escapeHtml(sheet.headers.join(", "))}</td>
        `;
        tbody.appendChild(row);
    }

    resultSection.classList.remove("hidden");
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}
