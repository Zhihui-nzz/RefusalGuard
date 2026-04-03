import { useCallback, useRef } from "react";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFunction = (...args: any[]) => any;

/**
 * Returns a stable function reference that always calls the latest version
 * of the provided callback. Useful for event handlers that need stable
 * identity without stale closure issues.
 */
export function usePersistFn<T extends AnyFunction>(fn: T): T {
  const fnRef = useRef<T>(fn);
  fnRef.current = fn;

  const persistFn = useCallback((...args: Parameters<T>): ReturnType<T> => {
    return fnRef.current(...args);
  }, []) as T;

  return persistFn;
}
