import React, { createContext, useContext, useState, useCallback } from 'react';

const STORAGE_KEY = 'bpp:comparison_items';
const WINDOW_KEY = 'bpp:analysis_window';
const MAX_ITEMS = 20;

// An item is a business key with wildcards: `{ cultivar_code }` alone means every
// plant of that cultivar (what a search result can say), while an item that also
// carries batch / treatment / replicate names one plant (what the Plant Viewer
// knows). The identity is therefore the whole key, not the cultivar code — two
// replicates of one cultivar are two different selections.
//
// Items written by an older build have only `cultivar_code`, which still reads
// correctly under this rule, so nothing needs migrating.
export function itemKey(item) {
  return [
    item.batch_code || '',
    item.cultivar_code || '',
    item.treatment_code || '',
    item.replicate_code == null ? '' : String(item.replicate_code),
  ].join('/');
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveToStorage(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

// Shared window (DAS bounds) carried into the export form. Read-only: stores only
// { das_min, das_max } bounds, never a copy of trait values.
function loadWindow() {
  try {
    const raw = localStorage.getItem(WINDOW_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveWindow(w) {
  if (w) localStorage.setItem(WINDOW_KEY, JSON.stringify(w));
  else localStorage.removeItem(WINDOW_KEY);
}

const ComparisonContext = createContext(null);

export function ComparisonProvider({ children }) {
  const [comparisonItems, setComparisonItems] = useState(loadFromStorage);
  const [analysisWindow, setAnalysisWindowState] = useState(loadWindow);

  const setAnalysisWindow = useCallback((w) => {
    setAnalysisWindowState(w);
    saveWindow(w);
  }, []);

  const addToComparison = useCallback((item) => {
    setComparisonItems((prev) => {
      if (prev.some((i) => itemKey(i) === itemKey(item))) return prev;
      if (prev.length >= MAX_ITEMS) return prev;
      const next = [...prev, item];
      saveToStorage(next);
      return next;
    });
  }, []);

  // Accepts either a whole item or a bare cultivar code, so the cultivar-level
  // callers (search results) are unaffected by the finer granularity.
  const removeFromComparison = useCallback((itemOrCode) => {
    const key = typeof itemOrCode === 'object' ? itemKey(itemOrCode) : itemKey({ cultivar_code: itemOrCode });
    setComparisonItems((prev) => {
      const next = prev.filter((i) => itemKey(i) !== key);
      saveToStorage(next);
      return next;
    });
  }, []);

  const clearComparison = useCallback(() => {
    setComparisonItems([]);
    saveToStorage([]);
    setAnalysisWindowState(null);
    saveWindow(null);
  }, []);

  const isInComparison = useCallback(
    (itemOrCode) => {
      const key = typeof itemOrCode === 'object' ? itemKey(itemOrCode) : itemKey({ cultivar_code: itemOrCode });
      return comparisonItems.some((i) => itemKey(i) === key);
    },
    [comparisonItems]
  );

  return (
    <ComparisonContext.Provider
      value={{
        comparisonItems,
        addToComparison,
        removeFromComparison,
        clearComparison,
        isInComparison,
        analysisWindow,
        setAnalysisWindow,
        itemKey,
        maxItems: MAX_ITEMS,
      }}
    >
      {children}
    </ComparisonContext.Provider>
  );
}

export function useComparison() {
  const ctx = useContext(ComparisonContext);
  if (!ctx) throw new Error('useComparison must be used within ComparisonProvider');
  return ctx;
}
