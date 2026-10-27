import React, { useState, useEffect, useRef } from 'react';
import { apiV2 as api } from '../services/api';

// Three presentations of the same viewer:
//   'grid'    thumbnail row (default)
//   'compact' small chip (thumbnail + count) for placing next to a title
//   'card'    one large image at its own aspect ratio, height-capped
// All of them open the same full-screen viewer (zoom / pan / keyboard / download).

// Tallest a 'card' photo may render. The photo card on the cultivar page caps its
// own height just above this (title + padding + this), so the image is never cut.
export const CARD_PHOTO_MAX_HEIGHT = 430;
const ImageGallery = ({ cultivarCode, compact = false, variant = compact ? 'compact' : 'grid' }) => {
  const [images, setImages] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Zoom and Pan state
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const imageContainerRef = useRef(null);
  const lastMousePosition = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const loadImages = async () => {
      if (!cultivarCode) return;
      
      try {
        setLoading(true);
        const response = await api.get(`/query/cultivars/${cultivarCode}/images`);
        const webpImages = (response.data.images || []).filter(img => img.toLowerCase().endsWith('.webp'));
        setImages(webpImages);
        setError(null);
      } catch (err) {
        setError('Failed to load images');
        console.error('Error loading images:', err);
      } finally {
        setLoading(false);
      }
    };

    loadImages();
  }, [cultivarCode]);

  const resetZoomAndPan = () => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
  };

  const openModal = (index) => {
    setCurrentIndex(index);
    resetZoomAndPan();
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
  };

  const goToPrevious = () => {
    setCurrentIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1));
    resetZoomAndPan();
  };

  const goToNext = () => {
    setCurrentIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1));
    resetZoomAndPan();
  };

  const handleKeyDown = (e) => {
    if (!isModalOpen) return;
    
    switch (e.key) {
      case 'ArrowLeft':
        goToPrevious();
        break;
      case 'ArrowRight':
        goToNext();
        break;
      case 'Escape':
        closeModal();
        break;
    }
  };

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isModalOpen, currentIndex]); // Add currentIndex to dependencies

  const getImageCaption = (filename) => {
    return filename
      .replace(/\.(webp|jpg|jpeg|png)$/i, '')
      .replace(`${cultivarCode}-`, '');
  };

  // Zoom handlers
  const handleZoomIn = () => setScale(s => Math.min(s * 1.2, 5));
  const handleZoomOut = () => setScale(s => Math.max(s / 1.2, 0.5));

  const handleWheel = (e) => {
    e.preventDefault();
    if (e.deltaY < 0) {
      handleZoomIn();
    } else {
      handleZoomOut();
    }
  };

  // Pan handlers
  const handleMouseDown = (e) => {
    if (scale > 1) {
      e.preventDefault();
      setIsDragging(true);
      lastMousePosition.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging && scale > 1) {
      e.preventDefault();
      const dx = e.clientX - lastMousePosition.current.x;
      const dy = e.clientY - lastMousePosition.current.y;
      lastMousePosition.current = { x: e.clientX, y: e.clientY };
      setPosition(p => ({ x: p.x + dx, y: p.y + dy }));
    }
  };

  const handleMouseUp = () => setIsDragging(false);
  const handleMouseLeave = () => setIsDragging(false);

  // Download handler
  const handleDownload = () => {
    const imageUrl = `/media/uploads/img/${cultivarCode}/${images[currentIndex]}`;
    const link = document.createElement('a');
    link.href = imageUrl;
    link.download = images[currentIndex];
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const compactChipStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '10px',
    padding: '6px 14px 6px 6px',
    border: '1px solid #ddd',
    borderRadius: '10px',
    backgroundColor: '#fff',
    boxShadow: '0 2px 4px rgba(0,0,0,0.08)',
    font: 'inherit',
    color: '#333',
    cursor: 'pointer',
  };

  const short = variant === 'compact' || variant === 'card';

  if (loading) {
    if (short) return <span style={{ color: '#6c757d', fontSize: '0.9rem' }}>Loading images…</span>;
    return <p>Loading images...</p>;
  }

  if (error) {
    if (short) return <span style={{ color: '#c0392b', fontSize: '0.9rem' }}>Images unavailable</span>;
    return <p style={{ color: 'red' }}>{error}</p>;
  }

  if (images.length === 0) {
    if (short) return <span style={{ color: '#6c757d', fontSize: '0.9rem' }}>No images</span>;
    return <p>No images available for this cultivar.</p>;
  }

  // Top view first: it is the same viewpoint the trait pipeline measures from.
  const preferredIndex = Math.max(0, images.findIndex((f) => /topview/i.test(f)));

  const thumbnailStyle = {
    width: '120px',
    height: '120px',
    objectFit: 'cover',
    cursor: 'pointer',
    border: '2px solid #ddd',
    borderRadius: '8px',
    margin: '5px',
    transition: 'border-color 0.3s ease',
  };

  const modalOverlayStyle = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  };

  const modalContentStyle = {
    position: 'relative',
    width: '85vw',
    height: '85vh',
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '20px',
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
  };

  const imageContainerStyle = {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f8f9fa',
    border: '1px solid #e9ecef',
    borderRadius: '4px',
    overflow: 'hidden',
    marginBottom: '15px',
    cursor: isDragging ? 'grabbing' : (scale > 1 ? 'grab' : 'default'),
  };

  const modalImageStyle = {
    maxWidth: '100%',
    maxHeight: '100%',
    objectFit: 'contain',
    display: 'block',
    transition: 'transform 0.1s ease-out',
    transform: `scale(${scale}) translate(${position.x}px, ${position.y}px)`,
  };

  const navigationButtonStyle = {
    position: 'absolute',
    top: '50%',
    transform: 'translateY(-50%)',
    backgroundColor: 'rgba(255, 255, 255, 0.8)',
    border: 'none',
    borderRadius: '50%',
    width: '50px',
    height: '50px',
    fontSize: '24px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1001,
  };

  const closeButtonStyle = {
    position: 'absolute',
    top: '10px',
    right: '10px',
    backgroundColor: 'transparent',
    border: 'none',
    fontSize: '24px',
    cursor: 'pointer',
    color: '#666',
    zIndex: 1001,
  };

  const controlsContainerStyle = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '10px',
    padding: '10px',
  };

  const controlButtonStyle = {
    padding: '8px 16px',
    fontSize: '16px',
    cursor: 'pointer',
    border: '1px solid #ccc',
    borderRadius: '4px',
    backgroundColor: '#f0f0f0',
  };

  return (
    <div
      style={
        variant === 'compact' ? { display: 'inline-block' }
          : variant === 'card' ? { height: '100%', minHeight: 0, display: 'flex' }
            : undefined
      }
    >
      {variant === 'card' ? (
        /* One large image, always at its own aspect ratio. It used to fill the card
           with object-fit: cover, which meant the rendered shape was dictated by
           whatever vertical space the neighbouring column happened to leave over —
           a cultivar grown in ten batches turned the photo into a cropped sliver,
           and the single-column breakpoint cropped ~35% off it. Bounded by
           CARD_PHOTO_MAX_HEIGHT instead (see the card's maxHeight in
           CultivarDetailPage, which is kept just above it), so nothing is cut. */
        <button
          type="button"
          onClick={() => openModal(preferredIndex)}
          title={`${getImageCaption(images[preferredIndex])} — click to browse all ${images.length}`}
          style={{
            padding: 0, border: 'none', background: 'none', cursor: 'pointer',
            width: '100%', minHeight: 0, display: 'flex',
            justifyContent: 'center', alignItems: 'flex-start', overflow: 'hidden',
          }}
        >
          <img
            src={`/media/uploads/img/${cultivarCode}/${images[preferredIndex]}`}
            alt={`${cultivarCode} - ${getImageCaption(images[preferredIndex])}`}
            style={{
              maxWidth: '100%', maxHeight: CARD_PHOTO_MAX_HEIGHT,
              width: 'auto', height: 'auto',
              display: 'block', borderRadius: 4, border: '1px solid #ddd',
            }}
          />
        </button>
      ) : variant === 'compact' ? (
        /* Small chip, e.g. next to a page title */
        <button
          type="button"
          style={compactChipStyle}
          onClick={() => openModal(0)}
          title={`Browse ${images.length} cultivar photo${images.length === 1 ? '' : 's'}`}
          onMouseOver={(e) => { e.currentTarget.style.borderColor = '#007bff'; }}
          onMouseOut={(e) => { e.currentTarget.style.borderColor = '#ddd'; }}
        >
          <img
            src={`/media/uploads/img/${cultivarCode}/${images[0]}`}
            alt={`${cultivarCode} preview`}
            style={{ width: 44, height: 44, objectFit: 'cover', borderRadius: 7, display: 'block' }}
            onError={(e) => { e.target.style.visibility = 'hidden'; }}
          />
          <span style={{ textAlign: 'left', lineHeight: 1.25 }}>
            <span style={{ fontWeight: 600, display: 'block' }}>
              Photos ({images.length})
            </span>
            <span style={{ fontSize: '0.82rem', color: '#6c757d' }}>click to browse</span>
          </span>
        </button>
      ) : (
        /* Thumbnail Grid */
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
          {images.map((image, index) => (
            <img
              key={index}
              src={`/media/uploads/img/${cultivarCode}/${image}`}
              alt={`${cultivarCode} - ${getImageCaption(image)}`}
              style={thumbnailStyle}
              onClick={() => openModal(index)}
              onMouseOver={(e) => e.target.style.borderColor = '#007bff'}
              onMouseOut={(e) => e.target.style.borderColor = '#ddd'}
              onError={(e) => {
                e.target.style.display = 'none';
              }}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      {isModalOpen && (
        <div style={modalOverlayStyle} onClick={closeModal}>
          <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
            <button style={closeButtonStyle} onClick={closeModal}>
              ×
            </button>
            
            <button
              style={{...navigationButtonStyle, left: '10px'}}
              onClick={(e) => { e.stopPropagation(); goToPrevious(); }}
              disabled={images.length <= 1}
            >
              ←
            </button>
            
            <button
              style={{...navigationButtonStyle, right: '10px'}}
              onClick={(e) => { e.stopPropagation(); goToNext(); }}
              disabled={images.length <= 1}
            >
              →
            </button>

            <div 
              ref={imageContainerRef}
              style={imageContainerStyle}
              onWheel={handleWheel}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseLeave}
            >
              <img
                src={`/media/uploads/img/${cultivarCode}/${images[currentIndex]}`}
                alt={`${cultivarCode} - ${getImageCaption(images[currentIndex])}`}
                style={modalImageStyle}
              />
            </div>
            
            <div style={controlsContainerStyle}>
              <button style={controlButtonStyle} onClick={handleZoomOut}>-</button>
              <button style={controlButtonStyle} onClick={resetZoomAndPan}>Reset</button>
              <button style={controlButtonStyle} onClick={handleZoomIn}>+</button>
              <button style={controlButtonStyle} onClick={handleDownload}>Download</button>
            </div>

            <div style={{ padding: '10px' }}>
              <h4 style={{ margin: '0 0 10px 0', color: '#333' }}>
                {getImageCaption(images[currentIndex])}
              </h4>
              <p style={{ margin: 0, color: '#666', fontSize: '14px' }}>
                Image {currentIndex + 1} of {images.length}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ImageGallery;