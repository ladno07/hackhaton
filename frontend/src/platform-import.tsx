import { useState } from "react";
import { Download, ExternalLink } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api, errorText, plain } from "./lib";
import { useToast } from "./state";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import { Field, Table } from "./components/shared";

export const platformNames: Record<string, string> = {
  codeforces: "Codeforces",
  yandex_contest: "Яндекс Контест",
  ctfd: "CTFd",
};
const contestHints: Record<string, [string, string, string]> = {
  codeforces: ["Номер контеста", "2050", "Из адреса codeforces.com/contest/2050"],
  yandex_contest: ["Номер контеста", "54321", "Из адреса contest.yandex.ru/contest/54321"],
  ctfd: ["Адрес площадки", "https://ctf.example.org", "Площадка CTFd, где шли соревнования"],
};
const UNMATCHED_SHOWN = 50;
const tokenHints: Record<string, string> = {
  yandex_contest:
    "OAuth-токен организатора контеста. Если не указан — берётся из настроек сервера",
  ctfd: "Токен администратора CTFd, если таблица закрыта. Не сохраняется",
};

// Where the published protocol came from, under the protocol table.
export function ResultsSource({ source }: any) {
  if (!source) return null;
  return (
    <p className="inline-note">
      Загружено из {platformNames[source.platform]}: {plain(source.title)}
      {source.url && (
        <>
          {" · "}
          <a className="text-link" href={source.url} target="_blank" rel="noreferrer">
            таблица площадки <ExternalLink size={12} />
          </a>
        </>
      )}
    </p>
  );
}

export function PlatformImport({ comp }: any) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Download size={14} /> Загрузить из…
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title="Протокол из тестирующей системы" wide>
        {open && <PlatformImportForm comp={comp} onDone={() => setOpen(false)} />}
      </Dialog>
    </>
  );
}

