import React, { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';
import { Container, Navbar, Nav, Spinner } from 'react-bootstrap';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './services/queryClient';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { CultivarProvider } from './contexts/CultivarContext';
import { ComparisonProvider } from './contexts/ComparisonContext';
import AdminRoute from './components/AdminRoute';
import ErrorBoundary from './components/ErrorBoundary';
import HomePage from './pages/HomePage';
import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';

const SearchCultivarsPage = React.lazy(() => import('./pages/SearchCultivarsPage'));
const CultivarDetailPage = React.lazy(() => import('./pages/CultivarDetailPage'));
const PlantViewPage = React.lazy(() => import('./pages/PlantViewPage'));
const ExportPage = React.lazy(() => import('./pages/ExportPage'));
const BatchListPage = React.lazy(() => import('./pages/BatchListPage'));
const BatchFormPage = React.lazy(() => import('./pages/BatchFormPage'));
const BatchAppendPage = React.lazy(() => import('./pages/BatchAppendPage'));
const BatchDetailPage = React.lazy(() => import('./pages/BatchDetailPage'));
const BatchCoordinatesPage = React.lazy(() => import('./pages/BatchCoordinatesPage'));

const LoadingFallback = () => (
  <div className="d-flex justify-content-center align-items-center" style={{ minHeight: '50vh' }}>
    <Spinner animation="border" role="status">
      <span className="visually-hidden">Loading...</span>
    </Spinner>
  </div>
);

const NavigationBar = () => {
  const { managementEnabled } = useAuth();

  return (
    <Navbar bg="dark" variant="dark" expand="lg" className="mb-0">
      <Container fluid>
        <Navbar.Brand href="/">
          🌱 Plant Phenotyping Platform
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="basic-navbar-nav" />
        <Navbar.Collapse id="basic-navbar-nav">
          <Nav className="me-auto">
            <Nav.Link as={Link} to="/search-cultivars">Cultivar Search</Nav.Link>
            <Nav.Link as={Link} to="/plant">Plant Viewer</Nav.Link>
            <Nav.Link as={Link} to="/export">Export Data</Nav.Link>
            {managementEnabled && (
              <Nav.Link as={Link} to="/admin/batches">Batch Registration</Nav.Link>
            )}
          </Nav>
          <Nav>
            <Nav.Link href={`${import.meta.env.VITE_APP_API_URL || '/api/v1'}/docs`} target="_blank" rel="noopener noreferrer">
              API Docs
            </Nav.Link>
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
};

function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <AuthProvider>
    <CultivarProvider>
    <ComparisonProvider>
      <Router>
        <div className="App">
          <NavigationBar />

          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/search-cultivars" element={<SearchCultivarsPage />} />
              <Route path="/cultivars/:cultivarId" element={<CultivarDetailPage />} />
              <Route path="/plant" element={<PlantViewPage />} />
              <Route path="/export" element={
                <ErrorBoundary>
                  <ExportPage />
                </ErrorBoundary>
              } />
              {/* Statistical analysis is out of the platform's scope: it lives in the
                  downstream analysis scripts, which is where every result in the
                  manuscript was actually produced. The page is withdrawn from the UI
                  rather than half-maintained (the platform is shared with reviewers,
                  and a half-working analysis page is worse than none). The page,
                  the /analysis endpoints and their services were removed. */}
              {/* On-demand image analysis (upload a frame, run YOLO) was removed
                  outright — page, router, service and the ultralytics/opencv/plantcv
                  dependencies. It was not part of the platform's job (trait
                  extraction happens in the offline worker pipeline), and unreachable
                  code is worse than no code in a repository that will be released
                  alongside the manuscript. `/image-analysis` now falls through to the
                  catch-all below. */}
              <Route path="/analysis" element={<Navigate to="/export" replace />} />
              <Route path="/data-analysis" element={<Navigate to="/export" replace />} />
              <Route path="/summary-figures" element={<Navigate to="/export" replace />} />
              <Route path="/batch-comparison" element={<Navigate to="/export" replace />} />
              <Route path="/admin/batches" element={
                <AdminRoute>
                  <BatchListPage />
                </AdminRoute>
              } />
              <Route path="/admin/batches/new" element={
                <AdminRoute>
                  <BatchFormPage />
                </AdminRoute>
              } />
              <Route path="/admin/batches/:batchCode/add" element={
                <AdminRoute>
                  <BatchAppendPage />
                </AdminRoute>
              } />
              <Route path="/admin/batches/:batchCode/coordinates" element={
                <AdminRoute>
                  <BatchCoordinatesPage />
                </AdminRoute>
              } />
              <Route path="/admin/batches/:batchCode" element={
                <AdminRoute>
                  <BatchDetailPage />
                </AdminRoute>
              } />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </div>
      </Router>
    </ComparisonProvider>
    </CultivarProvider>
    </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
