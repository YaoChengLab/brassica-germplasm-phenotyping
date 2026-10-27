import { useState, useCallback } from 'react';

const STORAGE_KEY = 'bpp:saved_queries';
const MAX_QUERIES = 50;

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveToStorage(queries) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(queries));
}

/**
 * Hook for managing saved search queries in localStorage.
 * Each query: { id, name, type, query, createdAt }
 */
export function useSavedQueries() {
  const [savedQueries, setSavedQueries] = useState(loadFromStorage);

  const saveQuery = useCallback((name, type, query) => {
    setSavedQueries((prev) => {
      const entry = {
        id: Date.now().toString(36),
        name,
        type,
        query,
        createdAt: new Date().toISOString(),
      };
      const next = [entry, ...prev].slice(0, MAX_QUERIES);
      saveToStorage(next);
      return next;
    });
  }, []);

  const deleteQuery = useCallback((id) => {
    setSavedQueries((prev) => {
      const next = prev.filter((q) => q.id !== id);
      saveToStorage(next);
      return next;
    });
  }, []);

  const loadQuery = useCallback(
    (id) => {
      return savedQueries.find((q) => q.id === id) ?? null;
    },
    [savedQueries]
  );

  return { savedQueries, saveQuery, deleteQuery, loadQuery };
}
