import { useEffect, useRef, useState } from 'react';

/**
 * Desplegable con checkboxes para filtros de selección múltiple (ej.
 * tecnología, franja horaria, sesión). Cerrado por defecto; el botón
 * muestra un resumen de la selección actual en vez de la lista completa,
 * para no ocupar espacio del header cuando no se está usando.
 *
 * Selección vacía = "todas" (ver kpisService.js/kpis backend): por eso el
 * resumen muestra `allLabel` tanto si no hay nada seleccionado como si
 * está todo seleccionado -- en ambos casos equivale a "sin filtro".
 */
export default function MultiSelectDropdown({ label, options, selected, onChange, allLabel = 'Todas' }) {
    const [abierto, setAbierto] = useState(false);
    const contenedorRef = useRef(null);

    useEffect(() => {
        function alHacerClicFuera(evento) {
            if (contenedorRef.current && !contenedorRef.current.contains(evento.target)) {
                setAbierto(false);
            }
        }
        document.addEventListener('mousedown', alHacerClicFuera);
        return () => document.removeEventListener('mousedown', alHacerClicFuera);
    }, []);

    const alternarValor = (valor) => {
        if (selected.includes(valor)) {
            onChange(selected.filter((v) => v !== valor));
        } else {
            onChange([...selected, valor]);
        }
    };

    const resumen = () => {
        if (selected.length === 0 || selected.length === options.length) return allLabel;
        if (selected.length === 1) {
            const opcion = options.find((o) => o.value === selected[0]);
            return opcion ? opcion.label : allLabel;
        }
        return `${selected.length} seleccionadas`;
    };

    return (
        <div className="kpis-date-filter" ref={contenedorRef} style={{ position: 'relative' }}>
            <span className="kpis-date-label">{label}</span>
            <button
                type="button"
                className="kpis-input kpis-multiselect-boton"
                onClick={() => setAbierto((valor) => !valor)}
            >
                {resumen()}
            </button>
            {abierto && (
                <div className="kpis-multiselect-panel">
                    {options.map((opcion) => (
                        <label key={opcion.value} className="kpis-multiselect-opcion">
                            <input
                                type="checkbox"
                                checked={selected.includes(opcion.value)}
                                onChange={() => alternarValor(opcion.value)}
                            />
                            {opcion.label}
                        </label>
                    ))}
                </div>
            )}
        </div>
    );
}
