import { useState } from "react";
import { Copy, KeyRound, Plus, Upload } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api, date, errorText, plain } from "./lib";
import { useAction, useData, useToast } from "./state";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import { Badge, Empty, Field, PageTitle, State, Table } from "./components/shared";

const tabs = [
  ["tokens", "Токены доступа"],
  ["webhooks", "Вебхуки"],
  ["import", "Импорт результатов"],
  ["api", "Описание API"],
];
const deliveryStatus: Record<string, [string, string]> = {
  pending: ["pending", "В очереди"],
  delivered: ["approved", "Доставлено"],
  failed: ["rejected", "Ошибка"],
};
const dateTime = (s: string) =>
  s ? new Date(s).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" }) : "—";

function useMeta() {
  const meta = useData("/integrations/meta");
  const names = (list: string) =>
    Object.fromEntries((meta.data?.[list] || []).map((x: any) => [x.id, x.name]));
  return { meta, scopes: names("scopes"), events: names("events") };
}

// Secrets are shown once: the server keeps only a hash of the token.
function Secret({ label, value, note }: any) {
  const toast = useToast();
  return (
    <div className="integration-secret">
      <Field label={label} hint={note}>
        <div className="integration-secret-value">
          <input readOnly value={value} onFocus={(e) => e.target.select()} />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              navigator.clipboard
                .writeText(value)
                .then(() => toast("Скопировано"), () => toast("Скопируйте вручную", true))
            }
          >
            <Copy size={14} /> Копировать
          </Button>
        </div>
      </Field>
    </div>
  );
}

function Checks({ options, value, onChange }: any) {
  return (
    <div className="role-checkboxes integration-checks">
      {Object.entries(options).map(([k, n]: any) => (
        <label className="check-line" key={k}>
          <input
            type="checkbox"
            checked={value.includes(k)}
            onChange={(e) =>
              onChange(e.target.checked ? [...value, k] : value.filter((x: string) => x !== k))
            }
          />
          <span>
            {n} <code>{k}</code>
          </span>
        </label>
      ))}
    </div>
  );
}

function TokenForm({ scopes, onCreated }: any) {
  const action = useAction();
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<string[]>(["competitions:read"]);
  const [expires, setExpires] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          onCreated(
            await action.mutateAsync({
              url: "/integrations/tokens",
              data: { name, scopes: chosen, expires_on: expires || null },
            }),
          );
        } catch {}
      }}
    >
      <Field label="Название" hint="Для какой системы токен, например «Сайт федерации»">
        <input required minLength={3} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="field">
        <span>Права</span>
        <Checks options={scopes} value={chosen} onChange={setChosen} />
      </div>
      <Field label="Действует до" hint="Пусто — бессрочно, пока токен не отозван">
        <input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
      </Field>
      <div className="form-footer">
        <Button disabled={action.isPending || !chosen.length}>Выпустить токен</Button>
      </div>
    </form>
  );
}

