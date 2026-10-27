import { useState } from "react";
import { ArrowRight, Dumbbell, Plus } from "lucide-react";
import { useAction, useAuth, useData } from "./state";
import { date, sexNames, today } from "./lib";
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

const stageShort: Record<string, string> = {
  np: "НП",
  ut: "УТ",
  ssm: "ССМ",
  vsm: "ВСМ",
};
const plain = (s: string) => s?.replace("Демо · ", "");
const value = (v: number | null, unit: string) =>
  v == null ? "—" : `${v} ${unit}`;

function Progress({ passed, total }: any) {
  return (
    <div className="standard-progress" title={`${passed} из ${total}`}>
      <span>
        <i style={{ width: total ? (passed / total) * 100 + "%" : 0 }} />
      </span>
      <small>
        {passed} из {total}
      </small>
    </div>
  );
}

function StageLine({ s }: any) {
  return (
    <span className="stage-line">
      {s.stage ? stageShort[s.stage] : s.training_stage || "Не указан"}
      {s.target && (
        <>
          <ArrowRight size={13} /> <b>{stageShort[s.target]}</b>
        </>
      )}
    </span>
  );
}

function ReadyBadge({ s }: any) {
  return s.ready ? (
    <Badge value="approved" label="Готов к переводу" />
  ) : (
    <Badge value={s.target ? "pending" : "ended"} label={s.target ? "Не готов" : "Последний этап"} />
  );
}

function RecordForm({ state }: any) {
  const action = useAction();
  const [form, setForm] = useState<any>({
    standard_id: "",
    value: "",
    tested_on: today(),
    comment: "",
  });
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));
  const chosen = state.recordable.find((s: any) => s.id === +form.standard_id);
  const stages = [state.target, state.stage].filter(Boolean);
  return (
    <form
      className="standard-record"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            url: `/attestation/${state.athlete_id}/results`,
            data: { ...form, standard_id: +form.standard_id, value: +form.value },
          });
          setForm((f: any) => ({ ...f, value: "", comment: "" }));
        } catch {}
      }}
    >
      <h3>Записать результат сдачи</h3>
      <div className="form-grid">
        <Field label="Норматив">
          <select
            required
            value={form.standard_id}
            onChange={(e) => set("standard_id", e.target.value)}
          >
            <option value="">Выберите…</option>
            {stages.map((stage: string) => (
              <optgroup
                key={stage}
                label={
                  (stage === state.target ? "Для перевода на " : "Текущий этап ") +
                  stageShort[stage]
                }
              >
                {state.recordable
                  .filter((s: any) => s.stage === stage)
                  .map((s: any) => (
                    <option key={s.id} value={s.id}>
                      {s.category_name} · {s.name}
                      {s.sex ? ` (${sexNames[s.sex].toLowerCase()})` : ""} ·{" "}
                      {s.threshold_text}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </Field>
        <Field label={"Результат" + (chosen ? ", " + chosen.unit : "")}>
          <input
            required
            type="number"
            min="0"
            step="any"
            value={form.value}
            onChange={(e) => set("value", e.target.value)}
          />
        </Field>
        <Field label="Дата сдачи">
          <input
            required
            type="date"
            max={today()}
            value={form.tested_on}
            onChange={(e) => set("tested_on", e.target.value)}
          />
        </Field>
        <Field label="Комментарий">
          <input
            maxLength={2000}
            placeholder="Например: контрольное тестирование, 2-я попытка"
            value={form.comment}
            onChange={(e) => set("comment", e.target.value)}
          />
        </Field>
      </div>
      <Button disabled={action.isPending}>Записать</Button>
    </form>
  );
}

function TransferForm({ state }: any) {
  const action = useAction();
  const [form, setForm] = useState({ order_number: "", decided_on: today(), comment: "" });
  return (
    <form
      className="standard-record"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            url: `/attestation/${state.athlete_id}/transfer`,
            data: { ...form, to_stage: state.target },
          });
        } catch {}
      }}
    >
      <h3>
        {state.stage ? "Перевод" : "Зачисление"} на этап «{state.target_name}»
      </h3>
      <div className="form-grid">
        <Field label="Номер приказа">
          <input
            required
            maxLength={120}
            value={form.order_number}
            onChange={(e) => setForm({ ...form, order_number: e.target.value })}
          />
        </Field>
        <Field label="Дата приказа">
          <input
            required
            type="date"
            max={today()}
            value={form.decided_on}
            onChange={(e) => setForm({ ...form, decided_on: e.target.value })}
          />
        </Field>
      </div>
      <Field label="Комментарий">
        <input
          maxLength={2000}
          value={form.comment}
          onChange={(e) => setForm({ ...form, comment: e.target.value })}
        />
      </Field>
      <p className="inline-hint">
        Этап в профиле спортсмена изменится, результаты нормативов и разряд
        сохранятся в основании перевода.
      </p>
      <Button disabled={action.isPending}>Оформить перевод</Button>
    </form>
  );
}

