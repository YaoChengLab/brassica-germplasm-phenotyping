import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Container, Row, Col, Card, Table, Button, Form, Spinner, Alert, Badge, ListGroup,
} from 'react-bootstrap';
import { getObservationPlants, updatePlacements, getCameraRackMap, getReferenceFrame } from '../services/adminBatchServiceV2';
import { formatApiError } from '../services/formatApiError';

// Image-first placement. Load a camera frame on the left, pick a plant on the
// right, then click the frame to set the plant's pixel coordinate. The frame's
// camera code (e.g. picA1-102-… -> A1-102) is the raspi sensor_code; the backend
// resolves it to the sensor and its rack, so one click fixes rack + sensor +
// coordinate together. Rack is NOT entered by hand anywhere.
//
// The frame is only loaded in the browser and never uploaded — the click reads a
// pixel from its natural resolution. One frame ≈ one camera tray, so a batch's
// plants are placed across several frames; the grid lists the whole batch and
// each frame places whichever plants are visible in it.
const DOT_COLORS = { placed: '#0d6efd', selected: '#dc3545' };
// Canonical full-frame name, e.g. picA1-102-202412040600.jpg. group(1) = camera code.
const FRAME_NAME_RE = /^pic(.+)-\d{12}\.(jpg|jpeg|png)$/i;
const ZOOM_MIN = 1;
const ZOOM_MAX = 6;
const ZOOM_STEP = 0.5;

