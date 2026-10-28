import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CoachChat } from "./coach-chat";
import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Code2,
  FileCheck2,
  Plus,
  ShieldCheck,
  Trophy,
  Users,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAction, useAuth, useData, useToast } from "./state";
import { chartColors, date, download, formats, roleNames, sexNames, today, trainingStages, plain, firstName } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import { StaffEditor, staffKinds } from "./staff";
import { TelegramConnection } from "./telegram";
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
import { PassportPanel } from "./passport-panel";
import { auditDetails, auditEntity } from "./audit-details";
import { ProfileDocuments, ProfileSportsSummary } from "./profile-documents";
import { platformNames } from "./platform-import";
const attentionGroups: [string, string, string][] = [
  ["applications", "Заявки на соревнования", "/competitions"],
  ["rank_applications", "Заявки на разряды и категории", "/ranks"],
  ["appeals", "Апелляции", "/appeals"],
  ["stage_transfers", "Готовы к переводу на этап", "/standards"],
  ["ranks", "Истекающие разряды", "/registry"],
  ["categories", "Истекающие судейские категории", "/registry"],
  ["reports", "Сроки отчётов", "/settings"],
];

function AttentionPanel() {
  const attention = useData("/dashboard/attention");
  const items: any[] = attention.data?.items || [];
  const soon = new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10);
  return (
    <section className="panel attention-panel">
      <div className="panel-heading">
        <div>
          <h2>
            <Clock3 size={18} /> Требует внимания
          </h2>
          <p>
            Решения федерации и сроки · истечение в ближайшие{" "}
            {attention.data?.window_days || 30} дней
          </p>
        </div>
        <span className="count-label">{items.length}</span>
      </div>
      <State query={attention}>
        {items.length ? (
          attentionGroups.map(([kind, label, link]) => {
            const group = items.filter((i) => i.kind === kind);
            return (
              <div className="attention-group" key={kind}>
                <div className="attention-group-title">
                  <span>{label}</span>
                  <b>{group.length}</b>
                </div>
                {group.slice(0, 3).map((i) => (
                  <Link
                    className="deadline-row"
                    key={kind + ":" + i.id}
                    to={i.link}
                  >
                    <span
                      className={
                        "deadline-dot " +
                        (i.overdue ||
                        (!["rank_applications", "stage_transfers"].includes(kind) &&
                          i.due_on <= soon)
                          ? "urgent"
                          : "")
                      }
                    />
                    <div>
                      <h3>
                        {plain(i.title)} · {i.detail}
                      </h3>
                      <p>
                        {i.overdue ? "просрочено · " : i.date_label + " "}
                        {date(i.due_on)}
                      </p>
                    </div>
                  </Link>
                ))}
                {group.length > 3 && (
                  <Link className="attention-more" to={link}>
                    Ещё {group.length - 3} <ArrowRight size={13} />
                  </Link>
                )}
              </div>
            );
          })
        ) : (
          <Empty
            text="Всё под контролем"
            hint="Нет заявок на рассмотрении и ближайших сроков."
          />
        )}
      </State>
    </section>
  );
}

