import React, { useState, useCallback, useEffect } from 'react';
import UnifiedSearchBar from '../components/search/UnifiedSearchBar';
import AdvancedFilterPanel from '../components/search/AdvancedFilterPanel';
import SavedQueryBar from '../components/search/SavedQueryBar';
import SearchResults from '../components/SearchResults';
import { fetchSearchResults, fetchDatabaseSummary } from '../services/queryServiceV2';
import { deriveCultivarCounts } from '../services/cultivarCounts';

const PAGE_SIZE = 50;

const SearchCultivarsPage = () => {
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentQuery, setCurrentQuery] = useState(null);
  const [isAdvancedQuery, setIsAdvancedQuery] = useState(false);
  const [resetTrigger, setResetTrigger] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [totalCount, setTotalCount] = useState(0);

  // Catalogue-level counts for the result header. Fetched once: the summary is
  // cached server-side and does not change with the query.
  const [cultivarCounts, setCultivarCounts] = useState(null);

  // UI state
  const [advancedOpen, setAdvancedOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchDatabaseSummary()
      .then((summary) => {
        if (!cancelled) setCultivarCounts(deriveCultivarCounts(summary));
      })
      .catch(() => {
        // The header simply omits the imaged count if this fails.
      });
    return () => { cancelled = true; };
  }, []);

  const handleSearch = useCallback(async (query, isNewSearch = true) => {
    if (loading && isNewSearch) return;
    setLoading(true);
    setError(null);

    const currentOffset = isNewSearch ? 0 : offset;
    const isAdvanced = !!query.filters;

    if (isNewSearch) {
      setSearchResults([]);
      setTotalCount(0);
      setOffset(0);
      setCurrentQuery(query);
      setIsAdvancedQuery(isAdvanced);
    }

    try {
      const searchPayload = {
        ...query,
        offset: currentOffset,
        limit: PAGE_SIZE,
      };

      const responseData = await fetchSearchResults(searchPayload, isAdvanced);

      if (!responseData || !('data' in responseData) || !('total_count' in responseData)) {
        throw new Error('Invalid response from server.');
      }

      setSearchResults((prev) => isNewSearch ? responseData.data : [...prev, ...responseData.data]);
      setTotalCount(responseData.total_count);
      const newTotalLoaded = currentOffset + responseData.data.length;
      setHasMore(newTotalLoaded < responseData.total_count);
      setOffset(newTotalLoaded);
    } catch (err) {
      setError('Failed to fetch search results. Please try again.');
      if (isNewSearch) {
        setSearchResults([]);
        setOffset(0);
        setHasMore(true);
        setTotalCount(0);
      }
    } finally {
      setLoading(false);
    }
  }, [loading, offset]);

  const loadMoreResults = useCallback(() => {
    if (!loading && hasMore && currentQuery) {
      handleSearch(currentQuery, false);
    }
  }, [loading, hasMore, currentQuery, handleSearch]);

  const handleClearResults = () => {
    setSearchResults([]);
    setCurrentQuery(null);
    setIsAdvancedQuery(false);
    setOffset(0);
    setHasMore(true);
    setTotalCount(0);
    setError(null);
    setResetTrigger((prev) => prev + 1);
  };

  // Empty query: the backend's faceted search with no filters and no search term
  // is the browse-all case.
  const handleBrowseAll = () => {
    handleSearch({}, true);
  };

  // Load a saved query
  const handleLoadSavedQuery = (query, isAdvanced) => {
    if (isAdvanced) {
      setAdvancedOpen(true);
    }
    handleSearch(query, true);
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h1 style={{ margin: 0 }}>Cultivar Search</h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={handleClearResults} style={{ ...btnStyle, backgroundColor: '#dc3545' }}>
            Clear
          </button>
          <button onClick={handleBrowseAll} style={{ ...btnStyle, backgroundColor: '#17a2b8' }}>
            Browse All
          </button>
        </div>
      </div>

      {/* Unified Search Bar */}
      <UnifiedSearchBar
        onSearch={handleSearch}
        onToggleAdvanced={() => setAdvancedOpen((prev) => !prev)}
        advancedOpen={advancedOpen}
      />

      {/* Saved Queries Bar */}
      <SavedQueryBar
        currentQuery={currentQuery}
        isAdvanced={isAdvancedQuery}
        onLoadQuery={handleLoadSavedQuery}
      />

      {/* Main layout: sidebar + results */}
      <div style={{ display: 'flex', gap: '20px' }}>
        {/* Left sidebar — only occupies width while the Advanced panel is open;
            the result count is rendered by SearchResults itself. */}
        {advancedOpen && (
          <div style={{ width: '280px', flexShrink: 0 }}>
            <AdvancedFilterPanel
              onSearch={handleSearch}
              resetTrigger={resetTrigger}
              visible={advancedOpen}
            />
          </div>
        )}

        {/* Results area */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {error && <p style={{ color: 'red' }}>Error: {error}</p>}

          <SearchResults
            results={searchResults}
            loadMore={loadMoreResults}
            hasMore={hasMore}
            loading={loading}
            totalCount={totalCount}
            cultivarCounts={cultivarCounts}
          />

          {!loading && !error && searchResults.length === 0 && currentQuery && (
            <p style={{ color: '#666', textAlign: 'center', padding: '40px 0' }}>
              No results found for your query.
            </p>
          )}
          {!loading && !error && !currentQuery && (
            <p style={{ color: '#888', textAlign: 'center', padding: '40px 0' }}>
              Enter search criteria above, or click &quot;Browse All&quot; to see all cultivars.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

const btnStyle = {
  padding: '8px 16px',
  color: 'white',
  border: 'none',
  borderRadius: '5px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: '600',
};

export default SearchCultivarsPage;
