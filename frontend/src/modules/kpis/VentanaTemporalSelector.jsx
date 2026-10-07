import { useEffect, useState } from 'react';

const MESES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];
const ANIO_ACTUAL = new Date().getFullYear();
const ANIOS_DISPONIBLES = Array.from({ length: 10 }, (_, i) => ANIO_ACTUAL - i);

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
function esBisiesto(anio) {
    return (anio % 4 === 0 && anio % 100 !== 0) || anio % 400 === 0;
}
function semanasEnAnioISO(anio) {
    // Un año ISO-8601 tiene 53 semanas si el 31 de diciembre cae jueves,
    // o si cae viernes y el año es bisiesto; si no, tiene 52.
    const unDiciembre = new Date(Date.UTC(anio, 11, 31));
    const diaSemana = unDiciembre.getUTCDay() || 7;
    return diaSemana === 4 || (diaSemana === 5 && esBisiesto(anio)) ? 53 : 52;
}
function fechaDeSemanaISO(anio, semana, diaSemana) {
    // diaSemana: 1=lunes ... 7=domingo. La semana 1 ISO es la que
    // contiene el primer jueves del año (equivalente: la que contiene el
    // 4 de enero) -- mismo criterio que usa kpis/services.py en el backend.
    const cuatroEnero = new Date(Date.UTC(anio, 0, 4));
    const diaSemanaCuatroEnero = cuatroEnero.getUTCDay() || 7;
    const lunesSemana1 = new Date(cuatroEnero);
    lunesSemana1.setUTCDate(cuatroEnero.getUTCDate() - diaSemanaCuatroEnero + 1);
    const resultado = new Date(lunesSemana1);
    resultado.setUTCDate(lunesSemana1.getUTCDate() + (semana - 1) * 7 + (diaSemana - 1));
    return resultado.toISOString().slice(0, 10);
}
function primerDiaDeSemanaISO(anio, semana) {
    return fechaDeSemanaISO(anio, semana, 1);
}
function ultimoDiaDeSemanaISO(anio, semana) {
    return fechaDeSemanaISO(anio, semana, 7);
}

/**
 * Selector de ventana temporal que se adapta a la periodicidad elegida:
 * con "diario" deja escoger cualquier día; con "mensual"/"anual"/"semanal"
 * solo deja escoger la granularidad que corresponde (mes+año, año, o
 * semana+año) -- no tiene sentido pedir un día exacto para una gráfica
 * que de todas formas agrupa por mes/año/semana.
 *
 * Mantiene su propio estado granular y se lo comunica al padre ya
 * convertido a fechas ISO (`onChange(inicio, fin)`) -- el padre sigue
 * trabajando solo con fechas, sin saber nada de esta conversión.
 */
export default function VentanaTemporalSelector({ periodo, startDate, endDate, onChange }) {
    const [anioInicio, setAnioInicio] = useState(() => anioDeFecha(startDate));
    const [mesInicio, setMesInicio] = useState(() => mesDeFecha(startDate));
    const [anioFin, setAnioFin] = useState(() => anioDeFecha(endDate));
    const [mesFin, setMesFin] = useState(() => mesDeFecha(endDate));
    const [semanaInicio, setSemanaInicio] = useState(1);
    const [semanaFin, setSemanaFin] = useState(1);

    useEffect(() => {
        if (periodo === 'mensual') {
            onChange(primerDiaDelMes(anioInicio, mesInicio), ultimoDiaDelMes(anioFin, mesFin));
        } else if (periodo === 'anual') {
            onChange(primerDiaDelAnio(anioInicio), ultimoDiaDelAnio(anioFin));
        } else if (periodo === 'semanal') {
            onChange(primerDiaDeSemanaISO(anioInicio, semanaInicio), ultimoDiaDeSemanaISO(anioFin, semanaFin));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [periodo, anioInicio, mesInicio, anioFin, mesFin, semanaInicio, semanaFin]);

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
                    {ANIOS_DISPONIBLES.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
                </select>
                <span className="kpis-date-separador">a</span>
                <select className="kpis-input" value={mesFin} onChange={(e) => setMesFin(Number(e.target.value))}>
                    {MESES.map((nombre, indice) => <option key={nombre} value={indice + 1}>{nombre}</option>)}
                </select>
                <select className="kpis-input" value={anioFin} onChange={(e) => setAnioFin(Number(e.target.value))}>
                    {ANIOS_DISPONIBLES.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
                </select>
            </div>
        );
    }

    if (periodo === 'anual') {
        return (
            <div className="kpis-date-inputs">
                <select className="kpis-input" value={anioInicio} onChange={(e) => setAnioInicio(Number(e.target.value))}>
                    {ANIOS_DISPONIBLES.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
                </select>
                <span className="kpis-date-separador">a</span>
                <select className="kpis-input" value={anioFin} onChange={(e) => setAnioFin(Number(e.target.value))}>
                    {ANIOS_DISPONIBLES.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
                </select>
            </div>
        );
    }

    // periodo === 'semanal'
    return (
        <div className="kpis-date-inputs">
            <select className="kpis-input" value={semanaInicio} onChange={(e) => setSemanaInicio(Number(e.target.value))}>
                {Array.from({ length: semanasEnAnioISO(anioInicio) }, (_, i) => i + 1).map((semana) => (
                    <option key={semana} value={semana}>Sem {semana}</option>
                ))}
            </select>
            <select className="kpis-input" value={anioInicio} onChange={(e) => setAnioInicio(Number(e.target.value))}>
                {ANIOS_DISPONIBLES.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
            </select>
            <span className="kpis-date-separador">a</span>
            <select className="kpis-input" value={semanaFin} onChange={(e) => setSemanaFin(Number(e.target.value))}>
                {Array.from({ length: semanasEnAnioISO(anioFin) }, (_, i) => i + 1).map((semana) => (
                    <option key={semana} value={semana}>Sem {semana}</option>
                ))}
            </select>
            <select className="kpis-input" value={anioFin} onChange={(e) => setAnioFin(Number(e.target.value))}>
                {ANIOS_DISPONIBLES.map((anio) => <option key={anio} value={anio}>{anio}</option>)}
            </select>
        </div>
    );
}
