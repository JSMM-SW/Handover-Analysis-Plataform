import { useEffect, useRef, useState } from 'react';
import { getGeo } from '../api';

export default function useMeasurements(executionIds, query, viewport, enabled = true) {
  const [result, setResult] = useState(null);
  const sequence = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const request = ++sequence.current;
    const params = { execution_id: executionIds, ...query, ...viewport };
    // Inputs represent Ecuador time, independent of the browser timezone.
    if (params.desde) params.desde = params.desde + 'T00:00:00-05:00';
    if (params.hasta) params.hasta = params.hasta + 'T23:59:59.999999-05:00';
    if (params.hora_inicio?.length === 5) params.hora_inicio += ':00';
    if (params.hora_fin?.length === 5) params.hora_fin += ':59.999999';

    getGeo('mediciones', params, controller.signal)
      .then((data) => {
        if (sequence.current === request && !controller.signal.aborted) {
          setResult({ executionIds, query, viewport, data, error: '' });
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError' && sequence.current === request && !controller.signal.aborted) {
          setResult((old) => ({ executionIds, query, viewport,
            data: old?.executionIds === executionIds && old?.query === query ? old.data : null,
            error: error.message }));
        }
      });

    return () => controller.abort();
  }, [executionIds, query, viewport, enabled]);

  const loading = !enabled || result?.query !== query || result?.executionIds !== executionIds;
  return {
    loading,
    updating: !loading && result?.viewport !== viewport,
    data: loading ? null : result?.data,
    error: loading ? '' : result?.error,
  };
}
