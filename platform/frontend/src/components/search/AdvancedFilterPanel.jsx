import React, { useState, useEffect } from 'react';
import { SEARCH_FIELDS, OPERATORS_BY_TYPE, FIELD_CATEGORIES } from './SearchFieldDefinitions';
import { fetchFilterOptions } from '../../services/queryServiceV2';

const AdvancedFilterPanel = ({ onSearch, resetTrigger, visible }) => {
  const [conditions, setConditions] = useState([
    { id: 1, field: '', operator: '', value: '', logic: 'AND' },
  ]);
  const [filterOptions, setFilterOptions] = useState(null);

  // Load filter options for enum fields (maturity_type, genome_type, etc.)
  useEffect(() => {
    let cancelled = false;
    fetchFilterOptions()
      .then((data) => {
        if (!cancelled) setFilterOptions(data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    setConditions([{ id: 1, field: '', operator: '', value: '', logic: 'AND' }]);
  }, [resetTrigger]);

  if (!visible) return null;

  const handleConditionChange = (id, key, val) => {
    setConditions((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        const updated = { ...c, [key]: val };
        // Reset operator and value when field changes
        if (key === 'field') {
          updated.operator = '';
          updated.value = '';
        }
        return updated;
      })
    );
  };

  const addCondition = () => {
    setConditions((prev) => [
      ...prev,
      { id: Date.now(), field: '', operator: '', value: '', logic: 'AND' },
    ]);
  };

  const removeCondition = (id) => {
    setConditions((prev) => prev.filter((c) => c.id !== id));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const valid = conditions.filter((c) => c.field && c.operator && c.value !== '');
    if (valid.length === 0) {
      alert('Please add at least one complete condition.');
      return;
    }

    const filters = valid.map((c) => {
      const fieldDef = SEARCH_FIELDS.find((f) => f.value === c.field);
      let processedValue = c.value;
      if (fieldDef?.type === 'number') {
        const num = parseFloat(c.value);
        if (!isNaN(num)) processedValue = num;
      }
      return { field: c.field, operator: c.operator, value: processedValue };
    });

    // Use the logic from the conditions (all share same logic for now)
    const logic = valid.length > 1 ? (valid[1]?.logic || 'AND') : 'AND';
    onSearch({ filters, logic });
  };

  // Only fields with a small closed vocabulary get a picker. Product name has
  // one distinct value per cultivar (336), so a truncated dropdown would hide
  // most of them; it stays a free-text Contains/Equals input instead.
  const getEnumValues = (fieldValue) => {
    if (!filterOptions) return null;
    if (fieldValue === 'genome_type' && filterOptions.genome_types) {
      return filterOptions.genome_types;
    }
    return null;
  };

  const renderValueInput = (condition) => {
    const fieldDef = SEARCH_FIELDS.find((f) => f.value === condition.field);
    if (!fieldDef) {
      return (
        <input
          type="text"
          value={condition.value}
          onChange={(e) => handleConditionChange(condition.id, 'value', e.target.value)}
          placeholder="Select a field first"
          disabled
          style={{ ...inputStyle, flexGrow: 1 }}
        />
      );
    }

    // Enum fields: render select
    const enumValues = getEnumValues(condition.field);
    if (fieldDef.isEnum || enumValues) {
      return (
        <select
          value={condition.value}
          onChange={(e) => handleConditionChange(condition.id, 'value', e.target.value)}
          style={{ ...inputStyle, flexGrow: 1 }}
        >
          <option value="">Select value...</option>
          {enumValues && enumValues.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      );
    }

    // Number fields
    if (fieldDef.type === 'number') {
      return (
        <input
          type="number"
          step="any"
          value={condition.value}
          onChange={(e) => handleConditionChange(condition.id, 'value', e.target.value)}
          placeholder="Enter number..."
          style={{ ...inputStyle, flexGrow: 1 }}
        />
      );
    }

    // Text fields
    return (
      <input
        type="text"
        value={condition.value}
        onChange={(e) => handleConditionChange(condition.id, 'value', e.target.value)}
        placeholder="Enter value..."
        style={{ ...inputStyle, flexGrow: 1 }}
      />
    );
  };

  return (
    <div style={{
      border: '1px solid #dee2e6',
      borderRadius: '8px',
      padding: '16px',
      marginBottom: '16px',
      backgroundColor: '#f8f9fa',
    }}>
      <h5 style={{ marginBottom: '12px', color: '#495057' }}>Advanced Filters</h5>
      <form onSubmit={handleSubmit}>
        {conditions.map((condition, index) => {
          const fieldDef = SEARCH_FIELDS.find((f) => f.value === condition.field);
          const availableOperators = fieldDef ? OPERATORS_BY_TYPE[fieldDef.type] : [];

          return (
            <div key={condition.id} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
              {/* Logic selector */}
              {index > 0 && (
                <select
                  value={condition.logic}
                  onChange={(e) => handleConditionChange(condition.id, 'logic', e.target.value)}
                  style={{ ...inputStyle, minWidth: '70px', fontWeight: '600' }}
                >
                  <option value="AND">AND</option>
                  <option value="OR">OR</option>
                </select>
              )}
              {index === 0 && <div style={{ minWidth: '70px' }} />}

              {/* Field selector with optgroups */}
              <select
                value={condition.field}
                onChange={(e) => handleConditionChange(condition.id, 'field', e.target.value)}
                style={{ ...inputStyle, minWidth: '160px' }}
              >
                <option value="">Select Field</option>
                {FIELD_CATEGORIES.map((cat) => (
                  <optgroup key={cat.key} label={cat.label}>
                    {SEARCH_FIELDS.filter((f) => f.category === cat.key).map((f) => (
                      <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>

              {/* Operator selector */}
              <select
                value={condition.operator}
                onChange={(e) => handleConditionChange(condition.id, 'operator', e.target.value)}
                disabled={!condition.field}
                style={{ ...inputStyle, minWidth: '140px' }}
              >
                <option value="">Operator</option>
                {availableOperators.map((op) => (
                  <option key={op.value} value={op.value}>{op.label}</option>
                ))}
              </select>

              {/* Value input (type-aware) */}
              {renderValueInput(condition)}

              {/* Remove button */}
              <button
                type="button"
                onClick={() => removeCondition(condition.id)}
                style={{
                  padding: '6px 10px',
                  backgroundColor: '#dc3545',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '13px',
                }}
              >
                ✕
              </button>
            </div>
          );
        })}

        <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
          <button
            type="button"
            onClick={addCondition}
            style={{
              padding: '8px 14px',
              backgroundColor: '#17a2b8',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontSize: '13px',
            }}
          >
            + Add Condition
          </button>
          <button
            type="submit"
            style={{
              padding: '8px 18px',
              backgroundColor: '#28a745',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontWeight: '600',
              fontSize: '13px',
            }}
          >
            Run Query
          </button>
        </div>
      </form>
    </div>
  );
};

const inputStyle = {
  padding: '6px 10px',
  borderRadius: '4px',
  border: '1px solid #ced4da',
  fontSize: '13px',
};

export default AdvancedFilterPanel;
