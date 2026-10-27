// Shared: regroup the per-plant table rows into the backend's plant_groups payload.
// Used by both create (BatchFormPage) and append (BatchAppendPage).

// Required date fields in the shared defaults (backend rejects empty dates with 422).
const REQUIRED_DATE_FIELDS = [
  ['walkin_entry_date', 'Nursery in date'],
  ['walkin_exit_date', 'Nursery out date'],
  ['obs_entry_date', 'Obs. in date'],
];
export const missingDefaultDates = (defaults) =>
  REQUIRED_DATE_FIELDS.filter(([k]) => !defaults[k]).map(([, label]) => label);

// Drop empty optional fields so the backend sees null, not "".
export const clean = (obj) => {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== '' && v !== undefined && v !== null) out[k] = v;
  }
  return out;
};

// Group rows by cultivar; treatment + walk-in + observation dates come from the
// shared defaults. replicate_count is the row count per cultivar.
export const buildPlantGroups = (defaults, rows, includePlacement = true) => {
  const groupsMap = new Map();
  rows.forEach((r) => {
    const key = r.cultivar_code;
    if (!groupsMap.has(key)) groupsMap.set(key, []);
    groupsMap.get(key).push(r);
  });

  return Array.from(groupsMap.entries()).map(([cultivar_code, rs]) => ({
    cultivar_code,
    treatment_code: defaults.treatment_code,
    replicate_count: rs.length,
    walkin_visits: [{
      chamber_code: defaults.walkin_chamber_code,
      entry_date: defaults.walkin_entry_date,
      exit_date: defaults.walkin_exit_date,
      growth_condition_id: Number(defaults.walkin_gc_id),
    }],
    observation: {
      growth_condition_id: Number(defaults.obs_gc_id),
      entry_date: defaults.obs_entry_date,
      ...clean({
        entry_time: defaults.obs_entry_time,
        exit_date: defaults.obs_exit_date,
        exit_time: defaults.obs_exit_time,
      }),
      // Rack and coords are both optional at create: a plant is registered with
      // just cultivar + replicate, then placed on the coordinate page (which
      // derives rack + sensor from the frame's camera code). Send rack_code/coords
      // only when present — the append page's inline edit still fills them.
      individuals: rs.map((r) => {
        const ind = { replicate_code: Number(r.replicate_code) };
        // When the placement UI is off (create form), never send rack/coords —
        // even if a restored draft still carries them in hidden fields.
        if (includePlacement) {
          if (r.rack_code) ind.rack_code = r.rack_code;
          const hasX = r.coordinate_x !== '' && r.coordinate_x != null;
          const hasY = r.coordinate_y !== '' && r.coordinate_y != null;
          if (hasX && hasY) {
            ind.coordinate_x = Number(r.coordinate_x);
            ind.coordinate_y = Number(r.coordinate_y);
          }
        }
        return ind;
      }),
    },
  }));
};
