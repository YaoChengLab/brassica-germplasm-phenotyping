import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { fetchCultivarDetails, fetchCultivarChamberTimeline } from '../services/queryServiceV2';
import CultivarPlots from '../components/CultivarPlots';
import CultivarSignatureTraits from '../components/CultivarSignatureTraits';
import ImageGallery, { CARD_PHOTO_MAX_HEIGHT } from '../components/ImageGallery';
import BatchGrowthTimeline from '../components/BatchGrowthTimeline';

// `cultivars.notes` is in practice the seed vendor's product page (221 of the 222
// filled rows are URLs). Render it as a short host link — the raw URLs are
// percent-encoded CJK slugs 200+ characters long with no break opportunities,
// which is what used to push the table out through the card.
const renderSeedSource = (value) => {
  try {
    const url = new URL(value);
    if (!/^https?:$/.test(url.protocol)) return value;
    let hint = value;
    try { hint = decodeURI(value); } catch { /* malformed escapes: keep raw */ }
    return (
      <a href={value} target="_blank" rel="noopener noreferrer" title={hint}>
        {url.hostname} ↗
      </a>
    );
  } catch {
    return value;
  }
};

const CultivarDetailPage = () => {
  const { cultivarId } = useParams();
  const [cultivar, setCultivar] = useState(null);
  const [batchGrowthChambers, setBatchGrowthChambers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [growthChambersLoading, setGrowthChambersLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadCultivarDetails = async () => {
      try {
        setLoading(true);
        const details = await fetchCultivarDetails(cultivarId);
        setCultivar(details);
      } catch (err) {
        setError('Failed to load cultivar details. Please try again.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    const loadBatchGrowthChambers = async () => {
      try {
        setGrowthChambersLoading(true);
        const data = await fetchCultivarChamberTimeline(cultivarId);
        setBatchGrowthChambers(data.batches || []);
      } catch (err) {
        console.error('Failed to load chamber timeline:', err);
        setBatchGrowthChambers([]);
      } finally {
        setGrowthChambersLoading(false);
      }
    };

    loadCultivarDetails();
    loadBatchGrowthChambers();
  }, [cultivarId]);





  if (loading) {
    return <p>Loading cultivar details...</p>;
  }

  if (error) {
    return <p style={{ color: 'red' }}>{error}</p>;
  }

  if (!cultivar) {
    return <p>Cultivar not found.</p>;
  }

  // Vertical density is the scarce resource on this page: the profile block is
  // reproduced as a figure, where every row of card padding costs
  // millimetres that the growth curves need. Card padding / cell padding / title
  // margins are all deliberately tighter than the browser defaults.
  const detailCardStyle = {
    border: '1px solid #ddd',
    borderRadius: '8px',
    padding: '14px 16px',
    backgroundColor: '#f9f9f9',
    boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
    // Grid items default to min-width:auto, i.e. they refuse to shrink below their
    // content's minimum width — one unbreakable string (a percent-encoded vendor
    // URL) then pushes the table straight through the card. minWidth: 0 lets the
    // card honour its grid track and the cell wrapping below do the work.
    minWidth: 0,
  };

  const cardTitleStyle = {
    margin: '0 0 8px',
    fontSize: '1.2rem',
  };

  const tableStyle = {
    width: '100%',
    borderCollapse: 'collapse',
  };

  const thTdStyle = {
    border: '1px solid #ddd',
    padding: '5px 9px',
    textAlign: 'left',
    overflowWrap: 'anywhere',
    lineHeight: 1.35,
  };

  const thStyle = {
    ...thTdStyle,
    backgroundColor: '#e9ecef',
    fontWeight: 'bold',
    // Fixed label column so a long value cannot squeeze the labels into two lines.
    width: '32%',
    whiteSpace: 'nowrap',
  };



  // Cultivar-intrinsic information only — per-batch counts live in the Batches
  // table. The sparse identity/provenance fields (permanent code, vendor product
  // code, vendor page) are rendered only when present, so a cultivar without them
  // does not show a wall of N/A.
  const seedSource = cultivar.notes;
  const infoRows = [
    { label: 'Common Name', value: cultivar.common_name || 'N/A' },
    { label: 'Cultivar Code', value: cultivar.cultivar_code },
    ...(cultivar.permanent_code
      ? [{ label: 'Permanent Code', value: cultivar.permanent_code }]
      : []),
    { label: 'Genome Type', value: cultivar.genome_type || 'N/A' },
    { label: 'Manufacturer', value: cultivar.manufacturer_name || 'N/A' },
    ...(cultivar.product_code
      ? [{ label: 'Product Code', value: cultivar.product_code }]
      : []),
    ...(seedSource
      ? [{ label: 'Seed Source', value: renderSeedSource(seedSource) }]
      : []),
    { label: 'Planting Time', value: cultivar.planting_time || 'N/A' },
    { label: 'Planting Description', value: cultivar.planting_description || 'N/A' },
  ];

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }} className="large-font-page">
      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0 }}>{cultivar.product_name || 'Cultivar Details'}</h1>
      </div>

      {/* Profile block: identity / provenance / photo on the left, the quantitative
          view on the right. Both columns stretch to the same height and the photo
          takes whatever the left column has left over. */}
      <div className="cultivar-profile-grid">
        <div className="cultivar-profile-left">
          <div style={detailCardStyle}>
            <h3 style={cardTitleStyle}>General Information</h3>
            <table style={tableStyle}>
              <tbody>
                {infoRows.map(({ label, value }) => (
                  <tr key={label}>
                    <td style={thStyle}>{label}</td>
                    <td style={thTdStyle}>{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={detailCardStyle}>
            <h3 style={cardTitleStyle}>Batches</h3>
            {cultivar.batches.length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Batch</th>
                      <th style={thStyle}>Sown</th>
                      <th style={thStyle}>Ended</th>
                      <th style={thStyle}>Days</th>
                      <th style={thStyle}>n</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* The API returns batches in group-by order; sort them so the
                        table reads chronologically like the trait table does. */}
                    {[...cultivar.batches]
                      .sort((a, b) => String(a.start_date).localeCompare(String(b.start_date)))
                      .map((batch, index) => {
                        const duration = (startDate, endDate) => {
                          if (!startDate || !endDate) return 'N/A';
                          return Math.ceil(
                            Math.abs(new Date(endDate) - new Date(startDate)) / 86400000,
                          );
                        };

                        return (
                          <tr key={index}>
                            <td style={thTdStyle}>{batch.batch_code}</td>
                            <td style={thTdStyle}>{batch.start_date || 'N/A'}</td>
                            <td style={thTdStyle}>{batch.end_date || 'N/A'}</td>
                            <td style={thTdStyle}>{duration(batch.start_date, batch.end_date)}</td>
                            <td style={thTdStyle}>{batch.plant_count}</td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>No batches associated with this cultivar.</p>
            )}
            <p style={{ margin: '10px 0 0', color: '#666', fontSize: '0.9rem' }}>
              {cultivar.treatments.length > 0
                ? `Treatments: ${cultivar.treatments
                  .map((t) => `${t.treatment_code} (n=${t.plant_count})`)
                  .join(', ')}. `
                : 'No treatments recorded. '}
              n = observation individuals; the nursery-tray record is not counted.
            </p>
          </div>

          {/* The photo card sits in the left column's 1fr row, so it would otherwise
              stretch to whatever the (much taller) right column dictates. Cap it at
              exactly what the photo needs — title + padding + the image's own height
              cap — so the image keeps its aspect ratio instead of being cover-cropped
              to the leftover space. */}
          <div style={{
            ...detailCardStyle,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            maxHeight: `${CARD_PHOTO_MAX_HEIGHT + 60}px`,
            overflow: 'hidden',
          }}>
            <h3 style={{ ...cardTitleStyle, flex: '0 0 auto' }}>Photo</h3>
            <ImageGallery cultivarCode={cultivar.cultivar_code} variant="card" />
          </div>
        </div>

        <div className="cultivar-profile-right">
          <div style={detailCardStyle}>
            <h3 style={cardTitleStyle}>Signature Traits</h3>
            <CultivarSignatureTraits cultivarId={cultivarId} />
          </div>

          <div style={detailCardStyle}>
            <h3 style={cardTitleStyle}>Growth Curves</h3>
            <CultivarPlots cultivarId={cultivarId} />
          </div>
        </div>
      </div>

      <div style={{ ...detailCardStyle, marginTop: '20px' }}>
        <h3 style={cardTitleStyle}>Chamber Residence &amp; Environment</h3>
        {growthChambersLoading ? (
          <p>Loading growth chamber data...</p>
        ) : batchGrowthChambers.length > 0 ? (
          <BatchGrowthTimeline batchesData={batchGrowthChambers} />
        ) : (
          <p>No growth chamber data available.</p>
        )}
      </div>
    </div>
  );
};

export default CultivarDetailPage;