import { useState, useEffect } from 'react';

/**
 * Lee el valor actual de una variable CSS del tema (ej. "--color-exito")
 * y lo mantiene sincronizado cuando el usuario alterna claro/oscuro.
 *
 * El nombre empieza con "use" (en inglés) a propósito: React exige ese
 * prefijo en toda función que llame a useState/useEffect para reconocerla
 * como hook (regla react-hooks/rules-of-hooks del lint).
 *
 * Los gráficos de Recharts se dibujan como SVG y reciben sus colores por
 * atributos (fill/stroke), no por CSS -- los navegadores no resuelven
 * `var(--token)` de forma confiable ahí (se ve todo en negro), y
 * html2canvas tampoco sabe interpretar `var(...)` al exportar el PDF.
 * Por eso se resuelve el valor real (ej. "#34d399") en JavaScript con
 * `getComputedStyle`, en vez de pasar el string `var(--token)` directo.
 *
 * El MutationObserver detecta cuando cambia `data-tema` en <html> (ya sea
 * por `alternarTema` en App.jsx o por `exportToPDF`, que fuerza el tema
 * oscuro durante la captura) para recalcular el color.
 *
 * Vive en su propio archivo (en vez de KpisDashboard.jsx) porque tanto el
 * dashboard en vivo como ReporteImprimible.jsx (usado también para
 * regenerar PDFs del historial) necesitan resolver estos mismos colores.
 *
 * @param {string} nombreVariable - nombre de la variable CSS, con "--".
 * @returns {string} el color ya resuelto (ej. "#34d399").
 */
export function useColorDeTema(nombreVariable) {
    const [color, setColor] = useState('#000000');

    useEffect(() => {
        const raiz = document.documentElement;
        const leerColor = () => {
            const valor = getComputedStyle(raiz).getPropertyValue(nombreVariable).trim();
            if (valor) setColor(valor);
        };
        leerColor();

        const observador = new MutationObserver(leerColor);
        observador.observe(raiz, { attributes: true, attributeFilter: ['data-tema'] });
        return () => observador.disconnect();
    }, [nombreVariable]);

    return color;
}

/**
 * Contenido de tooltip para los gráficos de distribución (hora/franja/día
 * de la semana): además de las series que ya dibuja Recharts (exitosos,
 * fallidos, indeterminados, ping-pongs), agrega la línea "Mediciones
 * registradas", que no es una serie graficada sino contexto de volumen de
 * datos (Paso 9 del plan de refactor).
 *
 * Recibe los colores de superficie/borde/texto por parámetro (en vez de
 * leerlos con el hook useColorDeTema) porque es una función común usada por
 * los 3 gráficos, no un componente propio.
 *
 * @param {object} props - props estándar de un `content` de Recharts (`active`, `payload`, `label`).
 * @param {string} colorSuperficie - color de fondo del tooltip, ya resuelto.
 * @param {string} colorBorde - color del borde del tooltip, ya resuelto.
 * @param {string} colorTexto - color del texto del tooltip, ya resuelto.
 * @returns {JSX.Element | null} el tooltip, o null si no hay nada que mostrar.
 */
export function renderTooltipConMediciones({ active, payload, label }, colorSuperficie, colorBorde, colorTexto) {
    if (!active || !payload || payload.length === 0) return null;

    const totalMediciones = payload[0].payload.total_mediciones;

    return (
        <div style={{
            backgroundColor: colorSuperficie,
            border: `1px solid ${colorBorde}`,
            borderRadius: '6px',
            padding: '8px 12px',
            color: colorTexto,
            fontSize: '13px',
        }}>
            <p style={{ margin: '0 0 4px', fontWeight: 600 }}>{label}</p>
            {payload.map((entry) => (
                <p key={entry.dataKey} style={{ margin: 0, color: entry.color }}>
                    {entry.name}: {entry.value}
                </p>
            ))}
            <p style={{ margin: '4px 0 0', paddingTop: '4px', borderTop: `1px solid ${colorBorde}` }}>
                Mediciones registradas: {totalMediciones}
            </p>
        </div>
    );
}
