import React from 'react';
import { Container, Alert } from 'react-bootstrap';
import { useAuth } from '../contexts/AuthContext';

/**
 * Route guard for the batch registration pages. There is no login; the only
 * check is whether this deployment exposes management (write) features.
 */
const AdminRoute = ({ children }) => {
  const { managementEnabled } = useAuth();

  // Management (write) features are disabled when ENVIRONMENT=production; the
  // backend /admin API isn't even mounted there, so guard the UI too.
  if (!managementEnabled) {
    return (
      <Container className="py-5">
        <Alert variant="secondary">
          <Alert.Heading>Read-only deployment</Alert.Heading>
          Batch registration is turned off here (ENVIRONMENT=production); browsing and export remain available.
        </Alert>
      </Container>
    );
  }

  return children;
};

export default AdminRoute;
