import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Download,
  FileText,
  Gavel,
  List,
  MapPin,
  Plus,
  Send,
  Settings2,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { useAction, useAuth, useData } from "./state";
import { date, formats, levels, today } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import {
  Badge,
  Empty,
  ExportButtons,
  Field,
  PageTitle,
  SearchBox,
  State,
  Table,
} from "./components/shared";
export function CompetitionForm({ initial, onSaved }: any) {
  const meta = useData("/metadata");
  const action = useAction();
  const [v, setV] = useState<any>(
    initial
      ? Object.fromEntries(
          [
            "title",
            "discipline_id",
            "type_id",
            "start_date",
            "end_date",
            "deadline",
            "location",
            "format",
            "level",
            "min_age",
            "max_age",
            "calendar_plan",
            "calendar_number",
            "regulation_url",
          ].map((k) => [k, initial[k]]),
        )
      : {
          title: "",
          discipline_id: 1,
          type_id: 1,
          start_date: today(),
          end_date: today(),
          deadline: today(),
          location: "Оренбург",
          format: "onsite",
          level: "regional",
          min_age: 0,
          max_age: 100,
          calendar_plan: "Оренбургская область",
          calendar_number: "",
          regulation_url: null,
        },
  );
  const set = (k: string, val: any) => setV({ ...v, [k]: val });
  const field = (k: string, label: string, type = "text", props: any = {}) => (
    <Field label={label}>
      <input
        required
        type={type}
        value={v[k] ?? ""}
        onChange={(e) =>
          set(k, type === "number" ? +e.target.value : e.target.value)
        }
        {...props}
      />
    </Field>
  );
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: initial ? "put" : "post",
            url: "/competitions" + (initial ? "/" + initial.id : ""),
            data: { ...v, regulation_url: v.regulation_url || null },
          });
          onSaved();
        } catch {}
      }}
    >
      {field("title", "Название соревнования")}
      <div className="form-grid">
        <Field label="Дисциплина">
          <select
            value={v.discipline_id}
            onChange={(e) => set("discipline_id", +e.target.value)}
          >
            {meta.data?.disciplines.map((d: any) => (
              <option value={d.id} key={d.id}>
                {d.short_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Тип соревнования">
          <select
            value={v.type_id}
            onChange={(e) => set("type_id", +e.target.value)}
          >
            {meta.data?.types.map((t: any) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="form-grid">
        {field("start_date", "Дата начала", "date")}
        {field("end_date", "Дата окончания", "date")}
      </div>
      <div className="form-grid">
        {field("deadline", "Заявки до", "date")}
        {field("location", "Место / площадка")}
      </div>
      <div className="form-grid">
        <Field label="Формат">
          <select
            value={v.format}
            onChange={(e) => set("format", e.target.value)}
          >
            {Object.entries(formats).map(([k, s]) => (
              <option value={k} key={k}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Уровень">
          <select
            value={v.level}
            onChange={(e) =>
              setV({
                ...v,
                level: e.target.value,
                calendar_plan:
                  e.target.value === "regional"
                    ? "Оренбургская область"
                    : "ЕКП",
              })
            }
          >
            {Object.entries(levels).map(([k, s]) => (
              <option value={k} key={k}>
                {s}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="form-grid">
        {field("min_age", "Минимальный возраст", "number", {
          min: 0,
          max: 100,
        })}
        {field("max_age", "Максимальный возраст", "number", {
          min: 0,
          max: 100,
        })}
      </div>
      <div className="form-grid">
        {field("calendar_plan", "Календарный план", "text", { readOnly: true })}
        {field("calendar_number", "Номер в календарном плане")}
      </div>
      <Field label="Ссылка на положение (PDF или документ)">
        <input
          type="url"
          value={v.regulation_url || ""}
          placeholder="https://…"
          onChange={(e) => set("regulation_url", e.target.value)}
        />
      </Field>
      <div className="form-footer">
        <Button disabled={action.isPending}>
          {initial ? "Сохранить" : "Создать черновик"}
        </Button>
      </div>
    </form>
  );
}
export function Competitions() {
  const { role } = useAuth();
  const [search, setSearch] = useState("");
  const [disc, setDisc] = useState("");
  const [state, setState] = useState("");
  const [eligible, setEligible] = useState(false);
  const [show, setShow] = useState(false);
  const meta = useData("/metadata");
  const query = useData(
    "/competitions?" +
      new URLSearchParams({
        q: search,
        ...(disc ? { discipline_id: disc } : {}),
        ...(state ? { state } : {}),
        eligible: String(eligible),
      }),
  );
  return (
    <>
      <PageTitle
        eyebrow="СЕЗОН / КАЛЕНДАРЬ"
        title="Соревнования"
        description="Выбирайте свой старт. Подавайте заявки. Достигайте большего."
      >
        {role === "admin" && (
          <Button onClick={() => setShow(true)}>
            <Plus size={17} />
            Создать соревнование
          </Button>
        )}
      </PageTitle>
      <div className="competition-summary">
        <span>
          <CalendarDays size={18} />
          <strong>{query.data?.length || 0}</strong> событий в календаре
        </span>
        <span>
          <i className="green-dot" /> Все шесть дисциплин спортивного
          программирования
        </span>
      </div>
      <section className="panel">
        <div className="toolbar">
          <SearchBox
            value={search}
            onChange={setSearch}
            placeholder="Поиск соревнования"
          />
          <select
            aria-label="Статус соревнования"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option value="">Все статусы</option>
            {role === "admin" && <option value="draft">Черновики</option>}
            <option value="open">Приём заявок</option>
            <option value="closed">Приём закрыт</option>
            <option value="published">Результаты</option>
          </select>
          {role === "athlete" && (
            <label className="check-line">
              <input
                type="checkbox"
                checked={eligible}
                onChange={(e) => setEligible(e.target.checked)}
              />
              Подходят по возрасту
            </label>
          )}
        </div>
        <div className="discipline-tabs">
          <button className={!disc ? "active" : ""} onClick={() => setDisc("")}>
            Все дисциплины
          </button>
          {meta.data?.disciplines.map((d: any) => (
            <button
              key={d.id}
              className={disc === String(d.id) ? "active" : ""}
              onClick={() => setDisc(String(d.id))}
            >
              {d.short_name}
            </button>
          ))}
        </div>
        <State query={query}>
          {query.data?.length ? (
            <div className="competition-list">
              {query.data.map((c: any) => (
                <Link
                  key={c.id}
                  to={"/competitions/" + c.id}
                  className="competition-card"
                >
                  <div className="competition-date">
                    <strong>{new Date(c.start_date).getDate()}</strong>
                    <span>
                      {new Date(c.start_date).toLocaleDateString("ru-RU", {
                        month: "long",
                      })}
                    </span>
                    <small>{new Date(c.start_date).getFullYear()}</small>
                  </div>
                  <div className="competition-main">
                    <div className="competition-tags">
                      <span className="discipline-label">{c.discipline}</span>
                      <span>{levels[c.level]}</span>
                    </div>
                    <h2>{c.title.replace("Демо · ", "")}</h2>
                    <div className="competition-meta">
                      <span>
                        <MapPin size={14} />
                        {c.location}
                      </span>
                      <span>
                        <Users size={14} />
                        {c.min_age}–{c.max_age} лет
                      </span>
                      <span>{formats[c.format]}</span>
                    </div>
                  </div>
                  <div className="competition-end">
                    <Badge value={c.state} />
                    <small>
                      {c.state === "open"
                        ? "До " + date(c.deadline)
                        : c.participants + " участников"}
                    </small>
                    <span className="event-open">
                      Подробнее <ArrowRight size={16} />
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <Empty text="Соревнования не найдены" />
          )}
        </State>
      </section>
      <Dialog
        open={show}
        onOpenChange={setShow}
        title="Новое соревнование"
        wide
      >
        <CompetitionForm onSaved={() => setShow(false)} />
      </Dialog>
    </>
  );
}
function ResultsEditor({ comp }: any) {
  const approved = comp.applications.filter(
    (a: any) => a.status === "approved",
  );
  const [results, setResults] = useState<any[]>(
    approved.map((a: any, i: number) => ({
      athlete_id: a.athlete_id,
      full_name: a.full_name,
      place: i + 1,
      score: 0,
    })),
  );
  const action = useAction();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate({
          url: "/competitions/" + comp.id + "/results",
          data: {
            results: results.map(({ athlete_id, place, score }) => ({
              athlete_id,
              place,
              score,
            })),
          },
        });
      }}
    >
      <div className="inline-note">
        Протокол включает всех одобренных участников. Укажите итоговые места от
        1 до {approved.length}. После публикации результаты и рейтинг обновятся
        автоматически.
      </div>
      <Table heads={["Спортсмен", "Место", "Баллы"]}>
        {results.map((r: any, i: number) => (
          <tr key={r.athlete_id}>
            <td>{r.full_name}</td>
            <td>
              <input
                aria-label={"Место: " + r.full_name}
                type="number"
                min="1"
                max={results.length}
                required
                value={r.place}
                onChange={(e) =>
                  setResults(
                    results.map((v, j) =>
                      j === i ? { ...v, place: +e.target.value } : v,
                    ),
                  )
                }
              />
            </td>
            <td>
              <input
                aria-label={"Баллы: " + r.full_name}
                type="number"
                min="0"
                step="any"
                required
                value={r.score}
                onChange={(e) =>
                  setResults(
                    results.map((v, j) =>
                      j === i ? { ...v, score: +e.target.value } : v,
                    ),
                  )
                }
              />
            </td>
          </tr>
        ))}
      </Table>
      <div className="panel-padding">
        <Button disabled={action.isPending || !results.length}>
          <Trophy size={16} />
          Опубликовать результаты и протокол
        </Button>
      </div>
    </form>
  );
}
export function CompetitionDetail() {
  const { id } = useParams();
  const { role, user } = useAuth();
  const query = useData("/competitions/" + id);
  const athletes = useData(
    "/athletes?mine=true",
    ["athlete", "coach"].includes(role),
  );
  const judges = useData("/judges", role === "admin");
  const action = useAction();
  const [tab, setTab] = useState("applications");
  const [edit, setEdit] = useState(false);
  const [athlete, setAthlete] = useState("");
  const [judge, setJudge] = useState("");
  const [position, setPosition] = useState("Главный судья");
  const comp = query.data;
  const [comments, setComments] = useState<Record<string, string>>({});
  return (
    <>
      <Link to="/competitions" className="back-link">
        <ArrowLeft size={16} />К календарю
      </Link>
      <State query={query}>
        {comp && (
          <>
            <PageTitle
              eyebrow={comp.discipline?.toUpperCase()}
              title={comp.title.replace("Демо · ", "")}
              description={`${date(comp.start_date)} — ${date(comp.end_date)} · ${comp.location}`}
            >
              <Badge value={comp.state} />
              {role === "admin" && comp.state === "draft" && (
                <>
                  <Button variant="outline" onClick={() => setEdit(true)}>
                    <Settings2 size={16} />
                    Изменить
                  </Button>
                  <Button
                    disabled={action.isPending}
                    onClick={() =>
                      action.mutate({
                        method: "patch",
                        url: "/competitions/" + id + "/state",
                        data: { state: "open" },
                      })
                    }
                  >
                    Открыть приём заявок
                  </Button>
                </>
              )}
              {role === "admin" && comp.state === "open" && (
                <Button
                  variant="outline"
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({
                      method: "patch",
                      url: "/competitions/" + id + "/state",
                      data: { state: "closed" },
                    })
                  }
                >
                  Закрыть приём заявок
                </Button>
              )}
              {role === "admin" && comp.state === "closed" && (
                <Button
                  variant="outline"
                  onClick={() =>
                    action.mutate({
                      method: "patch",
                      url: "/competitions/" + id + "/state",
                      data: { state: "open" },
                    })
                  }
                >
                  Возобновить приём
                </Button>
              )}
            </PageTitle>
            <div className="event-details-grid">
              <div className="panel event-info">
                <div>
                  <span>Формат</span>
                  <strong>{formats[comp.format]}</strong>
                </div>
                <div>
                  <span>Уровень</span>
                  <strong>{levels[comp.level]}</strong>
                </div>
                <div>
                  <span>Возраст на дату старта</span>
                  <strong>
                    {comp.min_age}–{comp.max_age} лет
                  </strong>
                </div>
                <div>
                  <span>Приём заявок до</span>
                  <strong>{date(comp.deadline)}</strong>
                </div>
                <div>
                  <span>Календарный план</span>
                  <strong>
                    {comp.calendar_plan} № {comp.calendar_number}
                  </strong>
                </div>
                <div>
                  <span>Положение</span>
                  {comp.regulation_url ? (
                    <a
                      href={comp.regulation_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-link"
                    >
                      Открыть документ <ArrowRight size={14} />
                    </a>
                  ) : (
                    <strong>Не прикреплено</strong>
                  )}
                </div>
              </div>
              {["athlete", "coach"].includes(role) && (
                <form
                  className="panel apply-panel"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    try {
                      await action.mutateAsync({
                        url: "/competitions/" + id + "/applications",
                        data: {
                          athlete_id:
                            role === "athlete" ? user.athlete_id : +athlete,
                        },
                      });
                    } catch {}
                  }}
                >
                  <span className="eyebrow">ВАШ СЛЕДУЮЩИЙ СТАРТ</span>
                  <h2>Участвовать в соревновании</h2>
                  <p>
                    Федерация рассмотрит заявку и сообщит решение в личном
                    кабинете.
                  </p>
                  {role === "coach" && (
                    <Field label="Спортсмен">
                      <select
                        required
                        value={athlete}
                        onChange={(e) => setAthlete(e.target.value)}
                      >
                        <option value="">Выберите подопечного</option>
                        {athletes.data?.map((a: any) => (
                          <option key={a.id} value={a.id}>
                            {a.full_name}
                          </option>
                        ))}
                      </select>
                    </Field>
                  )}
                  <Button
                    disabled={
                      action.isPending ||
                      comp.state !== "open" ||
                      comp.eligible === false ||
                      comp.deadline < today() ||
                      (role === "athlete" &&
                        comp.applications.some(
                          (a: any) => a.athlete_id === user.athlete_id,
                        ))
                    }
                  >
                    <Send size={16} />
                    {comp.applications.some(
                      (a: any) => a.athlete_id === user.athlete_id,
                    )
                      ? "Заявка уже подана"
                      : comp.eligible === false
                        ? "Не подходит по возрасту"
                        : comp.state === "open"
                          ? "Подать заявку"
                          : "Приём завершён"}
                  </Button>
                </form>
              )}
            </div>
            <section className="panel section-gap">
              <div className="tabs">
                {[
                  [
                    "applications",
                    role === "admin" ? "Заявки участников" : "Мои заявки",
                  ],
                  ["results", "Результаты и протокол"],
                  ["judges", "Судейская коллегия"],
                ].map(([k, v]) => (
                  <button
                    className={tab === k ? "active" : ""}
                    key={k}
                    onClick={() => setTab(k)}
                  >
                    {v}
                  </button>
                ))}
              </div>
              {tab === "applications" &&
                (comp.applications.length ? (
                  <Table
                    heads={["Спортсмен", "Дата заявки", "Статус", "Решение"]}
                  >
                    {comp.applications.map((a: any) => (
                      <tr key={a.id}>
                        <td>
                          <strong>{a.full_name}</strong>
                        </td>
                        <td>{date(a.created_at)}</td>
                        <td>
                          <Badge value={a.status} />
                          <small>{a.comment}</small>
                        </td>
                        <td>
                          {role === "admin" &&
                          a.status === "pending" &&
                          comp.state !== "published" ? (
                            <div className="moderation-actions">
                              <input
                                aria-label={"Комментарий для " + a.full_name}
                                placeholder="Комментарий к решению"
                                value={comments[a.id] || ""}
                                onChange={(e) =>
                                  setComments({
                                    ...comments,
                                    [a.id]: e.target.value,
                                  })
                                }
                              />
                              <div className="row-actions">
                                <Button
                                  size="sm"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    action.mutate({
                                      method: "patch",
                                      url: "/applications/" + a.id,
                                      data: {
                                        status: "approved",
                                        comment: comments[a.id] || "",
                                      },
                                    })
                                  }
                                >
                                  <Check size={14} />
                                  Одобрить
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    action.mutate({
                                      method: "patch",
                                      url: "/applications/" + a.id,
                                      data: {
                                        status: "rejected",
                                        comment: comments[a.id] || "",
                                      },
                                    })
                                  }
                                >
                                  <X size={14} />
                                  Отклонить
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <span>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <Empty
                    text="Заявок пока нет"
                    hint="Поданные заявки появятся здесь."
                  />
                ))}
              {tab === "results" &&
                (comp.state === "published" ? (
                  <>
                    <div className="panel-heading">
                      <h2>Итоговый протокол</h2>
                      <ExportButtons
                        base={"/exports/protocol/" + id}
                        name={"protocol-" + id}
                      />
                    </div>
                    <Table heads={["Место", "Спортсмен", "Баллы"]}>
                      {comp.results.map((r: any) => (
                        <tr key={r.id}>
                          <td>
                            <span
                              className={r.place <= 3 ? "place-medal" : "place"}
                            >
                              {r.place}
                            </span>
                          </td>
                          <td>{r.full_name}</td>
                          <td>{r.score}</td>
                        </tr>
                      ))}
                    </Table>
                  </>
                ) : role === "admin" && comp.state === "closed" ? (
                  <ResultsEditor
                    key={comp.applications
                      .map((a: any) => a.id + a.status)
                      .join(",")}
                    comp={comp}
                  />
                ) : (
                  <Empty
                    text="Протокол ещё не опубликован"
                    hint={
                      role === "admin"
                        ? "Закройте приём заявок, чтобы внести результаты."
                        : "Результаты появятся после завершения соревнования."
                    }
                  />
                ))}
              {tab === "judges" && (
                <>
                  {role === "admin" && comp.state !== "published" && (
                    <form
                      className="inline-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        action.mutate({
                          url: "/competitions/" + id + "/judges",
                          data: { judge_id: +judge, position },
                        });
                      }}
                    >
                      <Field label="Судья">
                        <select
                          required
                          value={judge}
                          onChange={(e) => setJudge(e.target.value)}
                        >
                          <option value="">Выберите судью</option>
                          {judges.data?.map((j: any) => (
                            <option value={j.id} key={j.id}>
                              {j.full_name}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Судейская должность">
                        <input
                          required
                          value={position}
                          onChange={(e) => setPosition(e.target.value)}
                        />
                      </Field>
                      <Button disabled={action.isPending}>Назначить</Button>
                    </form>
                  )}
                  {comp.judges.length ? (
                    <Table heads={["Судья", "Должность"]}>
                      {comp.judges.map((j: any) => (
                        <tr key={j.judge_id}>
                          <td>{j.full_name}</td>
                          <td>{j.position}</td>
                        </tr>
                      ))}
                    </Table>
                  ) : (
                    <Empty text="Коллегия ещё не назначена" />
                  )}
                </>
              )}
            </section>
            <Dialog
              open={edit}
              onOpenChange={setEdit}
              title="Редактировать соревнование"
              wide
            >
              <CompetitionForm initial={comp} onSaved={() => setEdit(false)} />
            </Dialog>
          </>
        )}
      </State>
    </>
  );
}
