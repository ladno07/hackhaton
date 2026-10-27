import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Download,
  FileText,
  Gavel,
  List,
  MapPin,
  Plus,
  Send,
  Settings2,
  Trash2,
  Trophy,
  Upload,
  Users,
  X,
} from "lucide-react";
import { useAction, useAuth, useData, useToast } from "./state";
import {
  ageHint,
  ageLimits,
  ageRules,
  date,
  download,
  errorText,
  fileSize,
  formats,
  groupLabel,
  levels,
  statuses,
  today,
} from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import {
  Badge,
  Empty,
  ExportButtons,
  Field,
  PageTitle,
  SearchBox,
  State,
  Table,
} from "./components/shared";
import { CompetitionTeams, TeamResultsEditor } from "./competition-teams";
const REGULATION_ACCEPT = ".pdf,.docx,.doc,.odt";
const REGULATION_MAX_MB = 10;
const regulationForm = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return form;
};
function tooBig(file: File | null) {
  return !!file && file.size > REGULATION_MAX_MB * 1024 * 1024;
}
export function Regulation({ comp }: any) {
  const { role } = useAuth();
  const action = useAction();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const file = comp.regulation_file;
  const editable = role === "admin" && comp.state !== "published";
  return (
    <div className="regulation">
      {file ? (
        <button
          type="button"
          className="text-link"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await download(
                "/competitions/" + comp.id + "/regulation",
                file.filename,
              );
            } catch (e) {
              toast(errorText(e), true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Download size={14} />
          Скачать положение
        </button>
      ) : (
        !comp.regulation_url && <strong>Не прикреплено</strong>
      )}
      {file && (
        <small>
          {file.filename} · {fileSize(file.size)} · {date(file.uploaded_at)}
        </small>
      )}
      {comp.regulation_url && (
        <a
          href={comp.regulation_url}
          target="_blank"
          rel="noreferrer"
          className="text-link"
        >
          Открыть по ссылке <ArrowRight size={14} />
        </a>
      )}
      {editable && (
        <div className="row-actions">
          <label className="text-link regulation-upload">
            <Upload size={14} />
            {file ? "Заменить файл" : "Загрузить файл"}
            <input
              type="file"
              accept={REGULATION_ACCEPT}
              disabled={action.isPending}
              onChange={(e) => {
                const f = e.target.files?.[0] || null;
                e.target.value = "";
                if (!f) return;
                if (tooBig(f))
                  return toast(
                    `Размер положения не должен превышать ${REGULATION_MAX_MB} МБ`,
                    true,
                  );
                action.mutate({
                  method: "put",
                  url: "/competitions/" + comp.id + "/regulation",
                  data: regulationForm(f),
                });
              }}
            />
          </label>
          {file && (
            <button
              type="button"
              className="text-link text-danger"
              disabled={action.isPending}
              onClick={() =>
                confirm("Удалить файл положения?") &&
                action.mutate({
                  method: "delete",
                  url: "/competitions/" + comp.id + "/regulation",
                })
              }
            >
              <Trash2 size={14} />
              Удалить
            </button>
          )}
        </div>
      )}
    </div>
  );
}
export function AgeHint({ check, self }: any) {
  const hint = ageHint(check, self);
  if (!hint) return null;
  return (
    <div className={"age-hint" + (hint.ok ? "" : " age-hint-no")} role="status">
      <strong>{hint.title}</strong>
      {hint.text}
      {self && check.reason === "sex_missing" && (
        <>
          {" "}
          <Link to="/profile">Заполнить профиль</Link>
        </>
      )}
    </div>
  );
}
export function CompetitionForm({ initial, onSaved }: any) {
  const meta = useData("/metadata");
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [v, setV] = useState<any>(
    initial
      ? Object.fromEntries(
          [
            "entry_mode",
            "team_min",
            "team_max",
            "team_rating",
            "title",
            "discipline_id",
            "type_id",
            "start_date",
            "end_date",
            "deadline",
            "location",
            "format",
            "status",
            "min_age",
            "max_age",
            "calendar_plan",
            "calendar_number",
            "regulation_url",
          ]
            .map((k) => [k, initial[k]])
            .concat([
              [
                "age_group_ids",
                (initial.age_groups || []).map((g: any) => g.id),
              ],
            ]),
        )
      : {
          entry_mode: "individual",
          team_min: 2,
          team_max: 3,
          team_rating: false,
          title: "",
          discipline_id: 1,
          type_id: 1,
          start_date: today(),
          end_date: today(),
          deadline: today(),
          location: "Оренбург",
          format: "onsite",
          status: "regional",
          min_age: 0,
          max_age: 100,
          age_group_ids: [],
          calendar_plan: "Оренбургская область",
          calendar_number: "",
          regulation_url: null,
        },
  );
  const set = (k: string, val: any) => setV({ ...v, [k]: val });
  const groups = (meta.data?.age_groups || []).filter(
    (g: any) => !g.discipline_id || g.discipline_id === v.discipline_id,
  );
  const picked = groups.filter((g: any) => v.age_group_ids.includes(g.id));
  const ratingLevel = meta.data?.rating_levels?.[v.status]?.[v.type_id];
  const field = (k: string, label: string, type = "text", props: any = {}) => (
    <Field label={label}>
      <input
        required
        type={type}
        value={v[k] ?? ""}
        onChange={(e) =>
          set(k, type === "number" ? +e.target.value : e.target.value)
        }
        {...props}
      />
    </Field>
  );
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          const saved = await action.mutateAsync({
            method: initial ? "put" : "post",
            url: "/competitions" + (initial ? "/" + initial.id : ""),
            data: {
              ...v,
              // groups of another discipline are dropped when it changes
              age_group_ids: picked.map((g: any) => g.id),
              regulation_url: v.regulation_url || null,
            },
          });
          if (file)
            await action.mutateAsync({
              method: "put",
              url: "/competitions/" + saved.id + "/regulation",
              data: regulationForm(file),
            });
          onSaved();
        } catch {}
      }}
    >
      {field("title", "Название соревнования")}
      <Field label="Зачёт">
        <select
          value={v.entry_mode}
          onChange={(e) => set("entry_mode", e.target.value)}
        >
          <option value="individual">Личный</option>
          <option value="team">Командный</option>
        </select>
      </Field>
      {v.entry_mode === "team" && (
        <>
          <div className="form-grid">
            {field("team_min", "Минимум участников в команде", "number", {
              min: 1,
              max: 50,
            })}
            {field("team_max", "Максимум участников в команде", "number", {
              min: v.team_min,
              max: 50,
            })}
          </div>
          <label className="check-line">
            <input
              type="checkbox"
              checked={v.team_rating}
              onChange={(e) => set("team_rating", e.target.checked)}
            />
            Начислять каждому участнику личный рейтинг за место команды
          </label>
        </>
      )}
      <div className="form-grid">
        <Field label="Дисциплина">
          <select
            value={v.discipline_id}
            onChange={(e) => set("discipline_id", +e.target.value)}
          >
            {meta.data?.disciplines.map((d: any) => (
              <option value={d.id} key={d.id}>
                {d.short_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Тип соревнования">
          <select
            value={v.type_id}
            onChange={(e) => set("type_id", +e.target.value)}
          >
            {meta.data?.types.map((t: any) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="form-grid">
        {field("start_date", "Дата начала", "date")}
        {field("end_date", "Дата окончания", "date")}
      </div>
      <div className="form-grid">
        {field("deadline", "Заявки до", "date")}
        {field("location", "Место / площадка")}
      </div>
      <div className="form-grid">
        <Field label="Формат">
          <select
            value={v.format}
            onChange={(e) => set("format", e.target.value)}
          >
            {Object.entries(formats).map(([k, s]) => (
              <option value={k} key={k}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Статус"
          hint={ratingLevel && "Уровень для рейтинга: " + levels[ratingLevel]}
        >
          <select
            value={v.status}
            onChange={(e) =>
              setV({
                ...v,
                status: e.target.value,
                calendar_plan:
                  e.target.value === "regional"
                    ? "Оренбургская область"
                    : "ЕКП",
              })
            }
          >
            {Object.entries(statuses).map(([k, s]) => (
              <option value={k} key={k}>
                {s}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="field" role="group" aria-labelledby="age-groups-label">
        <span id="age-groups-label">Возрастные группы</span>
        <div className="group-picker">
          {groups.map((g: any) => (
            <label className="check-line" key={g.id}>
              <input
                type="checkbox"
                checked={v.age_group_ids.includes(g.id)}
                onChange={(e) =>
                  set(
                    "age_group_ids",
                    e.target.checked
                      ? [...v.age_group_ids, g.id]
                      : v.age_group_ids.filter((x: number) => x !== g.id),
                  )
                }
              />
              <span title={ageRules[g.age_rule]}>{groupLabel(g)}</span>
            </label>
          ))}
        </div>
        <small>
          {picked.length
            ? "Допуск определяется группами, общий диапазон рассчитается автоматически"
            : "Группы не выбраны: допуск по диапазону возраста на дату старта"}
        </small>
      </div>
      {!picked.length && (
        <div className="form-grid">
          {field("min_age", "Минимальный возраст", "number", {
            min: 0,
            max: 100,
          })}
          {field("max_age", "Максимальный возраст", "number", {
            min: 0,
            max: 100,
          })}
        </div>
      )}
      <div className="form-grid">
        {field("calendar_plan", "Календарный план", "text", { readOnly: true })}
        {field("calendar_number", "Номер в календарном плане")}
      </div>
      <div className="form-grid">
        <Field
          label="Файл положения"
          hint={
            initial?.regulation_file && !file
              ? "Прикреплён: " + initial.regulation_file.filename
              : `PDF, DOCX, DOC или ODT, до ${REGULATION_MAX_MB} МБ`
          }
        >
          <input
            type="file"
            accept={REGULATION_ACCEPT}
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </Field>
        <Field label="Ссылка на положение (необязательно)">
          <input
            type="url"
            value={v.regulation_url || ""}
            placeholder="https://…"
            onChange={(e) => set("regulation_url", e.target.value)}
          />
        </Field>
      </div>
      <div className="form-footer">
        <Button disabled={action.isPending || tooBig(file)}>
          {initial ? "Сохранить" : "Создать черновик"}
        </Button>
      </div>
    </form>
  );
}
export function Competitions() {
  const { role } = useAuth();
  const [search, setSearch] = useState("");
  const [disc, setDisc] = useState("");
  const [state, setState] = useState("");
  const [eligible, setEligible] = useState(false);
  const [show, setShow] = useState(false);
  const meta = useData("/metadata");
  const query = useData(
    "/competitions?" +
      new URLSearchParams({
        q: search,
        ...(disc ? { discipline_id: disc } : {}),
        ...(state ? { state } : {}),
        eligible: String(eligible),
      }),
  );
  return (
    <>
      <PageTitle
        eyebrow="СЕЗОН / КАЛЕНДАРЬ"
        title="Соревнования"
        description="Выбирайте свой старт. Подавайте заявки. Достигайте большего."
      >
        {role === "admin" && (
          <Button onClick={() => setShow(true)}>
            <Plus size={17} />
            Создать соревнование
          </Button>
        )}
      </PageTitle>
      <div className="competition-summary">
        <span>
          <CalendarDays size={18} />
          <strong>{query.data?.length || 0}</strong> событий в календаре
        </span>
        <span>
          <i className="green-dot" /> Все шесть дисциплин спортивного
          программирования
        </span>
      </div>
      <section className="panel">
        <div className="toolbar">
          <SearchBox
            value={search}
            onChange={setSearch}
            placeholder="Поиск соревнования"
          />
          <select
            aria-label="Статус соревнования"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option value="">Все статусы</option>
            {role === "admin" && <option value="draft">Черновики</option>}
            <option value="open">Приём заявок</option>
            <option value="closed">Приём закрыт</option>
            <option value="published">Результаты</option>
          </select>
          {role === "athlete" && (
            <label className="check-line">
              <input
                type="checkbox"
                checked={eligible}
                onChange={(e) => setEligible(e.target.checked)}
              />
              Подходят по возрасту
            </label>
          )}
        </div>
        <div className="discipline-tabs">
          <button className={!disc ? "active" : ""} onClick={() => setDisc("")}>
            Все дисциплины
          </button>
          {meta.data?.disciplines.map((d: any) => (
            <button
              key={d.id}
              className={disc === String(d.id) ? "active" : ""}
              onClick={() => setDisc(String(d.id))}
            >
              {d.short_name}
            </button>
          ))}
        </div>
        <State query={query}>
          {query.data?.length ? (
            <div className="competition-list">
              {query.data.map((c: any) => (
                <Link
                  key={c.id}
                  to={"/competitions/" + c.id}
                  className="competition-card"
                >
                  <div className="competition-date">
                    <strong>{new Date(c.start_date).getDate()}</strong>
                    <span>
                      {new Date(c.start_date).toLocaleDateString("ru-RU", {
                        month: "long",
                      })}
                    </span>
                    <small>{new Date(c.start_date).getFullYear()}</small>
                  </div>
                  <div className="competition-main">
                    <div className="competition-tags">
                      <span className="discipline-label">{c.discipline}</span>
                      <span>{statuses[c.status]}</span>
                      <span>{c.type}</span>
                    </div>
                    <h2>{c.title.replace("Демо · ", "")}</h2>
                    <div className="competition-meta">
                      <span>
                        <MapPin size={14} />
                        {c.location}
                      </span>
                      <span>
                        <Users size={14} />
                        {ageLimits(c)}
                      </span>
                      {c.age_check && (
                        <span
                          className={
                            c.eligible ? "text-success" : "text-danger"
                          }
                        >
                          {c.eligible
                            ? "Вы проходите по возрасту"
                            : "Не проходите по возрасту"}
                        </span>
                      )}
                      <span>{formats[c.format]}</span>
                    </div>
                  </div>
                  <div className="competition-end">
                    <Badge value={c.state} />
                    <small>
                      {c.state === "open"
                        ? "До " + date(c.deadline)
                        : c.participants + " участников"}
                    </small>
                    <span className="event-open">
                      Подробнее <ArrowRight size={16} />
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <Empty text="Соревнования не найдены" />
          )}
        </State>
      </section>
      <Dialog
        open={show}
        onOpenChange={setShow}
        title="Новое соревнование"
        wide
      >
        <CompetitionForm onSaved={() => setShow(false)} />
      </Dialog>
    </>
  );
}
function ResultsEditor(props: any) {
  return props.comp.entry_mode === "team" ? (
    <TeamResultsEditor {...props} />
  ) : (
    <IndividualResultsEditor {...props} />
  );
}
function IndividualResultsEditor({ comp, correction, onDone }: any) {
  const approved = comp.applications.filter(
    (a: any) => a.status === "approved",
  );
  const [results, setResults] = useState<any[]>(
    correction
      ? comp.results.map((r: any) => ({ ...r, team_name: r.team_name || "" }))
      : approved.map((a: any, i: number) => ({
          athlete_id: a.athlete_id,
          full_name: a.full_name,
          team_name: "",
          place: i + 1,
          score: 0,
        })),
  );
  const [reason, setReason] = useState("");
  const action = useAction();
  const update = (i: number, k: string, val: any) =>
    setResults(results.map((v, j) => (j === i ? { ...v, [k]: val } : v)));
  const teams = [
    ...new Set(results.map((r) => r.team_name.trim()).filter(Boolean)),
  ];
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            method: correction ? "put" : "post",
            url: "/competitions/" + comp.id + "/results",
            data: {
              results: results.map(
                ({ athlete_id, place, score, team_name }) => ({
                  athlete_id,
                  place,
                  score,
                  team_name: team_name.trim() || null,
                }),
              ),
              ...(correction ? { reason } : {}),
            },
          });
          onDone?.();
        } catch {}
      }}
    >
      <div className="inline-note">
        Протокол включает всех одобренных участников. Одинаковые места
        допускаются: после N участников на одном месте следующее место
        пропускает N − 1 позиций (1, 1, 3). Для командного зачёта укажите
        название команды: у её участников должны совпадать место и баллы, а
        команда занимает одну позицию.{" "}
        {correction
          ? "Исправление сохранится новой редакцией, рейтинг пересчитается, участники получат уведомление."
          : "После публикации результаты и рейтинг обновятся автоматически."}
      </div>
      <datalist id={"teams-" + comp.id}>
        {teams.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
      <Table heads={["Спортсмен", "Команда", "Место", "Баллы"]}>
        {results.map((r: any, i: number) => (
          <tr key={r.athlete_id}>
            <td>
              <Link
                className="text-link"
                to={`/athletes/${r.athlete_id}/profile`}
              >
                {r.full_name}
              </Link>
            </td>
            <td>
              <input
                aria-label={"Команда: " + r.full_name}
                list={"teams-" + comp.id}
                maxLength={120}
                placeholder="Личный зачёт"
                value={r.team_name}
                onChange={(e) => update(i, "team_name", e.target.value)}
              />
            </td>
            <td>
              <input
                aria-label={"Место: " + r.full_name}
                type="number"
                min="1"
                max={results.length}
                required
                value={r.place}
                onChange={(e) => update(i, "place", +e.target.value)}
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
                onChange={(e) => update(i, "score", +e.target.value)}
              />
            </td>
          </tr>
        ))}
      </Table>
      <div className="panel-padding">
        {correction && (
          <Field label="Основание исправления">
            <textarea
              required
              minLength={5}
              maxLength={2000}
              rows={2}
              placeholder="Например: ошибка в подсчёте баллов, решение апелляционной комиссии"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        )}
        <div className="button-row">
          <Button disabled={action.isPending || !results.length}>
            <Trophy size={16} />
            {correction
              ? `Опубликовать редакцию ${comp.protocol_version + 1}`
              : "Опубликовать результаты и протокол"}
          </Button>
          {correction && (
            <Button type="button" variant="outline" onClick={onDone}>
              Отмена
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}
const changeText = (c: any) =>
  [
    c.old_place !== c.place && `место ${c.old_place} → ${c.place}`,
    c.old_score !== c.score && `баллы ${c.old_score} → ${c.score}`,
    c.old_team_name !== c.team_name &&
      `команда ${c.old_team_name || "—"} → ${c.team_name || "—"}`,
  ]
    .filter(Boolean)
    .join(", ");
function ProtocolHistory({ id }: any) {
  const history = useData(`/competitions/${id}/protocol-versions`);
  return (
    <State query={history}>
      {history.data?.length > 0 && (
        <div className="protocol-history">
          <h3>История редакций</h3>
          {history.data.map((v: any) => (
            <div className="protocol-version" key={v.version}>
              <div className="panel-heading">
                <div>
                  <strong>Редакция {v.version}</strong>
                  <p>
                    {date(v.created_at)}
                    {v.author ? " · " + v.author : ""} · {v.reason}
                  </p>
                </div>
                <ExportButtons
                  base={`/exports/protocol/${id}?version=${v.version}`}
                  name={`protocol-${id}-v${v.version}`}
                />
              </div>
              {v.changes.length > 0 && (
                <ul>
                  {v.changes.map((c: any) => (
                    <li key={c.result_id}>
                      {c.full_name}: {changeText(c)}
                    </li>
                  ))}
                </ul>
              )}
              {v.rank_warnings.length > 0 && (
                <div className="inline-error">
                  Исправление затронуло основания разрядов, проверьте их:{" "}
                  {v.rank_warnings.join("; ")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </State>
  );
}
// Документы о судействе: состав коллегии — федерации, Минспорту и судьям
// коллегии; отчёт главного судьи — после публикации протокола.
export function judgingDocs(comp: any, role: string, user: any) {
  const seat = comp.judges.find((j: any) => j.judge_id === user?.judge_id);
  const reader = role === "admin" || role === "ministry";
  const docs: [string, string][] = [];
  if (comp.judges.length && (reader || (role === "judge" && seat)))
    docs.push(["panel", "Состав судейской коллегии"]);
  if (
    comp.state === "published" &&
    (reader || (role === "judge" && seat?.position === "Главный судья"))
  )
    docs.push(["chief-report", "Отчёт главного судьи"]);
  return docs;
}
export function CompetitionDetail() {
  const { id } = useParams();
  const { role, user } = useAuth();
  const query = useData("/competitions/" + id);
  const athletes = useData(
    "/athletes?mine=true",
    ["athlete", "coach"].includes(role),
  );
  const judges = useData("/judges", role === "admin");
  const action = useAction();
  const [searchParams] = useSearchParams();
  const [selectedTab, setTab] = useState(
    searchParams.get("tab") === "teams" ? "teams" : "",
  );
  const [edit, setEdit] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const [athlete, setAthlete] = useState("");
  const [judge, setJudge] = useState("");
  const [position, setPosition] = useState("Главный судья");
  const comp = query.data;
  const tab =
    selectedTab || (comp?.entry_mode === "team" ? "teams" : "applications");
  const teamProtocol = comp?.results.some((r: any) => r.team_name);
  const eligibility = useData(
    `/competitions/${id}/eligibility?athlete_id=${athlete}`,
    role === "coach" && !!athlete,
  );
  const [comments, setComments] = useState<Record<string, string>>({});
  return (
    <>
      <Link to="/competitions" className="back-link">
        <ArrowLeft size={16} />К календарю
      </Link>
      <State query={query}>
        {comp && (
          <>
            <PageTitle
              eyebrow={comp.discipline?.toUpperCase()}
              title={comp.title.replace("Демо · ", "")}
              description={`${date(comp.start_date)} — ${date(comp.end_date)} · ${comp.location}`}
            >
              <Badge value={comp.state} />
              {role === "admin" && comp.state === "draft" && (
                <>
                  <Button variant="outline" onClick={() => setEdit(true)}>
                    <Settings2 size={16} />
                    Изменить
                  </Button>
                  <Button
                    disabled={action.isPending}
                    onClick={() =>
                      action.mutate({
                        method: "patch",
                        url: "/competitions/" + id + "/state",
                        data: { state: "open" },
                      })
                    }
                  >
                    Открыть приём заявок
                  </Button>
                </>
              )}
              {role === "admin" && comp.state === "open" && (
                <Button
                  variant="outline"
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({
                      method: "patch",
                      url: "/competitions/" + id + "/state",
                      data: { state: "closed" },
                    })
                  }
                >
                  Закрыть приём заявок
                </Button>
              )}
              {role === "admin" && comp.state === "closed" && (
                <Button
                  variant="outline"
                  onClick={() =>
                    action.mutate({
                      method: "patch",
                      url: "/competitions/" + id + "/state",
                      data: { state: "open" },
                    })
                  }
                >
                  Возобновить приём
                </Button>
              )}
            </PageTitle>
            {comp.entry_mode === "team" && (
              <div className="inline-note">
                Командный зачёт · {comp.team_min}–{comp.team_max} участников.
                Приглашения, состав и общая заявка — во вкладке{" "}
                <button
                  type="button"
                  className="text-link"
                  onClick={() => setTab("teams")}
                >
                  «Команды»
                </button>
                .
              </div>
            )}
            <div className="event-details-grid">
              <div className="panel event-info">
                <div>
                  <span>Формат</span>
                  <strong>{formats[comp.format]}</strong>
                </div>
                <div>
                  <span>Статус и тип</span>
                  <strong>
                    {statuses[comp.status]} · {comp.type}
                  </strong>
                </div>
                <div>
                  <span>Уровень для рейтинга</span>
                  <strong>{levels[comp.rating_level]}</strong>
                </div>
                <div>
                  <span>
                    {comp.age_groups.length
                      ? "Возрастные группы"
                      : "Возраст на дату старта"}
                  </span>
                  <strong>
                    {comp.age_groups.length
                      ? comp.age_groups.map((g: any) => (
                          <span key={g.id} className="block">
                            {groupLabel(g)}
                          </span>
                        ))
                      : ageLimits(comp)}
                  </strong>
                  {comp.age_groups.some((g: any) => g.age_rule === "year") && (
                    <small>Возраст считается по году рождения</small>
                  )}
                </div>
                <div>
                  <span>Приём заявок до</span>
                  <strong>{date(comp.deadline)}</strong>
                </div>
                <div>
                  <span>Календарный план</span>
                  <strong>
                    {comp.calendar_plan} № {comp.calendar_number}
                  </strong>
                </div>
                <div>
                  <span>Положение</span>
                  <Regulation comp={comp} />
                </div>
              </div>
              {comp.entry_mode !== "team" &&
                ["athlete", "coach"].includes(role) && (
                  <form
                    className="panel apply-panel"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      try {
                        await action.mutateAsync({
                          url: "/competitions/" + id + "/applications",
                          data: {
                            athlete_id:
                              role === "athlete" ? user.athlete_id : +athlete,
                          },
                        });
                      } catch {}
                    }}
                  >
                    <span className="eyebrow">ВАШ СЛЕДУЮЩИЙ СТАРТ</span>
                    <h2>Участвовать в соревновании</h2>
                    <p>
                      Федерация рассмотрит заявку и сообщит решение в личном
                      кабинете.
                    </p>
                    {role === "athlete" && (
                      <AgeHint check={comp.age_check} self />
                    )}
                    {role === "coach" && eligibility.data && (
                      <AgeHint check={eligibility.data} />
                    )}
                    {role === "coach" && (
                      <Field label="Спортсмен">
                        <select
                          required
                          value={athlete}
                          onChange={(e) => setAthlete(e.target.value)}
                        >
                          <option value="">Выберите подопечного</option>
                          {athletes.data?.map((a: any) => (
                            <option key={a.id} value={a.id}>
                              {a.full_name}
                            </option>
                          ))}
                        </select>
                      </Field>
                    )}
                    <Button
                      disabled={
                        action.isPending ||
                        comp.state !== "open" ||
                        comp.eligible === false ||
                        (role === "coach" &&
                          eligibility.data?.eligible === false) ||
                        comp.deadline < today() ||
                        (role === "athlete" &&
                          comp.applications.some(
                            (a: any) => a.athlete_id === user.athlete_id,
                          ))
                      }
                    >
                      <Send size={16} />
                      {comp.applications.some(
                        (a: any) => a.athlete_id === user.athlete_id,
                      )
                        ? "Заявка уже подана"
                        : comp.age_check?.reason === "sex_missing"
                          ? "Укажите пол в профиле"
                          : comp.eligible === false
                            ? "Не подходит по возрасту"
                            : comp.state === "open"
                              ? "Подать заявку"
                              : "Приём завершён"}
                    </Button>
                  </form>
                )}
            </div>
            <section className="panel section-gap">
              <div className="tabs">
                {[
                  ...(comp.entry_mode === "team" ? [["teams", "Команды"]] : []),
                  [
                    "applications",
                    role === "admin" || role === "ministry"
                      ? "Заявки участников"
                      : "Мои заявки",
                  ],
                  ["results", "Результаты и протокол"],
                  ["judges", "Судейская коллегия"],
                ].map(([k, v]) => (
                  <button
                    className={tab === k ? "active" : ""}
                    key={k}
                    onClick={() => setTab(k)}
                  >
                    {v}
                  </button>
                ))}
              </div>
              {tab === "teams" && comp.entry_mode === "team" && (
                <CompetitionTeams key={comp.id} comp={comp} />
              )}
              {tab === "applications" &&
                (comp.applications.length ? (
                  <Table
                    heads={[
                      "Спортсмен",
                      "Группа",
                      "Дата заявки",
                      "Статус",
                      "Решение",
                    ]}
                  >
                    {comp.applications.map((a: any) => (
                      <tr key={a.id}>
                        <td>
                          <Link
                            className="text-link"
                            to={`/athletes/${a.athlete_id}/profile`}
                          >
                            <strong>{a.full_name}</strong>
                          </Link>
                        </td>
                        <td>{a.age_group || "—"}</td>
                        <td>{date(a.created_at)}</td>
                        <td>
                          <Badge value={a.status} />
                          <small>{a.comment}</small>
                        </td>
                        <td>
                          {role === "admin" &&
                          a.status === "pending" &&
                          comp.state !== "published" ? (
                            <div className="moderation-actions">
                              <input
                                aria-label={"Комментарий для " + a.full_name}
                                placeholder="Комментарий к решению"
                                value={comments[a.id] || ""}
                                onChange={(e) =>
                                  setComments({
                                    ...comments,
                                    [a.id]: e.target.value,
                                  })
                                }
                              />
                              <div className="row-actions">
                                <Button
                                  size="sm"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    action.mutate({
                                      method: "patch",
                                      url: "/applications/" + a.id,
                                      data: {
                                        status: "approved",
                                        comment: comments[a.id] || "",
                                      },
                                    })
                                  }
                                >
                                  <Check size={14} />
                                  Одобрить
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={action.isPending}
                                  onClick={() =>
                                    action.mutate({
                                      method: "patch",
                                      url: "/applications/" + a.id,
                                      data: {
                                        status: "rejected",
                                        comment: comments[a.id] || "",
                                      },
                                    })
                                  }
                                >
                                  <X size={14} />
                                  Отклонить
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <span>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <Empty
                    text="Заявок пока нет"
                    hint="Поданные заявки появятся здесь."
                  />
                ))}
              {tab === "results" &&
                (comp.state === "published" && correcting ? (
                  <ResultsEditor
                    comp={comp}
                    correction
                    onDone={() => setCorrecting(false)}
                  />
                ) : comp.state === "published" ? (
                  <>
                    <div className="panel-heading">
                      <div>
                        <h2>Итоговый протокол</h2>
                        {comp.protocol_version > 1 && (
                          <p>Редакция {comp.protocol_version}</p>
                        )}
                      </div>
                      <div className="button-row">
                        {role === "admin" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setCorrecting(true)}
                          >
                            Исправить протокол
                          </Button>
                        )}
                        <ExportButtons
                          base={"/exports/protocol/" + id}
                          name={"protocol-" + id}
                        />
                      </div>
                    </div>
                    <Table
                      heads={
                        teamProtocol
                          ? ["Место", "Команда", "Спортсмен", "Баллы"]
                          : ["Место", "Спортсмен", "Баллы"]
                      }
                    >
                      {comp.results.map((r: any) => (
                        <tr key={r.id}>
                          <td>
                            <span
                              className={r.place <= 3 ? "place-medal" : "place"}
                            >
                              {r.place}
                            </span>
                          </td>
                          {teamProtocol && <td>{r.team_name || "—"}</td>}
                          <td>
                            <Link
                              className="text-link"
                              to={`/athletes/${r.athlete_id}/profile`}
                            >
                              {r.full_name}
                            </Link>
                          </td>
                          <td>{r.score}</td>
                        </tr>
                      ))}
                    </Table>
                    <ProtocolHistory id={id} />
                  </>
                ) : role === "admin" && comp.state === "closed" ? (
                  <ResultsEditor
                    key={comp.applications
                      .map((a: any) => a.id + a.status)
                      .join(",")}
                    comp={comp}
                  />
                ) : (
                  <Empty
                    text="Протокол ещё не опубликован"
                    hint={
                      role === "admin"
                        ? "Закройте приём заявок, чтобы внести результаты."
                        : "Результаты появятся после завершения соревнования."
                    }
                  />
                ))}
              {tab === "judges" && (
                <>
                  {role === "admin" && comp.state !== "published" && (
                    <form
                      className="inline-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        action.mutate({
                          url: "/competitions/" + id + "/judges",
                          data: { judge_id: +judge, position },
                        });
                      }}
                    >
                      <Field label="Судья">
                        <select
                          required
                          value={judge}
                          onChange={(e) => setJudge(e.target.value)}
                        >
                          <option value="">Выберите судью</option>
                          {judges.data?.map((j: any) => (
                            <option value={j.id} key={j.id}>
                              {j.full_name}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Судейская должность">
                        <input
                          required
                          value={position}
                          onChange={(e) => setPosition(e.target.value)}
                        />
                      </Field>
                      <Button disabled={action.isPending}>Назначить</Button>
                    </form>
                  )}
                  {judgingDocs(comp, role, user).length > 0 && (
                    <div className="judging-docs">
                      {judgingDocs(comp, role, user).map(([kind, label]) => (
                        <div key={kind}>
                          <span>{label}</span>
                          <ExportButtons
                            base={`/exports/${kind}/${comp.id}`}
                            name={`${kind}-${comp.id}`}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                  {comp.judges.length ? (
                    <Table heads={["Судья", "Должность"]}>
                      {comp.judges.map((j: any) => (
                        <tr key={j.judge_id}>
                          <td>{j.full_name}</td>
                          <td>{j.position}</td>
                        </tr>
                      ))}
                    </Table>
                  ) : (
                    <Empty text="Коллегия ещё не назначена" />
                  )}
                </>
              )}
            </section>
            <Dialog
              open={edit}
              onOpenChange={setEdit}
              title="Редактировать соревнование"
              wide
            >
              <CompetitionForm initial={comp} onSaved={() => setEdit(false)} />
            </Dialog>
          </>
        )}
      </State>
    </>
  );
}
