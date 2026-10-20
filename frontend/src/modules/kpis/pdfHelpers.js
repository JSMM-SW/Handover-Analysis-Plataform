import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

/**
 * Espera a que el navegador pinte dos frames seguidos.
 *
 * Al cambiar `data-tema`, el MutationObserver de `useColorDeTema` (ver
 * graficoHelpers.jsx) agenda un re-render de React; el primer frame deja
 * que React aplique los nuevos colores al DOM y el segundo garantiza que
 * el navegador ya los pintó antes de que html2canvas capture.
 *
 * @returns {Promise<void>} se resuelve después del segundo frame.
 */
function esperarRepintado() {
    return new Promise((resolver) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolver()));
    });
}

/**
 * Calcula dónde debe caer cada salto de página del PDF para que ninguna
 * sección (tarjeta, gráfico o tabla) quede partida entre dos páginas.
 *
 * En vez de avanzar en incrementos fijos de `altoPagina` (como antes), si
 * el límite de una página cae DENTRO de una sección, el corte se adelanta
 * al inicio de esa sección -- esa sección completa pasa entera a la
 * siguiente página. Si una sola sección es más alta que una página
 * completa, no hay forma de evitar el corte y se divide donde alcanza.
 *
 * @param {Array<{inicio: number, fin: number}>} limites - posición (en mm,
 * mismas unidades que `altoPagina`/`altoTotal`) de cada sección dentro de
 * la imagen completa capturada.
 * @param {number} altoPagina - alto de una página del PDF, en mm.
 * @param {number} altoTotal - alto de la imagen completa capturada, en mm.
 * @returns {number[]} los puntos de corte, de 0 a `altoTotal` inclusive.
 */
function calcularSaltosDePagina(limites, altoPagina, altoTotal) {
    const saltos = [0];
    let actual = 0;

    while (actual < altoTotal - 0.01) {
        const limitePagina = actual + altoPagina;
        if (limitePagina >= altoTotal) {
            saltos.push(altoTotal);
            break;
        }

        const seccionCruzada = limites.find(
            ({ inicio, fin }) => inicio < limitePagina - 0.01 && fin > limitePagina + 0.01
        );
        let corte = seccionCruzada ? seccionCruzada.inicio : limitePagina;
        if (corte <= actual + 0.01) {
            // La sección es más alta que una página completa: no se puede
            // evitar el corte, se divide donde alcanza.
            corte = limitePagina;
        }

        saltos.push(corte);
        actual = corte;
    }

    return saltos;
}

/**
 * Captura un elemento del DOM con html2canvas y lo guarda como PDF,
 * repartido en varias páginas A4 si no cabe en una sola, sin que ninguna
 * sección (tarjeta/gráfico/tabla, identificada por `.kpis-resumen-panel`
 * o `.kpis-card`) quede partida entre dos páginas.
 *
 * Compartida entre `KpisDashboard.jsx` (exportar el dashboard en vivo) y
 * `HistorialReportesModal.jsx` (regenerar un PDF antiguo desde su
 * snapshot guardado) -- antes vivía solo en `exportToPDF`, duplicarla
 * para el historial habría repetido toda esta matemática de páginas.
 *
 * El elemento debe estar ya en su estado final (clases/estilos de
 * captura aplicados) antes de llamar esta función -- ella solo espera el
 * repintado, mide, captura y arma el PDF.
 *
 * @param {HTMLElement} element - el elemento a capturar.
 * @param {string} nombreArchivo - nombre del archivo .pdf a descargar.
 * @returns {Promise<void>}
 */
export async function generarPdfDesdeElemento(element, nombreArchivo) {
    await esperarRepintado();

    // Posición (en px CSS, antes de escalar) de cada sección que no debe
    // partirse entre dos páginas, relativa al propio elemento capturado --
    // se mide ANTES de generar el canvas, con el DOM ya en su estado final.
    const rectRaiz = element.getBoundingClientRect();
    const alturaTotalPx = element.scrollHeight;
    const limitesSeccionPx = Array.from(
        element.querySelectorAll('.kpis-resumen-panel, .kpis-card')
    ).map((seccion) => {
        const rect = seccion.getBoundingClientRect();
        return { inicio: rect.top - rectRaiz.top, fin: rect.bottom - rectRaiz.top };
    });

    const fondoActual = getComputedStyle(document.documentElement).getPropertyValue('--color-fondo').trim();

    const canvas = await html2canvas(element, {
        backgroundColor: fondoActual,
        scale: 2,
    });

    const imgData = canvas.toDataURL('image/jpeg', 0.85);

    const pdf = new jsPDF('p', 'mm', 'a4');
    const anchoPdf = pdf.internal.pageSize.getWidth();
    const altoPagina = pdf.internal.pageSize.getHeight();
    const altoImagen = (canvas.height * anchoPdf) / canvas.width;

    // Convierte los límites de cada sección de px CSS a mm del PDF, con la
    // misma proporción que ya usa el resto de la imagen.
    const pxAMm = altoImagen / alturaTotalPx;
    const limitesSeccionMm = limitesSeccionPx.map(({ inicio, fin }) => ({
        inicio: inicio * pxAMm,
        fin: fin * pxAMm,
    }));

    const saltos = calcularSaltosDePagina(limitesSeccionMm, altoPagina, altoImagen);
    for (let indice = 0; indice < saltos.length - 1; indice += 1) {
        if (indice > 0) pdf.addPage();
        pdf.addImage(imgData, 'JPEG', 0, -saltos[indice], anchoPdf, altoImagen);
    }

    pdf.save(nombreArchivo);
}
