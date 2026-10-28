import { Link } from "react-router-dom";
import { useState } from "react";
import { useAuth, useAction, useData } from "./state";
import { Button } from "./components/ui/button";
import { Empty, Field, State } from "./components/shared";

import { plain } from "./lib";
export function TeamInvite({ team, comp }: any) {
  const { role } = useAuth();
  const action = useAction();
  const coach = role === "coach";
  const [mode, setMode] = useState("id");
  const [value, setValue] = useState("");
  const [lookup, setLookup] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const params = coach
    ? "mine=true"
    : new URLSearchParams({
        [mode === "id" ? "public_id" : "q"]: lookup,
      }).toString();
  const query = useData(
    `/competitions/${comp.id}/team-candidates?${params}`,
    coach || !!lookup,
  );
  const alreadyMember = (a: any) =>
    team.members.some((m: any) => m.athlete_id === a.id);
  const choices = (query.data || []).filter((a: any) => !alreadyMember(a));
  const selected =
    !coach && !lookup
      ? null
      : coach || mode === "name"
        ? choices.find((a: any) => String(a.id) === candidateId)
        : choices[0];
  const full = team.members.length >= comp.team_max;
  return (
    <section className="team-invite" aria-label="Приглашение спортсмена">
      <h3>{coach ? "Пригласить подопечного" : "Пригласить спортсмена"}</h3>
      {!coach && (
        <>
          <Field label="Способ поиска">
            <select
              value={mode}
              onChange={(e) => {
                setMode(e.target.value);
                setValue("");
                setLookup("");
                setCandidateId("");
              }}
            >
              <option value="id">По ID спортсмена</option>
              <option value="name">По ФИО</option>
            </select>
          </Field>
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              setCandidateId("");
              setLookup(value.trim());
            }}
          >
            <Field
              label={mode === "id" ? "ID спортсмена" : "ФИО спортсмена"}
              hint={
                mode === "id"
                  ? "Попросите спортсмена скопировать ID из раздела «Мой профиль»."
                  : "При совпадении ФИО сверяйте ID, организацию и муниципалитет."
              }
            >
              <input
                required
                minLength={mode === "id" ? 10 : 2}
                maxLength={mode === "id" ? 14 : 200}
                placeholder={mode === "id" ? "FSP-000123" : "Введите ФИО"}
                pattern={mode === "id" ? "[fF][sS][pP]-[0-9]{6,10}" : undefined}
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                  setLookup("");
                  setCandidateId("");
                }}
              />
            </Field>
            <Button variant="outline">Найти спортсмена</Button>
          </form>
        </>
      )}
      {(coach || lookup) && (
        <State query={query}>
          {(coach || mode === "name") && choices.length > 0 && (
            <Field label={coach ? "Мой подопечный" : "Найденные спортсмены"}>
              <select
                required
                value={candidateId}
                onChange={(e) => setCandidateId(e.target.value)}
              >
                <option value="">Выберите спортсмена</option>
                {choices.map((a: any) => (
                  <option key={a.id} value={a.id}>
                    {plain(a.full_name)} · {a.public_id} · {plain(a.organization)} ·{" "}
                    {a.municipality}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {!choices.length && (
            <Empty
              text={
                query.data?.some(alreadyMember)
                  ? "Спортсмен уже в составе команды"
                  : coach
                    ? "Нет доступных подопечных"
                    : "Спортсмен не найден"
              }
              hint={
                coach
                  ? "Показываются ваши подтверждённые подопечные по дисциплине соревнования, ещё не включённые в состав."
                  : "Проверьте ID или уточните ФИО у спортсмена."
              }
            />
          )}
        </State>
      )}
      {selected && !query.error && (
        <div className="invite-card" aria-label="Получатель приглашения">
          <Link className="text-link" to={`/athletes/${selected.id}/profile`}><strong>{plain(selected.full_name)}</strong></Link>
          <code>{selected.public_id}</code>
          <span>Организация: {plain(selected.organization)}</span>
          <span>Муниципалитет: {selected.municipality}</span>
        </div>
      )}
      <p>
        Проверьте карточку получателя. Приглашение поступит в его личный
        кабинет; участие нужно подтвердить самостоятельно.
      </p>
      {full && <p>Достигнут максимальный размер команды.</p>}
      <Button
        variant="outline"
        disabled={
          !selected ||
          !!query.error ||
          query.isFetching ||
          full ||
          action.isPending
        }
        onClick={async () => {
          if (!selected) return;
          try {
            await action.mutateAsync({
              url: `/competitions/${comp.id}/teams/${team.id}/members`,
              data: { public_id: selected.public_id },
            });
          } catch {}
        }}
      >
        Отправить приглашение
      </Button>
    </section>
  );
}
