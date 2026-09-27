import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { bootMax, captureLinkLogin } from './max/bridge'
// index.css первым: там базовая палитра и анимация кругов, ui.css её дополняет
// и местами переопределяет — порядок важен. theme-new.css идёт ПОСЛЕДНИМ:
// это слой нового визуального языка, он переопределяет только токены.
import './index.css'
import './design/ui.css'
import './design/theme-new.css'
import './design/dashboard.css'
// home-v2.css — главная по макету «MacBook Air - 15 (2)»: собственный холст
// 1710×1112, шрифты Unbounded/Golos; на остальные экраны не влияет.
import './design/home-v2.css'

// Внутри MAX сначала ждём библиотеку мессенджера (веб-версия не кладёт данные
// запуска в адрес), иначе первый экран решил бы, что мы обычный сайт.
// Личная ссылка от бота (#mlogin=...) забирается из адреса до первого экрана.
captureLinkLogin()
void bootMax().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
