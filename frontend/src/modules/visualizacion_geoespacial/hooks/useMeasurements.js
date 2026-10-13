import { useEffect, useRef, useState } from 'react';
import { getGeo } from '../api';

export default function useMeasurements(executionIds, query) {
  const [result, setResult] = useState(null);
  const sequence = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const request = ++sequence.current;
    const params = { execution_id: executionIds, ...query };
    // Inputs represent Ecuador time, independent of the browser timezone.
    if (params.desde) params.desde = params.desde + 'T00:00:00-05:00';
    if (params.hasta) params.hasta = params.hasta + 'T23:59:59.999999-05:00';
    if (params.hora_inicio?.length === 5) params.hora_inicio += ':00';
    if (params.hora_fin?.length === 5) params.hora_fin += ':59.999999';

    getGeo('mediciones', params, controller.signal)
      .then((data) => {
        if (sequence.current === request && !controller.signal.aborted) {
          setResult({ executionIds, query, data, error: '' });
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError' && sequence.current === request && !controller.signal.aborted) {
          setResult({ executionIds, query, data: null, error: error.message });
        }
      });

    return () => controller.abort();
  }, [executionIds, query]);

  const loading = result?.query !== query || result?.executionIds !== executionIds;
  return {
    loading,
    data: loading ? null : result?.data,
    error: loading ? '' : result?.error,
  };
}
