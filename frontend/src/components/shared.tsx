import { useState } from "react";
import {
  AlertCircle,
  ArrowDownToLine,
  Loader2,
  Search,
  Inbox,
} from "lucide-react";
import { Button } from "./ui/button";
import { download, errorText, stateNames } from "../lib";
import { useToast } from "../state";
export function PageTitle({
  eyebrow = "ПЛАТФОРМА ФСП",
  title,
  description,
  children,
}: any) {
  return (
    <div className="page-title">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="title-actions">{children}</div>
    </div>
  );
}
export function State({ query, children }: any) {
  if (query.isPending)
    return (
      <div className="state">
        <Loader2 className="spin" /> Загружаем данные…
      </div>
    );
  if (query.error)
    return (
      <div className="state error">
        <AlertCircle />
        <p>{errorText(query.error)}</p>
        <Button variant="outline" onClick={() => query.refetch()}>
          Повторить
        </Button>
      </div>
    );
  return children;
}
export function Empty({
  text = "Здесь пока нет записей",
  hint = "Попробуйте изменить фильтры или добавьте первую запись.",
}: any) {
  return (
    <div className="state">
      <Inbox size={30} />
      <strong>{text}</strong>
      <span>{hint}</span>
    </div>
  );
}
export function Badge({ value, label }: any) {
  return (
    <span className={"badge badge-" + value}>
      <i />
      {label || stateNames[value] || value}
    </span>
  );
}
export function SearchBox({
  value,
  onChange,
  placeholder = "Поиск по имени или названию",
}: any) {
  return (
    <div className="search">
      <Search size={17} />
      <input
        aria-label={placeholder}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
export function ExportButtons({
  base,
  name,
  formats = ["pdf", "docx", "xlsx"],
}: any) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <div className="export-buttons">
      {formats.map((fmt: string) => (
        <Button
          key={fmt}
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const [p, q] = base.split("?");
              await download(
                p + "." + fmt + (q ? "?" + q : ""),
                name + "." + fmt,
              );
            } catch (e) {
              toast(errorText(e), true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <ArrowDownToLine size={14} />
          {fmt.toUpperCase()}
        </Button>
      ))}
    </div>
  );
}
export function Field({ label, children, hint }: any) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Table({ heads, children }: any) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {heads.map((h: string, i: number) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export function Stat({ label, value, icon: Icon, note }: any) {
  return (
    <div className="stat">
      <div className="stat-top">
        {label}
        <span>{Icon && <Icon size={18} />}</span>
      </div>
      <strong>{value ?? "—"}</strong>
      <small>{note}</small>
    </div>
  );
}
