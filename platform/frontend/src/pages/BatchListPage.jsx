import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Container, Button, Table, Spinner, Alert } from 'react-bootstrap';
import { listBatches } from '../services/adminBatchServiceV2';

/**
 * Admin batch list. Reuses GET /query/batches/with-cultivars. Entry point to the
 * create form. (Lean scope: no edit/delete here — rare ops go through SQL.)
 */
const BatchListPage = () => {
  const navigate = useNavigate();
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        setBatches(await listBatches());
      } catch (e) {
        setError(e.response?.data?.detail || 'Failed to load batches');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <Container className="py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="mb-0">Batch Registration</h3>
        <Button variant="primary" onClick={() => navigate('/admin/batches/new')}>
          + New batch
        </Button>
      </div>

      {loading && <div className="text-center py-4"><Spinner animation="border" /></div>}
      {error && <Alert variant="danger">{error}</Alert>}

      {!loading && !error && (
        <Table striped bordered hover responsive>
          <thead>
            <tr>
              <th>Batch code</th>
              <th>Start date</th>
              <th>End date</th>
              <th>Cultivars</th>
              <th>Plants</th>
              <th>Plants with data</th>
              <th style={{ width: 110 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.batch_code ?? b.id}>
                <td>
                  <Button variant="link" className="p-0" onClick={() => navigate(`/admin/batches/${encodeURIComponent(b.batch_code)}`)}>
                    {b.batch_code}
                  </Button>
                </td>
                <td>{b.start_date ?? '—'}</td>
                <td>{b.end_date ?? '—'}</td>
                <td>{b.cultivar_count ?? b.cultivars?.length ?? '—'}</td>
                <td>{b.plant_count ?? '—'}</td>
                <td>{b.imaged_plant_count ?? '—'}</td>
                <td>
                  <Button variant="outline-primary" size="sm"
                    onClick={() => navigate(`/admin/batches/${encodeURIComponent(b.batch_code)}/add`)}>
                    Add plants
                  </Button>
                </td>
              </tr>
            ))}
            {batches.length === 0 && (
              <tr><td colSpan={7} className="text-center text-muted">No batches yet</td></tr>
            )}
          </tbody>
        </Table>
      )}
    </Container>
  );
};

export default BatchListPage;