function PlatformImportForm({ comp, onDone }: any) {
  const qc = useQueryClient();
  const toast = useToast();
  const last = comp.results_source;
  const [platform, setPlatform] = useState(last?.platform || "codeforces");
  const [contest, setContest] = useState(last?.contest || "");
  const [token, setToken] = useState("");
  const [reason, setReason] = useState("");
  const [bindings, setBindings] = useState<Record<string, number>>({});
  const [report, setReport] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const team = comp.entry_mode === "team";
  const correction = comp.state === "published";
  const [contestLabel, placeholder, hint] = contestHints[platform];

  const send = async (dryRun: boolean, bound = bindings) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/competitions/${comp.id}/results/platform`, {
        platform,
        contest: contest.trim(),
        token: token.trim() || null,
        bindings: bound,
        reason: reason.trim() || null,
        dry_run: dryRun,
      });
      if (dryRun) setReport(data);
      else {
        qc.invalidateQueries();
        toast(`Опубликована редакция протокола ${data.version}`);
        onDone();
      }
    } catch (e) {
      setReport(null);
      toast(errorText(e), true);
    } finally {
      setBusy(false);
    }
  };
  const reset = () => {
    setReport(null);
    setBindings({});
  };
  const bind = (login: string, athleteId: string) => {
    const next = { ...bindings };
    if (athleteId) next[login] = +athleteId;
    else delete next[login];
    setBindings(next);
    send(true, next);
  };
  const free = (report?.missing || []).filter(
    (m: any) => !Object.values(bindings).includes(m.id),
  );
  // an open contest has thousands of outsiders: find the login by search
  const needle = search.trim().toLowerCase();
  const others = (report?.unmatched || []).filter(
    (u: any) => !needle || (u.login + " " + u.name).toLowerCase().includes(needle),
  );
  const shown = others.slice(0, UNMATCHED_SHOWN);

  return (
    <div className="panel-padding">
      <p className="inline-note">
        Таблица результатов забирается с площадки, участники сопоставляются по
        логинам из профилей (или по ID вида FSP-000123). Места пересчитываются
        среди участников соревнования. До публикации ничего не сохраняется.
      </p>
      <div className="form-grid">
        <Field label="Площадка">
          <select
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              setContest("");
              setToken("");
              reset();
            }}
          >
            {Object.entries(platformNames).map(([k, n]) => (
              <option key={k} value={k}>
                {n}
              </option>
            ))}
          </select>
        </Field>
        <Field label={contestLabel} hint={hint}>
          <input
            required
            placeholder={placeholder}
            value={contest}
            onChange={(e) => {
              setContest(e.target.value);
              reset();
            }}
          />
        </Field>
      </div>
      {tokenHints[platform] && (
        <Field label="Токен доступа" hint={tokenHints[platform]}>
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </Field>
      )}
      {correction && (
        <Field label="Основание новой редакции" hint="Обязательно: протокол уже опубликован">
          <input minLength={5} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      )}
      <div className="award-actions">
        <Button
          variant="outline"
          disabled={busy || !contest.trim() || (correction && reason.trim().length < 5)}
          onClick={() => send(true)}
        >
          Проверить
        </Button>
        <Button disabled={busy || !report?.ready} onClick={() => send(false)}>
          {correction ? "Опубликовать новую редакцию" : "Опубликовать протокол"}
        </Button>
      </div>

      {report && (
        <>
          <p className="inline-note">
            {plain(report.source.title)}: найдено {report.matched.length} из{" "}
            {report.matched.length + report.missing.length}{" "}
            {team ? "команд" : "участников"}.{" "}
            {report.ready
              ? "Ниже — протокол в том виде, как он будет опубликован."
              : report.matched.length
                ? "Исправьте ошибки ниже, чтобы опубликовать протокол."
                : "Ни один участник соревнования не найден в таблице."}
          </p>
          {report.conflicts.length > 0 && (
            <div className="form-section">
              <h3>Нужно исправить</h3>
              {report.conflicts.map((c: string) => (
                <p className="inline-error" key={c}>
                  {c}
                </p>
              ))}
            </div>
          )}
          {report.missing.length > 0 && (
            <div className="form-section">
              <h3>Не войдут в протокол</h3>
              <p className="inline-note">
                {team
                  ? "Ни один участник команды не найден по логину, название тоже не совпало — команда останется без результата."
                  : "Не найдены в таблице площадки — останутся без результата. Если участник выступал под другим логином, привяжите его строку ниже или укажите логин в профиле."}
              </p>
              {report.missing.map((m: any) => (
                <div className="simple-row" key={m.id ?? m.team_id}>
                  <span>{plain(m.full_name)}</span>
                  <small>
                    {m.athlete_id || ""}
                    {m.in_protocol && " · уже в протоколе, нужно найти"}
                  </small>
                </div>
              ))}
            </div>
          )}
          {report.matched.length > 0 && (
            <Table heads={["Место", "На площадке", team ? "Команда" : "Спортсмен", "Логин", "Баллы"]}>
              {report.matched.map((m: any) => (
                <tr key={m.athlete_id || m.team_id}>
                  <td>{m.place}</td>
                  <td>{m.platform_place}</td>
                  <td>
                    {plain(m.full_name)}
                    {m.athlete_id && <small>{m.athlete_id}</small>}
                  </td>
                  <td>
                    {m.login}
                    {bindings[m.login] && <small>привязан вручную</small>}
                  </td>
                  <td>{m.score}</td>
                </tr>
              ))}
            </Table>
          )}
          {report.unmatched.length > 0 && (
            <>
              <div className="panel-heading">
                <div>
                  <h2>Не вошли в протокол</h2>
                  <p>
                    Участники контеста не из этого соревнования.
                    {!team && free.length > 0 && " Если это ваш участник под другим логином — привяжите его; логин сохранится в профиле при публикации."}
                  </p>
                </div>
              </div>
              <Field
                label="Поиск по логину или имени"
                hint={`Показано ${shown.length} из ${others.length}${needle ? " найденных" : ""} · всего в таблице ${report.unmatched.length}`}
              >
                <input value={search} onChange={(e) => setSearch(e.target.value)} />
              </Field>
              <Table heads={["На площадке", "Логин", "Причина", "Баллы", ...(team ? [] : ["Привязать"])]}>
                {shown.map((u: any) => (
                  <tr key={u.login + u.platform_place}>
                    <td>{u.platform_place}</td>
                    <td>
                      {u.login}
                      {u.name !== u.login && <small>{u.name}</small>}
                    </td>
                    <td>{u.reason}</td>
                    <td>{u.score}</td>
                    {!team && (
                      <td>
                        <select
                          aria-label={"Привязать логин " + u.login}
                          disabled={busy || free.length === 0}
                          value=""
                          onChange={(e) => bind(u.login, e.target.value)}
                        >
                          <option value="">—</option>
                          {free.map((m: any) => (
                            <option key={m.id} value={m.id}>
                              {plain(m.full_name)}
                            </option>
                          ))}
                        </select>
                      </td>
                    )}
                  </tr>
                ))}
              </Table>
            </>
          )}
          {Object.keys(bindings).length > 0 && (
            <div className="award-actions">
              <Button variant="outline" size="sm" disabled={busy} onClick={() => { setBindings({}); send(true, {}); }}>
                Сбросить ручные привязки
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
