import { useState } from 'react'
import { createPortal } from 'react-dom'

/**
 * Личный кабинет: аватар + никнейм. Клик открывает меню «Личный кабинет» /
 * «Настройки»; разделы пока заглушки (модалка).
 */
export function Profile() {
  const [menu, setMenu] = useState(false)
  const [modal, setModal] = useState<null | 'account' | 'settings'>(null)

  const open = (m: 'account' | 'settings') => {
    setModal(m)
    setMenu(false)
  }

  return (
    <div className="profile">
      {menu && <div className="profile__backdrop" onClick={() => setMenu(false)} />}
      {menu && (
        <div className="profile__menu glass" role="menu">
          <button type="button" className="profile__menu-item" onClick={() => open('account')}>
            Личный кабинет
          </button>
          <button type="button" className="profile__menu-item" onClick={() => open('settings')}>
            Настройки
          </button>
        </div>
      )}

      <button
        type="button"
        className="profile__btn"
        onClick={() => setMenu((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={menu}
      >
        <span className="profile__avatar" aria-hidden="true">
          А
        </span>
        <span className="profile__text">
          <span className="profile__name">Андрей</span>
          <span className="profile__role">Ученик</span>
        </span>
      </button>

      {modal &&
        createPortal(
          <div className="modal-backdrop" onClick={() => setModal(null)}>
            <div className="modal glass" onClick={(e) => e.stopPropagation()}>
              <h2 className="modal__title">
                {modal === 'account' ? 'Личный кабинет' : 'Настройки'}
              </h2>
              <p className="modal__body">
                {modal === 'account'
                  ? 'Профиль, прогресс и статистика по заданиям появятся здесь.'
                  : 'Настройки аккаунта и приложения появятся здесь.'}
              </p>
              <div className="modal__foot">
                <button
                  type="button"
                  className="exam-btn exam-btn--primary"
                  onClick={() => setModal(null)}
                >
                  Закрыть
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
