import {useCallback, useEffect, useState} from 'react';

export function useLoad<T>(loader: () => Promise<T>, dependencies: readonly unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setData(await loader()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load data.'); }
    finally { setLoading(false); }
  // The caller supplies the dependencies controlling reloading.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);
  useEffect(() => { void load(); }, [load]);
  return {data, loading, error, reload: load, setData};
}