export function Overview() {
  const { user, role } = useAuth();
  const stats = useData("/dashboard");
  const comps = useData("/competitions");
  const deadlines = useData("/deadlines", role !== "admin");
  const pop = useData(
    "/reports/population?start_year=" +
      (new Date().getFullYear() - 3) +
      "&end_year=" +
      new Date().getFullYear(),
    role === "admin" || role === "ministry",
  );
  const upcoming = (comps.data || [])
    .filter((c: any) => c.start_date >= today() && c.state !== "published")
    .sort((a: any, b: any) => a.start_date.localeCompare(b.start_date))
    .slice(0, 3);
  const s = stats.data;
  return (
    <>
      <PageTitle
        eyebrow={`${roleNames[role].toUpperCase()} / ЛИЧНЫЙ КАБИНЕТ`}
        title="Всё начинается с кода"
        description={`Здравствуйте, ${firstName(user.full_name)}. Вот что происходит в вашем спортивном сезоне.`}
      >
        <Link className="btn btn-outline" to="/competitions">
          <CalendarDays size={16} />
          Календарь соревнований
        </Link>
      </PageTitle>
      <div className="season-banner">
        <div className="banner-copy">
          <span className="season-pill">
            <i /> СЕЗОН {new Date().getFullYear()} ОТКРЫТ
          </span>
          <h2>
            Одна платформа.
            <br />
            Больше возможностей.
          </h2>
          <p>
            От первой заявки до сборной региона.
            <br />
            Управляйте своим спортивным будущим.
          </p>
          <Link to="/competitions">
            Найти соревнование <ArrowUpRight size={17} />
          </Link>
        </div>
        <div className="banner-art" aria-hidden="true">
          <div className="code-orbit orbit-one" />
          <div className="code-orbit orbit-two" />
          <span className="giant-code">&lt;/&gt;</span>
          <span className="art-label">CODE. COMPETE. GROW.</span>
        </div>
        <div className="banner-index">
          06{" "}
          <span>
            дисциплин.
            <br />
            одна команда.
          </span>
        </div>
      </div>
      <State query={stats}>
        <div className="stats-grid">
          <Stat
            label={
              role === "coach"
                ? "Мои спортсмены"
                : role === "athlete"
                  ? "Мои результаты"
                  : role === "judge"
                    ? "Назначения"
                    : "Спортсмены"
            }
            value={
              role === "judge"
                ? s?.assignments
                : role === "athlete"
                  ? s?.results
                  : s?.athletes
            }
            icon={Users}
            note={
              role === "admin" || role === "ministry"
                ? "в едином реестре"
                : role === "athlete"
                  ? "в опубликованных протоколах"
                  : role === "judge"
                    ? "предстоящие и текущие"
                    : "с активной связью"
            }
          />
          <Stat
            label="Соревнования"
            value={s?.competitions}
            icon={CalendarDays}
            note="в календаре федерации"
          />
          <Stat
            label={role === "judge" ? "Заявки на категорию" : "Заявки на рассмотрении"}
            value={role === "judge" ? s?.rank_applications : s?.applications}
            icon={FileCheck2}
            note={role === "admin" ? "требуют решения" : "ожидают решения федерации"}
          />
          <Stat
            label={
              role === "judge" ? "Действующие категории" : "Действующие разряды"
            }
            value={role === "judge" ? s?.categories : s?.ranks}
            icon={Trophy}
            note="по данным реестра"
          />
        </div>
      </State>
      <div className="dashboard-columns">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Ближайшие соревнования</h2>
              <p>Новые возможности для ваших побед</p>
            </div>
            <Link to="/competitions" className="text-link">
              Все <ArrowRight size={16} />
            </Link>
          </div>
          <State query={comps}>
            {upcoming.length ? (
              upcoming.map((c: any) => (
                <Link
                  className="upcoming-row"
                  key={c.id}
                  to={"/competitions/" + c.id}
                >
                  <div className="date-tile">
                    <time dateTime={c.start_date}>{date(c.start_date)}</time>
                  </div>
                  <div className="upcoming-copy">
                    <small>{c.discipline}</small>
                    <h3>{plain(c.title)}</h3>
                    <p>
                      {c.location} <i /> {formats[c.format]}
                    </p>
                  </div>
                  <ChevronRight size={18} />
                </Link>
              ))
            ) : (
              <Empty text="Ближайшие события пока не запланированы" />
            )}
          </State>
        </section>
        {role === "admin" ? (
          <AttentionPanel />
        ) : (
          <section className="panel attention-panel">
            <div className="panel-heading">
              <div>
                <h2>
                  <Clock3 size={18} /> Не пропустите
                </h2>
                <p>Сроки в вашем кабинете</p>
              </div>
              <span className="count-label">{deadlines.data?.length || 0}</span>
            </div>
            <State query={deadlines}>
              {deadlines.data?.length ? (
                deadlines.data.slice(0, 4).map((d: any, i: number) => (
                  <div className="deadline-row" key={d.kind + ":" + d.id}>
                    <span
                      className={"deadline-dot " + (i === 0 ? "urgent" : "")}
                    />
                    <div>
                      <h3>{plain(d.title)}</h3>
                      <p>{date(d.due_on)}</p>
                    </div>
                  </div>
                ))
              ) : (
                <Empty
                  text="Нет ближайших сроков"
                  hint="Уведомим, когда появится важное событие."
                />
              )}
            </State>
          </section>
        )}
      </div>
      {role === "admin" || role === "ministry" ? (
        <section className="panel growth-panel">
          <div className="panel-heading">
            <div>
              <h2>Сообщество растёт</h2>
              <p>
                Численность занимающихся · по годам начала и окончания занятий
              </p>
            </div>
            <Link to="/reports" className="text-link">
              Аналитика <ArrowRight size={16} />
            </Link>
          </div>
          <State query={pop}>
            <div className="growth-content">
              <div>
                <span className="eyebrow">СПОРТСМЕНЫ РЕГИОНА</span>
                <strong>{pop.data?.totals?.at(-1)?.count || 0}</strong>
                <p>
                  уникальных спортсменов
                  <br />в текущем году
                </p>
              </div>
              <div className="chart">
                <ResponsiveContainer width="100%" height={170}>
                  <AreaChart
                    data={pop.data?.totals || []}
                    margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient
                        id="primaryArea"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor={chartColors.primary}
                          stopOpacity={0.2}
                        />
                        <stop
                          offset="100%"
                          stopColor={chartColors.primary}
                          stopOpacity={0}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      strokeDasharray="4 5"
                      vertical={false}
                      stroke={chartColors.grid}
                    />
                    <XAxis dataKey="year" tickLine={false} axisLine={false} />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip />
                    <Area
                      dataKey="count"
                      name="Спортсменов"
                      stroke={chartColors.primary}
                      strokeWidth={3}
                      fill="url(#primaryArea)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </State>
        </section>
      ) : (
        <section className="panel quick-links">
          <div>
            <ShieldCheck size={28} />
            <h2>Следующий шаг в вашем сезоне</h2>
            <p>Проверьте профиль, результаты и сроки действия квалификации.</p>
          </div>
          {role === "athlete" && (
            <Link className="btn btn-outline" to="/coaching">
              Чаты с тренерами <ArrowRight size={16} />
            </Link>
          )}
          <Link
            className="btn btn-outline"
            to={
              role === "judge"
                ? "/assignments"
                : role === "coach"
                  ? "/coaching"
                  : "/profile"
            }
          >
            Открыть кабинет <ArrowRight size={16} />
          </Link>
        </section>
      )}
    </>
  );
}

