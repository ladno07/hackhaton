import { useState } from "react";
import { Download, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { useAction, useAuth, useData, useToast } from "./state";
import { date, download, errorText, fileSize, plain } from "./lib";
import { Button } from "./components/ui/button";
import { Dialog } from "./components/ui/dialog";
import {
  Empty,
  ExportButtons,
  Field,
  State,
  Table,
} from "./components/shared";

const DOCUMENT_ACCEPT =
  ".pdf,.docx,.doc,.odt,.xlsx,.xls,.ods,.jpg,.jpeg,.png";
const DOCUMENT_MAX_MB = 10;
const number = (n: number) => n.toLocaleString("ru-RU");
const blank = (year: number) => ({
  year,
  name: "",
  value: "",
  unit: "чел.",
  organization_id: "",
  source: "",
  comment: "",
});

function Documents({ indicator, editable }: any) {
  const action = useAction();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <div className="indicator-docs">
      {indicator.documents.map((d: any) => (
        <div className="indicator-doc" key={d.id}>
          <button
            type="button"
            className="text-link"
            disabled={busy}
            title={`${fileSize(d.size)} · ${date(d.uploaded_at)}`}
            onClick={async () => {
              setBusy(true);
              try {
                await download("/indicator-documents/" + d.id, d.filename);
              } catch (e) {
                toast(errorText(e), true);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Download size={13} />
            {d.filename}
          </button>
          {editable && (
            <button
              type="button"
              className="icon-btn"
              aria-label={"Удалить " + d.filename}
              disabled={action.isPending}
              onClick={() =>
                confirm(`Удалить документ «${d.filename}»?`) &&
                action.mutate({
                  method: "delete",
                  url: "/indicator-documents/" + d.id,
                })
              }
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      ))}
      {!indicator.documents.length && (
        <small className="indicator-missing">Документы не прикреплены</small>
      )}
      {editable && (
        <label className="text-link regulation-upload">
          <Upload size={13} />
          Прикрепить
          <input
            type="file"
            accept={DOCUMENT_ACCEPT}
            disabled={action.isPending}
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              if (f.size > DOCUMENT_MAX_MB * 1024 * 1024)
                return toast(
                  `Размер документа не должен превышать ${DOCUMENT_MAX_MB} МБ`,
                  true,
                );
              const form = new FormData();
              form.append("file", f);
              action.mutate({
                url: "/indicators/" + indicator.id + "/documents",
                data: form,
              });
            }}
          />
        </label>
      )}
    </div>
  );
}

function IndicatorForm({ initial, onSaved }: any) {
  const action = useAction();
  const meta = useData("/metadata");
  const [v, setV] = useState<any>(initial);
  const set = (k: string, value: any) => setV({ ...v, [k]: value });
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const { id, ...rest } = v;
        try {
          await action.mutateAsync({
            method: id ? "put" : "post",
            url: "/indicators" + (id ? "/" + id : ""),
            data: {
              year: +rest.year,
              name: rest.name,
              value: +rest.value,
              unit: rest.unit,
              organization_id: rest.organization_id ? +rest.organization_id : null,
              source: rest.source,
              comment: rest.comment,
            },
          });
          onSaved();
        } catch {}
      }}
    >
      <Field label="Показатель">
        <input
          required
          minLength={3}
          maxLength={240}
          placeholder="Например, численность по форме № 1-ФК"
          value={v.name}
          onChange={(e) => set("name", e.target.value)}
        />
      </Field>
      <div className="form-grid indicator-form-grid">
        <Field label="Год">
          <input
            required
            type="number"
            min="1970"
            max={new Date().getFullYear()}
            value={v.year}
            onChange={(e) => set("year", e.target.value)}
          />
        </Field>
        <Field label="Значение">
          <input
            required
            type="number"
            min="0"
            step="any"
            value={v.value}
            onChange={(e) => set("value", e.target.value)}
          />
        </Field>
        <Field label="Единица">
          <input
            required
            maxLength={40}
            value={v.unit}
            onChange={(e) => set("unit", e.target.value)}
          />
        </Field>
      </div>
      <Field label="Организация" hint="Если показатель взят из отчёта одной организации">
        <select
          value={v.organization_id ?? ""}
          onChange={(e) => set("organization_id", e.target.value)}
        >
          <option value="">По региону в целом</option>
          {meta.data?.organizations.map((o: any) => (
            <option key={o.id} value={o.id}>
              {plain(o.name)}
            </option>
          ))}
        </select>
      </Field>
      <Field
        label="Источник"
        hint="Откуда взято значение: форма статнаблюдения, отчёт организации, приказ"
      >
        <textarea
          required
          minLength={5}
          maxLength={2000}
          rows={3}
          value={v.source}
          onChange={(e) => set("source", e.target.value)}
        />
      </Field>
      <Field label="Комментарий">
        <textarea
          maxLength={2000}
          rows={2}
          value={v.comment}
          onChange={(e) => set("comment", e.target.value)}
        />
      </Field>
      {!v.id && (
        <div className="inline-note indicator-note">
          Подтверждающие документы можно прикрепить после сохранения.
        </div>
      )}
      <Button disabled={action.isPending}>Сохранить</Button>
    </form>
  );
}

