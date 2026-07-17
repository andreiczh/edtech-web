/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Адрес бэкенда голосовой петли. Дефолт — http://localhost:8000 (см. useConversation). */
  readonly VITE_BACKEND_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
