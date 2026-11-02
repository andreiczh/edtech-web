/** Local Vite-only visual fixtures. Not an entry point of the production build. */
import {useEffect, useState} from 'react'
import { createRoot } from 'react-dom/client'
import { TASKS, type TaskId } from '../ege2/tasks'
import type { TaskFeedback } from '../ege2/feedback'
import { ResultScreen } from '../mini/ResultScreen'
import { ResultScreen40 } from '../mini/ResultScreen40'
import { ResultScreen42 } from '../mini/ResultScreen42'
import { ResultView } from '../screens/ResultView'
import '../index.css'
import '../design/ui.css'
import '../design/theme-new.css'
import '../design/dashboard.css'
import '../design/home-v2.css'
import '../mini/mini.css'

const params = new URLSearchParams(location.search)
const id = Number(params.get('task') || 39) as TaskId
const task = TASKS[id] ?? TASKS[39]
const variant = task.variants[0]
const back = () => { location.href = '/scripts/ui-preview.html' }
const feedback: TaskFeedback = {
  score: id === 42 ? 5 : 1, max: task.maxScore,
  summary: 'Тестовый разбор интерфейса. Ответ содержит основную мысль, но некоторые пункты нужно раскрыть подробнее. Эта запись не отправлялась на оценивание.',
  accuracy_note: 'Учебный результат по распознанному тексту. Произношение и интонация требуют отдельной проверки.',
  score_status: id === 39 ? 'provisional' : undefined,
  misread_words: 1,
  errors: [{quote:'She go to school every day',correction:'She goes to school every day',explanation:'После she в Present Simple нужно окончание -s.'}],
  criteria: id === 42 ? ['Решение коммуникативной задачи','Организация высказывания','Языковое оформление'].map((name,i)=>({key:`K${i+1}`,name,score:i===0?3:1,max:i===0?4:3,comment:'Подробное пояснение критерия. Проверь, что названы преимущества и недостатки каждого способа, и поясни свой выбор.'})) : (variant.steps??[]).map((_,i)=>({key:`q${i+1}`,name:`Вопрос ${i+1}`,score:i===0?1:0,max:1,quote:'I like studying with my friends because we can help each other and discuss difficult questions.',correction:'I would prefer to study with my friends because we can help each other.',comment:'Соблюдай форму вопроса и отвечай на оба пункта.'})),
}
const failed = params.has('failure')
const common = {taskId:task.id,variant,feedback:failed?null:feedback,transcript:variant.readText || 'This is a synthetic response for visual interface testing.',failure:failed?'Сервер не завершил проверку за три минуты. Можно отправить эту же запись ещё раз.':null,blob:null,seconds:42,onQuit:back,onNext:back,onBack:back,onRetry:back}
const root = createRoot(document.getElementById('root')!)
if (!import.meta.env.DEV) throw new Error('UI fixtures are development-only')
if (!params.has('task')) root.render(<main style={{padding:32,color:'#222',background:'#fff',height:'100vh'}}><h1>UI fixtures · synthetic results</h1>{[39,40,41,42].map(n=><p key={n}><a href={`?task=${n}`}>Mobile result {n}</a> · <a href={`?task=${n}&desktop`}>Desktop result {n}</a> · <a href={`?task=${n}&failure`}>Failure {n}</a></p>)}</main>)
else if (params.has('desktop')) root.render(<div className="app" data-mode="light" style={{overflow:'auto',padding:24}}><ResultView feedback={feedback} transcript={common.transcript} taskId={task.id} variantId={variant.id} /></div>)
else root.render(<AudioFixture />)
function AudioFixture() {
  const [blob, setBlob] = useState<Blob | null>(null)
  useEffect(() => {
    let active = true
    void fetch('/docs/test-data/reading_39.mp3').then(r => r.blob()).then(b => active && setBlob(b))
    return () => { active = false }
  }, [])
  const props = {...common, blob}
  return <div className="mini">{id===42?<ResultScreen42 {...props}/>:id===40||id===41?<ResultScreen40 no={id-38} {...props}/>:<ResultScreen no={1} {...props}/>}</div>
}

