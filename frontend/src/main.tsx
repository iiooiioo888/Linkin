import './lib/randomUuidPolyfill'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './i18n'
import './index.css'
import { installAuthFetch } from './lib/auth'
import App from './App.tsx'
import LoginGate from './components/LoginGate.tsx'

installAuthFetch()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LoginGate>
      <App />
    </LoginGate>
  </StrictMode>,
)
