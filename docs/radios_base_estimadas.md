# Radios base estimadas

## Uso

1. En Geoespacial, marcar una o varias sesiones y pulsar **Analizar sesiones**.
2. En **Mapa de rutas y handovers**, activar **Radios Base**.
3. Pulsar un marcador morado para ver su sesión, celda, nodo, canal, PSC/PCI,
   coordenadas candidatas, cantidad de posiciones usadas y dispersión.

Los cálculos usan registros limpios de `handover_record`, en memoria y sin
escrituras a PostgreSQL. Se recalculan con las sesiones y filtros aplicados.
Los puntos anteriores a «Desde», leídos para detectar handovers, no participan.
La capa se oculta en Mapa de calor. Ocultarla no modifica los otros cálculos.

## Qué representa un marcador

Una ubicación candidata **por celda/sector**, no una torre física identificada.
Varias celdas pueden pertenecer a la misma antena. No es triangulación ni
trilateración y no se deduce distancia a partir de RSSI.

No hay operador/MCC/MNC en el dataset. Se presupone una sola red por sesión;
las sesiones nunca se mezclan. Dentro de cada sesión, se separan hoja,
tecnología, nodo, celda, canal (`earfcn`) y TAC/LAC (`tac`). PSC/PCI se muestra
como metadato opcional; no es una clave única ni interviene en la fórmula.
TAC/LAC puede faltar, pero canal y nodo deben estar disponibles.

Un archivo procesado dos veces genera estimaciones independientes iguales,
sin dar doble peso a un mismo centroide. Si las coordenadas coinciden, el mapa
usa un marcador compartido y enumera todas las sesiones/celdas en la burbuja.
El total indica estimaciones, no cantidad confirmada de antenas.

## Algoritmo y parámetros iniciales

Implementación: `backend/app/modules/visualizacion_geoespacial/radio_bases.py`.
Estos parámetros son decisiones experimentales, **no umbrales normativos ni
validados contra estaciones conocidas**:

| Parámetro | Valor inicial |
|---|---:|
| Precisión GPS máxima aceptada | 50 m |
| Piso de precisión para ponderar | 5 m |
| Tamaño de agrupación espacial | 10 m |
| Posiciones mínimas | 5 |
| Extensión mínima observada | 50 m |
| Extensión máxima para proyección local | 30 km |
| Fracción de posiciones con mejor señal | 20 % |

1. Rechazar identificadores faltantes/centinela, tecnología diferente de LTE/3G,
   coordenadas no finitas, (0,0), polos fuera de la proyección local,
   RSSI fuera de [-150, 0) dBm, o `accuracy` ausente, cero o superior a 50 m.
   El intervalo RSSI es una comprobación conservadora para este cálculo;
   no clasifica calidad de servicio. No se reemplaza un dato ausente por cero.
2. Agrupar por las claves anteriores. Eliminar muestras repetidas con la misma
   latitud, longitud, RSSI y precisión, aunque cambien el tiempo o el ID.
3. Proyectar localmente a metros usando radio terrestre 6371008.8 m:
   `x = R cos(lat0) (lon - lon0)`; `y = R (lat - lat0)` (ángulos en radianes).
   El origen es el promedio de las coordenadas deduplicadas de cada grupo.
4. Agrupar posiciones en cuadrados de 10 m. Cada cuadrado aporta la mediana
   de x, y, RSSI y precisión. Esto reduce el peso de paradas largas.
5. Exigir al menos cinco cuadrados y una diagonal de la extensión observada
   entre 50 m y 30 km. Si no se cumple, omitir el marcador y contar el grupo
   como insuficiente/no adecuado.
6. Tomar el 20 % de cuadrados con mayor RSSI, redondeando hacia arriba, con
   mínimo cinco. Incluir todos los empatados en el RSSI de corte para evitar
   seleccionar una dirección arbitraria cuando las señales sean iguales.
7. Calcular pesos y centroide:

   ```text
   peso_i = 10^((RSSI_i - RSSI_max) / 10) / max(accuracy_i, 5)^2
   X = suma(peso_i * x_i) / suma(peso_i)
   Y = suma(peso_i * y_i) / suma(peso_i)
   ```

8. Volver a latitud/longitud. Calcular dispersión RMS ponderada de las
   posiciones usadas alrededor del centroide. **No es un radio de confianza
   ni una estimación del error respecto de la antena real**.

RSRQ y RSSNR siguen disponibles en las mediciones, pero no se utilizan como
distancias ni como pesos en este primer algoritmo. PSC/PCI ausente no bloquea
el cálculo; su rango se interpreta según tecnología (PCI LTE 0–503, PSC 0–511).

La estimación puede quedar sobre el recorrido aunque la antena esté fuera.
Trayectos de un solo lado, RSSI afectado por interferencias, sectores y
propagación pueden desplazarla. Más datos no garantizan menor error. Para
validar el método se requieren sitios conocidos y medición del error en metros.

## Código y contrato

- `schemas.py`: añade `execution_id`, `psc_pci`, `earfcn`, `tac` a las mediciones;
  define `RadioBaseEstimate` y `RadioBaseSummary`.
- `services.py`: pasa las mediciones filtradas a `estimate_radio_bases`.
- `GET /api/v1/geoespacial/mediciones`: agrega `radios_base` y
  `resumen_radios_base` (descartes, duplicados, grupos y parámetros usados).
- `components/MapaGeoespacial.jsx`: dibuja marcadores y sus burbujas.
- `components/RadioBaseSummary.jsx`: explica el carácter estimado y muestra
  los motivos de exclusión. `GeoespacialPage.jsx` controla la capa.

Pruebas: `tests/unit/test_radio_bases.py`,
`tests/integration/test_geoespacial_endpoints.py` y `frontend/e2e/geoespacial.spec.js`.
La comprobación real de solo lectura está en `tests/check_radio_bases_readonly.py`.
