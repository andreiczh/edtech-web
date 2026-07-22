import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
// index.css первым: там базовая палитра и анимация кругов, ui.css её дополняет
// и местами переопределяет — порядок важен.
import './index.css'
import './design/ui.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
