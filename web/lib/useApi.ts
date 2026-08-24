"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAccessToken } from "@workos-inc/authkit-nextjs/components";
import { errorMessage } from "./format";

/**
 * One read path for every screen, so loading, failure and reload behave the
 * same everywhere. It does not change what is called or what comes back --
 * lib/api.ts is untouched -- it only makes sure no screen invents its own
 * idea of what "still loading" or "this failed" looks like.
 */
export type Query<T> = {
  data: T | null;
  error: string | null;
  /** A request is in flight. */
  loading: boolean;
  /** At least one request has settled. Distinguishes "no data yet" from
   *  "genuinely nothing to show", which are different screens. */
  settled: boolean;
  reload: () => void;
};

export function useApiQuery<T>(
  fetcher: (accessToken: string) => Promise<T>,
  deps: React.DependencyList,
  options: { enabled?: boolean } = {}
): Query<T> {
  const { accessToken } = useAccessToken();
  const enabled = options.enabled ?? true;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState(false);
  const [settled, setSettled] = useState(false);

  // An enabled query that has not settled yet is loading, even before the
  // access token has arrived and the request has actually been issued.
  // Without this a screen renders neither data, nor an error, nor a skeleton
  // for the moment the session is still resolving -- which is a blank page,
  // and a finance user reads a blank page as a broken product.
  const loading = inFlight || (enabled && !settled);

  // The fetcher closes over render-scope values and is a new function every
  // render; the dependency array passed by the caller is what decides when a
  // request is actually re-issued.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const latest = useRef(0);

  const run = useCallback(() => {
    if (!accessToken || !enabled) return;
    const requestId = ++latest.current;
    setInFlight(true);
    setError(null);
    fetcherRef.current(accessToken).then(
      (result) => {
        if (requestId !== latest.current) return; // a newer request has superseded this one
        setData(result);
        setInFlight(false);
        setSettled(true);
      },
      (err) => {
        if (requestId !== latest.current) return;
        setData(null);
        setError(errorMessage(err));
        setInFlight(false);
        setSettled(true);
      }
    );
  }, [accessToken, enabled]);

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, ...deps]);

  return { data, error, loading, settled, reload: run };
}

/**
 * The write path: an action a person triggers, which can fail, and whose
 * failure must be visible next to the control that caused it.
 */
export function useApiAction<Args extends unknown[], T>(
  action: (accessToken: string, ...args: Args) => Promise<T>
): {
  run: (...args: Args) => Promise<T | undefined>;
  busy: boolean;
  error: string | null;
  clearError: () => void;
} {
  const { accessToken } = useAccessToken();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actionRef = useRef(action);
  actionRef.current = action;

  const run = useCallback(
    async (...args: Args) => {
      if (!accessToken) {
        setError("Not signed in yet. Wait a moment and try again.");
        return undefined;
      }
      setBusy(true);
      setError(null);
      try {
        return await actionRef.current(accessToken, ...args);
      } catch (err) {
        setError(errorMessage(err));
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [accessToken]
  );

  return { run, busy, error, clearError: useCallback(() => setError(null), []) };
}
