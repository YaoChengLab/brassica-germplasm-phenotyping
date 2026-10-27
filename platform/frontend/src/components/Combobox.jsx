// Zero-dependency searchable select built from react-bootstrap primitives.
// Type to substring-filter options (case-insensitive, matches the whole label),
// click or keyboard (↑/↓/Enter/Esc) to pick. Used by the Plant Viewer's 4 key fields.
import React, {
  useState, useRef, useEffect, useMemo,
} from 'react';
import { Form, ListGroup } from 'react-bootstrap';

export default function Combobox({
  options,               // [{ value, label }]
  value,                 // currently selected value ('' = none)
  onChange,              // (value) => void
  placeholder = 'Type to search…',
  disabled = false,
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const boxRef = useRef(null);

  const selected = options.find((o) => String(o.value) === String(value));
  // While open, the box shows what the user is typing; when closed, the selected label.
  const inputText = open ? query : (selected?.label ?? '');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!open || !q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query, open]);

  // Close when clicking outside.
  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const pick = (o) => { onChange(o.value); setQuery(''); setOpen(false); };

  const onKey = (e) => {
    if (disabled) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault(); setOpen(true); setHi((h) => Math.min(h + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault(); setHi((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault(); if (open && filtered[hi]) pick(filtered[hi]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <Form.Control
        type="text"
        value={inputText}
        placeholder={selected ? selected.label : placeholder}
        disabled={disabled}
        autoComplete="off"
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setHi(0); }}
        onFocus={() => { setQuery(''); setOpen(true); setHi(0); }}
        onKeyDown={onKey}
      />
      {open && !disabled && filtered.length > 0 && (
        <ListGroup style={{
          position: 'absolute',
          zIndex: 1050,
          width: '100%',
          maxHeight: 260,
          overflowY: 'auto',
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        }}>
          {filtered.map((o, i) => (
            <ListGroup.Item
              key={o.value}
              action
              active={i === hi}
              onMouseDown={(e) => { e.preventDefault(); pick(o); }}
              onMouseEnter={() => setHi(i)}
              style={{ cursor: 'pointer', padding: '0.35rem 0.6rem' }}
            >
              {o.label}
            </ListGroup.Item>
          ))}
        </ListGroup>
      )}
      {open && !disabled && filtered.length === 0 && (
        <ListGroup style={{ position: 'absolute', zIndex: 1050, width: '100%' }}>
          <ListGroup.Item disabled className="text-muted small">No match</ListGroup.Item>
        </ListGroup>
      )}
    </div>
  );
}
