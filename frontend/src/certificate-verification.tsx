import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ShieldCheck, CircleX, TriangleAlert, Code2 } from "lucide-react";
import { date, plain } from "./lib";

export function CertificateVerification() {
  const { checkToken = "" } = useParams();
  const query = useQuery({
    queryKey: ["public-certificate", checkToken],
    queryFn: async () => (await axios.get(`/api/public/certificates/${encodeURIComponent(checkToken)}`)).data,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  const data = query.data;
  const missing = axios.isAxiosError(query.error) && query.error.response?.status === 404;
  const status = data?.status;
  const label = status === "confirmed" ? "Справка подтверждена" : status === "replaced" ? "Редакция заменена" : "Справка недействительна";
  const Icon = status === "confirmed" ? ShieldCheck : status === "replaced" ? TriangleAlert : CircleX;
  return <main className="verification-page">
    <header className="verification-header"><span className="verification-brand"><Code2 aria-hidden="true" /> ОренКод</span><Link to="/login">Войти в кабинет</Link></header>
    <section className="verification-card">
      <p className="eyebrow">ФСП Оренбургской области</p>
      <h1>Проверка справки об участии</h1>
      {query.isPending ? <p role="status">Проверяем запись…</p> : query.isError ? <div role="alert">
        <h2>{missing ? "Справка не найдена" : "Не удалось выполнить проверку"}</h2>
        <p>{missing ? "Ссылка неверна или запись больше недоступна. Попросите владельца заново скачать справку в разделе «Результаты»." : "Проверьте соединение и повторите попытку."}</p>
        {!missing && <button className="text-link" onClick={() => query.refetch()}>Повторить проверку</button>}
      </div> : <>
        <div className={`verification-status ${status}`} role="status"><Icon aria-hidden="true" /><strong>{label}</strong></div>
        <dl className="verification-details">
          <div><dt>Номер справки</dt><dd>{data.certificate_number}</dd></div>
          {data.competition_title && <div><dt>Соревнование</dt><dd>{plain(data.competition_title)}</dd></div>}
          <div><dt>Редакция протокола</dt><dd>{data.version}</dd></div>
          {data.published_at && <div><dt>Дата публикации</dt><dd>{date(data.published_at)}</dd></div>}
        </dl>
        <p>{status === "confirmed" ? "Запись существует и относится к актуальной опубликованной редакции протокола." : status === "replaced" ? "После выпуска справки протокол был исправлен. Попросите владельца предоставить справку по новой редакции." : "Запись больше не подтверждается опубликованными результатами. Обратитесь к владельцу справки или в федерацию."}</p>
      </>}
      <footer className="verification-note">Проверка доступна без входа. ФИО, личные данные и PDF здесь не публикуются. Страница подтверждает запись в системе; она не удостоверяет личность предъявителя и не является проверкой электронной подписи PDF.</footer>
    </section>
  </main>;
}
