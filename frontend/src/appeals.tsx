import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Scale, ShieldAlert } from "lucide-react";
import { useAction, useAuth, useData } from "./state";
import { date, today } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import {
  Badge,
  Empty,
  ExportButtons,
  Field,
  PageTitle,
  State,
  Table,
} from "./components/shared";

// reuse the badge colours of applications
const appealBadges: Record<string, string> = {
  pending: "pending",
  upheld: "approved",
  rejected: "rejected",
  withdrawn: "draft",
};
const violationKinds: Record<string, string> = {
  rules: "Нарушение правил соревнований",
  conduct: "Неспортивное поведение",
  doping: "Нарушение антидопинговых правил",
  other: "Иное нарушение",
};
const plain = (s: string) => s?.replace("Демо · ", "");

function AppealForm({ onDone }: any) {
  const options = useData("/appeals/options");
  const action = useAction();
  const [choice, setChoice] = useState("");
  const [reason, setReason] = useState("");
  const [request, setRequest] = useState("");
  const results = options.data?.results || [];
  const violations = options.data?.violations || [];
  return (
    <State query={options}>
      {results.length || violations.length ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const [subject, id] = choice.split(":");
            try {
              await action.mutateAsync({
                url: "/appeals",
                data: {
                  subject,
                  [subject + "_id"]: +id,
                  reason,
                  request,
                },
              });
              onDone();
            } catch {}
          }}
        >
          <p className="inline-hint">
            Апелляция на протокол подаётся в течение{" "}
            {options.data.result_days} дней после публикации редакции, на
            решение о нарушении — в течение {options.data.violation_days} дней.
          </p>
          <Field label="Что обжалуется">
            <select
              required
              value={choice}
              onChange={(e) => setChoice(e.target.value)}
            >
              <option value="">Выберите…</option>
              {results.length > 0 && (
                <optgroup label="Результат в протоколе">
                  {results.map((r: any) => (
                    <option key={r.result_id} value={"result:" + r.result_id}>
                      {plain(r.full_name)} · {plain(r.competition)} ·{" "}
                      {r.place} место, {r.score} б. · до {date(r.appeal_until)}
                    </option>
                  ))}
                </optgroup>
              )}
              {violations.length > 0 && (
                <optgroup label="Решение о нарушении">
                  {violations.map((v: any) => (
                    <option key={v.id} value={"violation:" + v.id}>
                      {plain(v.full_name)} · {v.summary} · до{" "}
                      {date(v.appeal_until)}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </Field>
          <Field label="Доводы" hint="Что произошло и чем это подтверждается">
            <textarea
              required
              minLength={10}
              maxLength={4000}
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
          <Field label="Требование">
            <input
              maxLength={2000}
              placeholder="Например: пересчитать баллы за задачу F"
              value={request}
              onChange={(e) => setRequest(e.target.value)}
            />
          </Field>
          <Button disabled={action.isPending}>Подать апелляцию</Button>
        </form>
      ) : (
        <Empty
          text="Обжаловать нечего"
          hint="Нет протоколов и решений о нарушениях, по которым не истёк срок подачи."
        />
      )}
    </State>
  );
}

function Correction({ appeal, rows, setRows }: any) {
  const comp = useData("/competitions/" + appeal.competition_id);
  useEffect(() => {
    if (!rows && comp.data?.results) setRows(comp.data.results);
  }, [comp.data]);
  if (comp.data?.entry_mode === "team")
    return (
      <p className="inline-hint">
        Командный протокол исправляется на{" "}
        <Link className="text-link" to={"/competitions/" + appeal.competition_id}>
          странице соревнования
        </Link>
        .
      </p>
    );
  const data = rows || [];
  const update = (id: number, k: string, v: number) =>
    setRows(data.map((r: any) => (r.athlete_id === id ? { ...r, [k]: v } : r)));
  return (
    <State query={comp}>
      <Table heads={["Спортсмен", "Место", "Баллы"]}>
        {data.map((r: any) => (
          <tr
            key={r.athlete_id}
            className={r.athlete_id === appeal.athlete_id ? "appeal-row" : ""}
          >
            <td>{plain(r.full_name)}</td>
            <td>
              <input
                aria-label={"Место: " + r.full_name}
                type="number"
                min="1"
                required
                value={r.place}
                onChange={(e) => update(r.athlete_id, "place", +e.target.value)}
              />
            </td>
            <td>
              <input
                aria-label={"Баллы: " + r.full_name}
                type="number"
                min="0"
                step="any"
                required
                value={r.score}
                onChange={(e) => update(r.athlete_id, "score", +e.target.value)}
              />
            </td>
          </tr>
        ))}
      </Table>
    </State>
  );
}

function DecisionForm({ appeal, onDone }: any) {
  const action = useAction();
  const [status, setStatus] = useState("upheld");
  const [decision, setDecision] = useState("");
  const [fix, setFix] = useState(false);
  const [rows, setRows] = useState<any[] | null>(null);
  const correcting = fix && status === "upheld" && appeal.subject === "result";
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: "patch",
            url: "/appeals/" + appeal.id,
            data: {
              status,
              decision,
              ...(correcting && rows
                ? {
                    correction: {
                      results: rows.map(({ athlete_id, place, score, team_name }) => ({
                        athlete_id,
                        place,
                        score,
                        team_name: team_name || null,
                      })),
                    },
                  }
                : {}),
            },
          });
          onDone();
        } catch {}
      }}
    >
      <p className="award-dialog-name">
        <strong>{plain(appeal.full_name)}</strong>
        {appeal.number}
      </p>
      <p className="appeal-text">{plain(appeal.subject_text)}</p>
      <p className="appeal-text">
        <b>Доводы:</b> {appeal.reason}
        {appeal.request && (
          <>
            <br />
            <b>Требование:</b> {appeal.request}
          </>
        )}
      </p>
      <Field label="Решение">
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="upheld">Удовлетворить</option>
          <option value="rejected">Отклонить</option>
        </select>
      </Field>
      <Field label="Мотивировка">
        <textarea
          required
          minLength={5}
          maxLength={4000}
          rows={3}
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
        />
      </Field>
      {status === "upheld" && appeal.subject === "violation" && (
        <p className="inline-hint">
          Решение о нарушении будет отменено, отстранение по нему снимется.
        </p>
      )}
      {status === "upheld" && appeal.subject === "result" && (
        <label className="check-line">
          <input
            type="checkbox"
            checked={fix}
            onChange={(e) => setFix(e.target.checked)}
          />
          Исправить протокол: опубликовать новую редакцию по этой апелляции
        </label>
      )}
      {correcting && <Correction appeal={appeal} rows={rows} setRows={setRows} />}
      <Button disabled={action.isPending || (correcting && !rows)}>
        Сохранить решение
      </Button>
    </form>
  );
}

