import React, { createContext, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiV2 } from '../services/api';

const CultivarContext = createContext();

export const useCultivars = () => {
  const context = useContext(CultivarContext);
  if (!context) {
    throw new Error('useCultivars must be used within a CultivarProvider');
  }
  return context;
};

export const CultivarProvider = ({ children }) => {
  const {
    data,
    isLoading: loading,
    error,
  } = useQuery({
    queryKey: ['cultivars', 'all'],
    queryFn: async () => {
      const response = await apiV2.get('/query/cultivars/all');
      return response.data;
    },
    staleTime: 5 * 60 * 1000,   // 5 minutes
    gcTime: 30 * 60 * 1000,     // 30 minutes
  });

  const cultivars = data?.data ?? [];
  const totalCount = data?.total_count ?? 0;

  const value = {
    cultivars,
    totalCount,
    loading,
    error: error ? error.message : null,
  };

  return (
    <CultivarContext.Provider value={value}>
      {children}
    </CultivarContext.Provider>
  );
};
