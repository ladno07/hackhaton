import { Link } from "react-router-dom";
import { useState } from "react";
import { useAuth, useAction, useData } from "./state";
import { today } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import { Empty, Field, State, Table } from "./components/shared";

import { TeamInvite } from "./team-invite";

const teamStatuses: Record<string, string> = {
  cancelled: "Снята с соревнования",
  draft: "Сбор состава",
  pending: "На рассмотрении",
  approved: "Допущена · состав зафиксирован",
  returned: "На исправлении · допуска нет",
};
const memberStatuses: Record<string, string> = {
  invited: "Ожидает подтверждения",
  accepted: "Участие подтверждено",
  declined: "Приглашение отклонено",
};

function TeamCard({ team, comp }: any) {
  const { role } = useAuth();
  const action = useAction();
  const [name, setName] = useState(team.name);
  const [captain, setCaptain] = useState(String(team.captain_id));
  const [comment, setComment] = useState("");
  const open = comp.state === "open" && comp.deadline >= today();
  const editable =
    open && team.can_manage && ["draft", "returned"].includes(team.status);
  const base = `/competitions/${comp.id}/teams/${team.id}`;
  const act = async (url: string, data?: any, method = "post") => {
    try {
      await action.mutateAsync({ url: base + url, data, method });
    } catch {}
  };
  return (
    <article className="competition-team">
      <div className="panel-heading">
        <div>
          <h2>{team.name}</h2>
          <p>
            {teamStatuses[team.status]} · Капитан: {team.captain}
          </p>
        </div>
        <strong>
          {team.members.filter((m: any) => m.status === "accepted").length}/
          {comp.team_max}
        </strong>
      </div>
      {team.comment && (
        <p className="inline-note">Комментарий: {team.comment}</p>
      )}
      <Table heads={["Участник", "Подтверждение", "Действия"]}>
        {team.members.map((m: any) => (
          <tr key={m.id}>
            <td>
              <Link
                className="text-link"
                to={`/athletes/${m.athlete_id}/profile`}
              >
                {m.full_name}
              </Link>
              <small>{m.public_id}</small>
              {m.athlete_id === team.captain_id && <small>Капитан</small>}
            </td>
            <td>{memberStatuses[m.status]}</td>
            <td>
              <div className="row-actions">
                {m.is_me &&
                  open &&
                  team.status !== "approved" &&
                  m.status === "invited" && (
                    <>
                      <Button
                        size="sm"
                        disabled={action.isPending}
                        onClick={() =>
                          act("/response", { status: "accepted" }, "patch")
                        }
                      >
                        Подтвердить участие
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={action.isPending}
                        onClick={() =>
                          act("/response", { status: "declined" }, "patch")
                        }
                      >
                        Отклонить
                      </Button>
                    </>
                  )}
                {m.is_me &&
                  open &&
                  team.status !== "approved" &&
                  m.status === "accepted" &&
                  m.athlete_id !== team.captain_id && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={action.isPending}
                      onClick={() =>
                        act("/response", { status: "declined" }, "patch")
                      }
                    >
                      Отозвать согласие
                    </Button>
                  )}
                {editable && m.athlete_id !== team.captain_id && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={action.isPending}
                    onClick={() =>
                      act(`/members/${m.athlete_id}`, undefined, "delete")
                    }
                  >
                    Исключить
                  </Button>
                )}
              </div>
            </td>
          </tr>
        ))}
      </Table>
      {editable && (
        <div className="team-controls">
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault();
              act("", { name, captain_id: +captain }, "put");
            }}
          >
            <Field label="Название">
              <input
                required
                minLength={2}
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Капитан">
              <select
                value={captain}
                onChange={(e) => setCaptain(e.target.value)}
              >
                {team.members.map((m: any) => (
                  <option key={m.id} value={m.athlete_id}>
                    {m.full_name} · {m.public_id}
                  </option>
                ))}
              </select>
            </Field>
            <Button variant="outline" disabled={action.isPending}>
              Сохранить
            </Button>
          </form>
          <TeamInvite team={team} comp={comp} />
          <p>
            Для подачи нужно {comp.team_min}–{comp.team_max} участников с
            подтверждённым согласием, включая капитана.
          </p>
          <Button disabled={action.isPending} onClick={() => act("/submit")}>
            Подать общую заявку
          </Button>
        </div>
      )}
      {editable && (
        <form
          className="team-controls"
          onSubmit={(e) => {
            e.preventDefault();
            act("/cancel", { reason: comment });
          }}
        >
          <Field label="Причина снятия команды">
            <input
              required
              minLength={5}
              maxLength={2000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </Field>
          <Button variant="outline" disabled={action.isPending}>
            Снять команду с соревнования
          </Button>
        </form>
      )}
      {role === "admin" &&
        team.status === "pending" &&
        ["open", "closed"].includes(comp.state) && (
          <div className="team-controls">
            <Field label="Комментарий к решению">
              <textarea
                maxLength={2000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </Field>
            <div className="button-row">
              <Button
                disabled={action.isPending}
                onClick={() =>
                  act("/review", { status: "approved", comment }, "patch")
                }
              >
                Допустить команду
              </Button>
              <Button
                variant="outline"
                disabled={action.isPending || comment.trim().length < 5}
                onClick={() =>
                  act("/review", { status: "returned", comment }, "patch")
                }
              >
                Вернуть на исправление
              </Button>
            </div>
          </div>
        )}
      {open &&
        (team.can_manage || role === "admin") &&
        ["pending", "approved"].includes(team.status) && (
          <form
            className="team-controls"
            onSubmit={(e) => {
              e.preventDefault();
              act("/reopen", { reason: comment });
            }}
          >
            <p>
              {team.status === "approved"
                ? "Для замены участника нужно снять допуск. После изменения состава потребуется повторное одобрение федерации."
                : "Для изменения состава отзовите заявку с рассмотрения."}
            </p>
            <Field label="Причина изменения состава">
              <input
                required
                minLength={5}
                maxLength={2000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </Field>
            <Button variant="outline" disabled={action.isPending}>
              {team.status === "approved"
                ? "Снять допуск и изменить состав"
                : "Отозвать на редактирование"}
            </Button>
          </form>
        )}
    </article>
  );
}

export function CompetitionTeams({ comp }: any) {
  const { role, user } = useAuth();
  const action = useAction();
  const query = useData(`/competitions/${comp.id}/teams`);
  const wards = useData(
    `/competitions/${comp.id}/team-candidates?mine=true`,
    role === "coach" && comp.state === "open" && comp.deadline >= today(),
  );
  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [captain, setCaptain] = useState("");
  const open = comp.state === "open" && comp.deadline >= today();
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Команды соревнования</h2>
          <p>
            Состав: {comp.team_min}–{comp.team_max}. Личный рейтинг за командный
            результат:{" "}
            {comp.team_rating
              ? "начисляется каждому участнику"
              : "не начисляется"}
            .
          </p>
        </div>
        {open && ["athlete", "coach"].includes(role) && (
          <Button onClick={() => setShow(true)}>Создать команду</Button>
        )}
      </div>
      <State query={query}>
        {query.data?.length ? (
          query.data.map((t: any) => (
            <TeamCard key={`${t.id}:${t.revision}`} team={t} comp={comp} />
          ))
        ) : (
          <Empty
            text="Команд пока нет"
            hint="Создайте команду или дождитесь приглашения. До допуска состав видят участники, создавший тренер и федерация."
          />
        )}
      </State>
      <Dialog open={show} onOpenChange={setShow} title="Новая команда">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await action.mutateAsync({
                url: `/competitions/${comp.id}/teams`,
                data: {
                  name,
                  captain_id: role === "athlete" ? user.athlete_id : +captain,
                },
              });
              setShow(false);
              setName("");
              setCaptain("");
            } catch {}
          }}
        >
          <Field label="Название команды">
            <input
              required
              minLength={2}
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          {role === "coach" ? (
            <Field label="Капитан из моих подопечных">
              <select
                required
                value={captain}
                onChange={(e) => setCaptain(e.target.value)}
              >
                <option value="">Выберите капитана</option>
                {wards.data?.map((a: any) => (
                  <option key={a.id} value={a.id}>
                    {a.full_name} · {a.public_id} · {a.organization} ·{" "}
                    {a.municipality}
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <p>
              Вы станете капитаном и подтвердите собственное участие при
              создании команды.
            </p>
          )}
          <p>
            Каждый приглашённый, включая назначенного тренером капитана,
            подтверждает участие в своём кабинете.
          </p>
          <Button disabled={action.isPending}>Создать команду</Button>
        </form>
      </Dialog>
    </>
  );
}

export function TeamResultsEditor({ comp, correction, onDone }: any) {
  const teams = useData(`/competitions/${comp.id}/teams`);
  return (
    <State query={teams}>
      <TeamResultsForm
        key={teams.data
          ?.filter((t: any) => t.status === "approved")
          .map((t: any) => `${t.id}:${t.revision}`)
          .join(",")}
        teams={teams.data || []}
        comp={comp}
        correction={correction}
        onDone={onDone}
      />
    </State>
  );
}
function TeamResultsForm({ teams, comp, correction, onDone }: any) {
  const action = useAction();
  const [reason, setReason] = useState("");
  const [rows, setRows] = useState(() =>
    teams
      .filter((t: any) => t.status === "approved")
      .map((t: any, i: number) => {
        const existing = correction
          ? comp.results.find(
              (r: any) => r.athlete_id === t.members[0]?.athlete_id,
            )
          : null;
        return {
          team_id: t.id,
          name: t.name,
          place: existing?.place || i + 1,
          score: existing?.score || 0,
        };
      }),
  );
  const update = (id: number, key: string, value: number) =>
    setRows(
      rows.map((r: any) => (r.team_id === id ? { ...r, [key]: value } : r)),
    );
  if (!rows.length)
    return (
      <Empty
        text="Нет допущенных команд"
        hint="Рассмотрите общие заявки во вкладке «Команды»."
      />
    );
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: correction ? "put" : "post",
            url: `/competitions/${comp.id}/results`,
            data: {
              team_results: rows.map(({ team_id, place, score }: any) => ({
                team_id,
                place,
                score,
              })),
              ...(correction ? { reason } : {}),
            },
          });
          onDone?.();
        } catch {}
      }}
    >
      <p className="inline-note">
        Один результат на допущенную команду. Место и баллы автоматически
        получит каждый участник зафиксированного состава. Общие места
        допускаются по правилу «1, 1, 3».
      </p>
      <Table heads={["Команда", "Место", "Баллы"]}>
        {rows.map((r: any) => (
          <tr key={r.team_id}>
            <td>{r.name}</td>
            <td>
              <input
                aria-label={`Место команды ${r.name}`}
                type="number"
                min={1}
                max={rows.length}
                required
                value={r.place}
                onChange={(e) => update(r.team_id, "place", +e.target.value)}
              />
            </td>
            <td>
              <input
                aria-label={`Баллы команды ${r.name}`}
                type="number"
                min={0}
                step="any"
                required
                value={r.score}
                onChange={(e) => update(r.team_id, "score", +e.target.value)}
              />
            </td>
          </tr>
        ))}
      </Table>
      {correction && (
        <Field label="Причина исправления">
          <textarea
            required
            minLength={5}
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
      )}
      <div className="team-controls">
        <Button disabled={action.isPending}>
          {correction
            ? "Сохранить новую редакцию"
            : "Опубликовать результаты команд"}
        </Button>
      </div>
    </form>
  );
}