function TokensTab() {
  const tokens = useData("/integrations/tokens");
  const { scopes } = useMeta();
  const action = useAction();
  const [dialog, setDialog] = useState(false);
  const [created, setCreated] = useState<any>(null);
  const close = () => {
    setDialog(false);
    setCreated(null);
  };
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Токены доступа</h2>
          <p>
            Внешняя система передаёт токен в заголовке Authorization. Токен
            даёт только отмеченные права и действует от имени выпустившего
            сотрудника, пока у него есть роль федерации.
          </p>
        </div>
        <Button onClick={() => setDialog(true)}>
          <Plus size={16} /> Новый токен
        </Button>
      </div>
      <State query={tokens}>
        {tokens.data?.length ? (
          <Table heads={["Название", "Права", "Выпущен", "Последний запрос", "Статус", ""]}>
            {tokens.data.map((t: any) => (
              <tr key={t.id}>
                <td>
                  <strong>{t.name}</strong>
                  <small>
                    <code>{t.prefix}…</code>
                  </small>
                </td>
                <td>
                  <div className="integration-tags">
                    {t.scopes.map((s: string) => (
                      <span key={s} title={scopes[s]}>{s}</span>
                    ))}
                  </div>
                </td>
                <td>
                  {date(t.created_at)}
                  <small>{plain(t.author)}</small>
                </td>
                <td>{dateTime(t.last_used_at)}</td>
                <td>
                  {t.active ? (
                    <Badge value="active" label={t.expires_on ? "До " + date(t.expires_on) : "Действует"} />
                  ) : (
                    <Badge value="rejected" label={t.revoked_at ? "Отозван" : "Истёк"} />
                  )}
                </td>
                <td>
                  {!t.revoked_at && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={action.isPending}
                      onClick={() =>
                        confirm(`Отозвать токен «${t.name}»? Система, которая им пользуется, потеряет доступ.`) &&
                        action.mutate({ method: "delete", url: "/integrations/tokens/" + t.id })
                      }
                    >
                      Отозвать
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty text="Токенов пока нет" hint="Выпустите токен для внешней системы." />
        )}
      </State>
      <Dialog open={dialog} onOpenChange={close} title={created ? "Токен выпущен" : "Новый токен"}>
        {created ? (
          <>
            <Secret
              label={created.name}
              value={created.token}
              note="Скопируйте токен сейчас: он показывается один раз и не хранится в системе."
            />
            <div className="form-footer">
              <Button onClick={close}>Готово</Button>
            </div>
          </>
        ) : (
          <TokenForm scopes={scopes} onCreated={setCreated} />
        )}
      </Dialog>
    </>
  );
}

function WebhookForm({ events, onCreated }: any) {
  const action = useAction();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [chosen, setChosen] = useState<string[]>(Object.keys(events));
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          onCreated(
            await action.mutateAsync({ url: "/integrations/webhooks", data: { name, url, events: chosen } }),
          );
        } catch {}
      }}
    >
      <Field label="Название">
        <input required minLength={3} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Адрес получателя" hint="POST-запрос с JSON. Адреса внутренней сети не принимаются.">
        <input
          required
          type="url"
          placeholder="https://example.org/orencode/webhook"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </Field>
      <div className="field">
        <span>События</span>
        <Checks options={events} value={chosen} onChange={setChosen} />
      </div>
      <div className="form-footer">
        <Button disabled={action.isPending || !chosen.length}>Добавить вебхук</Button>
      </div>
    </form>
  );
}

function Deliveries({ hook }: any) {
  const log = useData(`/integrations/webhooks/${hook.id}/deliveries`);
  const action = useAction();
  return (
    <State query={log}>
      {log.data?.length ? (
        <div className="integration-deliveries">
          {log.data.map((d: any) => {
            const [badge, label] = deliveryStatus[d.status];
            return (
              <details key={d.id}>
                <summary>
                  <Badge value={badge} label={label} />
                  <code>{d.event}</code>
                  <span>{dateTime(d.created_at)}</span>
                  <small>
                    попыток: {d.attempts}
                    {d.response_status ? ` · HTTP ${d.response_status}` : ""}
                    {d.status === "pending" && d.attempts > 0 && ` · повтор в ${dateTime(d.next_attempt_at)}`}
                  </small>
                </summary>
                {d.last_error && <p className="inline-error">{d.last_error}</p>}
                <pre>{JSON.stringify(d.payload, null, 2)}</pre>
                {d.status !== "delivered" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={action.isPending}
                    onClick={() => action.mutate({ url: `/integrations/deliveries/${d.id}/retry` })}
                  >
                    Отправить снова
                  </Button>
                )}
              </details>
            );
          })}
        </div>
      ) : (
        <Empty text="Событий пока не было" hint="Нажмите «Проверить», чтобы отправить тестовое событие." />
      )}
    </State>
  );
}

