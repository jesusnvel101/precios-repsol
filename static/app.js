const yearSelect = document.getElementById("yearSelect");
const btnLoadYear = document.getElementById("btnLoadYear");
const btnSaveYear = document.getElementById("btnSaveYear");
const tableBody = document.getElementById("tableBody");
const messageBox = document.getElementById("messageBox");

const kpiUltimoAnio = document.getElementById("kpiUltimoAnio");
const kpiUltimoMes = document.getElementById("kpiUltimoMes");
const kpiUltimaActualizacion = document.getElementById("kpiUltimaActualizacion");
const kpiCeldas = document.getElementById("kpiCeldas");

let configData = null;
let currentYearLoaded = null;

function showMessage(text, isError = false) {
    messageBox.className = isError ? "message-box error" : "message-box ok";
    messageBox.textContent = String(text);
}

function clearMessage() {
    messageBox.className = "message-box";
    messageBox.textContent = "";
}

function startClock() {
    const dateEl = document.getElementById("currentDate");
    const clockEl = document.getElementById("liveClock");

    function tick() {
        const now = new Date();
        dateEl.textContent = now.toLocaleDateString("es-MX");
        clockEl.textContent = now.toLocaleTimeString("es-MX", { hour12: false });
    }

    tick();
    setInterval(tick, 1000);
}

function blockInvalidNumericInput(input) {
    input.addEventListener("keydown", (event) => {
        if (["e", "E", "+", "-"].includes(event.key)) {
            event.preventDefault();
        }
    });

    input.addEventListener("paste", (event) => {
        const pasted = (event.clipboardData || window.clipboardData).getData("text");
        if (/[eE+\-]/.test(pasted)) {
            event.preventDefault();
        }
    });

    input.addEventListener("input", () => {
        let value = input.value.replace(/[eE+\-]/g, "");
        if (value !== "" && (!Number.isFinite(Number(value)) || Number(value) < 0)) {
            value = "";
        }
        input.value = value;
    });
}

async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        cache: "no-store",
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    let data = null;
    try {
        data = await response.json();
    } catch {
        data = null;
    }

    if (!response.ok) {
        throw new Error(data?.detail || data?.message || "Error en la solicitud.");
    }

    return data;
}

async function fetchConfig() {
    configData = await apiFetch("/api/config");
}

async function fetchDashboard() {
    const data = await apiFetch("/api/dashboard");

    kpiUltimoAnio.textContent = data.ultimo_anio_cargado ?? "-";
    kpiUltimoMes.textContent = data.ultimo_mes_cargado ?? "-";
    kpiUltimaActualizacion.textContent = data.ultima_actualizacion ?? "-";
    kpiCeldas.textContent = data.cantidad_celdas_con_datos ?? 0;
}

function buildYearOptions() {
    yearSelect.innerHTML = "";

    for (const year of configData.allowed_years) {
        const option = document.createElement("option");
        option.value = String(year);
        option.textContent = String(year);
        yearSelect.appendChild(option);
    }

    yearSelect.value = String(configData.current_year);
}

function createInput(value, enabled) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.step = "any";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.value = value ?? "";
    input.disabled = !enabled;

    if (enabled) {
        blockInvalidNumericInput(input);
    }

    return input;
}

function getBadgeHtml(enabled) {
    return enabled
        ? `<span class="badge badge-open">Habilitado</span>`
        : `<span class="badge badge-locked">Bloqueado</span>`;
}

function renderYearTable(yearData) {
    tableBody.innerHTML = "";

    for (const item of yearData.meses) {
        const tr = document.createElement("tr");
        tr.dataset.month = String(item.mes);

        if (!item.enabled) {
            tr.classList.add("locked-row");
        }

        tr.innerHTML = `
            <td class="month-name">${item.mes_nombre}</td>
            <td>${getBadgeHtml(item.enabled)}</td>
            <td></td>
            <td></td>
            <td></td>
            <td></td>
            <td class="updated-at">${item.updated_at || "-"}</td>
        `;

        const cells = tr.querySelectorAll("td");
        cells[2].appendChild(createInput(item.margen_fcc, item.enabled));
        cells[3].appendChild(createInput(item.margen_visbreaking, item.enabled));
        cells[4].appendChild(createInput(item.lvgo_diesel, item.enabled));
        cells[5].appendChild(createInput(item.lvgo_corte, item.enabled));

        tableBody.appendChild(tr);
    }
}

async function loadYear(year) {
    clearMessage();
    const data = await apiFetch(`/api/precios/${year}`);
    currentYearLoaded = Number(year);
    renderYearTable(data);
}

function buildSavePayloadFromTable() {
    const rows = Array.from(tableBody.querySelectorAll("tr"));
    const meses = [];

    for (const row of rows) {
        if (row.classList.contains("locked-row")) {
            continue;
        }

        const mes = Number(row.dataset.month);
        const inputs = row.querySelectorAll("input");

        meses.push({
            mes,
            margen_fcc: inputs[0].value === "" ? null : Number(inputs[0].value),
            margen_visbreaking: inputs[1].value === "" ? null : Number(inputs[1].value),
            lvgo_diesel: inputs[2].value === "" ? null : Number(inputs[2].value),
            lvgo_corte: inputs[3].value === "" ? null : Number(inputs[3].value),
        });
    }

    return { meses };
}

async function saveFullYear() {
    clearMessage();

    if (!currentYearLoaded) {
        showMessage("No hay un año cargado.", true);
        return;
    }

    const payload = buildSavePayloadFromTable();

    const data = await apiFetch(`/api/precios/${currentYearLoaded}/guardar-todo`, {
        method: "POST",
        body: JSON.stringify(payload),
    });

    showMessage(data.message || "Año guardado correctamente.");
    await loadYear(currentYearLoaded);
    await fetchDashboard();
}

yearSelect.addEventListener("change", async () => {
    try {
        await loadYear(Number(yearSelect.value));
    } catch (error) {
        showMessage(error.message || "No se pudo cargar el año.", true);
    }
});

btnLoadYear.addEventListener("click", async () => {
    try {
        await loadYear(Number(yearSelect.value));
    } catch (error) {
        showMessage(error.message || "No se pudo cargar el año.", true);
    }
});

btnSaveYear.addEventListener("click", async () => {
    try {
        btnSaveYear.disabled = true;
        await saveFullYear();
    } catch (error) {
        showMessage(error.message || "No se pudo guardar el año.", true);
    } finally {
        btnSaveYear.disabled = false;
    }
});

async function init() {
    startClock();

    try {
        await fetchConfig();
        buildYearOptions();
        await loadYear(Number(yearSelect.value));
        await fetchDashboard();
    } catch (error) {
        showMessage(error.message || "Error al inicializar.", true);
    }
}

init();