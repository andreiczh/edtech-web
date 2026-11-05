import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'

import { requestFocusedPractice, type AudioSpan, type PracticeGoal, type PracticeResult, type TaskFeedback } from '../ege2/feedback'
import { feedbackPayload, TASKS, type TaskId, type TaskVariant } from '../ege2/tasks'
import { useRecorder } from '../ege2/useRecorder'
import './FeedbackCoach.css'

function practiceGoals(taskId: TaskId, variant: TaskVariant, feedback: TaskFeedback): PracticeGoal[] {
  if (taskId === 42) return feedback.practice ?? []
  if (taskId !== 40 && taskId !== 41) return []
  return (feedback.criteria ?? []).flatMap((item, index) => {
    const prompt = variant.steps?.[index]
    if (!prompt || item.score >= item.max) return []
    return [{
      key: item.key,
      criterion: taskId === 41 ? `Ответ №${index + 1}` : `Вопрос №${index + 1}`,
      instruction: taskId === 41 ? 'Исправь замечание и ответь на все части вопроса двумя законченными фразами.'
        : 'Задай один прямой вопрос по этому пункту объявления.',
      before: item.comment || 'Этот пункт не засчитан.',
      quote: item.audio_span ? item.quote : undefined,
      audio_span: item.audio_span,
      example: item.correction,
      item: index,
    }]
  })
}

export function FeedbackCoach({ taskId, variant, feedback, player, hasRecording }: {
  taskId: TaskId
  variant: TaskVariant
  feedback: TaskFeedback
  player: RefObject<HTMLAudioElement | null>
  hasRecording: boolean
}) {
  const goals = useMemo(() => practiceGoals(taskId, variant, feedback), [taskId, variant, feedback])
  const [selected, setSelected] = useState<string | null>(null)
  const goal = goals.find((g) => g.key === selected)
  const [clipError, setClipError] = useState(false)
  const clip = useRef<AudioSpan | null>(null)
  const startingClip = useRef(false)
  const [result, setResult] = useState<PracticeResult | null>(null)
  const [failure, setFailure] = useState('')
  const [lastRecording, setLastRecording] = useState<Blob | null>(null)
  const [working, setWorking] = useState(false)
  const locked = useRef(false)
  const active = useRef(true)
  const request = useRef<AbortController | null>(null)
  const { start, stop, state, error } = useRecorder()
  const recording = state === 'recording'

  useEffect(() => {
    const audio = player.current
    if (!audio) return
    function onSeeked() {
      if (!audio || !clip.current) return
      if (startingClip.current && Math.abs(audio.currentTime - clip.current.start) > 0.5) {
        clip.current = null
        audio.pause()
        setClipError(true)
      }
      startingClip.current = false
    }
    function onTimeUpdate() {
      if (audio && clip.current && audio.currentTime >= clip.current.end) {
        clip.current = null
        audio.pause()
      }
    }
    audio.addEventListener('seeked', onSeeked)
    audio.addEventListener('timeupdate', onTimeUpdate)
    return () => {
      audio.removeEventListener('seeked', onSeeked)
      audio.removeEventListener('timeupdate', onTimeUpdate)
    }
  }, [player, hasRecording])

  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      request.current?.abort()
    }
  }, [])

  function select(target: PracticeGoal) {
    if (locked.current || recording) return
    player.current?.pause()
    setSelected(target.key)
    setFailure('')
    setResult(null)
    setLastRecording(null)
    setClipError(false)
    clip.current = null
    const audio = player.current
    const span = target.audio_span
    if (!audio || !span || !Number.isFinite(span.start) || !Number.isFinite(span.end)
      || span.start < 0 || span.end <= span.start) return
    clip.current = span
    startingClip.current = true
    try {
      audio.currentTime = span.start
      void audio.play().catch(() => {
        if (clip.current === span) setClipError(true)
      })
    } catch {
      setClipError(true)
    }
  }

  const submit = useCallback(async (take?: Blob) => {
    if (!goal || locked.current) return
    locked.current = true
    setWorking(true)
    setFailure('')
    const controller = new AbortController()
    request.current = controller
    try {
      const next = take ?? await stop()
      if (!active.current || controller.signal.aborted) return
      if (!next?.size) throw new Error('В повторе не оказалось звука. Проверь микрофон.')
      setLastRecording(next)
      const task = TASKS[taskId]
      setResult(await requestFocusedPractice(
        next, task.kind, feedbackPayload(task, variant), goal, controller.signal))
    } catch (e) {
      if (active.current && !controller.signal.aborted) {
        setFailure(e instanceof Error ? e.message : 'Повтор не удалось проверить.')
      }
    } finally {
      if (active.current) setWorking(false)
      locked.current = false
      if (request.current === controller) request.current = null
    }
  }, [goal, stop, taskId, variant])

  useEffect(() => {
    if (!recording) return
    const timer = setTimeout(() => void submit(), 25_000)
    return () => clearTimeout(timer)
  }, [recording, submit])

  async function startAttempt() {
    if (locked.current || recording) return
    locked.current = true
    player.current?.pause()
    setWorking(true)
    setResult(null)
    setFailure('')
    setLastRecording(null)
    await start()
    if (active.current) setWorking(false)
    locked.current = false
  }

  if (!goals.length) return null

  return (
    <section className="feedback-coach" aria-label="Отработка замечаний">
      <h3>Отработка замечаний</h3>
      <p>Выбери один фрагмент и попробуй сказать его ещё раз.</p>
      <div className="feedback-coach__goals">
        {goals.map((target) => (
          <button
            type="button"
            key={target.key}
            aria-expanded={selected === target.key}
            disabled={working || recording}
            onClick={() => select(target)}
          >
            <strong>{target.criterion}</strong>
            {target.quote && <span>{target.quote}</span>}
            {target.audio_span && hasRecording && <small>▶ Прослушать фрагмент</small>}
          </button>
        ))}
      </div>
      {goal && (
        <div className="feedback-coach__detail">
          {clipError && <p role="status">Не удалось перейти к фрагменту. Полную запись можно послушать выше.</p>}
          {goal.before && <p><strong>До повтора</strong> {goal.before}</p>}
          {goal.item != null && <p lang="en">{variant.steps?.[goal.item]}</p>}
          <p><strong>{goal.instruction}</strong></p>
          {goal.example && <p lang="en">{goal.example}</p>}
          <div className="feedback-coach__controls">
            <button type="button" disabled={working} onClick={recording ? () => void submit() : () => void startAttempt()}>
              {working ? 'Подожди…' : recording ? 'Закончить и проверить' : 'Записать короткий повтор'}
            </button>
            {failure && lastRecording && !recording && (
              <button type="button" disabled={working} onClick={() => void submit(lastRecording)}>
                Отправить запись повтора
              </button>
            )}
          </div>
          {recording && <p role="status">Идёт запись. До 25 секунд.</p>}
          {working && !recording && <p role="status">Проверяем этот фрагмент…</p>}
          {(failure || error) && <p role="alert">{failure || error}</p>}
          {result && (
            <div className="feedback-coach__result" role="status">
              <strong>После повтора · {goal.criterion}</strong>
              <p>{result.status === 'met' ? 'В этом фрагменте цель выполнена.'
                : result.status === 'try_again' ? 'Этот элемент стоит повторить ещё раз.'
                  : 'Пока не удалось уверенно проверить.'}</p>
              {result.quote && <blockquote lang="en">{result.quote}</blockquote>}
              {result.note && <p>{result.note}</p>}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
