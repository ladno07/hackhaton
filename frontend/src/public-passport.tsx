import { useParams, useSearchParams, Link, Navigate } from "react-router-dom";
import { useAuth, useData, useToast } from "./state";
import { date, download } from "./lib";
import { Button } from "./components/ui/button";
import { PageTitle, State, Empty, Table } from "./components/shared";

export function AthleteProfileView() {
  const { id } = useParams();
  const query = useData(`/athlete-profiles/${id}`);
  const data = query.data;
  return (
    <>
      <PageTitle
        title={data?.full_name || "Профиль спортсмена"}
        description={
          data?.public_id ||
          "Результаты и разделы, открытые владельцем профиля для пользователей платформы"
        }
      >
        <Button variant="outline" asChild>
          <Link to="/history">К результатам</Link>
        </Button>
      </PageTitle>
      <State query={query}>
        {data && (
          <>
            {(data.organization || data.municipality) && (
              <section className="panel info-card">
                <p>
                  {[data.organization, data.municipality]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </section>
            )}
            {data.visibility.show_results && (
              <div className="stats-grid section-gap">
                {[
                  [data.stats.competitions, "Выступления"],
                  [data.stats.wins, "Победы"],
                  [data.stats.podiums, "Призовые места"],
                ].map(([value, label]) => (
                  <section className="stat" key={String(label)}>
                    <div className="stat-top">{label}</div>
                    <strong>{value}</strong>
                  </section>
                ))}
              </div>
            )}
            <section className="panel section-gap">
              <div className="panel-heading">
                <h2>Результаты</h2>
              </div>
              {data.visibility.show_results ? (
                data.results.length ? (
                  <Table
                    heads={[
                      "Соревнование",
                      "Дата",
                      "Дисциплина",
                      "Место",
                      "Баллы",
                    ]}
                  >
                    {data.results.map((r: any, i: number) => (
                      <tr key={i}>
                        <td>
                          <strong>{r.title}</strong>
                          {r.team_name && <small>Команда: {r.team_name}</small>}
                        </td>
                        <td>{date(r.date)}</td>
                        <td>{r.discipline}</td>
                        <td>{r.place}</td>
                        <td>{r.score}</td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <Empty
                    text="Выступлений пока нет"
                    hint="Результаты появятся после публикации протокола."
                  />
                )
              ) : (
                <Empty
                  text="История выступлений скрыта владельцем"
                  hint="В профиле отображаются только разрешённые спортсменом разделы."
                />
              )}
            </section>
            <div className="profile-sections section-gap">
              {data.visibility.show_rating && (
                <section className="panel info-card">
                  <h2>Рейтинг · {data.season}</h2>
                  {data.ratings.length ? (
                    data.ratings.map((r: any) => (
                      <p key={r.discipline}>
                        <strong>{r.discipline}</strong>
                        <br />
                        {r.points} баллов · {r.position} место
                      </p>
                    ))
                  ) : (
                    <p>Рейтинг пока не сформирован.</p>
                  )}
                </section>
              )}
              {data.visibility.show_ranks && (
                <section className="panel info-card">
                  <h2>Спортивные разряды</h2>
                  {data.ranks.length ? (
                    data.ranks.map((r: any, i: number) => (
                      <p key={i}>
                        <strong>
                          {r.name} · {r.discipline}
                        </strong>
                        <br />
                        {r.active
                          ? "Действует до "
                          : "Требует подтверждения · "}
                        {date(r.expires_on)}
                      </p>
                    ))
                  ) : (
                    <p>Разряд не присвоен.</p>
                  )}
                </section>
              )}
              {data.visibility.show_disciplines && (
                <section className="panel info-card">
                  <h2>Дисциплины</h2>
                  {data.disciplines.map((d: any) => (
                    <p key={d.name}>
                      {d.name}
                      {d.start_year && (
                        <small>
                          {d.start_year}–{d.end_year || "по настоящее время"}
                        </small>
                      )}
                    </p>
                  ))}
                </section>
              )}
              {data.training_stage && (
                <section className="panel info-card">
                  <h2>Этап подготовки</h2>
                  <p>{data.training_stage}</p>
                </section>
              )}
              {data.visibility.show_team && (
                <section className="panel info-card">
                  <h2>Сборная</h2>
                  {data.team.length ? (
                    data.team.map((t: any) => (
                      <p key={t.discipline}>
                        {t.discipline} · {t.season}
                      </p>
                    ))
                  ) : (
                    <p>В текущем сезоне в состав не включён.</p>
                  )}
                </section>
              )}
              {data.rusada && (
                <section className="panel info-card">
                  <h2>Чистый спорт</h2>
                  <p>Курс РУСАДА пройден · {date(data.rusada.completed_on)}</p>
                </section>
              )}
            </div>
          </>
        )}
      </State>
    </>
  );
}

export function PrivateCertificate() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const version = params.get("version");
  const toast = useToast();
  const suffix = version ? `?version=${encodeURIComponent(version)}` : "";
  const query = useData(`/results/${id}/certificate${suffix}`);
  const data = query.data;
  return (
    <>
      <PageTitle
        title="Справка об участии"
        description="Документ доступен только владельцу результата, его действующему тренеру по дисциплине и федерации."
      >
        <Button variant="outline" asChild>
          <Link to="/history">К результатам</Link>
        </Button>
      </PageTitle>
      <State query={query}>
        {data && (
          <section className="panel info-card">
            <h2>{data.entry.full_name}</h2>
            <p>{data.competition.title}</p>
            <p>
              {date(data.competition.start_date)} ·{" "}
              {data.competition.discipline}
            </p>
            <p>
              {data.entry.organization}
              {data.entry.team_name && " · Команда: " + data.entry.team_name}
            </p>
            <p>
              Место: {data.entry.place} · Баллы: {data.entry.score}
            </p>
            <p>
              Номер справки: {data.certificate_number} · Редакция {data.version}
            </p>
            {!data.is_current && (
              <p className="inline-note">
                Эта редакция заменена. Актуальная редакция:{" "}
                {data.latest_version}.{" "}
                <Link className="text-link" to={`/certificates/${id}`}>
                  Посмотреть актуальный результат
                </Link>
              </p>
            )}
            <p>
              QR в PDF открывает публичную проверку номера и статуса без ФИО и личных данных. Полная справка доступна только в кабинете.
            </p>
            <Button
              onClick={() =>
                download(
                  `/results/${id}/certificate.pdf${suffix}`,
                  `${data.certificate_number}.pdf`,
                ).catch(() => toast("Не удалось скачать справку", true))
              }
            >
              Скачать справку PDF
            </Button>
            <Button asChild variant="outline"><Link to={data.verification_path}>Публичная проверка</Link></Button>
          </section>
        )}
      </State>
    </>
  );
}

export function LegacyPublicProfile() {
  const { token } = useAuth();
  return (
    <div className="state full-screen">
      <h1>Публичный доступ закрыт</h1>
      <p>
        Профили спортсменов доступны пользователям после входа. Справки
        находятся в личном разделе «Результаты».
      </p>
      <Button asChild>
        <Link to={token ? "/history" : "/login"}>
          {token ? "К результатам" : "Войти"}
        </Link>
      </Button>
    </div>
  );
}
