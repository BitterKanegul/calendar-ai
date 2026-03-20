import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { calendarAPI } from '../services/api';
import { showInfoToast } from '../common/toast/toast-message';

interface User {
  name: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshAuth = async () => {
    // SCREENSHOT MOCK — bypass auth check, remove before shipping
    setUser({ name: 'Naveen' });
    setIsLoading(false);
  };

  useEffect(() => {
    refreshAuth();
  }, []);

  useEffect(() => {
    // Set up callback for when API detects auth failure
    calendarAPI.setAuthFailureCallback(() => {
      setUser(null);
      showInfoToast('Oturum suresi doldu, lütfen tekrar giriş yapınız.');
    });
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const response = await calendarAPI.login({ email, password });
      setUser({
        name: response.user_name,
      });
    } catch (error) {
      throw error;
    }
  };

  const register = async (name: string, email: string, password: string) => {
    try {
      const response = await calendarAPI.register({ name, email, password });
      setUser({
        name: response.user_name,
      });
    } catch (error) {
      throw error;
    }
  };

  const logout = async () => {
    try {
      setIsLoading(true);
      await calendarAPI.logout();
      setUser(null);
    } catch (error) {
      console.error('Logout error:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
    refreshAuth,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}; 