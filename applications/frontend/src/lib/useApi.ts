import { useCallback, useEffect, useRef, useState } from "react";
import { normaliseError } from "./api";
import type { Envelope, Meta, NormalisedError } from "./api";

export interface ResourceState<T> {
  data: T | null;
  meta: Meta | null;
  loading: boolean;
  error: NormalisedError | null;
  reload: () => void;
}

/**
 * Envelope-aware loader. Pass the filter/pagination values used by the loader
 * as `keys` so the request re-runs when they change.
 */
export function useResource<T>(
  loader: () => Promise<Envelope<T>>,
  keys: ReadonlyArray<string | number | boolean | undefined>,
): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [nonce, setNonce] = useState(0);

  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const keySignature = keys.map((key) => String(key ?? "")).join("|");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loaderRef
      .current()
      .then((payload) => {
        if (!active) return;
        setData(payload.data);
        setMeta(payload.meta);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setData(null);
        setMeta(null);
        setError(normaliseError(err));
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [keySignature, nonce]);

  const reload = useCallback(() => setNonce((current) => current + 1), []);

  return { data, meta, loading, error, reload };
}

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: NormalisedError | null;
  reload: () => void;
}

/** Same contract for endpoints that do not use the {data, meta} envelope. */
export function useAsync<T>(loader: () => Promise<T>): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [nonce, setNonce] = useState(0);

  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loaderRef
      .current()
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setData(null);
        setError(normaliseError(err));
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [nonce]);

  const reload = useCallback(() => setNonce((current) => current + 1), []);
  return { data, loading, error, reload };
}
