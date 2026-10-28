import { useState } from "react";
import { Award, Banknote, CheckCircle2, FileText, Users } from "lucide-react";
import { useAction, useAuth, useData } from "./state";
import { date, levels, plain } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
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

const statusNames: Record<string, string> = {
  candidate: "Претендент",
  nominated: "В ходатайстве",
  awarded: "Премия присуждена",
  rejected: "Отказано",
};
// reuse the badge colours of applications
const statusBadges: Record<string, string> = {
  candidate: "draft",
  nominated: "pending",
  awarded: "approved",
  rejected: "rejected",
};
const rubles = (n: number) => n.toLocaleString("ru-RU") + " ₽";
// January: petitions for the previous year are still being prepared
const defaultYear = () => {
  const d = new Date();
  return d.getMonth() === 0 ? d.getFullYear() - 1 : d.getFullYear();
};

// dialogs ask for what the target status needs: a reason or an order number
const dialogs: Record<string, any> = {
  rejected: {
    title: "Отказ в премии",
    field: "comment",
    label: "Причина отказа",
    button: "Отказать",
  },
  awarded: {
    title: "Премия присуждена",
    field: "order_number",
    label: "Номер распоряжения Губернатора",
    button: "Сохранить",
  },
  cancel: {
    title: "Отмена присуждения",
    field: "comment",
    label: "Причина отмены",
    button: "Вернуть в ходатайство",
    status: "nominated",
  },
};

function StatusDialog({ year, item, kind, onDone }: any) {
  const action = useAction();
  const d = dialogs[kind];
  const [value, setValue] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: "put",
            url: `/governor-awards/${year}/${item.athlete_id}`,
            data: {
              status: d.status || kind,
              comment: d.field === "comment" ? value : item.comment,
              ...(d.field === "order_number" ? { order_number: value } : {}),
            },
          });
          onDone();
        } catch {}
      }}
    >
      <p className="award-dialog-name">
        <strong>{plain(item.full_name)}</strong>
        {rubles(item.amount)}
      </p>
      <Field label={d.label}>
        {d.field === "comment" ? (
          <textarea
            required
            maxLength={2000}
            rows={3}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        ) : (
          <input
            required
            maxLength={120}
            placeholder="Например, 45-рп"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
      </Field>
      <Button disabled={action.isPending}>{d.button}</Button>
    </form>
  );
}

function Actions({ year, item, onDialog }: any) {
  const action = useAction();
  const set = (status: string) =>
    action.mutate({
      method: "put",
      url: `/governor-awards/${year}/${item.athlete_id}`,
      data: { status, comment: item.comment },
    });
  const forward = (
    <Button
      size="sm"
      disabled={action.isPending || !item.eligible}
      title={item.eligible ? "" : "Претендент не может быть выдвинут"}
      onClick={() => set("nominated")}
    >
      В ходатайство
    </Button>
  );
  const reject = (
    <Button size="sm" variant="outline" onClick={() => onDialog("rejected")}>
      Отказать
    </Button>
  );
  const back = (label: string) => (
    <Button
      size="sm"
      variant="outline"
      disabled={action.isPending}
      onClick={() => set("candidate")}
    >
      {label}
    </Button>
  );
  return (
    <div className="award-actions">
      {item.status === "candidate" && (
        <>
          {forward}
          {reject}
        </>
      )}
      {item.status === "nominated" && (
        <>
          <Button size="sm" onClick={() => onDialog("awarded")}>
            Присуждена
          </Button>
          {reject}
          {back("Исключить")}
        </>
      )}
      {item.status === "rejected" && (
        <>
          {forward}
          {back("Вернуть")}
        </>
      )}
      {item.status === "awarded" && (
        <Button size="sm" variant="outline" onClick={() => onDialog("cancel")}>
          Отменить
        </Button>
      )}
    </div>
  );
}

function Achievement({ a, more }: any) {
  if (!a) return <>—</>;
  return (
    <>
      <strong>
        {a.place} место · {plain(a.title)}
      </strong>
      <small>
        {levels[a.level]} · {date(a.date)}
        {a.team_name && ` · команда «${a.team_name}»`}
      </small>
      {more > 0 && (
        <small className="award-more">
          ещё призовых результатов: {more}
        </small>
      )}
    </>
  );
}

function AmountEditor({ r }: any) {
  const [v, setV] = useState(r);
  const action = useAction();
  return (
    <form
      className="rule-editor award-rule"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate({
          method: "put",
          url: "/governor-award-rules/" + r.level,
          data: { first: +v.first, second: +v.second, third: +v.third },
        });
      }}
    >
      <strong>{levels[r.level]}</strong>
      {["first", "second", "third"].map((k, i) => (
        <Field label={i + 1 + " место, ₽"} key={k}>
          <input
            type="number"
            required
            min="0"
            max="10000000"
            step="500"
            value={v[k]}
            onChange={(e) => setV({ ...v, [k]: e.target.value })}
          />
        </Field>
      ))}
      <Button size="sm" variant="outline" disabled={action.isPending}>
        Сохранить
      </Button>
    </form>
  );
}