function ResultsTable({ results, withName = false }: any) {
  const { role } = useAuth();
  const action = useAction();
  return (
    <Table
      heads={[
        "Дата",
        ...(withName ? ["Спортсмен"] : []),
        "Норматив",
        "Результат",
        "Порог на дату",
        "Итог",
        "",
      ]}
    >
      {results.map((r: any) => (
        <tr key={r.id} className={r.expired ? "standard-expired" : ""}>
          <td>
            {date(r.tested_on)}
            {r.expired && <small>старше 12 месяцев</small>}
          </td>
          {withName && <td>{plain(r.full_name)}</td>}
          <td>
            <strong>{r.standard}</strong>
            <small>
              {r.category_name} · этап {r.stage_short}
              {r.comment ? " · " + r.comment : ""}
            </small>
          </td>
          <td className="standard-value">{value(r.value, r.unit)}</td>
          <td className="standard-threshold">{r.threshold_text}</td>
          <td>
            <Badge
              value={r.passed ? "approved" : "rejected"}
              label={r.passed ? "Выполнен" : "Не выполнен"}
            />
            {r.recorded_by_name && <small>{plain(r.recorded_by_name)}</small>}
          </td>
          <td>
            {role === "admin" && (
              <Button
                size="sm"
                variant="outline"
                disabled={action.isPending}
                onClick={() =>
                  confirm("Удалить ошибочно внесённый результат?") &&
                  action.mutate({
                    method: "delete",
                    url: `/attestation/results/${r.id}`,
                  })
                }
              >
                Удалить
              </Button>
            )}
          </td>
        </tr>
      ))}
    </Table>
  );
}

function TransfersList({ transfers }: any) {
  return (
    <div className="standard-transfers">
      {transfers.map((t: any) => (
        <div className="simple-row" key={t.id}>
          <span>
            {t.from_stage || "Без этапа"} <ArrowRight size={13} />{" "}
            <b>{t.to_stage_name}</b>
          </span>
          <small>
            Приказ № {t.order_number} от {date(t.decided_on)}
            {t.basis?.standards?.length
              ? ` · нормативов в основании: ${t.basis.standards.length}`
              : ""}
            {t.basis?.rank ? ` · разряд ${t.basis.rank}` : ""}
          </small>
        </div>
      ))}
    </div>
  );
}

