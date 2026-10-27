import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useData } from "./state";
import { date } from "./lib";
import { Button } from "./components/ui/button";
import { Empty, Field, PageTitle, Stat, State, Table } from "./components/shared";

export function AthleteSummary() {
  const { id } = useParams();
  const [year, setYear] = useState("");
  const [discipline, setDiscipline] = useState("");
  const params = new URLSearchParams();
  if (year) params.set("year", year);
  if (discipline) params.set("discipline_id", discipline);
  const query = useData(`/coaching/athletes/${id}/summary?${params}`);
  const data = query.data;
  return <>
    <PageTitle title="Сводка выступлений" description={data?.athlete.full_name || "Результаты подопечного"}>
      <Button variant="outline" asChild><Link to="/coaching">К моим спортсменам</Link></Button>
    </PageTitle>
    <section className="panel">
      <div className="toolbar">
        <Field label="Год">
          <select value={year} onChange={e => setYear(e.target.value)}>
            <option value="">Все годы</option>
            {data?.years.map((y: number) => <option key={y} value={y}>{y}</option>)}
          </select>
        </Field>
        <Field label="Дисциплина">
          <select value={discipline} onChange={e => setDiscipline(e.target.value)}>
            <option value="">Все дисциплины</option>
            {data?.disciplines.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        {(year || discipline) && <Button variant="ghost" onClick={() => { setYear(""); setDiscipline(""); }}>Сбросить</Button>}
      </div>
    </section>
    <State query={query}>
      {data && <>
        <div className="stats-grid section-gap">
          <Stat label="Выступления" value={data.stats.performances} note="По опубликованным протоколам" />
          <Stat label="Победы" value={data.stats.wins} note="Первое место" />
          <Stat label="Призовые места" value={data.stats.podiums} note="Места с первого по третье" />
          <Stat label="Лучшее место" value={data.stats.best_place} note="За выбранный период" />
        </div>
        <section className="panel section-gap">
          <div className="panel-heading"><h2>Выступления · {data.athlete.full_name}</h2></div>
          {data.results.length ? <Table heads={["Соревнование", "Дата", "Дисциплина", "Место", "Баллы", "Команда"]}>
            {data.results.map((r: any) => <tr key={r.id}>
              <td><Link to={`/competitions/${r.competition_id}`}><strong>{r.title}</strong></Link></td>
              <td>{date(r.start_date)}</td><td>{r.discipline}</td>
              <td><span className={r.place <= 3 ? "place-medal" : "place"}>{r.place}</span></td>
              <td>{r.score}</td><td>{r.team_name || "—"}</td>
            </tr>)}
          </Table> : <Empty text="Выступлений пока нет" hint="За выбранный период нет опубликованных результатов. Попробуйте изменить фильтры." />}
        </section>
      </>}
    </State>
  </>;
}
