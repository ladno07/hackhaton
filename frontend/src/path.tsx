import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  Flag,
  Medal,
  Route as RouteIcon,
  Target,
  Trophy,
} from "lucide-react";
import { api, date, levels } from "./lib";
import { useAuth, useData } from "./state";
import { Button } from "./components/ui/button";
import { FspLogo } from "./components/logo";
import {
  Badge,
  Empty,
  PageTitle,
  SearchBox,
  Stat,
  State,
  Table,
} from "./components/shared";

const applicationNames: Record<string, string> = {
  pending: "Заявка на рассмотрении",
  approved: "Заявка одобрена",
  rejected: "Заявка отклонена",
};

const stepIcons: Record<string, any> = {
  confirm: CalendarDays,
  apply: Medal,
  wait: Flag,
  compete: Target,
  none: RouteIcon,
};

// Ссылка на понятие справочника внутри кабинета.
function Term({ id, children }: any) {
  return (
    <Link className="term-link" to={`/help#${id}`} title="Открыть в справочнике">
      {children}
    </Link>
  );
}

function Ladder({ ladder, item }: any) {
  const current = ladder.indexOf(item.current_rank);
  const goals = new Set(item.goals.map((g: any) => g.rank));
  const ref = useRef<HTMLOListElement>(null);
  // На узком экране лестница прокручивается: показываем текущий разряд.
  useEffect(() => {
    const list = ref.current;
    const el = list?.children[current] as HTMLElement | undefined;
    if (list && el)
      list.scrollLeft = el.offsetLeft - list.offsetLeft - list.clientWidth / 3;
  }, [current]);
  return (
    <ol className="rank-ladder" aria-label="Лестница разрядов" ref={ref}>
      {ladder.map((name: string, i: number) => (
        <li
          key={name}
          className={
            i < current
              ? "passed"
              : i === current
                ? "current"
                : goals.has(name)
                  ? "goal"
                  : ""
          }
          aria-current={i === current ? "step" : undefined}
        >
          <i />
          <span>{name}</span>
        </li>
      ))}
    </ol>
  );
}

function NextStep({ step, athleteId, self }: any) {
  const Icon = stepIcons[step.kind] || RouteIcon;
  return (
    <div className={"next-step next-step-" + step.kind}>
      <Icon size={20} />
      <div>
        <strong>Следующий шаг</strong>
        <p>{step.text}</p>
      </div>
      {step.kind === "apply" && (
        <Button size="sm" asChild>
          <Link
            to={`/ranks?result=${step.result_id}&rank=${encodeURIComponent(step.rank)}`}
          >
            {self ? "Подать заявку" : "К заявке"} <ArrowRight size={14} />
          </Link>
        </Button>
      )}
      {step.kind === "confirm" && (
        <Button size="sm" variant="outline" asChild>
          <Link to="/competitions">
            Календарь <ArrowRight size={14} />
          </Link>
        </Button>
      )}
      {step.kind === "compete" && athleteId && (
        <Button size="sm" variant="outline" asChild>
          <Link to="/competitions">
            Подобрать старт <ArrowRight size={14} />
          </Link>
        </Button>
      )}
    </div>
  );
}

