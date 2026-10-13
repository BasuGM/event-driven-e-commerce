import { useEffect, useMemo, useRef } from "react"

/** Returns a stable function that calls `callback` once calls stop for `delay` ms. */
export function useDebouncedCallback<A extends unknown[]>(callback: (...args: A) => void, delay: number) {
  const callbackRef = useRef(callback)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    callbackRef.current = callback
  }, [callback])

  useEffect(() => () => clearTimeout(timer.current), [])

  return useMemo(() => {
    const debounced = (...args: A) => {
      clearTimeout(timer.current)
      timer.current = setTimeout(() => callbackRef.current(...args), delay)
    }
    debounced.cancel = () => clearTimeout(timer.current)
    return debounced
  }, [delay])
}
