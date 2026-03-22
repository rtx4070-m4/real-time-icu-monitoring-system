// src/App.tsx
import React, { useState, useEffect } from 'react';
import { ICUDashboard } from './components/dashboard/ICUDashboard';
import { LoginPage } from './components/layout/LoginPage';
import { AuthUser } from './types';

const App: React.FC = () => {
  const [user, setUser] = useState<AuthUser | null>(null);

  // Restore session from localStorage
  useEffect(() => {
    const token    = localStorage.getItem('icu_token');
    const username = localStorage.getItem('icu_username');
    const role     = localStorage.getItem('icu_role') as AuthUser['role'];
    const fullName = localStorage.getItem('icu_fullname');

    if (token && username) {
      setUser({ token, username, role: role ?? 'VIEWER', fullName: fullName ?? username });
    }
  }, []);

  const handleLogin = (authUser: AuthUser) => {
    localStorage.setItem('icu_token',    authUser.token);
    localStorage.setItem('icu_username', authUser.username);
    localStorage.setItem('icu_role',     authUser.role);
    localStorage.setItem('icu_fullname', authUser.fullName);
    setUser(authUser);
  };

  const handleLogout = () => {
    localStorage.removeItem('icu_token');
    localStorage.removeItem('icu_username');
    localStorage.removeItem('icu_role');
    localStorage.removeItem('icu_fullname');
    setUser(null);
  };

  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <ICUDashboard
      currentUser={user.username}
      onLogout={handleLogout}
    />
  );
};

export default App;
