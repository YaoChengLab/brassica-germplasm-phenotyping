import React, { useState, useRef, useEffect } from 'react';
import { useDebounce } from '../../hooks/useDebounce';
import { fetchSearchResults } from '../../services/queryServiceV2';

const UnifiedSearchBar = ({ onSearch, onToggleAdvanced, advancedOpen }) => {
  const [inputValue, setInputValue] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const debouncedInput = useDebounce(inputValue, 300);
  const wrapperRef = useRef(null);

  // Fetch suggestions when debounced input changes
  useEffect(() => {
    if (!debouncedInput || debouncedInput.length < 2) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    const fetchSuggestions = async () => {
      setSuggestionsLoading(true);
      try {
        const result = await fetchSearchResults(
          { search_term: debouncedInput, limit: 8, offset: 0 },
          false
        );
        if (!cancelled) {
          setSuggestions(result.data || []);
          setShowSuggestions(true);
        }
      } catch {
        if (!cancelled) setSuggestions([]);
      } finally {
        if (!cancelled) setSuggestionsLoading(false);
      }
    };
    fetchSuggestions();
    return () => { cancelled = true; };
  }, [debouncedInput]);

  // Close suggestions on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const executeSearch = (searchTerm) => {
    setShowSuggestions(false);
    onSearch({ search_term: searchTerm || inputValue });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      executeSearch();
    }
  };

  const handleSuggestionClick = (cultivar) => {
    setInputValue(cultivar.cultivar_code);
    setShowSuggestions(false);
    onSearch({ cultivar_code_filters: [cultivar.cultivar_code] });
  };

  return (
    <div ref={wrapperRef} style={{ position: 'relative', marginBottom: '16px' }}>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
            placeholder="Search by cultivar code or product name..."
            style={{
              width: '100%',
              padding: '10px 14px',
              borderRadius: '6px',
              border: '1px solid #ced4da',
              fontSize: '15px',
              boxSizing: 'border-box',
            }}
          />
          {suggestionsLoading && (
            <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: '#999', fontSize: '12px' }}>
              ...
            </span>
          )}
        </div>
        <button
          onClick={() => executeSearch()}
          disabled={!inputValue.trim()}
          style={{
            padding: '10px 20px',
            backgroundColor: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: inputValue.trim() ? 'pointer' : 'not-allowed',
            opacity: inputValue.trim() ? 1 : 0.55,
            fontWeight: '600',
            whiteSpace: 'nowrap',
          }}
        >
          Search
        </button>
        <button
          onClick={onToggleAdvanced}
          style={{
            padding: '10px 16px',
            backgroundColor: advancedOpen ? '#6c757d' : '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            fontWeight: '600',
            whiteSpace: 'nowrap',
          }}
        >
          {advancedOpen ? 'Hide Advanced' : 'Advanced'}
        </button>
      </div>

      {/* Suggestions dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            backgroundColor: 'white',
            border: '1px solid #dee2e6',
            borderRadius: '0 0 6px 6px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 1000,
            maxHeight: '320px',
            overflowY: 'auto',
          }}
        >
          {suggestions.map((cultivar) => (
            <div
              key={cultivar.id || cultivar.cultivar_code}
              onClick={() => handleSuggestionClick(cultivar)}
              style={{
                padding: '10px 14px',
                cursor: 'pointer',
                borderBottom: '1px solid #f0f0f0',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8f9fa')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'white')}
            >
              <div>
                <strong style={{ color: '#0056b3' }}>{cultivar.cultivar_code}</strong>
                <span style={{ marginLeft: '10px', color: '#666' }}>
                  {cultivar.product_name || 'N/A'}
                </span>
              </div>
              <span style={{ fontSize: '0.8em', color: '#999' }}>
                {cultivar.raspi_observation_count || 0} obs
              </span>
            </div>
          ))}
          <div
            onClick={() => executeSearch()}
            style={{
              padding: '10px 14px',
              cursor: 'pointer',
              textAlign: 'center',
              color: '#007bff',
              fontWeight: '600',
              borderTop: '1px solid #dee2e6',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8f9fa')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'white')}
          >
            Show all results for &quot;{inputValue}&quot;
          </div>
        </div>
      )}
    </div>
  );
};

export default UnifiedSearchBar;
