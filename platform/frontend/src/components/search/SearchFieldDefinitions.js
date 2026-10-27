/**
 * Shared field definitions and operator mappings for search components.
 *
 * RGB-derived traits only: 3D scan (weight / height / volume / digital biomass /
 * voxel count) and FLIR temperature fields were removed because the platform
 * does not present those modalities anywhere else. The backend rejects them.
 */

export const SEARCH_FIELDS = [
  // Cultivar fields
  { label: 'Cultivar Code', value: 'cultivar_code', type: 'text', category: 'cultivar' },
  { label: 'Product Name', value: 'product_name', type: 'text', category: 'cultivar' },
  { label: 'Common Name', value: 'common_name', type: 'text', category: 'cultivar' },
  { label: 'Manufacturer Name', value: 'manufacturer_name', type: 'text', category: 'cultivar' },
  { label: 'Genome Type', value: 'genome_type', type: 'text', category: 'cultivar', isEnum: true },

  // RaspiObservation fields
  { label: 'Leaf Count', value: 'leaf_count', type: 'number', category: 'raspi' },
  { label: 'Leaf Area (pixels)', value: 'leaf_area', type: 'number', category: 'raspi' },
];

export const OPERATORS_BY_TYPE = {
  text: [
    { label: 'Equals', value: 'eq' },
    { label: 'Contains', value: 'like' },
    { label: 'Not Equals', value: 'ne' },
    { label: 'Not Contains', value: 'not_like' },
  ],
  number: [
    { label: 'Equals', value: 'eq' },
    { label: 'Not Equals', value: 'ne' },
    { label: 'Greater Than', value: 'gt' },
    { label: 'Less Than', value: 'lt' },
    { label: 'Greater Than or Equal', value: 'gte' },
    { label: 'Less Than or Equal', value: 'lte' },
  ],
};

export const FIELD_CATEGORIES = [
  { key: 'cultivar', label: 'Cultivar' },
  { key: 'raspi', label: 'Raspi Observation' },
];