function WebhooksTab() {
  const hooks = useData("/integrations/webhooks");
  const { events } = useMeta();
  const action = useAction();
  const [dialog, setDialog] = useState<any>(null);
  const [secret, setSecret] = useState<any>(null);
  const close = () => {
    setDialog(null);
    setSecret(null);
  };
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Вебхуки</h2>
          <p>
            Система сама сообщает внешним сервисам о событиях. Каждый запрос
            подписан секретом вебхука; при ошибке отправка повторяется через
            1, 5, 15, 60 и 240 минут.
          </p>
        </div>
        <Button onClick={() => setDialog({ kind: "new" })}>
          <Plus size={16} /> Новый вебхук
        </Button>
      </div>
      <State query={hooks}>
        {hooks.data?.length ? (
          <Table heads={["Получатель", "События", "Доставка", "Включён", ""]}>
            {hooks.data.map((w: any) => (
              <tr key={w.id}>
                <td>
                  <strong>{w.name}</strong>
                  <small className="integration-url">{w.url}</small>
                </td>
                <td>
                  <div className="integration-tags">
                    {w.events.map((e: string) => (
                      <span key={e} title={events[e]}>{e}</span>
                    ))}
                  </div>
                </td>
                <td>
                  {w.deliveries.delivered} доставлено
                  <small>
                    {w.deliveries.pending ? `в очереди ${w.deliveries.pending}` : ""}
                    {w.deliveries.failed ? ` · ошибок ${w.deliveries.failed}` : ""}
                  </small>
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label="Вебхук включён"
                    checked={w.active}
                    onChange={(e) =>
                      action.mutate({
                        method: "patch",
                        url: "/integrations/webhooks/" + w.id,
                        data: { active: e.target.checked },
                      })
                    }
                  />
                </td>
                <td>
                  <div className="award-actions">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={action.isPending || !w.active}
                      onClick={() => action.mutate({ url: `/integrations/webhooks/${w.id}/test` })}
                    >
                      Проверить
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setDialog({ kind: "log", hook: w })}>
                      Журнал
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={action.isPending}
                      onClick={async () => {
                        if (!confirm("Сменить секрет? Получателю нужно будет обновить ключ проверки подписи.")) return;
                        try {
                          setSecret(await action.mutateAsync({ url: `/integrations/webhooks/${w.id}/secret` }));
                          setDialog({ kind: "secret" });
                        } catch {}
                      }}
                    >
                      Секрет
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={action.isPending}
                      onClick={() =>
                        confirm(`Удалить вебхук «${w.name}» вместе с журналом доставки?`) &&
                        action.mutate({ method: "delete", url: "/integrations/webhooks/" + w.id })
                      }
                    >
                      Удалить
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty text="Вебхуков пока нет" hint="Добавьте адрес, на который отправлять события." />
        )}
      </State>
      <Dialog
        open={!!dialog}
        onOpenChange={close}
        wide={dialog?.kind === "log"}
        title={
          dialog?.kind === "log"
            ? "Журнал доставки · " + dialog.hook.name
            : secret
              ? "Секрет вебхука"
              : "Новый вебхук"
        }
      >
        {dialog?.kind === "log" && <Deliveries hook={dialog.hook} />}
        {dialog && dialog.kind !== "log" &&
          (secret ? (
            <>
              <Secret
                label={secret.name}
                value={secret.secret}
                note="Секрет нужен получателю для проверки заголовка X-OrenCode-Signature. Он показывается один раз."
              />
              <div className="form-footer">
                <Button onClick={close}>Готово</Button>
              </div>
            </>
          ) : (
            <WebhookForm events={events} onCreated={setSecret} />
          ))}
      </Dialog>
    </>
  );
}

function ImportTab() {
  const competitions = useData("/competitions");
  const qc = useQueryClient();
  const toast = useToast();
  const [compId, setCompId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const ready = (competitions.data || []).filter(
    (c: any) => c.state === "published" || (c.state === "closed" && c.end_date <= new Date().toLocaleDateString("en-CA")),
  );
  const comp = ready.find((c: any) => String(c.id) === compId);
  const send = async (dryRun: boolean) => {
    if (!file || !comp) return;
    const form = new FormData();
    form.append("file", file);
    form.append("dry_run", String(dryRun));
    if (reason.trim()) form.append("reason", reason.trim());
    setBusy(true);
    try {
      const { data } = await api.post(`/competitions/${comp.id}/results/import`, form);
      if (dryRun) setPreview(data);
      else {
        setPreview(null);
        setFile(null);
        setReason("");
        qc.invalidateQueries();
        toast(`Опубликована редакция протокола ${data.version}`);
      }
    } catch (e) {
      setPreview(null);
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="panel-heading">
        <div>
          <h2>Импорт результатов</h2>
          <p>
            CSV из системы проведения соревнования. Сначала файл проверяется:
            все одобренные участники, по одному разу, места по правилу «1, 1,
            3». Для опубликованного протокола импорт создаёт новую редакцию.
          </p>
        </div>
      </div>
      <div className="panel-padding">
        <State query={competitions}>
          <div className="form-grid">
            <Field label="Соревнование" hint="Завершённые с закрытым приёмом заявок или с опубликованным протоколом">
              <select
                value={compId}
                onChange={(e) => {
                  setCompId(e.target.value);
                  setPreview(null);
                }}
              >
                <option value="">Выберите соревнование</option>
                {ready.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {plain(c.title)} · {date(c.start_date)}
                    {c.state === "published" ? " · протокол опубликован" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Файл CSV"
              hint={
                comp?.entry_mode === "team"
                  ? "Столбцы team;place;score — id или название допущенной команды"
                  : "Столбцы athlete;place;score — ID спортсмена вида FSP-000123"
              }
            >
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setPreview(null);
                }}
              />
            </Field>
          </div>
          {comp?.state === "published" && (
            <Field label="Основание новой редакции" hint="Обязательно: протокол уже опубликован">
              <input minLength={5} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          )}
          <div className="award-actions">
            <Button variant="outline" disabled={busy || !file || !comp} onClick={() => send(true)}>
              <Upload size={16} /> Проверить файл
            </Button>
            <Button
              disabled={busy || !preview || (comp?.state === "published" && reason.trim().length < 5)}
              onClick={() => send(false)}
            >
              {comp?.state === "published" ? "Опубликовать новую редакцию" : "Опубликовать протокол"}
            </Button>
          </div>
        </State>
      </div>
      {preview && (
        <>
          <p className="inline-note">
            Файл прошёл проверку: {preview.count} участн. Ниже — как будет
            выглядеть протокол. Пока ничего не сохранено.
          </p>
          <Table heads={["Место", "Спортсмен", "Организация", "Команда", "Баллы"]}>
            {preview.rows.map((r: any) => (
              <tr key={r.athlete_id}>
                <td>{r.place}</td>
                <td>
                  {plain(r.full_name)}
                  <small>{r.athlete_id}</small>
                </td>
                <td>{r.organization ? plain(r.organization) : "—"}</td>
                <td>{r.team_name || "—"}</td>
                <td>{r.score}</td>
              </tr>
            ))}
          </Table>
        </>
      )}
    </>
  );
}

const endpoints = [
  ["GET", "/api/v1/me", "любое", "Сведения о токене"],
  ["GET", "/api/v1/competitions?state=&from=&to=", "competitions:read", "Календарь (без черновиков)"],
  ["GET", "/api/v1/competitions/{id}", "competitions:read", "Соревнование"],
  ["GET", "/api/v1/competitions/{id}/applications", "applications:read", "Одобренные заявки"],
  ["GET", "/api/v1/competitions/{id}/protocol", "results:read", "Последняя редакция протокола"],
  ["POST", "/api/v1/competitions/{id}/results?dry_run=", "results:write", "Импорт результатов, JSON"],
  ["POST", "/api/v1/competitions/{id}/results.csv?dry_run=&reason=", "results:write", "Импорт результатов, CSV"],
];
const verifyExample = `import hashlib, hmac

def verify(secret: str, headers, body: bytes) -> bool:
    signed = headers["X-OrenCode-Timestamp"].encode() + b"." + body
    expected = "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, headers["X-OrenCode-Signature"])`;

function ApiTab() {
  const origin = window.location.origin;
  return (
    <div className="panel-padding integration-docs">
      <p>
        Полная схема запросов и ответов — в{" "}
        <a href="/docs" target="_blank" rel="noreferrer">Swagger</a> (раздел
        «API для внешних систем») и в <a href="/openapi.json" target="_blank" rel="noreferrer">openapi.json</a>.
        Подробное описание с примерами — в docs/INTEGRATIONS.md.
      </p>
      <h3>Авторизация</h3>
      <pre>{`curl -H "Authorization: Bearer ock_…" ${origin}/api/v1/competitions`}</pre>
      <p>
        401 — токен не передан, отозван или истёк; 403 — у токена нет нужного
        права; 404 — соревнование не найдено или протокол не опубликован; 409 и
        422 — данные не прошли проверку, текст ошибки в поле <code>detail</code>.
      </p>
      <Table heads={["Метод", "Адрес", "Право", "Назначение"]}>
        {endpoints.map(([m, path, scope, text]) => (
          <tr key={m + path}>
            <td><code>{m}</code></td>
            <td><code>{path}</code></td>
            <td><code>{scope}</code></td>
            <td>{text}</td>
          </tr>
        ))}
      </Table>
      <h3>Импорт результатов</h3>
      <pre>{`curl -X POST -H "Authorization: Bearer ock_…" -H "Content-Type: text/csv" \\
  --data-binary @results.csv "${origin}/api/v1/competitions/12/results.csv?dry_run=true"

athlete;place;score
FSP-000001;1;95,5
FSP-000002;2;80`}</pre>
      <p>
        Без <code>dry_run</code> первый импорт публикует протокол, повторный —
        новую редакцию с основанием <code>reason</code>. Участники получают
        уведомления, рейтинг пересчитывается, как при публикации из кабинета.
      </p>
      <h3>Вебхуки</h3>
      <pre>{`POST https://ваш-сервис/webhook
X-OrenCode-Event: protocol.published
X-OrenCode-Delivery: 42
X-OrenCode-Timestamp: 1767225600
X-OrenCode-Signature: sha256=…

{"id": "protocol.published:12:v1", "event": "protocol.published",
 "occurred_at": "…", "data": {"competition": {…}, "version": 1, "results": [...]}}`}</pre>
      <p>
        События: <code>competition.published</code> — соревнование вышло из
        черновика; <code>application.approved</code> — заявка спортсмена или
        команды одобрена; <code>protocol.published</code> — опубликована
        редакция протокола. Поле <code>id</code> уникально для события —
        используйте его, чтобы не обработать повтор дважды. Ответ 2xx считается
        доставкой.
      </p>
      <pre>{verifyExample}</pre>
    </div>
  );
}

export function Integrations() {
  const [tab, setTab] = useState("tokens");
  return (
    <>
      <PageTitle
        title="Интеграции"
        description="Токены доступа к API с ограничением прав, вебхуки о событиях федерации и импорт результатов из внешних систем."
      />
      <section className="panel">
        <div className="tabs">
          {tabs.map(([k, t]) => (
            <button className={tab === k ? "active" : ""} key={k} onClick={() => setTab(k)}>
              {t}
            </button>
          ))}
        </div>
        {tab === "tokens" && <TokensTab />}
        {tab === "webhooks" && <WebhooksTab />}
        {tab === "import" && <ImportTab />}
        {tab === "api" && <ApiTab />}
      </section>
      <div className="rating-explainer">
        <KeyRound size={22} />
        <p>
          Токен и секрет вебхука показываются один раз. Выпуск и отзыв токенов,
          изменения вебхуков и импорт результатов записываются в журнал
          действий; импорт через API — с названием токена.
        </p>
      </div>
    </>
  );
}
