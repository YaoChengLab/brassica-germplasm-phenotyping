import React from 'react';
import { Modal, Button, Table, Badge, Spinner, Alert } from 'react-bootstrap';

/**
 * Shows the dry-run expand (plants + chamber_history that would be written) and
 * confirms the real create. Props: show, preview (BatchPreviewResponse|null),
 * loading, error, onConfirm, onClose, creating.
 */
const PreviewModal = ({ show, preview, loading, error, onConfirm, onClose, creating }) => (
  <Modal show={show} onHide={onClose} size="lg" scrollable>
    <Modal.Header closeButton>
      <Modal.Title>Preview: records to be written</Modal.Title>
    </Modal.Header>
    <Modal.Body>
      {loading && (
        <div className="text-center py-4">
          <Spinner animation="border" /> <span className="ms-2">Expanding…</span>
        </div>
      )}
      {error && <Alert variant="danger">{error}</Alert>}
      {preview && !loading && (
        <>
          <div className="mb-3">
            <Badge bg="secondary" className="me-2">Batch {preview.batch_code}</Badge>
            <Badge bg="info" className="me-2">Start {preview.start_date}</Badge>
            <Badge bg="info" className="me-2">End {preview.end_date ?? '—'}</Badge>
            <Badge bg="primary" className="me-2">
              {preview.plant_count} plants (+{preview.nursery_group_count} nursery group{preview.nursery_group_count === 1 ? '' : 's'})
            </Badge>
            <Badge bg="primary">{preview.chamber_history_count} chamber_history</Badge>
          </div>

          <h6>Plants</h6>
          <Table size="sm" striped bordered className="mb-3">
            <thead>
              <tr><th>local</th><th>type</th><th>cultivar</th><th>treatment</th><th>rep</th><th>parent</th></tr>
            </thead>
            <tbody>
              {preview.plants.map((p) => (
                <tr key={p.local_id}>
                  <td>{p.local_id}</td>
                  <td>{p.plant_type === 'nursery_group' ? 'nursery' : 'individual'}</td>
                  <td>{p.cultivar_code}</td>
                  <td>{p.treatment_code}</td>
                  <td>{p.replicate_code ?? '—'}</td>
                  <td>{p.parent_local_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </Table>

          <h6>Chamber history</h6>
          <Table size="sm" striped bordered>
            <thead>
              <tr><th>plant</th><th>role</th><th>chamber</th><th>rack</th><th>gc</th><th>entry</th><th>exit</th><th>coord</th></tr>
            </thead>
            <tbody>
              {preview.chamber_history.map((c, i) => (
                <tr key={i}>
                  <td>{c.plant_local_id}</td>
                  <td>{c.role === 'walkin' ? 'nursery' : 'observation'}</td>
                  <td>{c.chamber_code}</td>
                  <td>{c.rack_code ?? 'no rack'}</td>
                  <td>{c.growth_condition_id}</td>
                  <td>{c.entry_date}{c.entry_time ? ` ${c.entry_time}` : ''}</td>
                  <td>{c.exit_date ?? '—'}{c.exit_time ? ` ${c.exit_time}` : ''}</td>
                  <td>{c.coordinate_x != null ? `(${c.coordinate_x}, ${c.coordinate_y})` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </Modal.Body>
    <Modal.Footer>
      <Button variant="secondary" onClick={onClose} disabled={creating}>Cancel</Button>
      <Button variant="success" onClick={onConfirm} disabled={loading || !!error || !preview || creating}>
        {creating ? <><Spinner size="sm" animation="border" /> Creating…</> : 'Create'}
      </Button>
    </Modal.Footer>
  </Modal>
);

export default PreviewModal;
