import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Container, Table, Badge, Button, Spinner, Alert, Card } from 'react-bootstrap';
import { getBatchDataStatus, setMilestone } from '../services/adminBatchServiceV2';
import { formatApiError } from '../services/formatApiError';

// One data-source cell. n = plants with data, N = observation plants of the cultivar,
// gateOk = lifecycle says this data is due. Distinguishes a real gap from 'not yet'.
const Cell = ({ n, N, gateOk }) => {
  let bg = 'light';
  let text = 'dark';
  let label;
  if (N === 0) { label = '—'; }
  else if (n === N) { bg = 'success'; text = 'light'; label = `${n}/${N}`; }
  else if (n > 0) { bg = 'warning'; label = `${n}/${N} partial`; }
  else if (gateOk) { bg = 'danger'; text = 'light'; label = `0/${N} missing`; }
  else { bg = 'secondary'; text = 'light'; label = `0/${N} not due`; }
  return <Badge bg={bg} text={text} className="border">{label}</Badge>;
};

const BatchDetailPage = () => {
  const navigate = useNavigate();
  const { batchCode } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try { setData(await getBatchDataStatus(batchCode)); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [batchCode]);

  // Optimistically flip the digital-camera milestone, persist, revert on failure.
  const toggleCamera = async (cc, current) => {
    setData((d) => ({
      ...d,
      cultivars: d.cultivars.map((c) =>
        c.cultivar_code === cc ? { ...c, digital_camera_shot: !current } : c),
    }));
    try {
      await setMilestone(batchCode, { cultivar_code: cc, stage: 'digital_camera', shot: !current });
    } catch (e) {
      setData((d) => ({
        ...d,
        cultivars: d.cultivars.map((c) =>
          c.cultivar_code === cc ? { ...c, digital_camera_shot: current } : c),
      }));
      alert(formatApiError(e));
    }
  };

  if (error) return <Container className="py-4"><Alert variant="danger">{error}</Alert></Container>;
  if (!data) return <Container className="py-5 text-center"><Spinner animation="border" /></Container>;

  const totalN = data.cultivars.reduce((s, c) => s + c.observation_plant_count, 0);

  return (
    <Container fluid className="py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="mb-0">Batch data completeness: <span className="text-primary">{batchCode}</span></h3>
        <div className="d-flex gap-2">
          <Button variant="outline-primary" onClick={() => navigate(`/admin/batches/${encodeURIComponent(batchCode)}/add`)}>Edit / append</Button>
          <Button variant="outline-primary" onClick={() => navigate(`/admin/batches/${encodeURIComponent(batchCode)}/coordinates`)}>Coordinates</Button>
          <Button variant="outline-secondary" onClick={() => navigate('/admin/batches')}>Back to list</Button>
        </div>
      </div>

      <Card className="mb-3">
        <Card.Body className="py-2 d-flex flex-wrap gap-3 align-items-center">
          <span>{data.cultivars.length} cultivars / {totalN} obs. plants</span>
          <span>Obs. in: {data.observation_entered
            ? <Badge bg="info">set → raspi due</Badge>
            : <Badge bg="secondary">not set</Badge>}</span>
          <span>Obs. out: {data.observation_exited
            ? <Badge bg="info">set → gantry due</Badge>
            : <Badge bg="secondary">not set</Badge>}</span>
        </Card.Body>
      </Card>

      <div className="mb-2 small text-muted">
        Legend: <Badge bg="success">complete n/N</Badge>{' '}
        <Badge bg="warning" text="dark">partial</Badge>{' '}
        <Badge bg="danger">missing</Badge>{' '}
        <Badge bg="secondary">not due</Badge>
      </div>

      <Table striped bordered hover responsive className="align-middle">
        <thead className="table-light">
          <tr>
            <th>Cultivar</th>
            <th>Obs. plants</th>
            <th>Raspi<div className="small text-muted fw-normal">RGB 2D</div></th>
            <th>Gantry 3D<div className="small text-muted fw-normal">physical</div></th>
            <th>Gantry thermal<div className="small text-muted fw-normal">FLIR</div></th>
            <th>Digital camera<div className="small text-muted fw-normal">gallery</div></th>
          </tr>
        </thead>
        <tbody>
          {data.cultivars.map((c) => (
            <tr key={c.cultivar_code}>
              <td className="fw-bold">{c.cultivar_code}</td>
              <td>{c.observation_plant_count}</td>
              <td><Cell n={c.raspi_plant_count} N={c.observation_plant_count} gateOk={data.observation_entered} /></td>
              <td><Cell n={c.physical_plant_count} N={c.observation_plant_count} gateOk={data.observation_exited} /></td>
              <td><Cell n={c.thermal_plant_count} N={c.observation_plant_count} gateOk={data.observation_exited} /></td>
              <td>
                <Button
                  size="sm"
                  variant={c.digital_camera_shot ? 'success' : 'outline-secondary'}
                  onClick={() => toggleCamera(c.cultivar_code, c.digital_camera_shot)}
                  title="Toggle: representative plant shot with the digital camera"
                >
                  {c.digital_camera_shot ? '✅ shot' : '⏳ not shot'}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <div className="small text-muted">
        Digital camera is event-backed (no data table): a representative plant per cultivar is shot,
        toggled by the button (stored in batch_milestones); a gallery view of the actual images is future work.
      </div>
    </Container>
  );
};

export default BatchDetailPage;