function AppealsTab({ onDecide }: any) {
  const { role } = useAuth();
  const [status, setStatus] = useState("");
  const q = useData("/appeals" + (status ? "?status=" + status : ""));
  const action = useAction();
  return (
    <>
      <div className="toolbar">
        <Field label="Статус">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Все</option>
            <option value="pending">На рассмотрении</option>
            <option value="upheld">Удовлетворены</option>
            <option value="rejected">Отклонены</option>
            <option value="withdrawn">Отозваны</option>
          </select>
        </Field>
      </div>
      <State query={q}>
        {q.data?.length ? (
          <Table heads={["№", "Спортсмен", "Предмет", "Доводы", "Статус", ""]}>
            {q.data.map((a: any) => (
              <tr key={a.id}>
                <td>
                  <strong>{a.number}</strong>
                  <small>{date(a.created_at)}</small>
                </td>
                <td>
                  <strong>{plain(a.full_name)}</strong>
                  {a.submitted_role === "coach" && (
                    <small>подал тренер · {plain(a.submitted_by_name)}</small>
                  )}
                </td>
                <td>
                  {a.competition_id && a.subject === "result" ? (
                    <Link className="text-link" to={"/competitions/" + a.competition_id}>
                      {plain(a.subject_text)}
                    </Link>
                  ) : (
                    plain(a.subject_text)
                  )}
                  {a.subject === "result" && a.current_place != null && (
                    <small>
                      сейчас: {a.current_place} место, {a.current_score} б.
                    </small>
                  )}
                </td>
                <td className="appeal-reason">
                  {a.reason}
                  {a.request && <small>Требование: {a.request}</small>}
                </td>
                <td>
                  <Badge value={appealBadges[a.status]} label={a.status_name} />
                  {a.decision && <small>{a.decision}</small>}
                  {a.resolution_version && (
                    <small>Редакция протокола {a.resolution_version}</small>
                  )}
                </td>
                <td>
                  <div className="award-actions">
                    {a.can_decide && (
                      <Button size="sm" onClick={() => onDecide(a)}>
                        Рассмотреть
                      </Button>
                    )}
                    {a.can_withdraw && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={action.isPending}
                        onClick={() =>
                          action.mutate({ url: `/appeals/${a.id}/withdraw` })
                        }
                      >
                        Отозвать
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty
            text="Апелляций нет"
            hint={
              role === "athlete" || role === "coach"
                ? "Апелляцию можно подать на результат в опубликованном протоколе или на решение о нарушении."
                : "Здесь появятся апелляции спортсменов и тренеров."
            }
          />
        )}
      </State>
    </>
  );
}

function ViolationForm({ onDone }: any) {
  const athletes = useData("/athletes");
  const comps = useData("/competitions");
  const action = useAction();
  const [form, setForm] = useState<any>({
    athlete_id: "",
    competition_id: "",
    kind: "rules",
    occurred_on: today(),
    description: "",
    sanction: "warning",
    suspended_until: "",
  });
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            url: "/violations",
            data: {
              ...form,
              athlete_id: +form.athlete_id,
              competition_id: form.competition_id ? +form.competition_id : null,
              suspended_until:
                form.sanction === "suspension" ? form.suspended_until : null,
            },
          });
          onDone();
        } catch {}
      }}
    >
      <Field label="Спортсмен">
        <select
          required
          value={form.athlete_id}
          onChange={(e) => set("athlete_id", e.target.value)}
        >
          <option value="">Выберите…</option>
          {(athletes.data || []).map((a: any) => (
            <option key={a.id} value={a.id}>
              {plain(a.full_name)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Соревнование" hint="Если нарушение связано с соревнованием">
        <select
          value={form.competition_id}
          onChange={(e) => set("competition_id", e.target.value)}
        >
          <option value="">Не связано</option>
          {(comps.data || [])
            .filter((c: any) => c.state !== "draft")
            .map((c: any) => (
              <option key={c.id} value={c.id}>
                {plain(c.title)} · {date(c.start_date)}
              </option>
            ))}
        </select>
      </Field>
      <div className="form-grid">
        <Field label="Вид">
          <select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
            {Object.entries(violationKinds).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Дата нарушения">
          <input
            type="date"
            required
            max={today()}
            value={form.occurred_on}
            onChange={(e) => set("occurred_on", e.target.value)}
          />
        </Field>
        <Field label="Санкция">
          <select
            value={form.sanction}
            onChange={(e) => set("sanction", e.target.value)}
          >
            <option value="warning">Предупреждение</option>
            <option value="suspension">Отстранение</option>
          </select>
        </Field>
        {form.sanction === "suspension" && (
          <Field label="Отстранён по">
            <input
              type="date"
              required
              min={today()}
              value={form.suspended_until}
              onChange={(e) => set("suspended_until", e.target.value)}
            />
          </Field>
        )}
      </div>
      <Field label="Описание">
        <textarea
          required
          minLength={5}
          maxLength={2000}
          rows={3}
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
        />
      </Field>
      <p className="inline-hint">
        Спортсмен и его тренеры получат уведомление и смогут подать апелляцию в
        течение 10 дней. Отстранение закрывает подачу заявок и исключает из
        рейтинга, сборной и премий.
      </p>
      <Button disabled={action.isPending}>Зафиксировать</Button>
    </form>
  );
}

function CancelForm({ violation, onDone }: any) {
  const action = useAction();
  const [reason, setReason] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            url: `/violations/${violation.id}/cancel`,
            data: { reason },
          });
          onDone();
        } catch {}
      }}
    >
      <p className="appeal-text">
        {plain(violation.full_name)} · {violation.summary}
      </p>
      <Field label="Причина отмены">
        <textarea
          required
          minLength={3}
          maxLength={2000}
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <Button disabled={action.isPending}>Отменить решение</Button>
    </form>
  );
}

