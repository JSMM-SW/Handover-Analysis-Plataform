from datetime import date
from app.modules.kpis.repository import KpisRepository
from app.modules.kpis.schemas import SignalMetricsResponse, KpiSummaryResponse

def calculate_global_kpis(target_date: date, repo: KpisRepository) -> SignalMetricsResponse:
    metrics = repo.get_daily_signal_metrics(target_date)
    
    total = metrics["total"]
    criticos = metrics["criticos"]
    riesgo = (criticos / total * 100) if total > 0 else 0.0
    
    return SignalMetricsResponse(
        fecha=target_date,
        total_mediciones=total,
        promedio_rsrp=round(metrics["promedio"], 2),
        eventos_criticos=criticos,
        tasa_riesgo=round(riesgo, 2)
    )

def calculate_kpi_summary(start_date: date, end_date: date, repo: KpisRepository) -> KpiSummaryResponse:
    secuencia_cruda = repo.get_sequence_data_by_range(start_date, end_date)
    
    total_ho = exitosos = fallidos = ping_pongs = uho_eventos = 0
    celdas_visitadas = []
    
    if secuencia_cruda:
        celda_actual = secuencia_cruda[0][0]
        celdas_visitadas.append(celda_actual)
        
        for i in range(1, len(secuencia_cruda)):
            cell_id, rsrp = secuencia_cruda[i]
            rsrp_anterior = secuencia_cruda[i-1][1]
            
            if cell_id != celda_actual:
                total_ho += 1
                celdas_visitadas.append(cell_id)
                celda_actual = cell_id
                
                if rsrp < -110:
                    fallidos += 1
                else:
                    exitosos += 1
                    
                if rsrp <= rsrp_anterior:
                    uho_eventos += 1
                    
        if len(celdas_visitadas) >= 3:
            for i in range(2, len(celdas_visitadas)):
                if celdas_visitadas[i] == celdas_visitadas[i-2]:
                    ping_pongs += 1

    hor = (exitosos / total_ho * 100) if total_ho > 0 else 0.0
    tasa_fallos = (fallidos / total_ho * 100) if total_ho > 0 else 0.0
    tasa_hopp = (ping_pongs / total_ho * 100) if total_ho > 0 else 0.0
    tasa_uho = (uho_eventos / total_ho * 100) if total_ho > 0 else 0.0
    
    return KpiSummaryResponse(
        fecha_inicio=start_date, fecha_fin=end_date,
        total_handovers=total_ho, exitosos=exitosos, fallidos=fallidos,
        hor_porcentaje=round(hor, 2), tasa_fallos=round(tasa_fallos, 2),
        ping_pongs=ping_pongs, tasa_hopp=round(tasa_hopp, 2),
        uho_eventos=uho_eventos, tasa_uho=round(tasa_uho, 2)
    )

from app.modules.kpis.schemas import HourlyDistributionResponse

def calculate_hourly_distribution(start_date: date, end_date: date, repo: KpisRepository) -> list[HourlyDistributionResponse]:
    secuencia_cruda = repo.get_sequence_with_timestamps(start_date, end_date)
    
    # Inicializar diccionario con las 24 horas (0 a 23) en cero
    distribucion = {hora: 0 for hora in range(24)}
    
    if secuencia_cruda:
        celda_actual = secuencia_cruda[0][0]
        
        for i in range(1, len(secuencia_cruda)):
            cell_id, timestamp = secuencia_cruda[i]
            
            if cell_id != celda_actual:
                # Extraer la hora exacta del handover (ej. 14 para las 14:00)
                distribucion[timestamp.hour] += 1
                celda_actual = cell_id
                
    return [
        HourlyDistributionResponse(hora=h, cantidad_handovers=c) 
        for h, c in distribucion.items()
    ]


from app.modules.kpis.schemas import DailyTrendResponse # Añadir arriba

def calculate_daily_trend(start_date: date, end_date: date, repo: KpisRepository) -> list[DailyTrendResponse]:
    secuencia_cruda = repo.get_full_sequence_data(start_date, end_date)
    datos_por_dia = {}
    
    if secuencia_cruda:
        celda_actual = secuencia_cruda[0][0]
        
        for i in range(1, len(secuencia_cruda)):
            cell_id, rsrp, timestamp = secuencia_cruda[i]
            fecha_str = timestamp.strftime("%Y-%m-%d")
            fecha_corta = timestamp.strftime("%d/%m")
            
            if fecha_str not in datos_por_dia:
                datos_por_dia[fecha_str] = {"fecha_corta": fecha_corta, "total": 0, "fallidos": 0}
                
            if cell_id != celda_actual:
                datos_por_dia[fecha_str]["total"] += 1
                if rsrp < -110:
                    datos_por_dia[fecha_str]["fallidos"] += 1
                celda_actual = cell_id
    
    resultado = []
    for stats in datos_por_dia.values():
        total = stats["total"]
        fallidos = stats["fallidos"]
        exitosos = total - fallidos
        
        hor = (exitosos / total * 100) if total > 0 else 0.0
        tasa_fallos = (fallidos / total * 100) if total > 0 else 0.0
        
        resultado.append(DailyTrendResponse(
            fecha_etiqueta=stats["fecha_corta"],
            hor_porcentaje=round(hor, 2),
            tasa_fallos=round(tasa_fallos, 2)
        ))
        
    return resultado