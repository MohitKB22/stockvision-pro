"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * localStorage-backed state that is safe to read during render.
 *
 * The obvious implementation — `useState(default)` plus a `useEffect` that reads
 * storage and calls `setState` — has two real problems:
 *
 *   1. It triggers a cascading render on every mount: React renders with the
 *      default, the effect fires, state changes, React renders again. React 19's
 *      compiler lints this (`react-hooks/set-state-in-effect`) precisely because
 *      it is a performance footgun at scale.
 *   2. It produces a visible flash — the sidebar expands, then collapses.
 *
 * `useSyncExternalStore` is the purpose-built primitive for exactly this: it reads
 * the external store during render on the client, uses `getServerSnapshot` during
 * SSR (so there is no hydration mismatch), and subscribes to `storage` events so
 * the value stays in sync across browser tabs for free.
 */
export function usePersistentState<T extends string>(
  key: string,
  defaultValue: T,
  isValid: (value: string) => value is T,
): [T, (next: T) => void] {
  const subscribe = useCallback(
    (onChange: () => void) => {
      // `storage` fires in OTHER tabs; the custom event covers the current one, so
      // a change is reflected everywhere immediately.
      const handler = (event: StorageEvent) => {
        if (event.key === null || event.key === key) onChange();
      };
      window.addEventListener("storage", handler);
      window.addEventListener("stockvision:storage", onChange);
      return () => {
        window.removeEventListener("storage", handler);
        window.removeEventListener("stockvision:storage", onChange);
      };
    },
    [key],
  );

  const getSnapshot = useCallback((): T => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored !== null && isValid(stored) ? stored : defaultValue;
    } catch {
      // Private browsing and some embedded webviews throw on localStorage access.
      // Falling back is strictly better than crashing the whole tree.
      return defaultValue;
    }
  }, [key, defaultValue, isValid]);

  // The server has no localStorage — it must return the default, and it must
  // return a STABLE reference, or React warns about an infinite loop.
  const getServerSnapshot = useCallback(() => defaultValue, [defaultValue]);

  const value = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setValue = useCallback(
    (next: T) => {
      try {
        window.localStorage.setItem(key, next);
      } catch {
        // Ignore quota/permission failures — the dispatch below still notifies
        // subscribers, so the UI responds even if the preference cannot persist.
      }
      window.dispatchEvent(new Event("stockvision:storage"));
    },
    [key],
  );

  return [value, setValue];
}

/** Boolean convenience wrapper over the same mechanism. */
export function usePersistentBoolean(
  key: string,
  defaultValue = false,
): [boolean, (next: boolean) => void] {
  const isValid = useCallback(
    (value: string): value is "true" | "false" => value === "true" || value === "false",
    [],
  );
  const [raw, setRaw] = usePersistentState<"true" | "false">(
    key,
    defaultValue ? "true" : "false",
    isValid,
  );
  const set = useCallback((next: boolean) => setRaw(next ? "true" : "false"), [setRaw]);
  return [raw === "true", set];
}
