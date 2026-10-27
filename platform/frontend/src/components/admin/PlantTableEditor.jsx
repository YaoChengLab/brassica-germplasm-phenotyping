import React, { useState } from 'react';
import { Card, Form, Row, Col, Table, Button, InputGroup, Badge } from 'react-bootstrap';

/**
 * CSV-style batch entry: batch-wide defaults filled once, then one narrow row per
 * plant. On submit BatchFormPage regroups rows by cultivar into the backend's
 * plant_groups payload.
 *
 * Placement columns (rack / X / Y) are gated behind `showPlacement`:
 *   - create (BatchFormPage): showPlacement=false — rack + coords are deferred to
 *     the coordinate page, which derives rack + sensor from the frame's camera code.
 *   - append/edit (BatchAppendPage): showPlacement=true — keeps inline typo-fixes.
 *
 * Props:
 *   defaults, onDefaults(next)         batch-wide shared fields
 *   rows, onRows(nextRows)             per-plant rows
 *   options {treatments, walkinChambers, growthConditions, g120Racks}
 *   cultivars [{id, cultivar_code, product_name}]   datalist source
 *   onAddCultivar(code)                inline-create a new cultivar
 *   showPlacement                      render rack / X / Y columns (default true)
 */

export const blankRow = () => ({
  cultivar_code: '', replicate_code: '', rack_code: '', coordinate_x: '', coordinate_y: '',
});