function DisciplinePath({ item, ladder, athleteId, self }: any) {
  return (
    <>
      <section className="panel section-gap">
        <div className="panel-heading">
          <div>
            <h2>
              <Trophy size={17} /> {item.name}
            </h2>
            <p>
              Занимается с {item.start_year} года ·{" "}
              {item.held ? (
                <>
                  разряд «{item.held.name}» до {date(item.held.expires_on)},
                  приказ {item.held.order_number}
                </>
              ) : (
                "разряда пока нет"
              )}
            </p>
          </div>
          {item.next_rank && (
            <Badge value="published" label={"Следующий: " + item.next_rank} />
          )}
        </div>
        <Ladder ladder={ladder} item={item} />
        <NextStep step={item.next_step} athleteId={athleteId} self={self} />
      </section>

      <div className="path-columns section-gap">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>
                <Target size={17} /> Цели по <Term id="evsk">ЕВСК</Term>
              </h2>
              <p>
                Предварительная подсказка по условиям, внесённым федерацией.
                Окончательно условия проверяются при рассмотрении заявки.
              </p>
            </div>
          </div>
          {item.goals.length ? (
            <div className="goal-list">
              {item.goals.map((g: any) => (
                <article
                  key={g.id}
                  className={"goal-card" + (g.achieved.length ? " done" : "")}
                >
                  <header>
                    <strong>Разряд «{g.rank}»</strong>
                    {g.achieved.length ? (
                      <Badge value="approved" label="Условие выполнено" />
                    ) : (
                      <Badge value="ended" label="Цель" />
                    )}
                  </header>
                  <ul>
                    <li>
                      <Term id="level">Уровень</Term>:{" "}
                      {levels[g.level] || g.level}
                    </li>
                    <li>Место не ниже {g.max_place}-го</li>
                    <li>Участников от {g.min_participants}</li>
                  </ul>
                  {g.achieved.map((a: any) => (
                    <div className="goal-result" key={a.result_id}>
                      <Link to={`/competitions/${a.competition_id}`}>
                        {a.title}
                      </Link>
                      <span>
                        {date(a.start_date)} · место {a.place} из{" "}
                        {a.participants}
                      </span>
                      {a.application && (
                        <Badge
                          value={a.application}
                          label={applicationNames[a.application]}
                        />
                      )}
                    </div>
                  ))}
                  <small>Источник: {g.source}</small>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              text="Условия для следующих разрядов не внесены"
              hint="Федерация добавляет условия ЕВСК с указанием источника. Пока можно ориентироваться на рейтинг."
            />
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>
              <RouteIcon size={17} /> Путь в дисциплине
            </h2>
          </div>
          <ol className="path-timeline">
            {[...item.timeline].reverse().map((e: any, i: number) => (
              <li key={i} className={"event-" + e.kind}>
                <time>{date(e.date)}</time>
                <div>
                  {e.competition_id ? (
                    <Link to={`/competitions/${e.competition_id}`}>
                      {e.title}
                    </Link>
                  ) : (
                    <strong>{e.title}</strong>
                  )}
                  {e.kind === "result" && <span>Место: {e.place}</span>}
                  {e.kind === "rank" && <span>Приказ {e.order_number}</span>}
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section className="panel section-gap">
        <div className="panel-heading">
          <div>
            <h2>
              <CalendarDays size={17} /> Ближайшие старты
            </h2>
            <p>Открытые соревнования дисциплины с приёмом заявок.</p>
          </div>
        </div>
        {item.upcoming.length ? (
          <Table heads={["Соревнование", "Дата", "Уровень", "Заявки до", ""]}>
            {item.upcoming.map((c: any) => (
              <tr key={c.id}>
                <td>
                  <Link to={`/competitions/${c.id}`}>
                    <strong>{c.title}</strong>
                  </Link>
                </td>
                <td>{date(c.start_date)}</td>
                <td>{levels[c.level] || c.level}</td>
                <td>{date(c.deadline)}</td>
                <td className="path-flags">
                  {c.counts_for_goal && (
                    <Badge value="published" label="Подходит для цели" />
                  )}
                  {!c.eligible && (
                    <Badge value="ended" label="Не подходит по возрасту" />
                  )}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty
            text="Открытых соревнований нет"
            hint="Календарь пополняется, загляните позже."
          />
        )}
      </section>
    </>
  );
}

export function PersonalPath() {
  const { id } = useParams();
  const { user, role } = useAuth();
  const athleteId = id || user.athlete_id;
  const self = role === "athlete";
  const query = useData(`/athletes/${athleteId}/path`, !!athleteId);
  const [active, setActive] = useState<number | null>(null);
  const data = query.data;
  const item =
    data?.disciplines.find((d: any) => d.id === active) || data?.disciplines[0];
  return (
    <>
      <PageTitle
        title={self ? "Мой путь" : "Личный путь спортсмена"}
        description={
          data
            ? [
                data.athlete.full_name,
                data.athlete.organization,
                data.athlete.training_stage,
              ]
                .filter(Boolean)
                .join(" · ")
            : "Разряды, цели по ЕВСК и следующий шаг в каждой дисциплине."
        }
      >
        <Button variant="outline" asChild>
          <Link to="/help">
            <BookOpen size={16} /> Справочник понятий
          </Link>
        </Button>
        {!self && (
          <Button variant="outline" asChild>
            <Link to={`/coaching/athletes/${athleteId}`}>
              Сводка выступлений
            </Link>
          </Button>
        )}
      </PageTitle>
      <State query={query}>
        {data && (
          <>
            <div className="stats-grid">
              <Stat
                label="Дисциплины"
                value={data.summary.disciplines}
                note="Текущие занятия"
              />
              <Stat
                label="Действующие разряды"
                value={data.summary.ranks}
                note="С неистёкшим сроком"
              />
              <Stat
                label="Можно подать заявку"
                value={data.summary.ready_to_apply}
                note="Результат подходит под условие"
              />
              <Stat
                label="Нужно подтвердить"
                value={data.summary.to_confirm}
                note="Срок разряда истекает"
              />
            </div>
            {data.disciplines.length > 1 && (
              <div
                className="navigator-chips"
                role="group"
                aria-label="Дисциплина"
              >
                {data.disciplines.map((d: any) => (
                  <button
                    key={d.id}
                    className={item?.id === d.id ? "active" : ""}
                    aria-pressed={item?.id === d.id}
                    onClick={() => setActive(d.id)}
                  >
                    {d.short_name} · {d.current_rank}
                  </button>
                ))}
              </div>
            )}
            {item ? (
              <DisciplinePath
                key={item.id}
                item={item}
                ladder={data.ladder}
                athleteId={athleteId}
                self={self}
              />
            ) : (
              <section className="panel">
                <Empty
                  text="Дисциплины не выбраны"
                  hint="Добавьте дисциплины в профиле, чтобы увидеть путь."
                />
              </section>
            )}
          </>
        )}
      </State>
    </>
  );
}

export function GlossaryContent({ base }: { base: string }) {
  const query = useQuery<any>({
    queryKey: ["public-glossary"],
    queryFn: async () => (await api.get("/public/glossary")).data,
  });
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const { hash } = useLocation();
  const data = query.data;
  // Переход по ссылке на понятие: после отрисовки, иначе макет вернёт прокрутку наверх.
  useEffect(() => {
    if (!hash || !data) return;
    const timer = setTimeout(() => {
      const el = document.getElementById(decodeURIComponent(hash.slice(1)));
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.classList.add("highlight");
      setTimeout(() => el?.classList.remove("highlight"), 1600);
    }, 50);
    return () => clearTimeout(timer);
  }, [hash, data]);
  const names: Record<string, string> = Object.fromEntries(
    (data?.terms || []).map((t: any) => [t.id, t.term]),
  );
  const needle = search.trim().toLowerCase();
  const terms = (data?.terms || []).filter(
    (t: any) =>
      (!category || t.category === category) &&
      (!needle ||
        t.term.toLowerCase().includes(needle) ||
        t.text.toLowerCase().includes(needle)),
  );
  return (
    <State query={query}>
      {data && (
        <>
          <div className="navigator-filters">
            <div className="navigator-chips" role="group" aria-label="Раздел">
              {["", ...data.categories].map((c: string) => (
                <button
                  key={c}
                  className={category === c ? "active" : ""}
                  aria-pressed={category === c}
                  onClick={() => setCategory(c)}
                >
                  {c || "Все понятия"}
                </button>
              ))}
            </div>
            <SearchBox
              value={search}
              onChange={setSearch}
              placeholder="Найти понятие"
            />
          </div>
          {terms.length ? (
            <div className="glossary-grid">
              {terms.map((t: any) => (
                <article className="panel glossary-term" id={t.id} key={t.id}>
                  <small>{t.category}</small>
                  <h3>{t.term}</h3>
                  <p>{t.text}</p>
                  {t.related.length > 0 && (
                    <div className="glossary-related">
                      См. также:{" "}
                      {t.related.map((r: string) => (
                        <Link
                          key={r}
                          to={`${base}#${r}`}
                          onClick={() => {
                            setSearch("");
                            setCategory("");
                          }}
                        >
                          {names[r]}
                        </Link>
                      ))}
                    </div>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <section className="panel">
              <Empty
                text="Понятие не найдено"
                hint="Попробуйте другое слово или раздел."
              />
            </section>
          )}

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Лестница разрядов и званий</h2>
                <p>От первого юношеского разряда до мастера спорта.</p>
              </div>
            </div>
            <ol className="rank-ladder">
              {data.ladder.map((name: string) => (
                <li key={name}>
                  <i />
                  <span>{name}</span>
                </li>
              ))}
            </ol>
          </section>

          <div className="path-columns">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Баллы рейтинга по уровням</h2>
                  <p>Действующие правила федерации за 1, 2 и 3 место.</p>
                </div>
              </div>
              <Table heads={["Уровень", "1 место", "2 место", "3 место"]}>
                {data.levels.map((l: any) => (
                  <tr key={l.id}>
                    <td>{l.name}</td>
                    {(l.points || [null, null, null]).map(
                      (p: number | null, i: number) => (
                        <td key={i}>{p ?? "—"}</td>
                      ),
                    )}
                  </tr>
                ))}
              </Table>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Условия ЕВСК на платформе</h2>
                  <p>
                    Внесены федерацией с источником. Это подсказка, а не
                    автоматическое присвоение.
                  </p>
                </div>
              </div>
              {data.evsk.length ? (
                <Table heads={["Дисциплина", "Разряд", "Условие"]}>
                  {data.evsk.map((r: any) => (
                    <tr key={r.id}>
                      <td>{r.discipline}</td>
                      <td>
                        <strong>{r.rank}</strong>
                      </td>
                      <td>
                        {r.level_name}, место не ниже {r.max_place}-го, от{" "}
                        {r.min_participants} участников
                        <small className="glossary-source">{r.source}</small>
                      </td>
                    </tr>
                  ))}
                </Table>
              ) : (
                <Empty
                  text="Условия пока не внесены"
                  hint="Федерация добавит их в разделе «Управление»."
                />
              )}
            </section>
          </div>
        </>
      )}
    </State>
  );
}

export function Help() {
  return (
    <>
      <PageTitle
        title="Справочник понятий"
        description="Простыми словами о разрядах, соревнованиях, рейтинге и документах."
      />
      <div className="glossary-page">
        <GlossaryContent base="/help" />
      </div>
    </>
  );
}

// Публичная версия справочника, доступна без входа.
export function PublicGlossary() {
  return (
    <div className="navigator-page">
      <header className="navigator-header">
        <Link to="/start" className="brand">
          <FspLogo className="brand-logo" />
        </Link>
        <div className="title-actions">
          <Link className="btn btn-ghost" to="/start">
            Навигатор
          </Link>
          <Link className="btn btn-primary" to="/login">
            Войти
          </Link>
        </div>
      </header>
      <main className="navigator-main">
        <section className="navigator-hero">
          <div className="eyebrow">СПРАВОЧНИК ПОНЯТИЙ · ФСП</div>
          <h1>Разряды, соревнования и рейтинг простыми словами</h1>
          <p>
            Для спортсменов, родителей и тренеров. Условия и баллы берутся из
            действующих правил платформы.
          </p>
        </section>
        <GlossaryContent base="/glossary" />
      </main>
    </div>
  );
}