function ViolationsTab({ onCancel }: any) {
  const { role } = useAuth();
  const q = useData("/violations");
  return (
    <State query={q}>
      {q.data?.length ? (
        <Table heads={["Дата", "Спортсмен", "Нарушение", "Санкция", "Статус", ""]}>
          {q.data.map((v: any) => (
            <tr key={v.id}>
              <td>{date(v.occurred_on)}</td>
              <td>
                <strong>{plain(v.full_name)}</strong>
                {v.competition && <small>{plain(v.competition)}</small>}
              </td>
              <td className="appeal-reason">
                <strong>{v.kind_name}</strong>
                <small>{plain(v.description)}</small>
              </td>
              <td>
                {v.sanction_name}
                {v.suspended_until && <small>по {date(v.suspended_until)}</small>}
              </td>
              <td>
                <Badge
                  value={v.status === "active" ? "rejected" : "draft"}
                  label={v.status === "active" ? "Действует" : "Отменено"}
                />
                {v.cancel_reason && <small>{v.cancel_reason}</small>}
                {v.can_appeal && (
                  <small>апелляция до {date(v.appeal_until)}</small>
                )}
              </td>
              <td>
                {role === "admin" && v.status === "active" && (
                  <div className="award-actions">
                    <Button size="sm" variant="outline" onClick={() => onCancel(v)}>
                      Отменить
                    </Button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty text="Нарушений нет" hint="Решения о нарушениях фиксирует федерация." />
      )}
    </State>
  );
}

export function Appeals() {
  const { role } = useAuth();
  const [tab, setTab] = useState("appeals");
  const [dialog, setDialog] = useState<any>(null);
  const close = () => setDialog(null);
  const applicant = role === "athlete" || role === "coach";
  const titles: Record<string, string> = {
    appeal: "Подать апелляцию",
    decide: "Рассмотрение апелляции",
    violation: "Зафиксировать нарушение",
    cancel: "Отмена решения о нарушении",
  };
  return (
    <>
      <PageTitle
        title="Апелляции и нарушения"
        description="Обжалование результатов протокола и решений о нарушениях; удовлетворённая апелляция исправляет протокол новой редакцией."
      >
        {(role === "admin" || role === "ministry") && tab === "appeals" && (
          <ExportButtons base="/exports/appeals" name="appeals" />
        )}
        {applicant && (
          <Button onClick={() => setDialog({ kind: "appeal" })}>
            <Scale size={16} /> Подать апелляцию
          </Button>
        )}
        {role === "admin" && tab === "violations" && (
          <Button onClick={() => setDialog({ kind: "violation" })}>
            <Plus size={16} /> Зафиксировать нарушение
          </Button>
        )}
      </PageTitle>
      <section className="panel">
        {role !== "judge" && (
          <div className="tabs">
            {[
              ["appeals", "Апелляции"],
              ["violations", "Нарушения"],
            ].map(([k, t]) => (
              <button
                className={tab === k ? "active" : ""}
                key={k}
                onClick={() => setTab(k)}
              >
                {t}
              </button>
            ))}
          </div>
        )}
        {tab === "appeals" ? (
          <AppealsTab onDecide={(a: any) => setDialog({ kind: "decide", item: a })} />
        ) : (
          <ViolationsTab
            onCancel={(v: any) => setDialog({ kind: "cancel", item: v })}
          />
        )}
      </section>
      {role === "judge" && (
        <div className="rating-explainer">
          <ShieldAlert size={22} />
          <p>
            Показаны апелляции на протоколы соревнований, где вы работаете в
            судейской коллегии. Решение принимает федерация.
          </p>
        </div>
      )}
      <Dialog
        open={!!dialog}
        onOpenChange={close}
        title={dialog ? titles[dialog.kind] : ""}
        wide={dialog?.kind === "decide"}
      >
        {dialog?.kind === "appeal" && <AppealForm onDone={close} />}
        {dialog?.kind === "decide" && (
          <DecisionForm appeal={dialog.item} onDone={close} />
        )}
        {dialog?.kind === "violation" && <ViolationForm onDone={close} />}
        {dialog?.kind === "cancel" && (
          <CancelForm violation={dialog.item} onDone={close} />
        )}
      </Dialog>
    </>
  );
}
