import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
// index.css первым: там базовая палитра и анимация кругов, ui.css её дополняет
// и местами переопределяет — порядок важен. theme-new.css идёт ПОСЛЕДНИМ:
// это слой нового визуального языка, он переопределяет только токены.
import './index.css'
import './design/ui.css'
import './design/theme-new.css'
import './design/dashboard.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
