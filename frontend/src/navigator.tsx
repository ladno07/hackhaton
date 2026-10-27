import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Building2, CalendarDays, MapPin, Users } from "lucide-react";
import { api, date, formats } from "./lib";
import { FspLogo } from "./components/logo";
import { Badge, Empty, State } from "./components/shared";

const steps = [
  ["Выберите дисциплину", "Шесть направлений: от алгоритмов до дронов."],
  ["Найдите, где заниматься", "Клубы и школы вашего муниципалитета с тренерами."],
  ["Зарегистрируйтесь", "До 18 лет понадобится согласие законного представителя."],
  ["Подайте заявку", "Выберите соревнование по возрасту и дисциплине."],
];

// 1 место, 2 места, 5 мест
const plural = (n: number, one: string, few: string, many: string) =>
  n % 10 === 1 && n % 100 !== 11
    ? one
    : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)
      ? few
      : many;

// Публичная страница без входа: только агрегаты и опубликованные события.
export function Navigator() {
  const query = useQuery<any>({
    queryKey: ["public-navigator"],
    queryFn: async () => (await api.get("/public/navigator")).data,
  });
  const [discipline, setDiscipline] = useState(0);
  const [municipality, setMunicipality] = useState("");
  const data = query.data;
  const names: Record<number, string> = Object.fromEntries(
    (data?.disciplines || []).map((d: any) => [d.id, d.short_name]),
  );
  const places = (data?.places || []).filter(
    (p: any) =>
      (!discipline || p.discipline_ids.includes(discipline)) &&
      (!municipality || p.municipality === municipality),
  );
  const events = (data?.competitions || []).filter(
    (c: any) => !discipline || c.discipline_id === discipline,
  );
  return (
    <div className="navigator-page">
      <header className="navigator-header">
        <Link to="/start" className="brand">
          <FspLogo className="brand-logo" />
        </Link>
        <div className="title-actions">
          <Link className="btn btn-ghost" to="/glossary">
            Справочник
          </Link>
          <Link className="btn btn-ghost" to="/login">
            Войти
          </Link>
          <Link className="btn btn-primary" to="/login?register=1">
            Регистрация
          </Link>
        </div>
      </header>
      <main className="navigator-main">
        <section className="navigator-hero">
          <div className="eyebrow">НАВИГАТОР ДЛЯ НОВИЧКА · ОРЕНБУРГСКАЯ ОБЛАСТЬ</div>
          <h1>С чего начать в спортивном программировании</h1>
          <p>
            Выберите дисциплину, найдите клуб рядом с домом и приходите на
            первые соревнования. Вход не нужен.
          </p>
          <ol className="navigator-steps">
            {steps.map(([title, text], i) => (
              <li key={title}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                <strong>{title}</strong>
                <p>{text}</p>
              </li>
            ))}
          </ol>
        </section>
        <State query={query}>
          <div className="navigator-filters">
            <div className="navigator-chips" role="group" aria-label="Дисциплина">
              {[{ id: 0, short_name: "Все дисциплины" }, ...(data?.disciplines || [])].map(
                (d: any) => (
                  <button
                    key={d.id}
                    className={discipline === d.id ? "active" : ""}
                    aria-pressed={discipline === d.id}
                    onClick={() => setDiscipline(d.id)}
                  >
                    {d.short_name}
                  </button>
                ),
              )}
            </div>
            <select
              aria-label="Муниципалитет"
              value={municipality}
              onChange={(e) => setMunicipality(e.target.value)}
            >
              <option value="">Все муниципалитеты</option>
              {(data?.municipalities || []).map((m: string) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </div>
          <section>
            <h2 className="navigator-title">Дисциплины</h2>
            <div className="navigator-grid">
              {(data?.disciplines || []).map((d: any) => (
                <button
                  key={d.id}
                  className={
                    "panel navigator-card discipline-card" +
                    (discipline === d.id ? " active" : "")
                  }
                  onClick={() => setDiscipline(discipline === d.id ? 0 : d.id)}
                >
                  <strong>{d.short_name}</strong>
                  <p>{d.about}</p>
                  <span>
                    {d.organizations}{" "}
                    {plural(d.organizations, "место", "места", "мест")} для
                    занятий · {d.upcoming}{" "}
                    {plural(d.upcoming, "соревнование", "соревнования", "соревнований")}{" "}
                    впереди
                  </span>
                </button>
              ))}
            </div>
          </section>
          <section>
            <h2 className="navigator-title">
              Где заниматься <small>{places.length}</small>
            </h2>
            {places.length ? (
              <div className="navigator-grid">
                {places.map((p: any) => (
                  <div className="panel navigator-card" key={p.id}>
                    <strong>
                      <Building2 size={16} /> {p.name.replace("Демо · ", "")}
                    </strong>
                    <p>
                      <MapPin size={13} /> {p.municipality} · {p.kind}
                    </p>
                    <div className="navigator-tags">
                      {p.discipline_ids.map((id: number) => (
                        <Badge key={id} value="published" label={names[id]} />
                      ))}
                    </div>
                    <span>
                      <Users size={13} />
                      {p.coaches > 0 && `Тренеров: ${p.coaches} · `}
                      Занимаются: {p.athletes}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                text="Пока нет мест для занятий"
                hint="Попробуйте другую дисциплину или муниципалитет."
              />
            )}
          </section>
          <section>
            <h2 className="navigator-title">
              Ближайшие соревнования <small>{events.length}</small>
            </h2>
            {events.length ? (
              <div className="panel">
                {events.map((c: any) => (
                  <div className="navigator-event" key={c.id}>
                    <div className="date-tile">
                      <strong>{new Date(c.start_date).getDate()}</strong>
                      <span>
                        {new Date(c.start_date).toLocaleDateString("ru-RU", {
                          month: "short",
                        })}
                      </span>
                    </div>
                    <div>
                      <h3>{c.title.replace("Демо · ", "")}</h3>
                      <p>
                        {names[c.discipline_id]} · {c.location} ·{" "}
                        {formats[c.format]} ·{" "}
                        {c.min_age > 0 || c.max_age < 100
                          ? `возраст ${c.min_age}–${c.max_age}`
                          : "без ограничений по возрасту"}
                      </p>
                    </div>
                    {c.registration_open ? (
                      <Badge value="open" label={"Заявки до " + date(c.deadline)} />
                    ) : (
                      <Badge value="ended" label="Приём заявок закрыт" />
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                text="Ближайших соревнований нет"
                hint="Календарь пополняется, загляните позже."
              />
            )}
          </section>
          <section className="navigator-cta panel">
            <div>
              <h2>
                <CalendarDays size={18} /> Готовы к первому старту?
              </h2>
              <p>
                Создайте аккаунт спортсмена: заявки подаются из личного кабинета.
              </p>
            </div>
            <Link className="btn btn-primary" to="/login?register=1">
              Зарегистрироваться <ArrowRight size={16} />
            </Link>
          </section>
        </State>
      </main>
    </div>
  );
}