export function Indicators({ start, end }: { start: number; end: number }) {
  const { role } = useAuth();
  const action = useAction();
  const [editing, setEditing] = useState<any>(null);
  const editable = role === "admin";
  const params = `start_year=${start}&end_year=${end}`;
  const q = useData("/indicators?" + params, end - start <= 30);
  return (
    <section className="panel section-gap">
      <div className="panel-heading">
        <div>
          <h2>Показатели развития</h2>
          <p>
            Показатели реестра считаются автоматически, внесённые — с
            источником и подтверждающими документами.
          </p>
        </div>
        <div className="title-actions">
          <ExportButtons base={"/exports/indicators?" + params} name="indicators" />
          {editable && (
            <Button size="sm" onClick={() => setEditing(blank(end))}>
              <Plus size={14} />
              Показатель
            </Button>
          )}
        </div>
      </div>
      <State query={q}>
        <Table heads={["По данным реестра", ...(q.data?.years || []), "Источник"]}>
          {q.data?.registry.map((r: any) => (
            <tr key={r.key}>
              <td>
                <strong>{r.name}</strong>
                <small>{r.unit}</small>
              </td>
              {r.values.map((v: any) => (
                <td key={v.year} className="indicator-value">
                  {number(v.value)}
                </td>
              ))}
              <td className="indicator-source">{r.source}</td>
            </tr>
          ))}
        </Table>
        <h3 className="indicator-subtitle">Внесённые показатели</h3>
        {q.data?.entered.length ? (
          <Table
            heads={[
              "Год",
              "Показатель",
              "Значение",
              "Источник",
              "Документы",
              ...(editable ? [""] : []),
            ]}
          >
            {q.data.entered.map((e: any) => (
              <tr key={e.id}>
                <td>{e.year}</td>
                <td>
                  <strong>{e.name}</strong>
                  {e.organization && <small>{plain(e.organization)}</small>}
                </td>
                <td className="indicator-value">
                  {number(e.value)} {e.unit}
                </td>
                <td className="indicator-source">
                  {e.source}
                  {e.comment && <small>{e.comment}</small>}
                </td>
                <td>
                  <Documents indicator={e} editable={editable} />
                </td>
                {editable && (
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Изменить показатель"
                        onClick={() =>
                          setEditing({
                            ...e,
                            organization_id: e.organization_id ?? "",
                          })
                        }
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Удалить показатель"
                        disabled={action.isPending}
                        onClick={() =>
                          confirm(
                            e.documents.length
                              ? "Удалить показатель вместе с документами?"
                              : "Удалить показатель?",
                          ) &&
                          action.mutate({
                            method: "delete",
                            url: "/indicators/" + e.id,
                          })
                        }
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </Table>
        ) : (
          <Empty
            text="За период нет внесённых показателей"
            hint="Добавьте значения из статистических форм и отчётов организаций."
          />
        )}
      </State>
      <Dialog
        open={!!editing}
        onOpenChange={() => setEditing(null)}
        title={editing?.id ? "Показатель развития" : "Новый показатель"}
      >
        {editing && (
          <IndicatorForm initial={editing} onSaved={() => setEditing(null)} />
        )}
      </Dialog>
    </section>
  );
}