const PlantTableEditor = ({
  defaults, onDefaults, rows, onRows, options, cultivars, onAddCultivar,
  showPlacement = true,
}) => {
  const [newCv, setNewCv] = useState('');
  const [addN, setAddN] = useState(5);

  const setD = (field, val) => onDefaults({ ...defaults, [field]: val });
  const setCell = (i, field, val) => onRows(rows.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)));

  const addRows = (n) => onRows([...rows, ...Array.from({ length: Math.max(1, n) }, blankRow)]);
  const dupLast = () => onRows([...rows, { ...(rows[rows.length - 1] || blankRow()) }]);
  const removeRow = (i) => onRows(rows.filter((_, idx) => idx !== i));

  // Copy the first row's value of a column down to every NEW row (existing rows
  // are left untouched — they hold persisted data).
  const fillDown = (field) => {
    if (!rows.length) return;
    const v = rows[0][field];
    onRows(rows.map((r) => (r._existing ? r : { ...r, [field]: v })));
  };

  // Renumber replicate_code 1..N within each cultivar for NEW rows only. Append
  // creates a fresh nursery group per cultivar, whose reps must be exactly 1..N.
  const autoNumberRep = () => {
    const counter = {};
    onRows(rows.map((r) => {
      if (r._existing) return r;
      const c = r.cultivar_code || '';
      counter[c] = (counter[c] || 0) + 1;
      return { ...r, replicate_code: counter[c] };
    }));
  };

  const addCultivar = async () => {
    const code = newCv.trim();
    if (!code) return;
    await onAddCultivar(code);
    setNewCv('');
  };

  return (
    <>
      <Card className="mb-3">
        <Card.Header className="py-2"><strong>Batch defaults</strong> (shared by all plants — fill once)</Card.Header>
        <Card.Body>
          <Row className="g-2">
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Treatment</Form.Label>
              <Form.Select size="sm" value={defaults.treatment_code}
                onChange={(e) => setD('treatment_code', e.target.value)}>
                {options.treatments.map((t) => (
                  <option key={t.id} value={t.treatment_code}>{t.treatment_code}</option>
                ))}
              </Form.Select>
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Nursery chamber</Form.Label>
              <Form.Select size="sm" value={defaults.walkin_chamber_code}
                onChange={(e) => setD('walkin_chamber_code', e.target.value)}>
                {options.walkinChambers.map((c) => <option key={c} value={c}>{c}</option>)}
              </Form.Select>
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Nursery in <span className="text-danger">*</span></Form.Label>
              <Form.Control size="sm" type="date" value={defaults.walkin_entry_date}
                onChange={(e) => setD('walkin_entry_date', e.target.value)} />
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Nursery out <span className="text-danger">*</span></Form.Label>
              <Form.Control size="sm" type="date" value={defaults.walkin_exit_date}
                onChange={(e) => setD('walkin_exit_date', e.target.value)} />
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Nursery GC</Form.Label>
              <Form.Select size="sm" value={defaults.walkin_gc_id}
                onChange={(e) => setD('walkin_gc_id', Number(e.target.value))}>
                {options.growthConditions.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
              </Form.Select>
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Obs. GC</Form.Label>
              <Form.Select size="sm" value={defaults.obs_gc_id}
                onChange={(e) => setD('obs_gc_id', Number(e.target.value))}>
                {options.growthConditions.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
              </Form.Select>
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Obs. in <span className="text-danger">*</span></Form.Label>
              <Form.Control size="sm" type="date" value={defaults.obs_entry_date}
                onChange={(e) => setD('obs_entry_date', e.target.value)} />
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Obs. in time</Form.Label>
              <Form.Control size="sm" type="time" step="1" value={defaults.obs_entry_time}
                onChange={(e) => setD('obs_entry_time', e.target.value)} />
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Obs. out (opt.)</Form.Label>
              <Form.Control size="sm" type="date" value={defaults.obs_exit_date}
                onChange={(e) => setD('obs_exit_date', e.target.value)} />
            </Col>
            <Col xs={6} md={2}>
              <Form.Label className="small fw-bold mb-0">Obs. out time</Form.Label>
              <Form.Control size="sm" type="time" step="1" value={defaults.obs_exit_time}
                onChange={(e) => setD('obs_exit_time', e.target.value)} />
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <Card className="mb-3">
        <Card.Header className="d-flex flex-wrap gap-2 align-items-center py-2">
          <strong>Plants ({rows.length})</strong>
          <div className="ms-auto d-flex flex-wrap gap-2 align-items-center">
            <InputGroup size="sm" style={{ width: 230 }}>
              <Form.Control placeholder="New cultivar code" value={newCv}
                onChange={(e) => setNewCv(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCultivar())} />
              <Button variant="outline-success" onClick={addCultivar}>Add cultivar</Button>
            </InputGroup>
            <Button variant="outline-secondary" size="sm" onClick={autoNumberRep}>Auto-number rep</Button>
          </div>
        </Card.Header>
        <Card.Body className="p-0">
          {!showPlacement && (
            <div className="small text-muted px-3 py-2 border-bottom">
              Rack &amp; coordinates are set later on the <strong>Coordinates</strong> page,
              where clicking a camera frame fixes rack + sensor + position from the frame&apos;s camera code.
            </div>
          )}
          <datalist id="cultivar-options">
            {cultivars.map((c) => (
              <option key={c.id ?? c.cultivar_code} value={c.cultivar_code}>
                {c.product_name ? `${c.cultivar_code} — ${c.product_name}` : c.cultivar_code}
              </option>
            ))}
          </datalist>
          <Table size="sm" bordered hover responsive className="mb-0 align-middle">
            <thead className="table-light">
              <tr>
                <th style={{ width: 40 }}>#</th>
                <th>Cultivar <FillBtn onClick={() => fillDown('cultivar_code')} /></th>
                <th style={{ width: 80 }}>rep</th>
                {showPlacement && <th style={{ width: 140 }}>Rack <FillBtn onClick={() => fillDown('rack_code')} /></th>}
                {showPlacement && <th style={{ width: 90 }}>X <span className="small text-muted fw-normal">opt.</span></th>}
                {showPlacement && <th style={{ width: 90 }}>Y <span className="small text-muted fw-normal">opt.</span></th>}
                <th style={{ width: 44 }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={r._existing ? 'table-light' : undefined}>
                  <td className="text-muted text-center">{i + 1}</td>
                  <td>
                    {r._existing ? (
                      <span className="d-inline-flex align-items-center">
                        <Badge bg="light" text="dark" className="border me-1">saved</Badge>
                        {r.cultivar_code}
                      </span>
                    ) : (
                      <Form.Control size="sm" list="cultivar-options" placeholder="type / pick cultivar"
                        value={r.cultivar_code} onChange={(e) => setCell(i, 'cultivar_code', e.target.value)} />
                    )}
                  </td>
                  <td>
                    <Form.Control size="sm" type="number" min={1} value={r.replicate_code}
                      onChange={(e) => setCell(i, 'replicate_code', e.target.value)} />
                  </td>
                  {showPlacement && (
                    <td>
                      <Form.Select size="sm" value={r.rack_code}
                        onChange={(e) => setCell(i, 'rack_code', e.target.value)}>
                        <option value="">—</option>
                        {options.g120Racks.map((rk) => (
                          <option key={rk.id} value={rk.rack_code}>{rk.rack_code}</option>
                        ))}
                      </Form.Select>
                    </td>
                  )}
                  {showPlacement && (
                    <td>
                      <Form.Control size="sm" type="number" min={1} value={r.coordinate_x}
                        onChange={(e) => setCell(i, 'coordinate_x', e.target.value)} />
                    </td>
                  )}
                  {showPlacement && (
                    <td>
                      <Form.Control size="sm" type="number" min={1} value={r.coordinate_y}
                        onChange={(e) => setCell(i, 'coordinate_y', e.target.value)} />
                    </td>
                  )}
                  <td className="text-center">
                    <Button variant="outline-danger" size="sm"
                      disabled={r._existing || rows.length <= 1}
                      title={r._existing ? 'existing plant — cannot delete here' : 'remove row'}
                      onClick={() => removeRow(i)}>×</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card.Body>
        <Card.Footer className="d-flex flex-wrap gap-2 align-items-center py-2">
          <Button variant="outline-primary" size="sm" onClick={() => addRows(1)}>+ Add row</Button>
          <Button variant="outline-secondary" size="sm" onClick={dupLast}>Duplicate last</Button>
          <InputGroup size="sm" style={{ width: 170 }}>
            <Button variant="outline-primary" onClick={() => addRows(Number(addN))}>+ Add N</Button>
            <Form.Control type="number" min={1} value={addN} onChange={(e) => setAddN(e.target.value)} />
          </InputGroup>
        </Card.Footer>
      </Card>
    </>
  );
};

const FillBtn = ({ onClick }) => (
  <Button variant="link" size="sm" className="p-0 ms-1 align-baseline" title="fill column from first row"
    onClick={onClick} style={{ fontSize: '0.75rem' }}>↓fill</Button>
);

export default PlantTableEditor;