function AthleteCard({ athleteId }: any) {
  const q = useData(`/attestation/${athleteId}`);
  const s = q.data;
  return (
    <State query={q}>
      {s && (
        <div className="standard-card">
          <div className="standard-summary">
            <div>
              <small>Спортсмен</small>
              <strong>{plain(s.full_name)}</strong>
              <span>{s.sex ? sexNames[s.sex] : "Пол не указан"}</span>
            </div>
            <div>
              <small>Этап</small>
              <strong>
                <StageLine s={s} />
              </strong>
              <span>{s.target_name || s.stage_name}</span>
            </div>
            <div>
              <small>Нормативы</small>
              <strong>
                {s.passed} из {s.total}
              </strong>
              <Progress passed={s.passed} total={s.total} />
            </div>
            <div>
              <small>Разряд</small>
              <strong>{s.rank || "Нет"}</strong>
              <span>
                {s.rank_required ? `нужен «${s.rank_required}»` : "не требуется"}
              </span>
            </div>
            <div>
              <small>Итог</small>
              <ReadyBadge s={s} />
              {s.ready_since && <span>с {date(s.ready_since)}</span>}
            </div>
          </div>
          {s.blockers.length > 0 && (
            <ul className="standard-blockers">
              {s.blockers.map((b: string) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
          {s.target && (
            <>
              <h3>Нормативы для перевода на этап «{s.target_name}»</h3>
              {s.items.length ? (
                <Table heads={["Вид", "Норматив", "Порог", "Лучший результат", "Итог"]}>
                  {s.items.map((i: any) => (
                    <tr key={i.id}>
                      <td>{i.category_name}</td>
                      <td>
                        <strong>{i.name}</strong>
                        <small>
                          {i.sex ? sexNames[i.sex] : "Для всех"}
                          {i.discipline ? " · " + i.discipline : ""}
                        </small>
                      </td>
                      <td className="standard-threshold">{i.threshold_text}</td>
                      <td className="standard-value">
                        {value(i.best_value, i.unit)}
                        {i.best_on && (
                          <small>
                            {date(i.best_on)} · попыток: {i.attempts}
                          </small>
                        )}
                      </td>
                      <td>
                        <Badge
                          value={i.met ? "approved" : i.best_value == null ? "ended" : "rejected"}
                          label={
                            i.met
                              ? "Выполнен"
                              : i.best_value == null
                                ? "Нет результата"
                                : "Не выполнен"
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </Table>
              ) : (
                <Empty
                  text="Нормативов нет"
                  hint="Федерация ещё не внесла нормативы этого этапа в справочник."
                />
              )}
              <p className="inline-hint">
                Учитывается лучший результат за последние {s.valid_days} дней,
                он сравнивается с действующим порогом справочника по этапу,
                дисциплинам и полу спортсмена.
              </p>
            </>
          )}
          {s.can_transfer && <TransferForm state={s} />}
          {s.can_record && s.recordable.length > 0 && <RecordForm state={s} />}
          <h3>История сдачи</h3>
          {s.results.length ? (
            <ResultsTable results={s.results} />
          ) : (
            <Empty text="Результатов пока нет" hint="Результаты вносят тренер или федерация." />
          )}
          {s.transfers.length > 0 && (
            <>
              <h3>Переводы между этапами</h3>
              <TransfersList transfers={s.transfers} />
            </>
          )}
        </div>
      )}
    </State>
  );
}

function ReadinessTab({ onOpen }: any) {
  const [filter, setFilter] = useState("");
  const q = useData("/attestation");
  const items = (q.data || []).filter(
    (i: any) => !filter || String(i.ready) === filter,
  );
  return (
    <>
      <div className="toolbar standard-toolbar">
        <Field label="Готовность">
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">Все</option>
            <option value="true">Готовы к переводу</option>
            <option value="false">Не готовы</option>
          </select>
        </Field>
      </div>
      <State query={q}>
        {items.length ? (
          <Table heads={["Спортсмен", "Этап", "Нормативы", "Разряд", "Итог", ""]}>
            {items.map((s: any) => (
              <tr key={s.athlete_id}>
                <td>
                  <strong>{plain(s.full_name)}</strong>
                  <small>{s.sex ? sexNames[s.sex] : "Пол не указан"}</small>
                </td>
                <td>
                  <StageLine s={s} />
                </td>
                <td>
                  <Progress passed={s.passed} total={s.total} />
                </td>
                <td>
                  {s.rank || "—"}
                  {s.rank_required && <small>нужен {s.rank_required}</small>}
                </td>
                <td className="appeal-reason">
                  <ReadyBadge s={s} />
                  {!s.ready && s.target && <small>{s.blockers.join("; ")}</small>}
                </td>
                <td>
                  <div className="award-actions">
                    <Button size="sm" variant="outline" onClick={() => onOpen(s)}>
                      Открыть
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty text="Спортсменов нет" hint="Здесь появятся спортсмены, которых вы ведёте." />
        )}
      </State>
    </>
  );
}

function StandardForm({ standard, onDone }: any) {
  const meta = useData("/metadata");
  const action = useAction();
  const [form, setForm] = useState<any>(
    standard
      ? { ...standard, sex: standard.sex || "", discipline_id: standard.discipline_id || "" }
      : {
          stage: "np",
          category: "ofp",
          name: "",
          unit: "",
          better: "higher",
          threshold: "",
          sex: "",
          discipline_id: "",
          source: "",
          sort_order: 0,
        },
  );
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const keys = ["stage", "category", "name", "unit", "better", "source"];
        try {
          await action.mutateAsync({
            method: standard ? "put" : "post",
            url: standard ? `/standards/${standard.id}` : "/standards",
            data: {
              ...Object.fromEntries(keys.map((k) => [k, form[k]])),
              threshold: +form.threshold,
              sort_order: +form.sort_order || 0,
              sex: form.sex || null,
              discipline_id: form.discipline_id ? +form.discipline_id : null,
            },
          });
          onDone();
        } catch {}
      }}
    >
      <div className="form-grid">
        <Field label="Этап" hint="Норматив для зачисления или перевода на этап">
          <select value={form.stage} onChange={(e) => set("stage", e.target.value)}>
            {Object.entries(stageShort).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Вид подготовки">
          <select value={form.category} onChange={(e) => set("category", e.target.value)}>
            <option value="ofp">ОФП — общая физическая</option>
            <option value="sfp">СФП — специальная физическая</option>
          </select>
        </Field>
      </div>
      <Field label="Норматив">
        <input
          required
          minLength={3}
          maxLength={200}
          placeholder="Например: Бег 30 м"
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </Field>
      <div className="form-grid">
        <Field label="Единица">
          <input
            required
            maxLength={40}
            placeholder="с, раз, см"
            value={form.unit}
            onChange={(e) => set("unit", e.target.value)}
          />
        </Field>
        <Field label="Зачёт">
          <select value={form.better} onChange={(e) => set("better", e.target.value)}>
            <option value="higher">Не меньше порога (≥)</option>
            <option value="lower">Не больше порога (≤), например время</option>
          </select>
        </Field>
        <Field label="Порог">
          <input
            required
            type="number"
            min="0"
            step="any"
            value={form.threshold}
            onChange={(e) => set("threshold", e.target.value)}
          />
        </Field>
        <Field label="Пол">
          <select value={form.sex} onChange={(e) => set("sex", e.target.value)}>
            <option value="">Для всех</option>
            <option value="male">Юноши, мужчины</option>
            <option value="female">Девушки, женщины</option>
          </select>
        </Field>
        <Field label="Дисциплина">
          <select
            value={form.discipline_id}
            onChange={(e) => set("discipline_id", e.target.value)}
          >
            <option value="">Все дисциплины</option>
            {(meta.data?.disciplines || []).map((d: any) => (
              <option key={d.id} value={d.id}>
                {d.short_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Порядок">
          <input
            type="number"
            min="0"
            value={form.sort_order}
            onChange={(e) => set("sort_order", e.target.value)}
          />
        </Field>
      </div>
      <Field label="Источник" hint="Приказ об утверждении ФССП, приложение и пункт">
        <input
          maxLength={2000}
          value={form.source}
          onChange={(e) => set("source", e.target.value)}
        />
      </Field>
      {standard && (
        <p className="inline-hint">
          Новый порог сразу применяется к расчёту готовности; внесённые
          результаты сохраняют порог на дату сдачи.
        </p>
      )}
      <Button disabled={action.isPending}>Сохранить</Button>
    </form>
  );
}

function CatalogTab({ onEdit }: any) {
  const { role } = useAuth();
  const [stage, setStage] = useState("");
  const [category, setCategory] = useState("");
  const [sex, setSex] = useState("");
  const [archived, setArchived] = useState(false);
  const params = new URLSearchParams(
    Object.entries({ stage, category, sex, archived: archived ? "true" : "" }).filter(
      ([, v]) => v,
    ),
  ).toString();
  const q = useData("/standards" + (params ? "?" + params : ""));
  const action = useAction();
  return (
    <>
      <div className="toolbar standard-toolbar">
        <Field label="Этап">
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">Все</option>
            {Object.entries(stageShort).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Вид">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">ОФП и СФП</option>
            <option value="ofp">ОФП</option>
            <option value="sfp">СФП</option>
          </select>
        </Field>
        <Field label="Пол">
          <select value={sex} onChange={(e) => setSex(e.target.value)}>
            <option value="">Все</option>
            <option value="male">Юноши, мужчины</option>
            <option value="female">Девушки, женщины</option>
          </select>
        </Field>
        {role === "admin" && (
          <label className="check-line">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />
            Архив
          </label>
        )}
      </div>
      <State query={q}>
        {q.data?.length ? (
          <Table heads={["Этап", "Вид", "Норматив", "Пол", "Порог", ""]}>
            {q.data.map((s: any) => (
              <tr key={s.id}>
                <td>
                  <strong>{s.stage_short}</strong>
                  <small>{s.stage_name}</small>
                </td>
                <td>{s.category_name}</td>
                <td className="appeal-reason">
                  <strong>{s.name}</strong>
                  <small>
                    {s.discipline || "Все дисциплины"}
                    {s.source ? " · " + plain(s.source) : ""}
                  </small>
                </td>
                <td>{s.sex ? sexNames[s.sex] : "Для всех"}</td>
                <td className="standard-value">{s.threshold_text}</td>
                <td>
                  {role === "admin" && (
                    <div className="award-actions">
                      {!s.archived_at && (
                        <Button size="sm" variant="outline" onClick={() => onEdit(s)}>
                          Изменить
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={action.isPending}
                        onClick={() =>
                          action.mutate({
                            url: `/standards/${s.id}/${s.archived_at ? "restore" : "archive"}`,
                          })
                        }
                      >
                        {s.archived_at ? "Восстановить" : "В архив"}
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty
            text={archived ? "Архив пуст" : "Нормативов нет"}
            hint="Нормативы ОФП и СФП по этапам вносит федерация."
          />
        )}
      </State>
    </>
  );
}

function HistoryTab() {
  const q = useData("/attestation/history");
  return (
    <State query={q}>
      {q.data && (
        <div className="standard-card">
          <h3>Переводы между этапами</h3>
          {q.data.transfers.length ? (
            <Table heads={["Дата", "Спортсмен", "Перевод", "Приказ"]}>
              {q.data.transfers.map((t: any) => (
                <tr key={t.id}>
                  <td>{date(t.decided_on)}</td>
                  <td>{plain(t.full_name)}</td>
                  <td>
                    {t.from_stage || "Без этапа"} → <b>{t.to_stage_name}</b>
                  </td>
                  <td>
                    № {t.order_number}
                    {t.comment && <small>{t.comment}</small>}
                  </td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty text="Переводов нет" hint="Перевод оформляет федерация, когда нормативы выполнены." />
          )}
          <h3>Сдача нормативов</h3>
          {q.data.results.length ? (
            <ResultsTable results={q.data.results} withName />
          ) : (
            <Empty text="Результатов нет" hint="Результаты вносят тренер или федерация." />
          )}
        </div>
      )}
    </State>
  );
}

export function Standards() {
  const { role } = useAuth();
  const [tab, setTab] = useState("readiness");
  const [dialog, setDialog] = useState<any>(null);
  const close = () => setDialog(null);
  const mine = useData("/attestation", role === "athlete");
  const tabs = [
    ["readiness", role === "athlete" ? "Моя аттестация" : "Готовность к переводу"],
    ["catalog", "Справочник нормативов"],
    ["history", "История"],
  ];
  return (
    <>
      <PageTitle
        title="Нормативы и аттестация"
        description="Нормативы ОФП и СФП по федеральному стандарту спортивной подготовки: сравнение результатов с порогами по этапу, дисциплине и полу и готовность к переводу на следующий этап."
      >
        {(role === "admin" || role === "ministry") && tab === "readiness" && (
          <ExportButtons base="/exports/attestation" name="attestation" />
        )}
        {role === "admin" && tab === "catalog" && (
          <Button onClick={() => setDialog({ kind: "standard" })}>
            <Plus size={16} /> Добавить норматив
          </Button>
        )}
      </PageTitle>
      <section className="panel">
        <div className="tabs">
          {tabs.map(([k, t]) => (
            <button className={tab === k ? "active" : ""} key={k} onClick={() => setTab(k)}>
              {t}
            </button>
          ))}
        </div>
        {tab === "readiness" &&
          (role === "athlete" ? (
            <State query={mine}>
              {mine.data?.[0] ? (
                <AthleteCard athleteId={mine.data[0].athlete_id} />
              ) : (
                <Empty text="Профиль спортсмена не найден" />
              )}
            </State>
          ) : (
            <ReadinessTab onOpen={(s: any) => setDialog({ kind: "athlete", item: s })} />
          ))}
        {tab === "catalog" && (
          <CatalogTab onEdit={(s: any) => setDialog({ kind: "standard", item: s })} />
        )}
        {tab === "history" && <HistoryTab />}
      </section>
      <div className="rating-explainer">
        <Dumbbell size={22} />
        <p>
          Для перевода на этап нужно выполнить все его нормативы — общие для
          вида спорта и по дисциплинам, которыми занимается спортсмен, — с
          порогами для его пола. Для этапов ССМ и ВСМ дополнительно нужен
          разряд КМС и МС. Перевод оформляет федерация приказом.
        </p>
      </div>
      <Dialog
        open={!!dialog}
        onOpenChange={close}
        title={
          dialog?.kind === "athlete"
            ? "Аттестация спортсмена"
            : dialog?.item
              ? "Изменение норматива"
              : "Новый норматив"
        }
        wide={dialog?.kind === "athlete"}
      >
        {dialog?.kind === "athlete" && <AthleteCard athleteId={dialog.item.athlete_id} />}
        {dialog?.kind === "standard" && (
          <StandardForm standard={dialog.item} onDone={close} />
        )}
      </Dialog>
    </>
  );
}
