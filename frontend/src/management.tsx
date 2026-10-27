import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Download,
  FileCheck2,
  FileText,
  Plus,
  Settings2,
  ShieldAlert,
  Trophy,
  Users,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAction, useAuth, useData } from "./state";
import {
  ageRange,
  ageRules,
  date,
  levels,
  ranks,
  roleNames,
  sexNames,
  today,
} from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import {
  Badge,
  Empty,
  ExportButtons,
  Field,
  PageTitle,
  SearchBox,
  Stat,
  State,
  Table,
} from "./components/shared";
import { ProfileEditor } from "./pages";

export function Registry() {
  const { role } = useAuth();
  const [tab, setTab] = useState("athletes");
  const [search, setSearch] = useState("");
  const [disc, setDisc] = useState("");
  const [org, setOrg] = useState("");
  const [rank, setRank] = useState("");
  const [municipality, setMunicipality] = useState("");
  const [maxAge, setMaxAge] = useState("100");
  const [editing, setEditing] = useState<any>(null);
  const [orgEdit, setOrgEdit] = useState<any>(null);
  const [suspension, setSuspension] = useState<any>(null);
  const meta = useData("/metadata");
  const ath = useData(
    "/athletes?" +
      new URLSearchParams({
        q: search,
        ...(disc ? { discipline_id: disc } : {}),
        ...(org ? { organization_id: org } : {}),
        rank,
        municipality,
        max_age: maxAge,
      }),
  );
  const coaches = useData("/coaches");
  const judges = useData("/judges");
  const action = useAction();
  return (
    <>
      <PageTitle
        title="Единый реестр"
        description="Спортсмены, тренеры, судьи и организации региона."
      >
        {role === "admin" && tab === "organizations" && (
          <Button
            onClick={() =>
              setOrgEdit({ name: "", kind: "Клуб", municipality: "Оренбург" })
            }
          >
            <Plus size={16} />
            Добавить организацию
          </Button>
        )}
      </PageTitle>
      <section className="panel">
        <div className="tabs">
          {[
            ["athletes", "Спортсмены"],
            ["coaches", "Тренеры"],
            ["judges", "Судьи"],
            ["organizations", "Организации"],
          ].map(([k, t]) => (
            <button
              className={tab === k ? "active" : ""}
              key={k}
              onClick={() => setTab(k)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="toolbar">
          <SearchBox value={search} onChange={setSearch} />
          {tab === "athletes" && (
            <>
              <select
                aria-label="Дисциплина"
                value={disc}
                onChange={(e) => setDisc(e.target.value)}
              >
                <option value="">Все дисциплины</option>
                {meta.data?.disciplines.map((d: any) => (
                  <option key={d.id} value={d.id}>
                    {d.short_name}
                  </option>
                ))}
              </select>
              <select
                aria-label="Организация"
                value={org}
                onChange={(e) => setOrg(e.target.value)}
              >
                <option value="">Все организации</option>
                {meta.data?.organizations.map((o: any) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
        {tab === "athletes" && (
          <div className="toolbar secondary-toolbar">
            <input
              aria-label="Муниципалитет"
              placeholder="Муниципалитет"
              value={municipality}
              onChange={(e) => setMunicipality(e.target.value)}
            />
            <select
              aria-label="Разряд"
              value={rank}
              onChange={(e) => setRank(e.target.value)}
            >
              <option value="">Все разряды</option>
              {ranks.slice(1).map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
            <label className="inline-age">
              Возраст до{" "}
              <input
                aria-label="Максимальный возраст"
                type="number"
                min="0"
                max="100"
                value={maxAge}
                onChange={(e) => setMaxAge(e.target.value)}
              />
            </label>
          </div>
        )}
        {tab === "athletes" && (
          <State query={ath}>
            {ath.data?.length ? (
              <Table
                heads={[
                  "Спортсмен",
                  "Организация / муниципалитет",
                  "Дисциплины",
                  "Разряд",
                  "Действия",
                ]}
              >
                {ath.data.map((a: any) => (
                  <tr key={a.id}>
                    <td>
                      <div className="person-cell">
                        <span className="avatar avatar-soft">
                          {a.full_name.replace("Демо · ", "").slice(0, 1)}
                        </span>
                        <div>
                          <strong>{a.full_name.replace("Демо · ", "")}</strong>
                          <small>
                            {a.age} лет · ID {a.id}
                          </small>
                        </div>
                      </div>
                    </td>
                    <td>
                      {a.organization}
                      <small>{a.municipality}</small>
                    </td>
                    <td>
                      <div className="tag-stack">
                        {a.disciplines.map((d: any) => (
                          <span key={d.discipline_id} className="tag">
                            {
                              meta.data?.disciplines.find(
                                (x: any) => x.id === d.discipline_id,
                              )?.short_name
                            }
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      {a.ranks
                        ?.filter((r: any) => r.expires_on >= today())
                        .map((r: any) => (
                          <span key={r.id} className="tag rank-tag">
                            {r.name}
                          </span>
                        )) || "—"}
                      {a.suspended_until && a.suspended_until >= today() && (
                        <Badge value="rejected" label="Отстранён" />
                      )}
                    </td>
                    <td>
                      {role === "admin" ? (
                        <div className="row-actions">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditing(a)}
                          >
                            Профиль
                          </Button>
                          <button
                            className="icon-btn"
                            aria-label={"Отстранение: " + a.full_name}
                            onClick={() => setSuspension(a)}
                          >
                            <ShieldAlert size={16} />
                          </button>
                        </div>
                      ) : (
                        <span>Подайте запрос в разделе связей</span>
                      )}
                    </td>
                  </tr>
                ))}
              </Table>
            ) : (
              <Empty />
            )}
          </State>
        )}
        {tab === "coaches" && (
          <State query={coaches}>
            {coaches.data?.length ? (
              <Table heads={["Тренер", "Организация"]}>
                {coaches.data
                  .filter((c: any) =>
                    c.full_name.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((c: any) => (
                    <tr key={c.id}>
                      <td>
                        <strong>{c.full_name}</strong>
                      </td>
                      <td>
                        {meta.data?.organizations.find(
                          (o: any) => o.id === c.organization_id,
                        )?.name || "Без организации"}
                      </td>
                    </tr>
                  ))}
              </Table>
            ) : (
              <Empty />
            )}
          </State>
        )}
        {tab === "judges" && (
          <State query={judges}>
            <Table heads={["Судья", "Категория", "Срок действия"]}>
              {judges.data
                ?.filter((j: any) =>
                  j.full_name.toLowerCase().includes(search.toLowerCase()),
                )
                .map((j: any) => (
                  <tr key={j.id}>
                    <td>
                      <strong>{j.full_name}</strong>
                    </td>
                    <td>
                      {j.categories.map((c: any) => (
                        <small key={c.id}>{c.name}</small>
                      ))}
                    </td>
                    <td>
                      {j.categories.map((c: any) => (
                        <small key={c.id}>{date(c.expires_on)}</small>
                      ))}
                    </td>
                  </tr>
                ))}
            </Table>
          </State>
        )}
        {tab === "organizations" && (
          <State query={meta}>
            <Table heads={["Организация", "Тип", "Муниципалитет", ""]}>
              {meta.data?.organizations
                .filter((o: any) =>
                  o.name.toLowerCase().includes(search.toLowerCase()),
                )
                .map((o: any) => (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.name}</strong>
                    </td>
                    <td>{o.kind}</td>
                    <td>{o.municipality}</td>
                    <td>
                      {role === "admin" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setOrgEdit(o)}
                        >
                          Изменить
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
            </Table>
          </State>
        )}
      </section>
      <Dialog
        open={!!editing}
        onOpenChange={() => setEditing(null)}
        title="Профиль спортсмена"
        wide
      >
        {editing && (
          <ProfileEditor athlete={editing} onSaved={() => setEditing(null)} />
        )}
      </Dialog>
      <Dialog
        open={!!orgEdit}
        onOpenChange={() => setOrgEdit(null)}
        title="Организация"
      >
        {orgEdit && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const { id, ...data } = orgEdit;
              try {
                await action.mutateAsync({
                  method: id ? "put" : "post",
                  url: "/organizations" + (id ? "/" + id : ""),
                  data,
                });
                setOrgEdit(null);
              } catch {}
            }}
          >
            {[
              ["name", "Название"],
              ["kind", "Тип"],
              ["municipality", "Муниципалитет"],
            ].map(([k, l]) => (
              <Field key={k} label={l}>
                <input
                  required
                  value={orgEdit[k]}
                  onChange={(e) =>
                    setOrgEdit({ ...orgEdit, [k]: e.target.value })
                  }
                />
              </Field>
            ))}
            <Button disabled={action.isPending}>Сохранить</Button>
          </form>
        )}
      </Dialog>
      <Dialog
        open={!!suspension}
        onOpenChange={() => setSuspension(null)}
        title="Отстранение спортсмена"
      >
        {suspension && (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await action.mutateAsync({
                  method: "put",
                  url: "/athletes/" + suspension.id + "/suspension",
                  data: {
                    suspended_until: suspension.suspended_until || null,
                    reason: suspension.suspension_reason || "",
                  },
                });
                setSuspension(null);
              } catch {}
            }}
          >
            <p className="inline-note">
              Действующее отстранение исключает спортсмена из рейтинга и
              запрещает подачу заявок. Пустая дата снимает ограничение.
            </p>
            <Field label="Действует до">
              <input
                type="date"
                value={suspension.suspended_until || ""}
                onChange={(e) =>
                  setSuspension({
                    ...suspension,
                    suspended_until: e.target.value,
                  })
                }
              />
            </Field>
            <Field label="Основание">
              <textarea
                required
                minLength={3}
                value={suspension.suspension_reason || ""}
                onChange={(e) =>
                  setSuspension({
                    ...suspension,
                    suspension_reason: e.target.value,
                  })
                }
              />
            </Field>
            <Button disabled={action.isPending}>Сохранить</Button>
          </form>
        )}
      </Dialog>
    </>
  );
}

function RankRequest({ onDone }: any) {
  const { role } = useAuth();
  const results = useData("/results", role !== "judge");
  const action = useAction();
  const [result, setResult] = useState("");
  const [name, setName] = useState(
    role === "judge" ? "Судья третьей категории" : "III",
  );
  const [kind, setKind] = useState("assignment");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const r = results.data?.find((r: any) => r.id === +result);
        try {
          await action.mutateAsync({
            url: "/rank-applications",
            data:
              role === "judge"
                ? { name, kind }
                : { name, kind, result_id: +result, athlete_id: r?.athlete_id },
          });
          onDone();
        } catch {}
      }}
    >
      {role !== "judge" && (
        <Field label="Основание: результат соревнования">
          <select
            required
            value={result}
            onChange={(e) => setResult(e.target.value)}
          >
            <option value="">Выберите опубликованный результат</option>
            {results.data?.map((r: any) => (
              <option key={r.id} value={r.id}>
                {r.full_name} · {r.title} · место {r.place}
              </option>
            ))}
          </select>
        </Field>
      )}
      <Field
        label={
          role === "judge" ? "Судейская категория" : "Запрашиваемый разряд"
        }
      >
        {role === "judge" ? (
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {[
              "Юный спортивный судья",
              "Судья третьей категории",
              "Судья второй категории",
              "Судья первой категории",
              "Всероссийская категория",
            ].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        ) : (
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {ranks.slice(1).map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Цель заявки">
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="assignment">Присвоение</option>
          <option value="confirmation">Подтверждение</option>
        </select>
      </Field>
      <p className="inline-note">
        Спортсмен с действующей связью с тренером обращается за разрядом через
        тренера по соответствующей дисциплине.
      </p>
      <Button disabled={action.isPending}>Подать заявку</Button>
    </form>
  );
}
function RankReview({ application, onDone }: any) {
  const action = useAction();
  const [v, setV] = useState({
    status: "approved",
    assigned_on: today(),
    expires_on: "",
    order_number: "",
    comment: "",
  });
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: "patch",
            url: "/rank-applications/" + application.id,
            data: {
              ...v,
              assigned_on: v.status === "approved" ? v.assigned_on : null,
              expires_on: v.status === "approved" ? v.expires_on : null,
              order_number: v.order_number || null,
            },
          });
          onDone();
        } catch {}
      }}
    >
      <p>
        {application.full_name} · <strong>{application.name}</strong>
      </p>
      <Field label="Решение">
        <select
          value={v.status}
          onChange={(e) => setV({ ...v, status: e.target.value })}
        >
          <option value="approved">Одобрить</option>
          <option value="rejected">Отклонить</option>
        </select>
      </Field>
      {v.status === "approved" && (
        <>
          <div className="form-grid">
            <Field label="Дата присвоения">
              <input
                required
                type="date"
                value={v.assigned_on}
                onChange={(e) => setV({ ...v, assigned_on: e.target.value })}
              />
            </Field>
            <Field label="Действует до">
              <input
                required
                type="date"
                value={v.expires_on}
                onChange={(e) => setV({ ...v, expires_on: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Номер приказа">
            <input
              required
              value={v.order_number}
              onChange={(e) => setV({ ...v, order_number: e.target.value })}
            />
          </Field>
        </>
      )}
      <Field label="Обоснование решения">
        <textarea
          value={v.comment}
          onChange={(e) => setV({ ...v, comment: e.target.value })}
        />
      </Field>
      <Button disabled={action.isPending}>Сохранить решение</Button>
    </form>
  );
}
export function Ranks() {
  const { role } = useAuth();
  const list = useData("/rank-applications");
  const current = useData("/ranks");
  const candidates = useData("/evsk-candidates", role === "admin");
  const [show, setShow] = useState(false);
  const [review, setReview] = useState<any>(null);
  return (
    <>
      <PageTitle
        title="Разряды и судейские категории"
        description="Заявки, основания присвоения и контроль сроков действия."
      >
        {role !== "admin" && (
          <Button onClick={() => setShow(true)}>
            <Plus size={16} />
            Подать заявку
          </Button>
        )}
      </PageTitle>
      <section className="panel">
        <div className="panel-heading">
          <h2>Действующие и архивные квалификации</h2>
        </div>
        <State query={current}>
          {current.data?.sports.length + current.data?.categories.length > 0 ? (
            <Table
              heads={[
                "Спортсмен / судья",
                "Разряд / категория",
                "Дата / приказ",
                "Действует до",
                "Основание",
              ]}
            >
              {[...current.data.sports, ...current.data.categories].map(
                (r: any) => (
                  <tr key={(r.athlete_id ? "a" : "j") + r.id}>
                    <td>
                      <strong>{r.full_name}</strong>
                    </td>
                    <td>{r.name}</td>
                    <td>
                      {date(r.assigned_on)}
                      <small>{r.order_number}</small>
                    </td>
                    <td>
                      <span
                        className={r.expires_on < today() ? "text-danger" : ""}
                      >
                        {date(r.expires_on)}
                      </span>
                    </td>
                    <td>
                      {r.result_id
                        ? "Результат #" + r.result_id
                        : "Решение федерации"}
                    </td>
                  </tr>
                ),
              )}
            </Table>
          ) : (
            <Empty text="Квалификации пока не присвоены" />
          )}
        </State>
      </section>
      <section className="panel section-gap">
        <div className="panel-heading">
          <h2>Заявки на рассмотрение</h2>
        </div>
        <State query={list}>
          {list.data?.length ? (
            <Table
              heads={["Заявитель", "Квалификация", "Основание", "Статус", ""]}
            >
              {list.data.map((a: any) => (
                <tr key={a.id}>
                  <td>
                    <strong>{a.full_name}</strong>
                    <small>{date(a.created_at)}</small>
                  </td>
                  <td>
                    {a.name}
                    <small>
                      {a.kind === "confirmation"
                        ? "Подтверждение"
                        : "Присвоение"}
                    </small>
                  </td>
                  <td>
                    {a.result_id
                      ? "Результат #" + a.result_id
                      : "Судейская категория"}
                  </td>
                  <td>
                    <Badge value={a.status} />
                    <small>{a.comment}</small>
                  </td>
                  <td>
                    {role === "admin" && a.status === "pending" && (
                      <Button size="sm" onClick={() => setReview(a)}>
                        Рассмотреть
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty text="Заявок пока нет" />
          )}
        </State>
      </section>
      {role === "admin" && (
        <section className="panel section-gap">
          <div className="panel-heading">
            <div>
              <h2>Предварительные подсказки ЕВСК</h2>
              <p>
                На основе условий из раздела «Управление». Требуется проверка
                всех нормативных требований.
              </p>
            </div>
          </div>
          <State query={candidates}>
            {candidates.data?.length ? (
              <Table
                heads={["Спортсмен", "Соревнование", "Разряд", "Источник"]}
              >
                {candidates.data.map((c: any, i: number) => (
                  <tr key={i}>
                    <td>{c.full_name}</td>
                    <td>{c.competition}</td>
                    <td>{c.rank}</td>
                    <td>{c.source}</td>
                  </tr>
                ))}
              </Table>
            ) : (
              <Empty
                text="Нет настроенных совпадений"
                hint="Добавьте подтверждённые условия подсветки. Нормативы ЕВСК в PDF не приведены."
              />
            )}
          </State>
        </section>
      )}
      <Dialog open={show} onOpenChange={setShow} title="Заявка на квалификацию">
        <RankRequest onDone={() => setShow(false)} />
      </Dialog>
      <Dialog
        open={!!review}
        onOpenChange={() => setReview(null)}
        title="Рассмотрение заявки"
      >
        {review && (
          <RankReview application={review} onDone={() => setReview(null)} />
        )}
      </Dialog>
    </>
  );
}

export function Ratings() {
  const { role } = useAuth();
  const meta = useData("/metadata");
  const [season, setSeason] = useState(new Date().getFullYear());
  const [disc, setDisc] = useState("1");
  const [maxAge, setMaxAge] = useState("100");
  const [minAge, setMinAge] = useState("0");
  const [minRank, setMinRank] = useState("");
  const query = useData(
    "/ratings?" +
      new URLSearchParams({
        season: String(season),
        discipline_id: disc,
        min_age: minAge,
        max_age: maxAge,
        ...(minRank ? { min_rank: minRank } : {}),
      }),
  );
  const team = useData("/team?season=" + season + "&discipline_id=" + disc);
  const [selected, setSelected] = useState<number[]>([]);
  const action = useAction();
  useEffect(() => {
    setSelected((team.data || []).map((t: any) => t.athlete_id));
  }, [team.data]);
  return (
    <>
      <PageTitle
        title="Рейтинг и сборная региона"
        description="Баллы за сезон по каждой дисциплине. Прозрачный расчёт на основе протоколов."
      />
      <div className="rating-explainer">
        <Trophy size={22} />
        <p>
          <strong>Каждый результат имеет значение.</strong> Баллы за призовые
          места суммируются. Два и более призовых результата за сезон дают
          коэффициент ×1,2. Действующее отстранение исключает спортсмена.
        </p>
      </div>
      <section className="panel">
        <div className="toolbar">
          <Field label="Сезон">
            <input
              type="number"
              min="2000"
              max="2100"
              value={season}
              onChange={(e) => setSeason(+e.target.value)}
            />
          </Field>
          <Field label="Дисциплина">
            <select value={disc} onChange={(e) => setDisc(e.target.value)}>
              {meta.data?.disciplines.map((d: any) => (
                <option value={d.id} key={d.id}>
                  {d.short_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Возраст от">
            <input
              type="number"
              min="0"
              max="100"
              value={minAge}
              onChange={(e) => setMinAge(e.target.value)}
            />
          </Field>
          <Field label="До">
            <input
              type="number"
              min="0"
              max="100"
              value={maxAge}
              onChange={(e) => setMaxAge(e.target.value)}
            />
          </Field>
          <Field label="Минимальный разряд">
            <select
              value={minRank}
              onChange={(e) => setMinRank(e.target.value)}
            >
              <option value="">Без ограничений</option>
              {ranks.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </Field>
        </div>
        <State query={query}>
          {query.data?.length ? (
            <Table
              heads={[
                "Позиция",
                "Спортсмен",
                "Разряд",
                "Коэффициент",
                "Рейтинг",
                role === "admin" ? "В сборную" : "Сборная",
              ]}
            >
              {query.data.map((r: any, i: number) => (
                <tr key={r.athlete_id}>
                  <td>
                    <span className={i < 3 ? "place-medal" : "place"}>
                      {i + 1}
                    </span>
                  </td>
                  <td>
                    <strong>{r.full_name.replace("Демо · ", "")}</strong>
                    <small>{r.age} лет</small>
                    <details>
                      <summary>Как рассчитан рейтинг</summary>
                      {r.breakdown.map((b: any) => (
                        <small key={b.competition_id}>
                          {b.title}: место {b.place} → {b.points} баллов
                        </small>
                      ))}
                      <small>
                        Сумма × {r.coefficient} = {r.points}
                      </small>
                    </details>
                  </td>
                  <td>{r.rank}</td>
                  <td>
                    <span className={r.coefficient > 1 ? "coefficient" : ""}>
                      ×{r.coefficient}
                    </span>
                  </td>
                  <td>
                    <strong className="rating-points">{r.points}</strong>
                  </td>
                  <td>
                    {role === "admin" ? (
                      <input
                        aria-label={"Включить в сборную: " + r.full_name}
                        type="checkbox"
                        checked={selected.includes(r.athlete_id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, r.athlete_id]
                              : selected.filter((x) => x !== r.athlete_id),
                          )
                        }
                      />
                    ) : team.data?.some(
                        (t: any) => t.athlete_id === r.athlete_id,
                      ) ? (
                      <Badge value="active" label="В составе" />
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty text="За выбранный сезон результатов пока нет" />
          )}
        </State>
      </section>
      <section className="panel section-gap">
        <div className="panel-heading">
          <div>
            <h2>Сборная Оренбургской области</h2>
            <p>
              {team.data?.length || 0} спортсменов в сохранённом составе · сезон{" "}
              {season}
            </p>
          </div>
          {role === "admin" && (
            <Button
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  method: "put",
                  url: "/team",
                  data: { season, discipline_id: +disc, athlete_ids: selected },
                })
              }
            >
              <Check size={16} />
              Сохранить состав ({selected.length})
            </Button>
          )}
        </div>
        {team.data?.map((t: any) => (
          <div className="simple-row" key={t.athlete_id}>
            <span>{t.full_name}</span>
            {!t.eligible && (
              <Badge value="rejected" label="Действует отстранение" />
            )}
          </div>
        ))}
        {role === "admin" && (
          <div className="team-exports">
            <div>
              <strong>Список сборной</strong>
              <ExportButtons
                base={
                  "/exports/team?season=" + season + "&discipline_id=" + disc
                }
                name={"team-" + season}
              />
            </div>
            <div>
              <strong>Проект приказа</strong>
              <ExportButtons
                base={
                  "/exports/team?season=" +
                  season +
                  "&discipline_id=" +
                  disc +
                  "&order=true"
                }
                name={"team-order-" + season}
              />
            </div>
          </div>
        )}
      </section>
    </>
  );
}

export function Reports() {
  const year = new Date().getFullYear();
  const [start, setStart] = useState(year - 1);
  const [end, setEnd] = useState(year);
  const [disc, setDisc] = useState("");
  const [org, setOrg] = useState("");
  const [municipality, setMunicipality] = useState("");
  const [maxAge, setMaxAge] = useState("100");
  const meta = useData("/metadata");
  const params = new URLSearchParams({
    start_year: String(start),
    end_year: String(end),
    ...(disc ? { discipline_id: disc } : {}),
    ...(org ? { organization_id: org } : {}),
    municipality,
    max_age: maxAge,
  }).toString();
  const q = useData("/reports/population?" + params);
  return (
    <>
      <PageTitle
        title="Аналитика и отчёты"
        description="Численность и динамика развития спортивного программирования."
      >
        <ExportButtons
          base={"/exports/population?" + params}
          name="population"
        />
      </PageTitle>
      <section className="panel">
        <div className="toolbar">
          <Field label="С года">
            <input
              type="number"
              min="1970"
              max="2100"
              value={start}
              onChange={(e) => setStart(+e.target.value)}
            />
          </Field>
          <Field label="По год">
            <input
              type="number"
              min={start + 1}
              max="2100"
              value={end}
              onChange={(e) => setEnd(+e.target.value)}
            />
          </Field>
          <Field label="Дисциплина">
            <select value={disc} onChange={(e) => setDisc(e.target.value)}>
              <option value="">Все дисциплины</option>
              {meta.data?.disciplines.map((d: any) => (
                <option key={d.id} value={d.id}>
                  {d.short_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Организация">
            <select value={org} onChange={(e) => setOrg(e.target.value)}>
              <option value="">Все организации</option>
              {meta.data?.organizations.map((o: any) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="toolbar secondary-toolbar">
          <input
            aria-label="Муниципалитет"
            placeholder="Муниципалитет"
            value={municipality}
            onChange={(e) => setMunicipality(e.target.value)}
          />
          <label className="inline-age">
            Возраст до{" "}
            <input
              aria-label="Возраст до"
              type="number"
              min="0"
              max="100"
              value={maxAge}
              onChange={(e) => setMaxAge(e.target.value)}
            />
          </label>
        </div>
        <State query={q}>
          <div className="report-chart">
            <ResponsiveContainer height={260} width="100%">
              <BarChart data={q.data?.totals || []}>
                <CartesianGrid strokeDasharray="4 5" vertical={false} />
                <XAxis dataKey="year" axisLine={false} tickLine={false} />
                <YAxis
                  allowDecimals={false}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip />
                <Bar
                  name="Спортсменов"
                  dataKey="count"
                  fill="#bb2e40"
                  radius={[5, 5, 0, 0]}
                  maxBarSize={80}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="inline-note">{q.data?.source}</div>
          {q.data?.rows.length ? (
            <Table heads={q.data.headers}>
              {q.data.rows.map((r: any[], i: number) => (
                <tr key={i}>
                  {r.map((c: any, j: number) => (
                    <td key={j}>{c}</td>
                  ))}
                </tr>
              ))}
            </Table>
          ) : (
            <Empty text="Нет данных за выбранный период" />
          )}
        </State>
      </section>
    </>
  );
}

function UserRoles({ u }: any) {
  const action = useAction();
  const [roles, setRoles] = useState<string[]>(u.roles);
  return (
    <tr>
      <td>
        <strong>{u.full_name}</strong>
        <small>{u.email}</small>
      </td>
      <td>
        <div className="role-checkboxes">
          {Object.entries(roleNames).map(([k, n]) => (
            <label className="check-line" key={k}>
              <input
                type="checkbox"
                checked={roles.includes(k)}
                onChange={(e) =>
                  setRoles(
                    e.target.checked
                      ? [...roles, k]
                      : roles.filter((r) => r !== k),
                  )
                }
              />
              {n}
            </label>
          ))}
        </div>
      </td>
      <td>
        <Button
          size="sm"
          variant="outline"
          disabled={action.isPending || !roles.length}
          onClick={() =>
            action.mutate({
              method: "put",
              url: "/users/" + u.id + "/roles",
              data: { roles },
            })
          }
        >
          Сохранить
        </Button>
      </td>
    </tr>
  );
}
function RuleEditor({ r }: any) {
  const [v, setV] = useState(r);
  const action = useAction();
  return (
    <form
      className="rule-editor"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate({
          method: "put",
          url: "/rating-rules/" + r.level,
          data: { first: +v.first, second: +v.second, third: +v.third },
        });
      }}
    >
      <strong>{levels[r.level]}</strong>
      {["first", "second", "third"].map((k, i) => (
        <Field label={i + 1 + " место"} key={k}>
          <input
            type="number"
            required
            min="0"
            max="10000"
            value={v[k]}
            onChange={(e) => setV({ ...v, [k]: e.target.value })}
          />
        </Field>
      ))}
      <Button size="sm" variant="outline" disabled={action.isPending}>
        Сохранить
      </Button>
    </form>
  );
}
const emptyGroup = {
  name: "",
  discipline_id: null,
  sex: null,
  min_age: 14,
  max_age: 17,
  age_rule: "year",
  sort_order: 0,
};
function AgeGroups() {
  const meta = useData("/metadata");
  const action = useAction();
  const [g, setG] = useState<any>(emptyGroup);
  const [editing, setEditing] = useState<number | null>(null);
  const set = (k: string, val: any) => setG({ ...g, [k]: val });
  const disciplines = Object.fromEntries(
    (meta.data?.disciplines || []).map((d: any) => [d.id, d.short_name]),
  );
  return (
    <div className="panel-padding">
      <div className="inline-note">
        Группы по правилам вида спорта. Федерация выбирает их в карточке
        соревнования, а спортсмен видит подсказку, проходит ли он по возрасту.
        Группы по умолчанию — заготовка: сверьте границы с действующими
        правилами вида спорта. Группу, по которой уже объявлено соревнование,
        изменить нельзя — создайте новую.
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await action.mutateAsync({
              method: editing ? "put" : "post",
              url: "/age-groups" + (editing ? "/" + editing : ""),
              data: g,
            });
            setG(emptyGroup);
            setEditing(null);
          } catch {}
        }}
      >
        <div className="form-grid">
          <Field label="Название">
            <input
              required
              minLength={2}
              placeholder="Например, Юноши"
              value={g.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </Field>
          <Field label="Пол">
            <select
              value={g.sex || ""}
              onChange={(e) => set("sex", e.target.value || null)}
            >
              <option value="">Любой</option>
              {Object.entries(sexNames).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Возраст от">
            <input
              type="number"
              required
              min="0"
              max="100"
              value={g.min_age}
              onChange={(e) => set("min_age", +e.target.value)}
            />
          </Field>
          <Field label="Возраст до" hint="100 — без верхней границы">
            <input
              type="number"
              required
              min={g.min_age}
              max="100"
              value={g.max_age}
              onChange={(e) => set("max_age", +e.target.value)}
            />
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Как считать возраст">
            <select
              value={g.age_rule}
              onChange={(e) => set("age_rule", e.target.value)}
            >
              {Object.entries(ageRules).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Дисциплина">
            <select
              value={g.discipline_id || ""}
              onChange={(e) =>
                set("discipline_id", e.target.value ? +e.target.value : null)
              }
            >
              <option value="">Все дисциплины</option>
              {meta.data?.disciplines.map((d: any) => (
                <option key={d.id} value={d.id}>
                  {d.short_name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="row-actions">
          <Button disabled={action.isPending}>
            {editing ? "Сохранить группу" : "Добавить группу"}
          </Button>
          {editing && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setG(emptyGroup);
                setEditing(null);
              }}
            >
              Отмена
            </Button>
          )}
        </div>
      </form>
      <div className="section-gap">
        <State query={meta}>
          <Table
            heads={["Группа", "Пол", "Возраст", "Расчёт", "Дисциплина", ""]}
          >
            {meta.data?.age_groups.map((r: any) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.name}</strong>
                </td>
                <td>{r.sex ? sexNames[r.sex] : "Любой"}</td>
                <td>{ageRange(r.min_age, r.max_age)}</td>
                <td>{ageRules[r.age_rule]}</td>
                <td>{disciplines[r.discipline_id] || "Все"}</td>
                <td>
                  <div className="row-actions">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditing(r.id);
                        setG({
                          name: r.name,
                          discipline_id: r.discipline_id,
                          sex: r.sex,
                          min_age: r.min_age,
                          max_age: r.max_age,
                          age_rule: r.age_rule,
                          sort_order: r.sort_order,
                        });
                      }}
                    >
                      Изменить
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={action.isPending}
                      onClick={() =>
                        confirm(`Удалить группу «${r.name}»?`) &&
                        action.mutate({
                          method: "delete",
                          url: "/age-groups/" + r.id,
                        })
                      }
                    >
                      Удалить
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        </State>
      </div>
    </div>
  );
}
export function Settings() {
  const users = useData("/users");
  const rules = useData("/rating-rules");
  const meta = useData("/metadata");
  const evsk = useData("/evsk-rules");
  const action = useAction();
  const [tab, setTab] = useState("rules");
  const [type, setType] = useState("");
  const [deadline, setDeadline] = useState({
    title: "",
    due_on: today(),
    done: false,
  });
  const [ev, setEv] = useState<any>({
    discipline_id: 1,
    level: "regional",
    rank_name: "III",
    max_place: 3,
    min_participants: 10,
    source: "",
  });
  return (
    <>
      <PageTitle
        title="Управление платформой"
        description="Правила расчёта, справочники, доступ и условия подсветки ЕВСК."
      />
      <section className="panel">
        <div className="tabs">
          {[
            ["rules", "Правила рейтинга"],
            ["users", "Доступ и роли"],
            ["references", "Справочники и сроки"],
            ["age", "Возрастные группы"],
            ["evsk", "Подсказки ЕВСК"],
          ].map(([k, v]) => (
            <button
              key={k}
              className={tab === k ? "active" : ""}
              onClick={() => setTab(k)}
            >
              {v}
            </button>
          ))}
        </div>
        {tab === "rules" && (
          <div className="panel-padding">
            <p className="inline-note">
              Рейтинг пересчитывается при публикации протокола и запросе
              таблицы. Места ниже третьего дают 0 баллов. Коэффициент
              стабильности 1,2 применяется к сумме за дисциплину и сезон.
            </p>
            <State query={rules}>
              {rules.data?.map((r: any) => <RuleEditor key={r.level} r={r} />)}
            </State>
          </div>
        )}
        {tab === "users" && (
          <State query={users}>
            <Table heads={["Пользователь", "Доступные роли", ""]}>
              {users.data?.map((u: any) => <UserRoles key={u.id} u={u} />)}
            </Table>
          </State>
        )}
        {tab === "references" && (
          <div className="settings-columns">
            <div>
              <h2>Типы соревнований</h2>
              <div className="tag-stack">
                {meta.data?.types.map((t: any) => (
                  <span className="tag" key={t.id}>
                    {t.name}
                  </span>
                ))}
              </div>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await action.mutateAsync({
                      url: "/competition-types",
                      data: { name: type },
                    });
                    setType("");
                  } catch {}
                }}
              >
                <Field label="Новый тип">
                  <input
                    required
                    minLength={2}
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                  />
                </Field>
                <Button disabled={action.isPending}>Добавить тип</Button>
              </form>
            </div>
            <div>
              <h2>Срок отчётности</h2>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await action.mutateAsync({
                      url: "/deadlines",
                      data: deadline,
                    });
                    setDeadline({ ...deadline, title: "" });
                  } catch {}
                }}
              >
                <Field label="Название отчёта / задачи">
                  <input
                    required
                    minLength={3}
                    value={deadline.title}
                    onChange={(e) =>
                      setDeadline({ ...deadline, title: e.target.value })
                    }
                  />
                </Field>
                <Field label="Срок">
                  <input
                    required
                    type="date"
                    value={deadline.due_on}
                    onChange={(e) =>
                      setDeadline({ ...deadline, due_on: e.target.value })
                    }
                  />
                </Field>
                <Button disabled={action.isPending}>Добавить срок</Button>
              </form>
            </div>
          </div>
        )}
        {tab === "age" && <AgeGroups />}
        {tab === "evsk" && (
          <div className="panel-padding">
            <div className="inline-note">
              PDF не содержит таблиц ЕВСК. Условия вносит федерация с указанием
              нормативного источника. Совпадение — предварительная подсказка,
              решение о разряде принимает федерация после проверки всех
              требований.
            </div>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await action.mutateAsync({ url: "/evsk-rules", data: ev });
                  setEv({ ...ev, source: "" });
                } catch {}
              }}
            >
              <div className="form-grid">
                <Field label="Дисциплина">
                  <select
                    value={ev.discipline_id}
                    onChange={(e) =>
                      setEv({ ...ev, discipline_id: +e.target.value })
                    }
                  >
                    {meta.data?.disciplines.map((d: any) => (
                      <option value={d.id} key={d.id}>
                        {d.short_name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Уровень">
                  <select
                    value={ev.level}
                    onChange={(e) => setEv({ ...ev, level: e.target.value })}
                  >
                    {Object.entries(levels).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <div className="form-grid">
                <Field label="Разряд">
                  <select
                    value={ev.rank_name}
                    onChange={(e) =>
                      setEv({ ...ev, rank_name: e.target.value })
                    }
                  >
                    {ranks.slice(1).map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Место не ниже">
                  <input
                    type="number"
                    required
                    min="1"
                    value={ev.max_place}
                    onChange={(e) =>
                      setEv({ ...ev, max_place: +e.target.value })
                    }
                  />
                </Field>
                <Field label="Минимум участников">
                  <input
                    type="number"
                    required
                    min="1"
                    value={ev.min_participants}
                    onChange={(e) =>
                      setEv({ ...ev, min_participants: +e.target.value })
                    }
                  />
                </Field>
              </div>
              <Field label="Нормативный источник и пункт">
                <textarea
                  minLength={10}
                  required
                  value={ev.source}
                  onChange={(e) => setEv({ ...ev, source: e.target.value })}
                />
              </Field>
              <Button disabled={action.isPending}>Добавить условие</Button>
            </form>
            <div className="section-gap">
              <State query={evsk}>
                {evsk.data?.map((r: any) => (
                  <div className="simple-row" key={r.id}>
                    <span>
                      {r.rank_name} · место ≤ {r.max_place} · от{" "}
                      {r.min_participants} участников<small>{r.source}</small>
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        action.mutate({
                          method: "delete",
                          url: "/evsk-rules/" + r.id,
                        })
                      }
                    >
                      Удалить
                    </Button>
                  </div>
                ))}
              </State>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
