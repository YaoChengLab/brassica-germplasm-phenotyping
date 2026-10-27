import React, { useCallback, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Card, Row, Col, Badge, Button } from 'react-bootstrap';
import { useComparison } from '../contexts/ComparisonContext';

const fmt = (n) => (n || 0).toLocaleString();

const DataBadge = ({ label, count }) => (
  <Badge
    bg={count > 0 ? 'info' : 'light'}
    text={count > 0 ? undefined : 'muted'}
    className="me-1 fw-normal"
  >
    {label} {fmt(count)}
  </Badge>
);

const IdentityRow = ({ label, value }) => (
  <div className="d-flex small text-muted">
    <span className="text-nowrap me-1">{label}:</span>
    <span className="text-truncate text-body">{value || 'N/A'}</span>
  </div>
);

const SearchResults = ({ results, loadMore, hasMore, loading, totalCount, cultivarCounts }) => {
  const observer = useRef();
  const navigate = useNavigate();
  const { comparisonItems, addToComparison, removeFromComparison, isInComparison } = useComparison();

  const lastResultElementRef = useCallback(node => {
    if (loading) return;
    if (observer.current) observer.current.disconnect();
    observer.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore) {
        loadMore();
      }
    });
    if (node) observer.current.observe(node);
  }, [loading, hasMore, loadMore]);

  if (!results || results.length === 0) {
    return null;
  }

  // "N with images" is a catalogue-level count, so it is only shown when the
  // result set IS the whole catalogue; appending it to a filtered result would
  // read as if it described that result. The two numbers differ because a
  // cultivar can be catalogued without ever having been grown and imaged, and
  // seeing them side by side here is what keeps this page from disagreeing with
  // the home-page count.
  const imagedNote = cultivarCounts?.catalogued && cultivarCounts?.imaged != null
    && totalCount === cultivarCounts.catalogued
    ? `, ${fmt(cultivarCounts.imaged)} with images`
    : '';

  const handleComparisonToggle = (cultivar) => {
    if (isInComparison(cultivar.cultivar_code)) {
      removeFromComparison(cultivar.cultivar_code);
    } else {
      addToComparison({
        cultivar_code: cultivar.cultivar_code,
        product_name: cultivar.product_name,
      });
    }
  };

  return (
    <div style={{ border: '1px solid #eee', padding: '15px', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
      <h4 className="mb-3">Found {fmt(totalCount)} Cultivars{imagedNote}:</h4>
      <Row xs={1} sm={2} lg={3} className="g-3">
        {results.map((cultivar, index) => {
          const isLastElement = results.length === index + 1;
          const inComparison = isInComparison(cultivar.cultivar_code);

          return (
            <Col key={cultivar.id} ref={isLastElement ? lastResultElementRef : null}>
              <Card className="h-100 shadow-sm">
                <Link
                  to={`/cultivars/${cultivar.cultivar_code}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-decoration-none text-reset"
                >
                  {cultivar.thumbnail_url ? (
                    <Card.Img
                      variant="top"
                      src={cultivar.thumbnail_url}
                      alt={cultivar.product_name || cultivar.cultivar_code}
                      loading="lazy"
                      style={{ height: '180px', objectFit: 'cover', backgroundColor: '#f1f3f5' }}
                    />
                  ) : (
                    <div
                      className="d-flex align-items-center justify-content-center text-muted small"
                      style={{ height: '180px', backgroundColor: '#f1f3f5' }}
                    >
                      No image
                    </div>
                  )}
                  <Card.Body className="pb-2">
                    <Card.Title className="h6 mb-2 text-truncate" style={{ color: '#0056b3' }}>
                      {cultivar.product_name || 'N/A'}
                    </Card.Title>
                    <IdentityRow label="Common" value={cultivar.common_name} />
                    <IdentityRow label="Edible part" value={cultivar.edible_part} />
                    <IdentityRow label="Genome" value={cultivar.genome_type} />
                    <IdentityRow label="Code" value={cultivar.cultivar_code} />
                    <div className="mt-2">
                      <DataBadge label="Raspi" count={cultivar.raspi_observation_count} />
                    </div>
                  </Card.Body>
                </Link>
                <Card.Footer className="bg-white border-0 pt-0">
                  <Button
                    size="sm"
                    variant={inComparison ? 'success' : 'outline-primary'}
                    className="w-100"
                    onClick={() => handleComparisonToggle(cultivar)}
                  >
                    {inComparison ? '✓ In export selection' : '+ Add to export selection'}
                  </Button>
                </Card.Footer>
              </Card>
            </Col>
          );
        })}
      </Row>

      {loading && <p className="text-center py-3">Loading more...</p>}
      {!hasMore && results.length > 0 && <p className="text-center py-3 text-muted">End of results.</p>}

      {/* Floating selection button — the selection's destination is the export form
          (the comparison/analysis page is withdrawn; analysis is downstream). */}
      {comparisonItems.length > 0 && (
        <div style={{ position: 'fixed', bottom: '24px', right: '24px', zIndex: 1000 }}>
          <Button
            onClick={() => navigate('/export')}
            className="rounded-pill shadow d-flex align-items-center gap-2 fw-bold"
          >
            Export selection
            <Badge bg="light" text="primary" pill>{comparisonItems.length}</Badge>
          </Button>
        </div>
      )}
    </div>
  );
};

export default SearchResults;
