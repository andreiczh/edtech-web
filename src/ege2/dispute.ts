/**
 * Несогласие с ИИ: словарь причин, проверка полноты и отправка.
 *
 * Почему форма, а не одна кнопка «не согласен». Кнопка сообщает ровно один бит
 * — «где-то не так», — а чтобы ЧТО-ТО ПОЧИНИТЬ, нужны четыре вещи: что именно
 * оспаривается, из-за чего, каким балл должен быть и что человек имел в виду
 * словами. Без них жалоба не суммируется с другими и не проверяется. Поэтому
 * поля обязательные, и обязательность проверяет ещё и сервер (backend/
 * disputes.py): форму можно обойти, функцию — нет.
 *
 * Коды причин ДУБЛИРУЮТСЯ здесь и на сервере намеренно: сервер не должен
 * ходить в сеть за словарём, а тексты — это интерфейс, их место тут. За тем,
 * чтобы списки не разъехались, следит backend/test_disputes.py — он читает
 * ЭТОТ файл и сверяет коды.
 *
 * Модуль НАРОЧНО без импортов: его гоняют тесты обычным node (см.
 * dispute.test.ts), а любой импорт браузерного модуля утащил бы за собой
 * localStorage и import.meta.env. Отправка живёт в feedback.ts, рядом с
 * остальной сетью.
 */

/** С чем именно человек не согласен. От этого зависит и набор причин, и то,
    что видно владельцу в админке. */
export type DisputeTarget =
  | 'score'
  | 'item'
  | 'criterion'
  | 'error'
  | 'talk_review'
  | 'talk_reply'
  | 'app'

export type DisputeKind = 'reading' | 'dialogue' | 'interview' | 'monologue' | 'talk' | 'app'

export interface ReasonOption {
  code: string
  label: string
  targets: DisputeTarget[]
  /** Подсказка в поле объяснения: человеку проще дописать начатую мысль. */
  hint: string
}

/** Минимум символов в объяснении — столько же требует сервер. */
export const MIN_COMMENT = 10

/* Формулировки от первого лица ученика: он выбирает своё ощущение, а не
   диагноз системы. «Ложноположительное срабатывание проверки» никто не
   выберет, а «это не ошибка — так можно» выберет каждый, кто так думает. */
export const REASONS: ReasonOption[] = [
  {
    code: 'misheard',
    label: 'Записали не то, что я сказал',
    targets: ['score', 'item', 'criterion', 'error', 'talk_review'],
    hint: 'Например: я сказал their, а в расшифровке there',
  },
  {
    code: 'no_error',
    label: 'Это не ошибка — так можно',
    targets: ['score', 'item', 'criterion', 'error', 'talk_review'],
    hint: 'Почему так можно сказать? Правило, пример, учебник',
  },
  {
    code: 'missed',
    label: 'Ошибку не заметили',
    targets: ['score', 'item', 'criterion', 'talk_review'],
    hint: 'Что именно надо было засчитать за ошибку',
  },
  {
    code: 'unfair',
    label: 'Балл занижен',
    targets: ['score', 'item', 'criterion'],
    hint: 'Что в ответе есть такого, за что балл должен быть выше',
  },
  {
    code: 'too_soft',
    label: 'Балл завышен',
    targets: ['score', 'item', 'criterion'],
    hint: 'Чего в ответе не хватало, а балл всё равно поставили',
  },
  {
    code: 'unclear',
    label: 'Объяснение непонятное или противоречит себе',
    targets: ['score', 'item', 'criterion', 'error', 'talk_review'],
    hint: 'Что именно непонятно или где разбор спорит сам с собой',
  },
  {
    code: 'off_context',
    label: 'Ответил не на то, о чём шла речь',
    targets: ['talk_reply'],
    hint: 'О чём говорил ты и куда свернул собеседник',
  },
  {
    code: 'invented',
    label: 'Придумал то, чего я не говорил',
    targets: ['talk_reply', 'talk_review'],
    hint: 'Какие слова тебе приписали',
  },
  {
    code: 'shallow',
    label: 'Пусто и скучно, без встречного вопроса',
    targets: ['talk_reply'],
    hint: 'Чего ты ждал в ответ',
  },
  {
    code: 'tone',
    label: 'Ведёт себя не как выбранный характер',
    targets: ['talk_reply'],
    hint: 'Что не сходится с характером собеседника',
  },
  {
    code: 'bad_english',
    label: 'Сам говорит с ошибками',
    targets: ['talk_reply', 'talk_review'],
    hint: 'Какая фраза собеседника звучит неправильно',
  },
  {
    code: 'bug',
    label: 'Что-то сломалось',
    targets: ['score', 'item', 'criterion', 'error', 'talk_review', 'talk_reply', 'app'],
    hint: 'Что нажал и что произошло вместо ожидаемого',
  },
  {
    code: 'other',
    label: 'Другое',
    targets: ['score', 'item', 'criterion', 'error', 'talk_review', 'talk_reply', 'app'],
    hint: 'Расскажи своими словами',
  },
]

export function reasonsFor(target: DisputeTarget): ReasonOption[] {
  return REASONS.filter((r) => r.targets.includes(target))
}

export interface DisputeDraft {
  reason: string
  comment: string
  /** Что человек сказал на самом деле — обязательно при жалобе на распознавание. */
  said: string
  /** Балл, который должен был стоять. -1 — «дело не в балле», null — не выбрано. */
  claimScore: number | null
}

export const EMPTY_DRAFT: DisputeDraft = { reason: '', comment: '', said: '', claimScore: null }

/**
 * Что мешает отправить жалобу — одной фразой, либо null, если всё на месте.
 *
 * Одна функция и на блокировку кнопки, и на подсказку под ней: разъехавшись,
 * они дали бы неотправляемую форму без объяснения причины — худший вид тупика.
 */
export function formProblem(draft: DisputeDraft, needScore: boolean): string | null {
  if (!draft.reason) return 'Выбери, что не так'
  if (needScore && draft.claimScore === null) return 'Отметь, каким должен быть балл'
  if (draft.reason === 'misheard' && draft.said.trim().length < 2)
    return 'Напиши, что ты сказал на самом деле'
  const comment = draft.comment.trim()
  if (comment.length < MIN_COMMENT)
    return `Опиши, что не так — ещё ${MIN_COMMENT - comment.length} символов`
  return null
}

export interface DisputeContext {
  kind: DisputeKind
  target: DisputeTarget
  /** Ключ спорного места: q3, K1, цитата ошибки. Для кластеризации в админке. */
  targetKey?: string
  /** То же место словами — чтобы владелец не расшифровывал ключи. */
  targetLabel?: string
  score?: number
  max?: number
  variant?: string
  /** Улика: расшифровка ответа или спорные реплики. Без неё спор не пересмотреть. */
  transcript?: string
  /** Снимок разбора целиком — то, с чем спорят. */
  feedback?: unknown
  /** Обстановка: текст задания, соседние реплики, что было на экране. */
  context?: Record<string, unknown>
}
