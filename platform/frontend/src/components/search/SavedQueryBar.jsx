import React, { useState } from 'react';
import { useSavedQueries } from '../../hooks/useSavedQueries';

const SavedQueryBar = ({ currentQuery, isAdvanced, onLoadQuery }) => {
  const { savedQueries, saveQuery, deleteQuery } = useSavedQueries();
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [queryName, setQueryName] = useState('');

  const handleSave = () => {
    if (!queryName.trim() || !currentQuery) return;
    saveQuery(queryName.trim(), isAdvanced ? 'advanced' : 'basic', currentQuery);
    setQueryName('');
    setShowSaveInput(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') setShowSaveInput(false);
  };

  const handleLoad = (query) => {
    onLoadQuery(query.query, query.type === 'advanced');
  };

  if (savedQueries.length === 0 && !currentQuery) return null;

  return (
    <div style={{
      display: 'flex',
      gap: '8px',
      alignItems: 'center',
      flexWrap: 'wrap',
      marginBottom: '12px',
      padding: '8px 0',
    }}>
      {/* Saved query pills */}
      {savedQueries.length > 0 && (
        <>
          <span style={{ fontSize: '12px', color: '#6c757d', fontWeight: '600' }}>Saved:</span>
          {savedQueries.map((q) => (
            <span
              key={q.id}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 10px',
                backgroundColor: q.type === 'advanced' ? '#e8daef' : '#d4edda',
                border: `1px solid ${q.type === 'advanced' ? '#c39bd3' : '#a3d9a5'}`,
                borderRadius: '12px',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              <span onClick={() => handleLoad(q)} title={`Load: ${q.name}`}>
                {q.name}
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteQuery(q.id);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#999',
                  fontSize: '11px',
                  padding: '0 2px',
                  lineHeight: 1,
                }}
                title="Delete"
              >
                x
              </button>
            </span>
          ))}
        </>
      )}

      {/* Save current query */}
      {currentQuery && (
        <>
          {showSaveInput ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <input
                type="text"
                value={queryName}
                onChange={(e) => setQueryName(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Query name..."
                autoFocus
                style={{
                  padding: '3px 8px',
                  borderRadius: '4px',
                  border: '1px solid #ced4da',
                  fontSize: '12px',
                  width: '120px',
                }}
              />
              <button
                onClick={handleSave}
                disabled={!queryName.trim()}
                style={{
                  padding: '3px 8px',
                  backgroundColor: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
              >
                Save
              </button>
              <button
                onClick={() => setShowSaveInput(false)}
                style={{
                  padding: '3px 8px',
                  backgroundColor: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              onClick={() => setShowSaveInput(true)}
              style={{
                padding: '3px 10px',
                backgroundColor: 'transparent',
                border: '1px dashed #adb5bd',
                borderRadius: '12px',
                fontSize: '12px',
                cursor: 'pointer',
                color: '#6c757d',
              }}
            >
              + Save Query
            </button>
          )}
        </>
      )}
    </div>
  );
};

export default SavedQueryBar;