const BatchCoordinatesPage = () => {
  const navigate = useNavigate();
  const { batchCode } = useParams();

  const [plants, setPlants] = useState(null);   // [ObservationPlantOut]
  const [cameraMap, setCameraMap] = useState({}); // camera code -> rack_code
  const [loadErr, setLoadErr] = useState(null);
  const [coords, setCoords] = useState({});      // plant_id -> {x, y, ref} | null (working copy)
  const [original, setOriginal] = useState({});  // plant_id -> "x,y|ref" snapshot for diffing
  const [selectedId, setSelectedId] = useState(null);
  const [imgSrc, setImgSrc] = useState(null);
  const [imgName, setImgName] = useState('');   // filename of the loaded frame
  const [imgDims, setImgDims] = useState(null); // {w, h} natural pixels, set on <img> onLoad
  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const imgRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await getObservationPlants(batchCode);
        setPlants(data);
        const c = {};
        const o = {};
        data.forEach((p) => {
          c[p.plant_id] = (p.coordinate_x != null && p.coordinate_y != null)
            ? { x: p.coordinate_x, y: p.coordinate_y, ref: p.coord_ref_image || null } : null;
          o[p.plant_id] = c[p.plant_id] ? `${p.coordinate_x},${p.coordinate_y}|${p.coord_ref_image || ''}` : '';
        });
        setCoords(c);
        setOriginal(o);
      } catch (e) { setLoadErr(formatApiError(e)); }
    })();
    getCameraRackMap().then(setCameraMap).catch(() => setCameraMap({}));
  }, [batchCode]);

  const rackOf = (ref) => {
    const m = ref && FRAME_NAME_RE.exec(ref);
    return m ? (cameraMap[m[1]] || null) : null;
  };

  // Camera code + resolved rack of the loaded frame (what the backend maps to).
  const cameraCode = useMemo(() => {
    const m = imgName && FRAME_NAME_RE.exec(imgName);
    return m ? m[1] : null;
  }, [imgName]);
  const currentRack = cameraCode ? (cameraMap[cameraCode] || null) : null;

  // Rack a cultivar resolves to, from any of its placed plants' frames (all of a
  // cultivar's reps sit on one camera/rack). Live-fills as you place.
  const cultivarRack = (cult) => {
    for (const rep of grid.reps) {
      const pl = grid.cellMap.get(`${cult}|${rep}`);
      const c = pl && coords[pl.plant_id];
      if (c && c.ref) { const r = rackOf(c.ref); if (r) return r; }
    }
    return null;
  };

  // Whole-batch tray grid: cultivars (rows, code asc) x replicates (columns).
  // Plants with no replicate can't sit on the matrix -> "other" fallback list.
  const grid = useMemo(() => {
    const all = plants || [];
    const withRep = all.filter((p) => p.replicate_code != null);
    const cultivars = [...new Set(withRep.map((p) => p.cultivar_code))].sort();
    const reps = [...new Set(withRep.map((p) => p.replicate_code))].sort((a, b) => a - b);
    const cellMap = new Map();
    withRep.forEach((p) => cellMap.set(`${p.cultivar_code}|${p.replicate_code}`, p));
    const orphans = all.filter((p) => p.replicate_code == null);
    return { cultivars, reps, cellMap, orphans };
  }, [plants]);

  // Natural placement order (top->bottom by cultivar, left->right by rep) for auto-advance.
  const orderedPlants = useMemo(() => {
    const out = [];
    grid.cultivars.forEach((cult) => grid.reps.forEach((rep) => {
      const pl = grid.cellMap.get(`${cult}|${rep}`);
      if (pl) out.push(pl);
    }));
    grid.orphans.forEach((pl) => out.push(pl));
    return out;
  }, [grid]);

  const onPickImage = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (imgSrc) URL.revokeObjectURL(imgSrc);
    setImgSrc(URL.createObjectURL(f));
    setImgName(f.name);
    setImgDims(null);
    setZoom(1);
    setMsg(FRAME_NAME_RE.test(f.name) ? null
      : { v: 'warning', t: `Filename "${f.name}" is not a full frame (pic<camera>-yyyymmddHHMM.jpg); saving will be rejected. Load the archived original frame.` });
  };
  useEffect(() => () => { if (imgSrc) URL.revokeObjectURL(imgSrc); }, [imgSrc]);

  // Click on the frame -> natural-pixel coordinate for the selected plant. Works at
  // any zoom: getBoundingClientRect reflects the on-screen (scaled) size, so the
  // naturalWidth/rect.width ratio maps the click back to true pixels.
  const onImageClick = (e) => {
    if (!imgName) return;
    if (selectedId == null) { setMsg({ v: 'warning', t: 'Pick a plant on the right first, then click the frame' }); return; }
    const img = imgRef.current;
    if (!img || !img.naturalWidth) return;
    const rect = img.getBoundingClientRect();
    const px = Math.round((e.clientX - rect.left) * (img.naturalWidth / rect.width));
    const py = Math.round((e.clientY - rect.top) * (img.naturalHeight / rect.height));
    if (px <= 0 || py <= 0) return; // backend requires gt=0
    setCoords((c) => ({ ...c, [selectedId]: { x: px, y: py, ref: imgName } }));
    const idx = orderedPlants.findIndex((p) => p.plant_id === selectedId);
    const nextUnplaced = orderedPlants.slice(idx + 1).find((p) => !coords[p.plant_id]);
    setSelectedId(nextUnplaced ? nextUnplaced.plant_id : selectedId);
  };

  const clearOne = (pid) => setCoords((c) => ({ ...c, [pid]: null }));

  // Fetch an archived frame from the 8T1 store by filename (used to restore the
  // view after a reload, which drops the locally-loaded image).
  const loadFrame = async (filename) => {
    try {
      const blob = await getReferenceFrame(filename);
      if (imgSrc) URL.revokeObjectURL(imgSrc);
      setImgSrc(URL.createObjectURL(blob));
      setImgName(filename);
      setImgDims(null);
      setZoom(1);
      setMsg(null);
    } catch {
      setMsg({ v: 'info', t: `Frame ${filename} couldn't be auto-loaded from the archive; load it manually.` });
    }
  };

  // Select a plant. If it's already placed, also pull up the frame it was digitized
  // from — so clicking a placed cell reopens that photo with its dots. Unplaced
  // cells only select (they'll be placed on whatever frame is currently loaded).
  const selectPlant = (pid) => {
    setSelectedId(pid);
    const c = coords[pid];
    if (c && c.ref && c.ref !== imgName) loadFrame(c.ref);
  };

  const bumpZoom = (d) => setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round((z + d) * 10) / 10)));

  // Changed & fully-placed plants -> PATCH updates. Each update carries its own
  // reference frame, so placements made across several frames save in one call
  // (the backend derives each plant's rack/sensor from its frame's camera code).
  const pendingUpdates = () => (plants || [])
    .filter((p) => {
      const c = coords[p.plant_id];
      if (!c || p.replicate_code == null || !c.ref) return false;
      return `${c.x},${c.y}|${c.ref}` !== original[p.plant_id];
    })
    .map((p) => {
      const c = coords[p.plant_id];
      return {
        plant_id: p.plant_id,
        replicate_code: p.replicate_code,
        coordinate_x: c.x,
        coordinate_y: c.y,
        reference_image: c.ref,
      };
    });

  const save = async () => {
    const updates = pendingUpdates();
    if (updates.length === 0) { setMsg({ v: 'info', t: 'No placements to save' }); return; }
    setSaving(true);
    setMsg(null);
    try {
      const res = await updatePlacements(batchCode, { updates });
      setOriginal((o) => {
        const next = { ...o };
        updates.forEach((u) => { next[u.plant_id] = `${u.coordinate_x},${u.coordinate_y}|${u.reference_image}`; });
        return next;
      });
      setMsg({ v: 'success', t: `Saved ${res.updated_count ?? updates.length} placements` });
    } catch (e) { setMsg({ v: 'danger', t: formatApiError(e) }); }
    finally { setSaving(false); }
  };

  if (loadErr) return <Container className="py-4"><Alert variant="danger">{loadErr}</Alert></Container>;
  if (!plants) return <Container className="py-5 text-center"><Spinner animation="border" /></Container>;

  const nPlaced = plants.filter((p) => coords[p.plant_id]).length;
  const nPending = pendingUpdates().length;

  // G120 observation window (date + HH:MM) — the entry time is the frame timestamp
  // to load; usually one value per batch, but split entries show as a list.
  const fmtDT = (d, t) => (d ? `${d}${t ? ` ${String(t).slice(0, 5)}` : ''}` : null);
  const obsIn = [...new Set(plants.map((p) => fmtDT(p.entry_date, p.entry_time)).filter(Boolean))].sort();
  const obsOut = [...new Set(plants.map((p) => fmtDT(p.exit_date, p.exit_time)).filter(Boolean))].sort();

  // Compact one-cell renderer for the tray grid. A plant placed on a *different*
  // frame still reads as placed (green); only current-frame dots draw on the image.
  const Cell = ({ pl }) => {
    if (!pl) return <td className="text-center text-muted bg-light">—</td>;
    const c = coords[pl.plant_id];
    const on = pl.plant_id === selectedId;
    const cls = on ? 'table-primary' : (c ? 'table-success' : '');
    return (
      <td className={`${cls} text-center`} style={{ cursor: 'pointer', minWidth: 66 }}
        onClick={() => selectPlant(pl.plant_id)}
        title={c ? `${pl.cultivar_code} rep${pl.replicate_code} @ (${c.x},${c.y})${c.ref ? `\nframe: ${c.ref}` : ''}` : `${pl.cultivar_code} rep${pl.replicate_code} (unplaced)`}>
        {c
          ? <><span className="text-success">●</span> <small>{c.x},{c.y}</small>
              <Button variant="link" size="sm" className="p-0 ms-1 text-danger" style={{ lineHeight: 1 }}
                onClick={(e) => { e.stopPropagation(); clearOne(pl.plant_id); }} title="clear">×</Button></>
          : <span className="text-muted">○</span>}
      </td>
    );
  };

  return (
    <Container fluid className="py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h3 className="mb-0">Coordinates: <span className="text-primary">{batchCode}</span></h3>
          {obsIn.length > 0 && (
            <div className="small">
              <span className="text-muted">Obs. in:</span> <strong>{obsIn.join(' / ')}</strong>
              {obsOut.length > 0 && <>{' '}<span className="text-muted ms-2">Obs. out:</span> {obsOut.join(' / ')}</>}
              <span className="text-muted"> — load the frame at the entry time</span>
            </div>
          )}
          <div className="small text-muted">
            Load a camera frame, pick a plant, click to place. Rack + sensor are derived from the frame&apos;s camera code.
          </div>
        </div>
        <Button variant="outline-secondary" size="sm"
          onClick={() => navigate(`/admin/batches/${encodeURIComponent(batchCode)}`)}>Back to batch</Button>
      </div>

      {msg && <Alert variant={msg.v} className="py-2" dismissible onClose={() => setMsg(null)}>{msg.t}</Alert>}

      <Row className="g-3">
        <Col lg={8}>
          <Card>
            <Card.Header className="py-2 d-flex justify-content-between align-items-center flex-wrap gap-2">
              <div className="d-flex gap-2 align-items-center">
                <span className="small text-nowrap fw-semibold">{imgSrc ? 'Change frame' : 'Load frame'}</span>
                <Form.Control type="file" accept="image/*" size="sm" style={{ maxWidth: 220 }}
                  onChange={onPickImage} />
                <Form.Check type="switch" id="grid" label="Guides" checked={showGrid}
                  onChange={(e) => setShowGrid(e.target.checked)} />
                {imgSrc && (
                  <div className="d-flex align-items-center gap-1">
                    <Button variant="outline-secondary" size="sm" onClick={() => bumpZoom(-ZOOM_STEP)} disabled={zoom <= ZOOM_MIN}>−</Button>
                    <span className="small text-muted" style={{ width: 40, textAlign: 'center' }}>{zoom.toFixed(1)}×</span>
                    <Button variant="outline-secondary" size="sm" onClick={() => bumpZoom(ZOOM_STEP)} disabled={zoom >= ZOOM_MAX}>＋</Button>
                    <Button variant="outline-secondary" size="sm" onClick={() => setZoom(1)} disabled={zoom === 1}>Reset</Button>
                  </div>
                )}
              </div>
              <span className="small text-muted">
                {imgName
                  ? <>Camera <Badge bg={cameraCode ? 'info' : 'secondary'}>{cameraCode || '???'}</Badge>
                      {' → '}Rack <Badge bg={currentRack ? 'success' : 'danger'}>{currentRack || 'unknown'}</Badge>
                      {' '}<code>{imgName}</code></>
                  : 'Load the archived frame for one camera tray'}
              </span>
            </Card.Header>
            <Card.Body className="p-0 bg-dark" style={{ overflow: 'auto', maxHeight: '78vh' }}>
              {!imgSrc ? (
                <div className="text-center text-muted py-5">No frame loaded — click &quot;Choose file&quot; above to load a local camera frame</div>
              ) : (
                <div style={{ position: 'relative', width: `${zoom * 100}%`, lineHeight: 0 }}>
                  <img ref={imgRef} src={imgSrc} alt="frame" onClick={onImageClick}
                    onLoad={(e) => setImgDims({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
                    style={{ width: '100%', display: 'block', cursor: 'crosshair' }} />
                  {showGrid && (
                    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                      {[25, 50, 75].map((p) => (
                        <div key={`v${p}`} style={{ position: 'absolute', left: `${p}%`, top: 0, bottom: 0, width: 1, background: 'rgba(255,255,255,0.35)' }} />
                      ))}
                      {[33, 66].map((p) => (
                        <div key={`h${p}`} style={{ position: 'absolute', top: `${p}%`, left: 0, right: 0, height: 1, background: 'rgba(255,255,255,0.35)' }} />
                      ))}
                    </div>
                  )}
                  {imgDims && plants.map((p) => {
                    const c = coords[p.plant_id];
                    if (!c || c.ref !== imgName) return null; // only this frame's placements
                    const left = (c.x / imgDims.w) * 100;
                    const top = (c.y / imgDims.h) * 100;
                    const on = p.plant_id === selectedId;
                    return (
                      <div key={p.plant_id} style={{
                        position: 'absolute', left: `${left}%`, top: `${top}%`,
                        transform: 'translate(-50%, -50%)', pointerEvents: 'none',
                      }}>
                        <div style={{
                          width: 14, height: 14, borderRadius: '50%',
                          background: on ? DOT_COLORS.selected : DOT_COLORS.placed,
                          border: '2px solid #fff', boxShadow: '0 0 3px rgba(0,0,0,0.6)',
                        }} />
                        <div style={{
                          position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)',
                          whiteSpace: 'nowrap', fontSize: 11, color: '#fff',
                          textShadow: '0 0 3px #000', lineHeight: 1.1,
                        }}>{p.cultivar_code} r{p.replicate_code}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col lg={4}>
          <Card>
            {/* Save lives at the top so it's always reachable without scrolling
                past a long cultivar list. */}
            <Card.Header className="py-2">
              <div className="d-flex justify-content-between align-items-center">
                <span>Plants <Badge bg="secondary">{plants.length}</Badge>
                  <span className="small text-muted ms-2">placed {nPlaced}/{plants.length}</span>
                </span>
                <div className="d-flex align-items-center gap-2">
                  <span className="small text-muted">{nPending} unsaved</span>
                  <Button variant="success" size="sm" disabled={saving || nPending === 0} onClick={save}>
                    {saving ? <Spinner size="sm" animation="border" /> : 'Save placements'}
                  </Button>
                </div>
              </div>
            </Card.Header>
            <Card.Body className="p-2">
              <div className="small text-muted mb-1">Click a cell to select a plant, then click the frame to place it. Click a placed (green) cell to reopen its frame with the marked points.</div>
              {/* Scroll the table internally so a long cultivar list doesn't stretch
                  the page; the header (with Save) stays put. Column headers stick. */}
              <div style={{ maxHeight: '66vh', overflowY: 'auto' }}>
                <Table bordered size="sm" className="mb-0 text-center align-middle">
                  <thead className="table-light" style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                    <tr>
                      <th style={{ width: 84 }}>Cultivar</th>
                      <th style={{ width: 60 }}>Rack</th>
                      {grid.reps.map((rep) => <th key={rep}>rep{rep}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {grid.cultivars.map((cult) => {
                      const cr = cultivarRack(cult);
                      return (
                        <tr key={cult}>
                          <th className="table-light text-nowrap" scope="row">{cult}</th>
                          <td className="small">
                            {cr ? <Badge bg="light" text="dark" className="border">{cr}</Badge>
                                : <span className="text-muted">—</span>}
                          </td>
                          {grid.reps.map((rep) => (
                            <Cell key={rep} pl={grid.cellMap.get(`${cult}|${rep}`)} />
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>

                {grid.orphans.length > 0 && (
                  <div className="mt-2">
                    <div className="small text-danger">Other (no rep, not saveable — set a rep first):</div>
                    <ListGroup variant="flush">
                      {grid.orphans.map((p) => (
                        <ListGroup.Item key={p.plant_id} action active={p.plant_id === selectedId}
                          onClick={() => selectPlant(p.plant_id)} className="py-1">
                          {p.cultivar_code} <span className="text-muted small">rep?</span>
                        </ListGroup.Item>
                      ))}
                    </ListGroup>
                  </div>
                )}
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
};

export default BatchCoordinatesPage;
