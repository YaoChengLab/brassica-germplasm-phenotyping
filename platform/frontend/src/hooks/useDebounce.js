import { useState, useEffect } from 'react';

/**
 * Debounce a value. Returns the debounced value that only updates
 * after the specified delay has passed since the last change.
 */
export function useDebounce(value, delay = 300) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