export function History() {
  const { role } = useAuth();
  // Минспорт видит протоколы, но не персональные отчёты каждого спортсмена
  const personal = role !== "ministry";
  const q = useData("/results");
  const toast = useToast();
  const a = useData("/athletes?mine=true", personal);
  const [search, setSearch] = useState("");
  return (
    <>
      <PageTitle
        title="История выступлений"
        description="Результаты опубликованных протоколов в одном месте."
      />
      <section className="panel">
        <div className="toolbar">
          <SearchBox value={search} onChange={setSearch} />
        </div>
        <State query={q}>
          {q.data?.length ? (
            <Table
              heads={[
                "Спортсмен / соревнование",
                "Дата",
                "Место",
                "Баллы",
                "Протокол",
                ...(personal ? ["Справка об участии"] : []),
              ]}
            >
              {q.data
                .filter((r: any) =>
                  (r.full_name + r.title)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .map((r: any) => (
                  <tr key={r.id}>
                    <td>
                      <Link
                        className="text-link"
                        to={`/athletes/${r.athlete_id}/profile`}
                      >
                        <strong>{plain(r.full_name)}</strong>
                      </Link>
                      <small>{plain(r.title)}</small>
                    </td>
                    <td>{date(r.start_date)}</td>
                    <td>
                      <span className={r.place <= 3 ? "place-medal" : "place"}>
                        {r.place}
                      </span>
                    </td>
                    <td>{r.score}</td>
                    <td>
                      <ExportButtons
                        base={"/exports/protocol/" + r.competition_id}
                        name={"protocol-" + r.competition_id}
                      />
                    </td>
                    {personal && (
                    <td>
                      {r.can_download_certificate ? (
                        <div className="row-actions">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              download(
                                `/results/${r.id}/certificate.pdf`,
                                `certificate-${r.id}.pdf`,
                              ).catch(() =>
                                toast(
                                  "Не удалось скачать справку: проверьте доступ к результату",
                                  true,
                                ),
                              )
                            }
                          >
                            Скачать PDF
                          </Button>
                          <Button size="sm" variant="ghost" asChild>
                            <Link to={`/certificates/${r.id}`}>
                              Открыть справку
                            </Link>
                          </Button>
                        </div>
                      ) : (
                        <span>Недоступно по текущей связи</span>
                      )}
                    </td>
                    )}
                  </tr>
                ))}
            </Table>
          ) : (
            <Empty
              text="Выступлений пока нет"
              hint="Результаты появятся после публикации протокола."
            />
          )}
        </State>
      </section>
      {personal && (
        <section className="panel section-gap">
          <div className="panel-heading">
            <h2>Отчёт о выступлениях спортсмена</h2>
          </div>
          {a.data?.map((x: any) => (
            <div className="simple-row" key={x.id}>
              <span>{plain(x.full_name)}</span>
              <ExportButtons
                base={"/exports/athlete/" + x.id}
                name={"athlete-" + x.id}
              />
            </div>
          ))}
        </section>
      )}
    </>
  );
}