function Amounts() {
  const { role } = useAuth();
  const rules = useData("/governor-award-rules");
  const order = [
    "russian_championship",
    "russian_junior",
    "interregional",
    "regional",
  ];
  const sorted = (rules.data || [])
    .slice()
    .sort((a: any, b: any) => order.indexOf(a.level) - order.indexOf(b.level));
  return (
    <section className="panel section-gap">
      <div className="panel-heading">
        <div>
          <h2>Справочник сумм</h2>
          <p>
            Сумма премии за призовое место по уровню соревнования. Нулевая
            сумма — место не даёт права на премию.
          </p>
        </div>
      </div>
      <State query={rules}>
        {role === "admin" ? (
          sorted.map((r: any) => <AmountEditor r={r} key={r.level} />)
        ) : (
          <Table heads={["Уровень", "1 место", "2 место", "3 место"]}>
            {sorted.map((r: any) => (
              <tr key={r.level}>
                <td>{levels[r.level]}</td>
                {[r.first, r.second, r.third].map((n, i) => (
                  <td key={i}>{n ? rubles(n) : "—"}</td>
                ))}
              </tr>
            ))}
          </Table>
        )}
      </State>
    </section>
  );
}

export function GovernorAwards() {
  const { role } = useAuth();
  const [year, setYear] = useState(defaultYear());
  const [status, setStatus] = useState("");
  const [dialog, setDialog] = useState<any>(null);
  const valid = year >= 2000 && year <= new Date().getFullYear();
  const q = useData("/governor-awards?year=" + year, valid);
  const items = (q.data?.items || []).filter(
    (i: any) => !status || i.status === status,
  );
  const totals = q.data?.totals;
  const editable = role === "admin";
  return (
    <>
      <PageTitle
        title="Премии Губернатора"
        description="Претенденты по опубликованным протоколам, ходатайство и решения по каждому спортсмену."
      >
        <ExportButtons
          base={"/exports/governor-awards?year=" + year}
          name={"governor-awards-" + year}
        />
      </PageTitle>
      <div className="rating-explainer">
        <Award size={22} />
        <p>
          <strong>
            Ходатайство за {year} год подаётся до{" "}
            {q.data ? date(q.data.deadline) : "1 февраля"}.
          </strong>
          Претенденты отбираются автоматически: призовые места на
          соревнованиях, для уровня которых в справочнике указана сумма.
          Премия назначается один раз в год по лучшему достижению, сумма
          фиксируется при включении в ходатайство. Отстранённые спортсмены
          не выдвигаются.
        </p>
      </div>
      <State query={q}>
        <div className="stats-grid section-gap">
          <Stat label="Претендентов" value={totals?.candidate} icon={Users} />
          <Stat
            label="В ходатайстве"
            value={totals && totals.nominated + totals.awarded}
            icon={FileText}
          />
          <Stat
            label="Присуждено"
            value={totals?.awarded}
            icon={CheckCircle2}
            note={totals && rubles(totals.awarded_amount)}
          />
          <Stat
            label="Сумма ходатайства"
            value={totals && rubles(totals.nominated_amount)}
            icon={Banknote}
          />
        </div>
      </State>
      <section className="panel">
        <div className="toolbar">
          <Field label="Год достижений">
            <input
              type="number"
              min="2000"
              max={new Date().getFullYear()}
              value={year}
              onChange={(e) => setYear(+e.target.value)}
            />
          </Field>
          <Field label="Статус">
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Все</option>
              {Object.entries(statusNames).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <State query={q}>
          {items.length ? (
            <Table
              heads={[
                "Спортсмен",
                "Достижение",
                "Сумма",
                "Статус",
                ...(editable ? [""] : []),
              ]}
            >
              {items.map((i: any) => (
                <tr key={i.athlete_id}>
                  <td>
                    <strong>{plain(i.full_name)}</strong>
                    <small>{i.organization || i.municipality}</small>
                  </td>
                  <td>
                    <Achievement
                      a={i.basis}
                      more={Math.max(0, i.achievements.length - 1)}
                    />
                  </td>
                  <td className="award-amount">{rubles(i.amount)}</td>
                  <td>
                    <Badge
                      value={statusBadges[i.status]}
                      label={statusNames[i.status]}
                    />
                    {i.order_number && (
                      <small>Распоряжение № {i.order_number}</small>
                    )}
                    {i.comment && <small>{i.comment}</small>}
                    {i.suspended && (
                      <small className="award-warning">Отстранён</small>
                    )}
                    {!i.eligible && !i.suspended && (
                      <small className="award-warning">
                        Достижение не подтверждается протоколами
                      </small>
                    )}
                  </td>
                  {editable && (
                    <td>
                      <Actions
                        year={year}
                        item={i}
                        onDialog={(kind: string) => setDialog({ kind, item: i })}
                      />
                    </td>
                  )}
                </tr>
              ))}
            </Table>
          ) : (
            <Empty
              text={
                status ? "Нет записей с этим статусом" : "Претендентов за год нет"
              }
              hint="Претенденты появятся после публикации протоколов с призовыми местами."
            />
          )}
        </State>
      </section>
      <Amounts />
      <Dialog
        open={!!dialog}
        onOpenChange={() => setDialog(null)}
        title={dialog ? dialogs[dialog.kind].title : ""}
      >
        {dialog && (
          <StatusDialog
            year={year}
            item={dialog.item}
            kind={dialog.kind}
            onDone={() => setDialog(null)}
          />
        )}
      </Dialog>
    </>
  );
}
