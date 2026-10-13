// const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// async function waitForMap(element) {
//   const deadline = Date.now() + 12000;
//   let settled = 0;
//   while (Date.now() < deadline) {
//     if (!element.isConnected) throw new Error('La vista del mapa cambió. Vuelve a intentar la descarga.');
//     const tiles = [...element.querySelectorAll('img.leaflet-tile')];
//     const ready = tiles.length && tiles.every((tile) => tile.complete && tile.naturalWidth > 0);
//     const moving = element.querySelector('.leaflet-zoom-anim, .leaflet-pan-anim');
//     settled = ready && !moving ? settled + 1 : 0;
//     if (settled >= 3) return;
//     await delay(100);
//   }
//   throw new Error('El mapa base no terminó de cargar. Comprueba la conexión y vuelve a descargar.');
// }

// export async function downloadMap(element, { tab, heatMetric = 'handovers', sessionLabels }) {
//   const { default: html2canvas } = await import('html2canvas');
//   await waitForMap(element);
//   const canvas = await html2canvas(element, {
//     useCORS: true, allowTaint: false, backgroundColor: '#ffffff',
//     scale: 2, logging: false, imageTimeout: 12000,
//     ignoreElements: (node) => node.matches('.leaflet-control-zoom, .leaflet-popup-pane, .leaflet-tooltip-pane'),
//     onclone: (doc) => {
//       // Embed loaded tiles instead of risking missing images on a second request.
//       const originalTiles = element.querySelectorAll('img.leaflet-tile');
//       const clonedTiles = doc.querySelectorAll('.geo-export img.leaflet-tile');
//       originalTiles.forEach((tile, index) => {
//         const image = document.createElement('canvas');
//         image.width = tile.naturalWidth;
//         image.height = tile.naturalHeight;
//         image.getContext('2d').drawImage(tile, 0, 0);
//         clonedTiles[index].src = image.toDataURL('image/png');
//         clonedTiles[index].style.opacity = '1';
//       });
//     },
//   });
//   if (!element.isConnected) throw new Error('La vista del mapa cambió. Vuelve a intentar la descarga.');
//   const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
//   if (!blob) throw new Error('No se pudo generar la imagen. Vuelve a intentar.');
//   const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
//   const session = sessionLabels.length === 1 ? `sesion_${sessionLabels[0]}` : 'varias_sesiones';
//   const url = URL.createObjectURL(blob);
//   const link = document.createElement('a');
//   link.href = url;
//   const view = tab === 'calor' ? (heatMetric === 'handovers' ? 'calor' : `calor_${heatMetric}`) : 'handovers';
//   link.download = `mapa_${view}_${session}_${date}.png`;
//   document.body.append(link);
//   link.click();
//   link.remove();
//   setTimeout(() => URL.revokeObjectURL(url), 1000);
// }
/**
 * Espera un tiempo fijo.
 *
 * @param {number} ms - milisegundos a esperar.
 * @returns {Promise<void>}
 */
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Espera a que el mapa de Leaflet termine de cargar sus teselas y deje de
 * moverse (zoom/pan), exigiendo 3 comprobaciones seguidas estables.
 *
 * @param {HTMLElement} element - contenedor del área exportable.
 * @returns {Promise<void>}
 * @throws {Error} si la vista cambió o el mapa no cargó en 12 segundos.
 */
async function waitForMap(element) {
  const deadline = Date.now() + 12000;
  let settled = 0;
  while (Date.now() < deadline) {
    if (!element.isConnected) throw new Error('La vista del mapa cambió. Vuelve a intentar la descarga.');
    const tiles = [...element.querySelectorAll('img.leaflet-tile')];
    const ready = tiles.length && tiles.every((tile) => tile.complete && tile.naturalWidth > 0);
    const moving = element.querySelector('.leaflet-zoom-anim, .leaflet-pan-anim');
    settled = ready && !moving ? settled + 1 : 0;
    if (settled >= 3) return;
    await delay(100);
  }
  throw new Error('El mapa base no terminó de cargar. Comprueba la conexión y vuelve a descargar.');
}

/**
 * Captura el área del mapa (mapa + leyenda) y la descarga como PNG.
 *
 * El color de fondo de la captura se toma de la variable de tema
 * `--color-superficie` (la misma que usa `.geo-export`), para que las
 * esquinas redondeadas no queden blancas cuando el tema es oscuro.
 *
 * @param {HTMLElement} element - contenedor del área exportable.
 * @param {object} opciones
 * @param {string} opciones.tab - pestaña activa ('rutas' o 'calor').
 * @param {string} [opciones.heatMetric] - capa activa del mapa de calor.
 * @param {Array<string|number>} opciones.sessionLabels - sesiones analizadas.
 * @returns {Promise<void>}
 * @throws {Error} si la vista cambió o no se pudo generar la imagen.
 */
export async function downloadMap(element, { tab, heatMetric = 'handovers', sessionLabels }) {
  const { default: html2canvas } = await import('html2canvas');
  await waitForMap(element);
  const fondoTema = getComputedStyle(document.documentElement).getPropertyValue('--color-superficie').trim() || '#ffffff';
  const canvas = await html2canvas(element, {
    useCORS: true, allowTaint: false, backgroundColor: fondoTema,
    scale: 2, logging: false, imageTimeout: 12000,
    ignoreElements: (node) => node.matches('.leaflet-control-zoom, .leaflet-popup-pane, .leaflet-tooltip-pane'),
    onclone: (doc) => {
      // Embed loaded tiles instead of risking missing images on a second request.
      const originalTiles = element.querySelectorAll('img.leaflet-tile');
      const clonedTiles = doc.querySelectorAll('.geo-export img.leaflet-tile');
      originalTiles.forEach((tile, index) => {
        const image = document.createElement('canvas');
        image.width = tile.naturalWidth;
        image.height = tile.naturalHeight;
        image.getContext('2d').drawImage(tile, 0, 0);
        clonedTiles[index].src = image.toDataURL('image/png');
        clonedTiles[index].style.opacity = '1';
      });
    },
  });
  if (!element.isConnected) throw new Error('La vista del mapa cambió. Vuelve a intentar la descarga.');
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('No se pudo generar la imagen. Vuelve a intentar.');
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const session = sessionLabels.length === 1 ? `sesion_${sessionLabels[0]}` : 'varias_sesiones';
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const view = tab === 'calor' ? (heatMetric === 'handovers' ? 'calor' : `calor_${heatMetric}`) : 'handovers';
  link.download = `mapa_${view}_${session}_${date}.png`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