export function ProfileEditor({ athlete, onSaved }: any) {
  const { role } = useAuth();
  const meta = useData("/metadata");
  const action = useAction();
  const [v, setV] = useState<any>({
    full_name: athlete.full_name,
    sex: athlete.sex || "",
    organization_id: athlete.organization_id,
    organization_since: today(),
    municipality: athlete.municipality,
    training_stage: athlete.training_stage || "",
    rusada_date: athlete.rusada_date || null,
    rusada_certificate: athlete.rusada_certificate || null,
    disciplines: athlete.disciplines || [],
    platform_logins: athlete.platform_logins || {},
  });
  const change = (k: string, val: any) => setV({ ...v, [k]: val });
  const moved =
    (v.organization_id || null) !== (athlete.organization_id || null);
  const history = athlete.organization_history || [];
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: "put",
            url: "/athletes/" + athlete.id,
            data: {
              ...v,
              organization_since: moved ? v.organization_since : null,
              sex: v.sex || null,
              disciplines: v.disciplines.map(
                ({ discipline_id, start_year, end_year }: any) => ({
                  discipline_id,
                  start_year,
                  end_year: end_year ?? null,
                }),
              ),
              rusada_certificate: v.rusada_certificate || null,
              rusada_date: v.rusada_date || null,
              training_stage: v.training_stage || null,
            },
          });
          onSaved?.();
        } catch {}
      }}
    >
      <div className="form-grid">
        <Field label="ФИО">
          <input
            required
            minLength={3}
            value={v.full_name}
            onChange={(e) => change("full_name", e.target.value)}
          />
        </Field>
        <Field label="Дата рождения" hint="Указана при регистрации">
          <input type="date" readOnly value={athlete.birth_date || ""} />
        </Field>
        <Field label="Пол" hint="Нужен для возрастных групп соревнований">
          <select value={v.sex} onChange={(e) => change("sex", e.target.value)}>
            <option value="">Не указан</option>
            {Object.entries(sexNames).map(([k, s]) => (
              <option key={k} value={k}>
                {s}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="form-grid">
        <Field label="Муниципалитет">
          <input
            required
            value={v.municipality}
            onChange={(e) => change("municipality", e.target.value)}
          />
        </Field>
        <Field label="Организация">
          <select
            value={v.organization_id || ""}
            onChange={(e) =>
              change("organization_id", e.target.value ? +e.target.value : null)
            }
          >
            <option value="">Без организации</option>
            {meta.data?.organizations.map((o: any) => (
              <option key={o.id} value={o.id}>
                {plain(o.name)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {moved && (
        <Field
          label="Дата перехода"
          hint="С этой даты спортсмен учитывается в новой организации"
        >
          <input
            type="date"
            required
            max={today()}
            value={v.organization_since}
            onChange={(e) => change("organization_since", e.target.value)}
          />
        </Field>
      )}
      {history.length > 0 && (
        <div className="form-section">
          <h3>История организаций</h3>
          {history.map((p: any) => (
            <div className="simple-row" key={p.id}>
              <span>{plain(p.organization)}</span>
              <small>
                {date(p.start_date)} —{" "}
                {p.end_date ? date(p.end_date) : "по н. в."}
              </small>
            </div>
          ))}
        </div>
      )}
      <Field
        label="Этап подготовки"
        hint={
          role === "admin"
            ? "Перевод по нормативам оформляется в разделе «Нормативы и аттестация»"
            : "Меняет федерация по результатам аттестации"
        }
      >
        <select
          disabled={role !== "admin"}
          value={v.training_stage}
          onChange={(e) => change("training_stage", e.target.value)}
        >
          <option value="">Не указан</option>
          {[
            ...trainingStages,
            ...(v.training_stage && !trainingStages.includes(v.training_stage)
              ? [v.training_stage]
              : []),
          ].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>
      <div className="form-section">
        <h3>Дисциплины и годы занятий</h3>
        {meta.data?.disciplines.map((d: any) => {
          const entry = v.disciplines.find(
            (x: any) => x.discipline_id === d.id,
          );
          return (
            <div key={d.id} className="enrollment-row">
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={!!entry}
                  onChange={(e) =>
                    change(
                      "disciplines",
                      e.target.checked
                        ? [
                            ...v.disciplines,
                            {
                              discipline_id: d.id,
                              start_year: new Date().getFullYear(),
                              end_year: null,
                            },
                          ]
                        : v.disciplines.filter(
                            (x: any) => x.discipline_id !== d.id,
                          ),
                    )
                  }
                />
                {d.short_name}
              </label>
              {entry && (
                <>
                  <input
                    aria-label={"Год начала: " + d.short_name}
                    type="number"
                    min="1970"
                    max={new Date().getFullYear()}
                    value={entry.start_year}
                    onChange={(e) =>
                      change(
                        "disciplines",
                        v.disciplines.map((x: any) =>
                          x === entry
                            ? { ...x, start_year: +e.target.value }
                            : x,
                        ),
                      )
                    }
                  />
                  <input
                    aria-label={"Год окончания: " + d.short_name}
                    type="number"
                    placeholder="Занимается"
                    value={entry.end_year || ""}
                    min={entry.start_year}
                    onChange={(e) =>
                      change(
                        "disciplines",
                        v.disciplines.map((x: any) =>
                          x === entry
                            ? {
                                ...x,
                                end_year: e.target.value
                                  ? +e.target.value
                                  : null,
                              }
                            : x,
                        ),
                      )
                    }
                  />
                </>
              )}
            </div>
          );
        })}
      </div>
      <div className="form-section">
        <h3>Логины на платформах</h3>
        <p className="inline-note">
          По ним результаты контестов подтягиваются в протокол соревнования.
        </p>
        <div className="form-grid">
          {Object.entries(platformNames).map(([k, n]) => (
            <Field label={n} key={k}>
              <input
                maxLength={100}
                autoComplete="off"
                value={v.platform_logins[k] || ""}
                onChange={(e) =>
                  change("platform_logins", {
                    ...v.platform_logins,
                    [k]: e.target.value,
                  })
                }
              />
            </Field>
          ))}
        </div>
      </div>
      <div className="form-grid">
        <Field label="Дата прохождения РУСАДА">
          <input
            type="date"
            value={v.rusada_date || ""}
            onChange={(e) => change("rusada_date", e.target.value)}
          />
        </Field>
        <Field label="Ссылка на сертификат">
          <input
            type="url"
            placeholder="https://…"
            value={v.rusada_certificate || ""}
            onChange={(e) => change("rusada_certificate", e.target.value)}
          />
        </Field>
      </div>
      <div className="form-footer">
        <Button disabled={action.isPending}>Сохранить профиль</Button>
      </div>
    </form>
  );
}
function StaffProfile({ kind, id }: any) {
  const q = useData(staffKinds[kind].url + "/" + id);
  return (
    <>
      <PageTitle
        title="Мой профиль"
        description={`Карточка ${staffKinds[kind].title}: контакты, организация и дисциплины.`}
      />
      <section className="panel form-panel">
        <State query={q}>
          {q.data?.archived_at && (
            <p className="inline-note">
              Карточка в архиве с {date(q.data.archived_at)}:{" "}
              {q.data.archive_reason}. Изменения недоступны — обратитесь в
              федерацию.
            </p>
          )}
          {q.data && (
            <StaffEditor
              key={q.data.id}
              kind={kind}
              card={q.data}
              disabled={!!q.data.archived_at}
            />
          )}
        </State>
      </section>
    </>
  );
}

export function Profile() {
  const { user, role } = useAuth();
  if (role === "coach" || role === "judge")
    return <StaffProfile kind={role} id={user[role + "_id"]} />;
  if (role === "admin" || role === "ministry")
    return (
      <>
        <PageTitle title="Мой профиль" description="Данные вашей учётной записи и документы." />
        <div className="profile-layout">
          <section className="panel form-panel">
            <Field label="ФИО"><input readOnly value={user.full_name} /></Field>
            <Field label="Электронная почта"><input readOnly value={user.email} /></Field>
            <Field label="Дата рождения"><input readOnly type="date" value={user.birth_date || ""} /></Field>
            <Field label="Активный кабинет"><input readOnly value={roleNames[role]} /></Field>
            <Field label="Доступные роли"><input readOnly value={user.roles.map((r: string) => roleNames[r] || r).join(", ")} /></Field>
          </section>
          <aside><ProfileDocuments user={user} /></aside>
        </div>
      </>
    );
  return <AthleteProfile user={user} />;
}

function AthleteProfile({ user }: any) {
  const toast = useToast();
  const q = useData("/athletes/" + user.athlete_id);
  return (
    <>
      <PageTitle
        title="Мой профиль"
        description="Спортивная информация, дисциплины и документы."
      />
      <div className="profile-layout">
        <section className="panel form-panel">
          <State query={q}>
            {q.data && <ProfileEditor key={q.data.id} athlete={q.data} />}
          </State>
        </section>
        <aside>
          <PassportPanel user={user} />
          {q.data && <ProfileSportsSummary athlete={q.data} />}
          <section className="panel info-card section-gap">
            <h2>Мой ID спортсмена</h2>
            <p>
              Передайте ID капитану, чтобы он пригласил именно вас в команду.
            </p>
            <Field label="Публичный ID спортсмена">
              <input
                readOnly
                value={q.data?.public_id || user.athlete_public_id || ""}
                onFocus={(e) => e.currentTarget.select()}
              />
            </Field>
            <Button
              size="sm"
              variant="outline"
              disabled={!q.data?.public_id}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(q.data.public_id);
                  toast("ID скопирован");
                } catch {
                  toast("Выделите ID и скопируйте его через Ctrl+C", true);
                }
              }}
            >
              Скопировать ID
            </Button>
          </section>
          <ProfileDocuments user={user} />
          <section className="panel info-card section-gap">
            <h2>Чистый спорт</h2>
            <p>Информация об антидопинговом образовании и прохождении курса.</p>
            <a
              className="text-link"
              href="https://rusada.ru"
              target="_blank"
              rel="noreferrer"
            >
              Официальный сайт РУСАДА <ArrowUpRight size={15} />
            </a>
          </section>
        </aside>
      </div>
    </>
  );
}

export function Coaching() {
  const { role } = useAuth();
  const [search, setSearch] = useSearchParams();
  const chatId = Number(search.get("chat"));
  const q = useData("/links");
  const athletes = useData("/athletes", role === "coach");
  const meta = useData("/metadata");
  const [show, setShow] = useState(false);
  const [athlete, setAthlete] = useState("");
  const [discipline, setDiscipline] = useState("1");
  const action = useAction();
  return (
    <>
      <PageTitle
        title={role === "coach" ? "Связь со спортсменами" : "Связи с тренерами"}
        description={role === "athlete"
          ? "Подтвердите заявку тренера — первым действием в строке появится чат с ним."
          : "Привязка действует только после подтверждения спортсменом. История изменений сохраняется."}
      >
        {role === "coach" && (
          <Button onClick={() => setShow(true)}>
            <Plus size={16} />
            Пригласить спортсмена
          </Button>
        )}
      </PageTitle>
      <section className="panel">
        <State query={q}>
          {q.data?.length ? (
            <Table
              heads={["Спортсмен", "Тренер / дисциплина", "Статус", "Действия"]}
            >
              {q.data.map((l: any) => (
                <tr key={l.id}>
                  <td>
                    <Link
                      className="text-link"
                      to={`/athletes/${l.athlete_id}/profile`}
                    >
                      <strong>{plain(l.athlete)}</strong>
                    </Link>
                    <small>{l.athlete_public_id}</small>
                    <details>
                      <summary>История связи</summary>
                      {l.history.map((h: any) => (
                        <small key={h.id}>
                          {date(h.at)} · {h.status}
                        </small>
                      ))}
                    </details>
                  </td>
                  <td>
                    {l.coach}
                    <small>
                      {
                        meta.data?.disciplines.find(
                          (d: any) => d.id === l.discipline_id,
                        )?.short_name
                      }
                    </small>
                  </td>
                  <td>
                    <Badge value={l.status} />
                  </td>
                  <td>
                    <div className="row-actions">
                      {["athlete", "coach"].includes(role) && l.status === "active" && (
                        <Button size="sm" variant="outline" onClick={() => setSearch({ chat: String(l.id) })}>
                          Чат
                        </Button>
                      )}
                      {["coach", "admin"].includes(role) &&
                        l.status === "active" && (
                          <Button size="sm" variant="outline" asChild>
                            <Link to={`/coaching/athletes/${l.athlete_id}`}>
                              Сводка выступлений
                            </Link>
                          </Button>
                        )}
                      {["coach", "admin"].includes(role) &&
                        l.status === "active" && (
                          <Button size="sm" variant="outline" asChild>
                            <Link to={`/path/${l.athlete_id}`}>Личный путь</Link>
                          </Button>
                        )}
                      {role === "athlete" &&
                        ["pending", "paused"].includes(l.status) && (
                          <Button
                            size="sm"
                            disabled={action.isPending}
                            onClick={() =>
                              action.mutate({
                                method: "patch",
                                url: "/links/" + l.id,
                                data: { status: "active" },
                              }, { onSuccess: () => setSearch({ chat: String(l.id) }) })
                            }
                          >
                            Подтвердить
                          </Button>
                        )}
                      {l.status === "active" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            action.mutate({
                              method: "patch",
                              url: "/links/" + l.id,
                              data: { status: "paused" },
                            })
                          }
                        >
                          Приостановить
                        </Button>
                      )}
                      {l.status !== "ended" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            action.mutate({
                              method: "patch",
                              url: "/links/" + l.id,
                              data: { status: "ended" },
                            })
                          }
                        >
                          Завершить
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty
              text={role === "athlete" ? "Связей с тренерами пока нет" : "Связей со спортсменами пока нет"}
              hint="Тренер отправляет запрос; спортсмен подтверждает его в своём кабинете."
            />
          )}
        </State>
      </section>
      {chatId > 0 && ["athlete", "coach"].includes(role) && (
        <CoachChat key={`${role}-${chatId}`} linkId={chatId} onClose={() => setSearch({})} />
      )}
      <Dialog open={show} onOpenChange={setShow} title="Запрос на привязку">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await action.mutateAsync({
                url: "/links",
                data: { athlete_id: +athlete, discipline_id: +discipline },
              });
              setShow(false);
            } catch {}
          }}
        >
          <Field label="Спортсмен">
            <select
              required
              value={athlete}
              onChange={(e) => setAthlete(e.target.value)}
            >
              <option value="">Выберите спортсмена</option>
              {athletes.data?.map((a: any) => (
                <option key={a.id} value={a.id}>
                  {plain(a.full_name)} · {a.municipality}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Дисциплина">
            <select
              value={discipline}
              onChange={(e) => setDiscipline(e.target.value)}
            >
              {meta.data?.disciplines.map((d: any) => (
                <option value={d.id} key={d.id}>
                  {d.short_name}
                </option>
              ))}
            </select>
          </Field>
          <Button disabled={action.isPending}>Отправить запрос</Button>
        </form>
      </Dialog>
    </>
  );
}
export function Notifications() {
  const { role } = useAuth();
  const q = useData("/notifications");
  const action = useAction();
  return (
    <>
      <PageTitle
        title="Уведомления"
        description={role === "ministry"
          ? "События платформы и напоминания. Доставка на почту."
          : "События платформы и напоминания. Доставка на почту и в подключённый Telegram."}
      />
      {role !== "ministry" && <TelegramConnection />}
      <section className="panel">
        <State query={q}>
          {q.data?.length ? (
            q.data.map((n: any) => (
              <div
                className={"notice-row " + (!n.read_at ? "unread" : "")}
                key={n.id}
              >
                <div className="notice-icon">
                  <Bell size={18} />
                </div>
                <div>
                  <h3>{plain(n.title)}</h3>
                  <p>{n.body}</p>
                  {n.event_key.startsWith("competition-team:") && (
                    <Link
                      className="text-link"
                      to={`/competitions/${n.event_key.split(":")[1]}?tab=teams`}
                    >
                      Открыть команду
                    </Link>
                  )}
                  <small>
                    <time dateTime={n.created_at}>
                      {new Date(n.created_at).toLocaleString("ru-RU", {
                        day: "2-digit", month: "2-digit", year: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </time>
                  </small>
                </div>
                {!n.read_at && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      action.mutate({
                        method: "patch",
                        url: "/notifications/" + n.id + "/read",
                      })
                    }
                  >
                    <Check size={16} />
                    Прочитано
                  </Button>
                )}
              </div>
            ))
          ) : (
            <Empty text="Новых уведомлений пока нет" />
          )}
        </State>
      </section>
    </>
  );
}
export function Deadlines() {
  const query = useData("/deadlines");
  return <>
    <PageTitle title="Мои сроки" description="Соревнования, разряды, категории и отчётность в пределах вашего кабинета." />
    <section className="panel panel-padding"><State query={query}>
      {query.data?.length ? <Table heads={["Событие", "Срок", "Подробнее"]}>
        {query.data.map((item: any) => <tr key={`${item.kind}:${item.id}`}>
          <td>{plain(item.title)}</td><td>{date(item.due_on)}</td>
          <td><Link to={item.kind === "competition" ? `/competitions/${item.id}` : ["rank", "category"].includes(item.kind) ? "/ranks" : "/settings"}>Открыть</Link></td>
        </tr>)}
      </Table> : <Empty text="Предстоящих сроков пока нет" />}
    </State></section>
  </>;
}
export function Audit() {
  const q = useData("/audit");
  const [search, setSearch] = useState("");
  return (
    <>
      <PageTitle
        title="Журнал действий"
        description="Кто, когда и что изменил в платформе. Последние 500 событий."
      />
      <section className="panel">
        <div className="toolbar">
          <SearchBox value={search} onChange={setSearch} />
        </div>
        <State query={q}>
          {q.data?.length ? (
            <Table
              heads={["Время", "Пользователь", "Роль", "Действие", "Детали"]}
            >
              {q.data
                .filter((x: any) =>
                  (x.action + x.full_name)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .map((x: any) => (
                  <tr key={x.id}>
                    <td>{date(x.created_at)} {new Date(x.created_at).toLocaleTimeString("ru-RU")}</td>
                    <td>{plain(x.full_name)}</td>
                    <td>{roleNames[x.active_role]}</td>
                    <td>
                      <strong>{x.action}</strong>
                      <small>
                        {auditEntity(x.entity, x.entity_id)}
                      </small>
                    </td>
                    <td>
                      {auditDetails(x.details).length ? (
                        <dl className="audit-detail">
                          {auditDetails(x.details).map(([label, value]) => (
                            <div key={label}>
                              <dt>{label}:</dt>
                              <dd>{value}</dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <span className="muted">Нет дополнительных сведений</span>
                      )}
                    </td>
                  </tr>
                ))}
            </Table>
          ) : (
            <Empty />
          )}
        </State>
      </section>
    </>
  );
}
