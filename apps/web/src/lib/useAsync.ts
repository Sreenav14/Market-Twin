import { DependencyList, useEffect, useState } from "react";

export type AsyncState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "ready"; data: T; error: null }
  | { status: "error"; data: null; error: string };

export function useAsync<T>(loader: () => Promise<T>, dependencies: DependencyList): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading", data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });

    loader().then((data) => {
      if (!cancelled) setState({ status: "ready", data, error: null });
    }).catch((error: unknown) => {
      if (!cancelled) setState({ status: "error", data: null, error: error instanceof Error ? error.message : "Unknown error." });
    });

    return () => { cancelled = true; };
    // Loader identity is intentionally controlled by the supplied dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  return state;
}
