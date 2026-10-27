import { useState } from "react";
import { Link } from "react-router-dom";
import { useData, useToast } from "./state";
import { date, download, errorText, stateNames, today } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import { State } from "./components/shared";

export function ProfileDocuments({ user }: any) {
  const q = useData("/my/documents");
  const [selected, setSelected] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  async function save(doc: any) {
    setBusy(doc.id);
    try {
      await download(`/my/documents/${doc.id}.pdf`, `consent-${doc.id}.pdf`);
    } catch (error) {
      toast(errorText(error), true);
    } finally {
      setBusy(null);
    }
  }
  return (
    <section className="panel info-card section-gap">
      <h2>Документы</h2>
      <p>Записи согласий на обработку персональных данных.</p>
      {user.guardian_name && <p>Законный представитель: {user.guardian_name}</p>}
      {user.guardian_name && !user.guardian_consent_at && (
        <p className="inline-note">Согласие представителя не зафиксировано.</p>
      )}
      <State query={q}>
        {q.data?.length ? q.data.map((doc: any) => (
          <div className="form-section" key={doc.id}>
            <h3>{doc.title}</h3>
            <p>Принято {date(doc.accepted_at)} · версия {doc.version}</p>
            <div className="export-buttons">
              <Button size="sm" variant="outline" onClick={() => setSelected(doc)}>Просмотреть</Button>
              <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => save(doc)}>
                {busy === doc.id ? "Скачиваем…" : "Скачать PDF"}
              </Button>
            </div>
          </div>
        )) : <p>Сохранённых записей согласий нет.</p>}
      </State>
      <Dialog open={!!selected} onOpenChange={(open) => { if (!open) setSelected(null); }} title={selected?.title || "Согласие"}>
        {selected && (
          <div className="panel-padding">
            <p><strong>ФИО:</strong> {selected.subject_name}</p>
            <p><strong>Дата рождения:</strong> {date(selected.birth_date)}</p>
            <p><strong>Кем принято:</strong> {selected.accepted_by || "Не указано"}</p>
            <p><strong>Дата принятия:</strong> {new Date(selected.accepted_at).toLocaleString("ru-RU")}</p>
            <p><strong>Версия:</strong> {selected.version}</p>
            <p><strong>Оператор:</strong> {selected.operator}</p>
            <div className="form-section">
              <h3>Текст согласия</h3>
              <p>{selected.text || "Текст этой версии согласия в системе не сохранён. Доступны только сведения о факте принятия."}</p>
            </div>
            <p className="inline-note">{selected.note}</p>
            <Button disabled={busy !== null} onClick={() => save(selected)}>Скачать PDF</Button>
          </div>
        )}
      </Dialog>
    </section>
  );
}

export function ProfileSportsSummary({ athlete }: any) {
  const links = useData("/links");
  const meta = useData("/metadata");
  const coaches = links.data?.filter((l: any) => l.athlete_id === athlete.id && ["active", "paused"].includes(l.status));
  const currentRanks = (athlete.ranks || []).filter((r: any, i: number, all: any[]) =>
    r.assigned_on <= today() && r.expires_on >= today() &&
    !all.slice(0, i).some((prev: any) => prev.discipline_id === r.discipline_id && prev.assigned_on <= today() && prev.expires_on >= today())
  );
  const discipline = (id: number) => meta.data?.disciplines.find((d: any) => d.id === id)?.name || "Дисциплина №" + id;
  return (
    <section className="panel info-card section-gap">
      <h2>Тренеры и разряды</h2>
      <State query={links}>
        {coaches?.length ? coaches.map((l: any) => (
          <p key={l.id}><strong>{l.coach}</strong><br />{discipline(l.discipline_id)} · {stateNames[l.status]}</p>
        )) : <p>Подтверждённых связей с тренерами пока нет.</p>}
      </State>
      <Link className="text-link" to="/coaching">Связи с тренерами</Link>
      <div className="form-section">
        <h3>Текущие разряды</h3>
        {currentRanks.length ? currentRanks.map((r: any) => (
          <p key={r.id}><strong>{r.name}</strong> · {discipline(r.discipline_id)}<br />Действует до {date(r.expires_on)}</p>
        )) : <p>Действующих разрядов пока нет.</p>}
        <Link className="text-link" to="/ranks">Разряды и история присвоений</Link>
      </div>
    </section>
  );
}
