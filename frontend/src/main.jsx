import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { ThemeProvider } from './ThemePicker.jsx';
import { applyTheme, readTheme, applyColorMode, readColorMode } from './themes.js';
import './styles.css';
import './themes.css';
import './newspaper.css';

applyTheme(readTheme());
applyColorMode(readColorMode());
createRoot(document.getElementById('root')).render(<React.StrictMode><ThemeProvider><App /></ThemeProvider></React.StrictMode>);
