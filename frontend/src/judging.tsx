import { useState } from "react";
import { Link } from "react-router-dom";
import { useData } from "./state";
import { date, statuses, plain } from "./lib";
import { Button } from "./components/ui/button";
import {
  Badge,
  Empty,
  ExportButtons,
  Field,
  PageTitle,
  Stat,
  State,
  Table,
} from "./components/shared";

const dates = (a: any) =>
  a.start_date === a.end_date
    ? date(a.start_date)
    : `${date(a.start_date)} — ${date(a.end_date)}`;

export function Assignments() {
  const q = useData("/assignments?scope=upcoming");
  return <>
    <PageTitle title="Назначения" description="Предстоящие и текущие соревнования, на которые вас назначила федерация.">
      <Button variant="outline" asChild><Link to="/judging">Мои соревнования</Link></Button>
    </PageTitle>
    <section className="panel">
      <State query={q}>
        {q.data?.length ? <Table heads={["Соревнование", "Даты", "Дисциплина", "Место проведения", "Должность", "Статус"]}>
          {q.data.map((j: any) => <tr key={j.competition_id}>
            <td><Link to={"/competitions/" + j.competition_id}><strong>{plain(j.title)}</strong></Link></td>
            <td>{dates(j)}</td><td>{j.discipline}</td><td>{j.location}</td><td>{j.position}</td>
            <td><Badge value={j.state} /></td>
          </tr>)}
        </Table> : <Empty text="Предстоящих назначений нет" hint="Федерация назначает судей на соревнования. Прошедшие соревнования — в разделе «Мои соревнования»." />}
      </State>
    </section>
  </>;
}

export function JudgingHistory() {
  const [year, setYear] = useState("");
  const query = useData("/judging/report" + (year ? "?year=" + year : ""));
  const data = query.data;
  return <>
    <PageTitle title="Мои соревнования" description="Прошедшие соревнования, где вы работали в судейской коллегии, и отчёт о судейской деятельности.">
      <Button variant="outline" asChild><Link to="/assignments">К назначениям</Link></Button>
    </PageTitle>
    <section className="panel">
      <div className="toolbar">
        <Field label="Год">
          <select value={year} onChange={e => setYear(e.target.value)}>
            <option value="">Все годы</option>
            {data?.years.map((y: number) => <option key={y} value={y}>{y}</option>)}
          </select>
        </Field>
        <ExportButtons base={"/exports/judging" + (year ? "?year=" + year : "")} name={"judging" + (year ? "-" + year : "")} />
      </div>
    </section>
    <State query={query}>
      {data && <>
        <div className="stats-grid section-gap">
          <Stat label="Соревнования" value={data.stats.competitions} note="Работа в судейской коллегии" />
          <Stat label="Главным судьёй" value={data.stats.chief} note="Из них в должности главного судьи" />
          <Stat label="Участники" value={data.stats.participants} note="По протоколам соревнований" />
          <Stat label="Дисциплины" value={data.stats.disciplines} note="За выбранный период" />
        </div>
        <section className="panel section-gap">
          <div className="panel-heading"><h2>Отчёт · {plain(data.judge.full_name)}</h2></div>
          {data.items.length ? <Table heads={["Соревнование", "Даты", "Дисциплина", "Статус", "Должность", "Участников", "Протокол", "Документы"]}>
            {data.items.map((i: any) => <tr key={i.competition_id}>
              <td><Link to={"/competitions/" + i.competition_id}><strong>{plain(i.title)}</strong></Link><br /><small>{i.location}</small></td>
              <td>{dates(i)}</td><td>{i.discipline}</td><td>{statuses[i.status] || i.status}</td>
              <td>{i.position}</td><td>{i.participants}</td><td><Badge value={i.state} /></td>
              <td className="judging-doc-links">
                <div><small>Состав</small><ExportButtons base={"/exports/panel/" + i.competition_id} name={"panel-" + i.competition_id} formats={["pdf"]} /></div>
                {i.position === "Главный судья" && i.state === "published" && <div><small>Отчёт</small><ExportButtons base={"/exports/chief-report/" + i.competition_id} name={"chief-report-" + i.competition_id} formats={["pdf"]} /></div>}
              </td>
            </tr>)}
          </Table> : <Empty text="Прошедших соревнований нет" hint="Здесь появятся соревнования, где вы работали, после их завершения." />}
        </section>
      </>}
    </State>
  </>;
}
