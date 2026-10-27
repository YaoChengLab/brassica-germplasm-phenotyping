import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiV2 } from '../services/api';

/**
 * The platform has no login: every visitor acts as the one fixed operator the
 * backend records in provenance (BPP_OPERATOR, default "admin"). This context
 * only reports whether the deployment exposes the batch registration pages.
 */
const AuthContext = createContext();

const OPERATOR = { username: 'admin', is_admin: true };

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  // Whether this deployment exposes admin write features (false when
  // ENVIRONMENT=production). Default false until /config confirms, so write UI
  // never flashes on a read-only deployment.
  const [managementEnabled, setManagementEnabled] = useState(false);

  useEffect(() => {
    apiV2.get('/config')
      .then((res) => setManagementEnabled(!!res.data?.management_enabled))
      .catch(() => setManagementEnabled(false));
  }, []);

  const value = {
    user: OPERATOR,
    managementEnabled
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
