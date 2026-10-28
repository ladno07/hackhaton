import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Plus, ClipboardList } from "lucide-react";
import { useAction, useAuth, useData } from "./state";
import { date, today } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import { Empty, ExportButtons, Field, PageTitle, State, Table } from "./components/shared";
import "./training.css";
import { LessonMaterials, MaterialManager } from "./training-materials";

const stages: Record<string, string> = { np: "НП", ut: "УТ", ssm: "ССМ", vsm: "ВСМ" };
const attendanceNames: Record<string, string> = { unmarked: "Не отмечено", present: "Присутствовал", absent: "Отсутствовал" };

function GroupForm({ initial, onClose }: any) {
  const meta = useData("/metadata");
  const coaches = useData("/coaches");
  const action = useAction();
  const [form, setForm] = useState<any>(initial || {
    name: "", organization_id: "", discipline_id: "", coach_id: "", stage: "np", program: "", capacity: 20,
  });
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));
  const org = meta.data?.organizations.find((o: any) => o.id === +form.organization_id);
  return <form onSubmit={async e => {
    e.preventDefault();
    const data = { name: form.name, organization_id: +form.organization_id, discipline_id: +form.discipline_id,
      coach_id: +form.coach_id, stage: form.stage, program: form.program, capacity: +form.capacity };
    try { await action.mutateAsync({ method: initial ? "put" : "post", url: "/training-groups" + (initial ? `/${initial.id}` : ""), data }); onClose(); } catch {}
  }}>
    <Field label="Название группы"><input required maxLength={160} value={form.name} onChange={e => set("name", e.target.value)} /></Field>
    <Field label="Организация"><select required value={form.organization_id} onChange={e => setForm({ ...form, organization_id: e.target.value, coach_id: "", program: "" })}>
      <option value="">Выберите организацию</option>{meta.data?.organizations.map((o: any) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select></Field>
    <Field label="Программа" hint="Программы добавляются в карточке организации в реестре.">
      <select required value={form.program} onChange={e => set("program", e.target.value)}><option value="">Выберите программу</option>
        {Array.from(new Set<string>([...(org?.programs || []), ...(initial?.program ? [initial.program] : [])])).map(p => <option key={p}>{p}</option>)}
      </select>
    </Field>
    <Field label="Дисциплина"><select required value={form.discipline_id} onChange={e => set("discipline_id", e.target.value)}>
      <option value="">Выберите дисциплину</option>{meta.data?.disciplines.map((d: any) => <option key={d.id} value={d.id}>{d.short_name}</option>)}
    </select></Field>
    <State query={coaches}><Field label="Тренер"><select required value={form.coach_id} onChange={e => set("coach_id", e.target.value)}>
      <option value="">Выберите тренера</option>{coaches.data?.filter((c: any) => !c.archived_at && c.organization_id === +form.organization_id && c.discipline_ids.includes(+form.discipline_id)).map((c: any) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
    </select></Field></State>
    <Field label="Этап подготовки"><select value={form.stage} onChange={e => set("stage", e.target.value)}>{Object.entries(stages).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
    <Field label="Количество мест"><input required type="number" min={1} max={500} value={form.capacity} onChange={e => set("capacity", e.target.value)} /></Field>
    <Button disabled={action.isPending}>Сохранить группу</Button>
  </form>;
}

function EnrollmentForm({ groupId, enrollment, groups, onClose }: any) {
  const action = useAction();
  const [form, setForm] = useState<any>({ athlete_public_id: "", start_date: today(), order_number: "", target_group_id: "" });
  const set = (key: string, value: string) => setForm({ ...form, [key]: value });
  return <form onSubmit={async e => {
    e.preventDefault();
    try {
      await action.mutateAsync(enrollment ? {
        url: `/group-enrollments/${enrollment.id}/transfer`,
        data: { target_group_id: +form.target_group_id, on: form.start_date, order_number: form.order_number },
      } : { url: `/training-groups/${groupId}/enrollments`, data: { athlete_public_id: form.athlete_public_id, start_date: form.start_date, order_number: form.order_number } });
      onClose();
    } catch {}
  }}>
    {enrollment ? <>
      <p>{enrollment.full_name} · {enrollment.public_id}</p>
      <Field label="Новая группа"><select required value={form.target_group_id} onChange={e => set("target_group_id", e.target.value)}>
        <option value="">Выберите группу</option>{groups.filter((g: any) => g.id !== groupId && !g.archived).map((g: any) => <option key={g.id} value={g.id}>{g.name} · {stages[g.stage]} · {g.organization}</option>)}
      </select></Field>
    </> : <Field label="FSP ID спортсмена"><input required maxLength={32} placeholder="FSP-000123" value={form.athlete_public_id} onChange={e => set("athlete_public_id", e.target.value)} /></Field>}
    <Field label={enrollment ? "Дата перевода" : "Дата зачисления"}><input required type="date" max={today()} value={form.start_date} onChange={e => set("start_date", e.target.value)} /></Field>
    <Field label="Номер приказа"><input required maxLength={120} value={form.order_number} onChange={e => set("order_number", e.target.value)} /></Field>
    <p className="inline-note">{enrollment ? "При смене организации история переходов обновится автоматически. Другие действующие зачисления в прежней организации нужно завершить отдельно." : "Организация спортсмена должна соответствовать группе; переход в организацию оформляется в профиле."} Этап спортсмена должен соответствовать группе. Переход на следующий этап оформляется в разделе аттестации.</p>
    <Button disabled={action.isPending}>{enrollment ? "Оформить перевод" : "Зачислить"}</Button>
  </form>;
}

function EndForm({ enrollment, onClose }: any) {
  const action = useAction();
  const [on, setOn] = useState(today());
  const [order, setOrder] = useState("");
  return <form onSubmit={async e => { e.preventDefault(); try {
    await action.mutateAsync({ url: `/group-enrollments/${enrollment.id}/end`, data: { on, order_number: order } }); onClose();
  } catch {} }}>
    <p>{enrollment.full_name}</p>
    <Field label="Последний день в группе"><input required type="date" min={enrollment.start_date} max={today()} value={on} onChange={e => setOn(e.target.value)} /></Field>
    <Field label="Номер приказа"><input required maxLength={120} value={order} onChange={e => setOrder(e.target.value)} /></Field>
    <Button disabled={action.isPending}>Завершить зачисление</Button>
  </form>;
}

function LessonForm({ groupId, initial, onClose, onCreated }: any) {
  const action = useAction();
  const [form, setForm] = useState<any>({ held_on: initial?.held_on || today(), topic: initial?.topic || "", duration_minutes: initial?.duration_minutes || 90,
    start_time: initial?.start_time?.slice(0, 5) || "18:00", timezone: initial?.timezone || "Asia/Yekaterinburg",
    format: initial?.format || "onsite", location: initial?.location || "", meeting_url: initial?.meeting_url || "", instructions: initial?.instructions || "", due_on: initial?.due_on || "" });
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));
  return <form onSubmit={async e => { e.preventDefault(); try {
    const result = await action.mutateAsync({ method: initial ? "put" : "post", url: initial ? `/training-lessons/${initial.id}` : `/training-groups/${groupId}/lessons`, data: { ...form, start_time: form.format === "correspondence" ? null : form.start_time, due_on: form.format === "correspondence" ? form.due_on || null : null, meeting_url: form.meeting_url || null } });
    if (!initial && onCreated) onCreated(result); else onClose();
  } catch {} }}>
    <Field label="Тема занятия"><input required minLength={2} maxLength={500} value={form.topic} onChange={e => set("topic", e.target.value)} /></Field>
    <div className="training-form-grid"><Field label={form.format === "correspondence" ? "Дата начала работы" : "Дата занятия"}><input required type="date" value={form.held_on} onChange={e => set("held_on", e.target.value)} /></Field>
      {form.format === "correspondence" ? <Field label="Выполнить до (включительно)"><input required type="date" min={form.held_on} value={form.due_on} onChange={e => set("due_on", e.target.value)} /></Field> : <Field label="Начало"><input required type="time" value={form.start_time} onChange={e => set("start_time", e.target.value)} /></Field>}</div>
    <Field label="Часовой пояс"><select value={form.timezone} onChange={e => set("timezone", e.target.value)}>
      <option value="Asia/Yekaterinburg">Екатеринбург / Оренбург (UTC+5)</option><option value="Europe/Moscow">Москва (UTC+3)</option><option value="Asia/Novosibirsk">Новосибирск (UTC+7)</option>
      {!["Asia/Yekaterinburg", "Europe/Moscow", "Asia/Novosibirsk"].includes(form.timezone) && <option>{form.timezone}</option>}
    </select></Field>
    <Field label={form.format === "correspondence" ? "Плановая трудоёмкость, минут" : "Продолжительность, минут"}><input required type="number" min={1} max={480} value={form.duration_minutes} onChange={e => set("duration_minutes", +e.target.value)} /></Field>
    <Field label="Формат"><select value={form.format} onChange={e => setForm({ ...form, format: e.target.value, location: ["online", "correspondence"].includes(e.target.value) ? "" : form.location, meeting_url: ["onsite", "correspondence"].includes(e.target.value) ? "" : form.meeting_url })}>
      <option value="onsite">Очно</option><option value="online">Онлайн — встреча по ссылке</option><option value="hybrid">Очно и онлайн</option><option value="correspondence">Заочно / самостоятельная работа</option>
    </select></Field>
    {["onsite", "hybrid"].includes(form.format) && <Field label="Адрес и кабинет"><input required maxLength={500} placeholder="Оренбург, ул. …, аудитория …" value={form.location} onChange={e => set("location", e.target.value)} /></Field>}
    {["online", "hybrid"].includes(form.format) && <Field label="Ссылка на онлайн-занятие" hint="Спортсмены откроют её из своей карточки занятия."><input required type="url" maxLength={2000} placeholder="https://…" value={form.meeting_url} onChange={e => set("meeting_url", e.target.value)} /></Field>}
    <Field label={form.format === "correspondence" ? "Задание для самостоятельной работы" : "Что подготовить и как пройдёт занятие"}><textarea required={form.format === "correspondence"} minLength={form.format === "correspondence" ? 3 : undefined} rows={4} maxLength={6000} placeholder={form.format === "correspondence" ? "Что изучить, какие задачи выполнить и какой результат подготовить…" : "Задачи, материалы, что взять с собой, как подключиться…"} value={form.instructions} onChange={e => set("instructions", e.target.value)} /></Field>
    <p className="inline-note">{form.format === "correspondence" ? "Спортсмен изучает задание самостоятельно до указанного срока. После создания добавьте файлы и ссылки в материалах занятия." : "Участники получат уведомление с расписанием. После окончания завершите занятие и отметьте посещаемость."}</p>
    <Button disabled={action.isPending}>{initial ? "Сохранить изменения и уведомить" : form.format === "correspondence" ? "Создать задание и добавить материалы" : "Запланировать и уведомить"}</Button>
  </form>;
}

const phaseNames: Record<string, string> = { upcoming: "Запланировано", in_progress: "Идёт сейчас", awaiting_completion: "Ожидает завершения тренером", completed: "Проведено", cancelled: "Отменено", not_started: "Заочное задание — скоро", self_study: "Самостоятельная работа", deadline_passed: "Срок выполнения истёк" };
const formats: Record<string, string> = { onsite: "Очно", online: "Онлайн", hybrid: "Очно и онлайн", correspondence: "Заочно / самостоятельная работа" };
const zoneNames: Record<string, string> = { "Asia/Yekaterinburg": "Оренбург / Екатеринбург, UTC+5", "Europe/Moscow": "Москва, UTC+3", "Asia/Novosibirsk": "Новосибирск, UTC+7" };
function lessonWhen(lesson: any) {
  if (lesson.format === "correspondence") return `С ${date(lesson.held_on)} · выполнить до ${date(lesson.due_on)} включительно (${zoneNames[lesson.timezone] || lesson.timezone})`;
  if (!lesson.starts_at) return `${date(lesson.held_on)} · время не было указано`;
  const options: Intl.DateTimeFormatOptions = { timeZone: lesson.timezone, hour: "2-digit", minute: "2-digit" };
  const start = new Date(lesson.starts_at), end = new Date(lesson.ends_at);
  return `${start.toLocaleDateString("ru-RU", { timeZone: lesson.timezone })} · ${start.toLocaleTimeString("ru-RU", options)} — ${end.toLocaleDateString("ru-RU", { timeZone: lesson.timezone }) !== start.toLocaleDateString("ru-RU", { timeZone: lesson.timezone }) ? end.toLocaleDateString("ru-RU", { timeZone: lesson.timezone }) + " " : ""}${end.toLocaleTimeString("ru-RU", options)} (${zoneNames[lesson.timezone] || lesson.timezone})`;
}

function LessonPlace({ lesson }: any) {
  return <div className="training-lesson-place">
    <p><strong>{formats[lesson.format]}</strong>{lesson.location && <> · {lesson.location}</>}</p>
    {lesson.meeting_url && lesson.status !== "cancelled" && ["upcoming", "in_progress"].includes(lesson.phase) && <Button asChild><a href={lesson.meeting_url} target="_blank" rel="noopener noreferrer">Подключиться к занятию ↗</a></Button>}
    {lesson.format !== "correspondence" && !lesson.location && !lesson.meeting_url && <p>Место проведения не было указано в старой записи журнала.</p>}
    {lesson.instructions && <div className="training-instructions"><strong>{lesson.format === "correspondence" ? "Задание для самостоятельной работы" : "Что делать и как подготовиться"}</strong><p>{lesson.instructions}</p></div>}
    <LessonMaterials materials={lesson.materials} />
    {lesson.format === "correspondence" && !lesson.materials?.length && <p className="training-muted">Файлы и ссылки пока не прикреплены. Задание описано выше.</p>}
    {lesson.cancellation_reason && <p className="training-cancelled">Причина отмены: {lesson.cancellation_reason}</p>}
  </div>;
}

function ReasonForm({ url, label, onClose }: any) {
  const [reason, setReason] = useState("");
  const action = useAction();
  return <form onSubmit={async e => { e.preventDefault(); try { await action.mutateAsync({ url, data: { reason } }); onClose(); } catch {} }}>
    <Field label="Причина"><textarea required minLength={3} maxLength={1000} rows={4} value={reason} onChange={e => setReason(e.target.value)} /></Field>
    <Button disabled={action.isPending}>{label}</Button>
  </form>;
}

function TrainingGuide({ role }: any) {
  const steps: Record<string, string[]> = {
    admin: ["Создайте организацию и укажите программы подготовки.", "Создайте группу, назначьте тренера и зачислите спортсменов по FSP ID.", "Тренер планирует занятия и ведёт посещаемость; вы контролируете историю и отчёты."],
    coach: ["Группу создаёт федерация и назначает вас тренером. Если группы нет, обратитесь в федерацию.", "Планируйте встречи с временем и местом либо заочные задания со сроком, файлами и ссылками.", "После встречи завершите занятие и отметьте посещаемость. Заочные задания закрываются отдельно."],
    athlete: ["Федерация зачисляет вас в группу. После зачисления здесь появятся расписание и тренер.", "Для встречи проверьте время и адрес/ссылку. Заочные задания изучайте самостоятельно по материалам до указанного срока.", "После очной или онлайн-встречи подтвердите отметку тренера. Для заочного задания следуйте его инструкции."],
    ministry: ["Федерация создаёт группы и оформляет зачисления.", "Тренеры планируют занятия и ведут посещаемость; спортсмены подтверждают отметки.", "Вы можете просматривать группы, расписание и отчёты без изменения данных."],
  };
  return <section className="training-guide" aria-label="Как проходят занятия">{(steps[role] || []).map((text, i) => <div key={text}><span>{i + 1}</span><p>{text}</p></div>)}</section>;
}

function TrainingAgenda({ onOpen }: any) {
  const schedule = useData("/training-schedule");
  useEffect(() => { const timer = window.setInterval(() => schedule.refetch(), 60000); return () => window.clearInterval(timer); }, [schedule.refetch]);
  return <section className="panel training-agenda section-gap">
    <div className="panel-heading"><div><h2>Ближайшие занятия</h2><p>Время указано в часовом поясе занятия. Здесь же — адрес, подключение и подготовка.</p></div></div>
    <State query={schedule}>{schedule.data?.length ? <div className="training-agenda-grid">{schedule.data.slice(0, 6).map((lesson: any) => <article className="training-agenda-card" key={lesson.id}>
      <span className={`training-phase training-phase-${lesson.phase}`}>{phaseNames[lesson.phase]}</span>
      <p className="training-when">{lessonWhen(lesson)}</p><h3>{lesson.topic}</h3><p className="training-muted">{lesson.group_name} · Тренер: {lesson.coach}</p>
      <LessonPlace lesson={lesson} />
      {lesson.phase === "awaiting_completion" && <p className="training-muted">Расписание закончилось. Тренер ещё не перенёс занятие в журнал.</p>}
      <Button variant="outline" onClick={() => onOpen(lesson.group_id)}>Открыть группу</Button>
    </article>)}</div> : <Empty text="Запланированных занятий пока нет" hint="Расписание публикует назначенный тренер или федерация. Проведённые занятия находятся в журнале группы." />}</State>
  </section>;
}

function GroupDetail({ groupId, groups }: any) {
  const { role } = useAuth();
  const detail = useData(`/training-groups/${groupId}`);
  const lessons = useData(`/training-groups/${groupId}/lessons`);
  useEffect(() => { const timer = window.setInterval(() => lessons.refetch(), 60000); return () => window.clearInterval(timer); }, [lessons.refetch]);
  const action = useAction();
  const [dialog, setDialog] = useState<any>(null);
  const group = detail.data;
  useEffect(() => { if (detail.isSuccess) document.getElementById("training-group-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [groupId, detail.isSuccess]);
  const canJournal = ["admin", "coach"].includes(role) && !group?.archived;
  const planned = (lessons.data || []).filter((l: any) => l.status === "planned");
  const completed = (lessons.data || []).filter((l: any) => l.status === "completed");
  const cancelled = (lessons.data || []).filter((l: any) => l.status === "cancelled");
  const close = () => setDialog(null);
  return <State query={detail}>{group && <>
    <section id="training-group-detail" className="panel section-gap training-detail">
      <header className="training-group-heading">
        <div><span className="training-eyebrow">Карточка группы{group.archived && " · В архиве"}</span><h2>{group.name}</h2><p>{group.organization} · {group.discipline}</p></div>
        <span className="training-stage">{stages[group.stage]}</span>
      </header>
      <dl className="training-summary">
        <div><dt>Программа подготовки</dt><dd>{group.program}</dd></div>
        <div><dt>Тренер</dt><dd>{group.coach}</dd></div>
        <div><dt>Заполненность группы</dt><dd>{group.enrolled_count} <span>из {group.capacity} мест</span></dd></div>
      </dl>
      <div className="training-actions">
        {role === "admin" && !group.archived && <>
          <Button variant="outline" onClick={() => setDialog({ kind: "edit" })}>Изменить группу</Button>
          <Button onClick={() => setDialog({ kind: "enroll" })}>Зачислить по FSP ID</Button>
          {group.enrolled_count === 0 && <Button variant="ghost" disabled={action.isPending} onClick={() => action.mutate({ url: `/training-groups/${groupId}/archive` })}>В архив</Button>}
        </>}
        <ExportButtons base={`/exports/training-groups/${groupId}`} name="training-journal" />
      </div>
      <div className="training-section-heading"><h3>Зачисления и история</h3><p>Периоды обучения и основания зачисления.</p></div>
      {group.enrollments.length ? <Table heads={["Спортсмен", "Период", "Приказ", ""]}>
        {group.enrollments.map((e: any) => <tr key={e.id}>
          <td>{e.full_name}<small>{e.public_id}</small></td>
          <td>{date(e.start_date)} — {e.end_date ? date(e.end_date) : "по настоящее время"}</td>
          <td>№ {e.order_number}{e.end_order_number && <small>Завершение: № {e.end_order_number}</small>}</td>
          <td>{role === "admin" && !e.end_date && <div className="row-actions">
            <Button size="sm" variant="outline" onClick={() => setDialog({ kind: "transfer", enrollment: e })}>Перевести</Button>
            <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "end", enrollment: e })}>Отчислить</Button>
          </div>}</td>
        </tr>)}
      </Table> : <Empty text="Спортсмены пока не зачислены" />}
    </section>
    <section className="panel section-gap training-agenda">
      <div className="panel-heading"><div><h2>Расписание и заочные задания</h2><p>Встречи с тренером и самостоятельная работа с материалами.</p></div>{canJournal && <Button onClick={() => setDialog({ kind: "lesson" })}><Plus size={16} /> Запланировать занятие</Button>}</div>
      <State query={lessons}>{planned.length ? <div className="training-agenda-grid">{[...planned].sort((a: any, b: any) => (a.starts_at || a.held_on).localeCompare(b.starts_at || b.held_on)).map((lesson: any) => <article className="training-agenda-card" key={lesson.id}>
        <span className={`training-phase training-phase-${lesson.phase}`}>{phaseNames[lesson.phase]}</span>
        <p className="training-when">{lessonWhen(lesson)}</p><h3>{lesson.topic}</h3><LessonPlace lesson={lesson} />
        {canJournal && <div className="row-actions">
          {lesson.phase === "awaiting_completion" && <Button disabled={action.isPending} onClick={() => action.mutate({ url: `/training-lessons/${lesson.id}/complete` })}>Занятие проведено — заполнить журнал</Button>}
          {lesson.format === "correspondence" && lesson.phase !== "not_started" && <Button disabled={action.isPending} onClick={() => action.mutate({ url: `/training-lessons/${lesson.id}/complete` })}>Закрыть заочное задание</Button>}
          <Button variant="outline" onClick={() => setDialog({ kind: "materials", lesson })}>Файлы и ссылки</Button>
          <Button variant="outline" onClick={() => setDialog({ kind: "lesson", lesson })}>{lesson.format === "correspondence" ? "Изменить задание / срок" : "Изменить время / место"}</Button>
          <Button variant="ghost" onClick={() => setDialog({ kind: "cancel", lesson })}>Отменить занятие</Button>
        </div>}
        {!canJournal && lesson.phase === "awaiting_completion" && <p className="training-muted">Ожидайте отметки тренера в журнале после завершения занятия.</p>}
      </article>)}</div> : <Empty text="Расписание пока не опубликовано" hint={canJournal ? "Нажмите «Запланировать занятие», укажите время и куда приходить или подключаться." : "Расписание публикует тренер этой группы. Проверьте уведомления позже."} />}</State>
      {cancelled.length > 0 && <details className="training-cancelled-list"><summary>Отменённые занятия · {cancelled.length}</summary>{cancelled.map((lesson: any) => <div key={lesson.id}><strong>{lesson.topic}</strong><p>{lessonWhen(lesson)}</p><p>Причина: {lesson.cancellation_reason}</p><LessonMaterials materials={lesson.materials} /></div>)}</details>}
    </section>
    <section className="panel section-gap training-journal">
      <div className="panel-heading"><div><h2>Журнал проведённых занятий</h2><p>После окончания тренер завершает занятие в расписании и заполняет посещаемость.</p></div></div>
      <p className="inline-note training-journal-note">Тренер отмечает посещение, спортсмен подтверждает свою отметку. Подтверждённые записи сохраняются без изменений.</p>
      <State query={lessons}>
        {completed.length ? completed.map((lesson: any) => <article className="training-lesson" key={lesson.id}>
          <header className="training-lesson-heading"><div><p>{lessonWhen(lesson)}</p><h3>{lesson.topic}</h3></div><span className="training-duration">{lesson.duration_minutes} минут</span></header>
          {(lesson.format === "correspondence" || lesson.materials?.length > 0) && <div className="training-completed-materials"><LessonPlace lesson={lesson} /></div>}
          {canJournal && <div className="training-materials-action"><Button size="sm" variant="outline" onClick={() => setDialog({ kind: "materials", lesson })}>Файлы и ссылки</Button></div>}
          {lesson.format === "correspondence" ? <p className="inline-note">Заочное задание закрыто тренером. Материалы доступны для повторения; посещаемость и часы автоматически не начисляются.</p> : <Table heads={["Спортсмен", "Посещение", "Подтверждение"]}>
            {lesson.attendance.map((a: any) => <tr key={a.id}>
              <td>{a.full_name}<small>{a.public_id}</small></td>
              <td>{canJournal && !a.confirmed_at ? <select aria-label={`Посещение: ${a.full_name}`} value={a.status} disabled={action.isPending} onChange={e => action.mutate({ method: "patch", url: `/lesson-attendance/${a.id}`, data: { status: e.target.value } })}>
                {Object.entries(attendanceNames).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
              </select> : attendanceNames[a.status]}{a.dispute_reason && <p className="training-dispute">Запрос исправления: {a.dispute_reason}</p>}</td>
              <td>{a.confirmed_at ? <>Подтверждено {date(a.confirmed_at)}</> : role === "athlete" && a.status !== "unmarked" && !a.dispute_reason ? <div className="row-actions"><Button size="sm" disabled={action.isPending} onClick={() => action.mutate({ url: `/lesson-attendance/${a.id}/confirm` })}>Подтвердить отметку</Button><Button size="sm" variant="outline" onClick={() => setDialog({ kind: "dispute", attendance: a })}>Сообщить об ошибке</Button></div> : a.dispute_reason ? "Ожидается исправление тренером" : a.status === "unmarked" ? "Ожидается отметка тренера" : "Ожидается подтверждение спортсменом"}</td>
            </tr>)}
          </Table>}
        </article>) : <Empty text="Проведённых занятий пока нет" hint="После окончания тренер завершит занятие из расписания, затем отметит посещаемость." />}
      </State>
    </section>
    <Dialog open={!!dialog} onOpenChange={close} wide={dialog?.kind === "materials"} title={({ edit: "Учебная группа", enroll: "Зачисление спортсмена", transfer: "Перевод в другую группу", end: "Отчисление", lesson: dialog?.lesson ? "Изменение занятия" : "Запланировать занятие", cancel: "Отмена занятия", dispute: "Запрос исправления посещаемости", materials: "Файлы и ссылки к занятию" } as any)[dialog?.kind] || ""}>
      {dialog?.kind === "edit" && <GroupForm initial={group} onClose={close} />}
      {["enroll", "transfer"].includes(dialog?.kind) && <EnrollmentForm groupId={groupId} enrollment={dialog.enrollment} groups={groups.filter((g: any) => g.discipline_id === group.discipline_id)} onClose={close} />}
      {dialog?.kind === "end" && <EndForm enrollment={dialog.enrollment} onClose={close} />}
      {dialog?.kind === "lesson" && <LessonForm groupId={groupId} initial={dialog.lesson} onClose={close} onCreated={(lesson: any) => lesson.format === "correspondence" ? setDialog({ kind: "materials", lesson }) : close()} />}
      {dialog?.kind === "materials" && <MaterialManager lesson={dialog.lesson} />}
      {dialog?.kind === "cancel" && <ReasonForm url={`/training-lessons/${dialog.lesson.id}/cancel`} label="Отменить и уведомить участников" onClose={close} />}
      {dialog?.kind === "dispute" && <ReasonForm url={`/lesson-attendance/${dialog.attendance.id}/dispute`} label="Отправить тренеру" onClose={close} />}
    </Dialog>
  </>}</State>;
}

export function Training() {
  const { role } = useAuth();
  const groups = useData("/training-groups");
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = Number(searchParams.get("group")) || null;
  const setSelected = (id: number) => setSearchParams({ group: String(id) });
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  return <div className="training-page">
    <PageTitle title={role === "athlete" ? "Мои группы и занятия" : "Группы и занятия"} description="Расписание тренировок, подключение к занятиям и посещаемость.">
      {role === "admin" && <><Button variant="outline" asChild><Link to="/registry?tab=organizations">Организации</Link></Button><Button onClick={() => setCreating(true)}><Plus size={16} /> Создать группу</Button></>}
    </PageTitle>
    <TrainingGuide role={role} />
    <TrainingAgenda onOpen={setSelected} />
    <section className="panel section-gap">
      <div className="panel-heading"><div><h2>{role === "athlete" ? "Мои учебные группы" : "Учебные группы"}</h2><p>{role === "coach" ? "Здесь только группы, в которых федерация назначила вас тренером." : "Откройте группу, чтобы увидеть расписание и журнал."}</p></div></div>
      <div className="training-search"><Field label="Поиск группы"><input value={search} placeholder="Группа, организация или дисциплина" onChange={e => setSearch(e.target.value)} /></Field></div>
      <State query={groups}>
        {groups.data?.length ? <Table heads={["Группа", "Организация", "Дисциплина / этап", "Тренер", "Состав", ""]}>
          {groups.data.filter((g: any) => `${g.name} ${g.organization} ${g.discipline}`.toLowerCase().includes(search.toLowerCase())).map((g: any) => <tr key={g.id}>
            <td><strong>{g.name}</strong>{g.archived && <small>В архиве</small>}</td><td>{g.organization}</td><td>{g.discipline} · {stages[g.stage]}</td><td>{g.coach}</td><td>{g.enrolled_count} / {g.capacity}</td>
            <td><Button size="sm" variant={selected === g.id ? "default" : "outline"} onClick={() => setSelected(g.id)}><ClipboardList size={15} /> Открыть</Button></td>
          </tr>)}
        </Table> : <Empty text="Учебных групп пока нет" hint={role === "admin" ? "Реестр → Организации: добавьте программу. Затем создайте группу и зачислите спортсменов." : role === "coach" ? "Группы создаёт федерация. Обратитесь к ней, чтобы вас назначили тренером группы." : "Группы появятся после зачисления федерацией. Сообщите федерации свой FSP ID из профиля."} />}
      </State>
    </section>
    {selected && <GroupDetail key={selected} groupId={selected} groups={groups.data || []} />}
    <Dialog open={creating} onOpenChange={setCreating} title="Создать учебную группу">{creating && <GroupForm onClose={() => setCreating(false)} />}</Dialog>
  </div>;
}
