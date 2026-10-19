import { useEffect, useState } from 'react';

const MESES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

function anioDeFecha(fechaISO) {
    return Number(fechaISO.slice(0, 4));
}
function mesDeFecha(fechaISO) {
    return Number(fechaISO.slice(5, 7));
}
function primerDiaDelMes(anio, mes) {
    return `${anio}-${String(mes).padStart(2, '0')}-01`;
}
function ultimoDiaDelMes(anio, mes) {
    const ultimoDia = new Date(anio, mes, 0).getDate(); // día 0 del mes siguiente = último día de este mes
    return `${anio}-${String(mes).padStart(2, '0')}-${String(ultimoDia).padStart(2, '0')}`;
}
function primerDiaDelAnio(anio) {
    return `${anio}-01-01`;
}
function ultimoDiaDelAnio(anio) {
    return `${anio}-12-31`;
}

/**
 * Selector de ventana temporal que se adapta a la periodicidad elegida:
 * con "diario" deja escoger cualquier día; con "mensual"/"anual" solo deja
 * escoger la granularidad que corresponde (mes+año, o año) -- no tiene
 * sentido pedir un día exacto para una gráfica que de todas formas agrupa
 * por mes/año.
 *
 * Mantiene su propio estado granular y se lo comunica al padre ya
 * convertido a fechas ISO (`onChange(inicio, fin)`) -- el padre sigue
 * trabajando solo con fechas, sin saber nada de esta conversión.
 *
 * `aniosDisponibles` lo calcula el padre (KpisDashboard) a partir de las
 * fechas reales de las sesiones cargadas -- Paso 7 del plan de refactor:
 * antes este componente mostraba "año actual y 9 anteriores" fijo, sin
 * relación con los datos que realmente existen.
 */
export default function VentanaTemporalSelector({ periodo, startDate, endDate, aniosDisponibles, onChange }) {
    const anioActual = new Date().getFullYear();
    const mesActual = new Date().getMonth() + 1;
    const [anioInicio, setAnioInicio] = useState(() => (startDate ? anioDeFecha(startDate) : anioActual));
    const [mesInicio, setMesInicio] = useState(() => (startDate ? mesDeFecha(startDate) : mesActual));
    const [anioFin, setAnioFin] = useState(() => (endDate ? anioDeFecha(endDate) : anioActual));
    const [mesFin, setMesFin] = useState(() => (endDate ? mesDeFecha(endDate) : mesActual));

    // `startDate`/`endDate` llegan vacíos en el primer render (antes de que
    // KpisDashboard ajuste la ventana automática a las sesiones cargadas);
    // el useState de arriba solo corre una vez al montar, así que sin este
    // efecto anioInicio/mesInicio quedaban congelados en el valor inicial
    // para siempre. Se sincroniza cada vez que el padre entrega fechas
    // válidas -- incluye las que este mismo componente genera via
    // onChange, pero eso es un no-op (misma fecha, mismo año/mes).
    useEffect(() => {
        if (!startDate || !endDate) return;
        // Estado derivado de una fuente externa (startDate/endDate que
        // llega del padre), no un efecto secundario evitable -- mismo
        // patrón que el resto del dashboard.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setAnioInicio(anioDeFecha(startDate));
        setMesInicio(mesDeFecha(startDate));
        setAnioFin(anioDeFecha(endDate));
        setMesFin(mesDeFecha(endDate));
    }, [startDate, endDate]);

    useEffect(() => {
        if (periodo === 'mensual') {
            onChange(primerDiaDelMes(anioInicio, mesInicio), ultimoDiaDelMes(anioFin, mesFin));
        } else if (periodo === 'anual') {
            onChange(primerDiaDelAnio(anioInicio), ultimoDiaDelAnio(anioFin));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [periodo, anioInicio, mesInicio, anioFin, mesFin]);

    if (periodo === 'diario') {
        return (
            <div className="kpis-date-inputs">
                <input type="date" className="kpis-input" value={startDate} onChange={(e) => onChange(e.target.value, endDate)} />
                <span className="kpis-date-separador">a</span>
                <input type="date" className="kpis-input" value={endDate} onChange={(e) => onChange(startDate, e.target.value)} />
            </div>
        );
    }

    if (periodo === 'mensual') {
        return (
            <div className="kpis-date-inputs">
                <select className="kpis-input" value={mesInicio} onChange={(e) => setMesInicio(Number(e.target.value))}>
                    {MESES.map((nombre, indice) => <option key={nombre} value={indice + 1}>{nombre}</option>)}
                </select>
                <select className="kpis-input" value={anioInicio} onChange={(e) => setAnioInicio(Number(e.target.value))}>
                    {aniosDisponibles.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
                </select>
                <span className="kpis-date-separador">a</span>
                <select className="kpis-input" value={mesFin} onChange={(e) => setMesFin(Number(e.target.value))}>
                    {MESES.map((nombre, indice) => <option key={nombre} value={indice + 1}>{nombre}</option>)}
                </select>
                <select className="kpis-input" value={anioFin} onChange={(e) => setAnioFin(Number(e.target.value))}>
                    {aniosDisponibles.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
                </select>
            </div>
        );
    }

    // periodo === 'anual'
    return (
        <div className="kpis-date-inputs">
            <select className="kpis-input" value={anioInicio} onChange={(e) => setAnioInicio(Number(e.target.value))}>
                {aniosDisponibles.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
            </select>
            <span className="kpis-date-separador">a</span>
            <select className="kpis-input" value={anioFin} onChange={(e) => setAnioFin(Number(e.target.value))}>
                {aniosDisponibles.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
            </select>
        </div>
    );
}
