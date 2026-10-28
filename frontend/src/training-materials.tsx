import { useState } from "react";
import { Download, ExternalLink, FileText, Link as LinkIcon, Upload } from "lucide-react";
import { useAction, useData, useToast } from "./state";
import { download, errorText } from "./lib";
import { Button } from "./components/ui/button";
import { Empty, Field, State } from "./components/shared";

const accept = ".pdf,.docx,.xlsx,.pptx,.zip,.png,.jpg,.jpeg,.txt,.md,.csv,.json,.py,.cpp,.c,.h,.hpp,.java,.js,.ts,.sql,.ipynb,.css,.html";
const size = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МБ` : `${Math.ceil(bytes / 1024)} КБ`;

function MaterialRow({ material, children }: any) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return <div className="training-material-row">
    {material.kind === "file" ? <FileText size={18} /> : <LinkIcon size={18} />}
    <div className="training-material-copy"><strong>{material.title}</strong><small>{material.kind === "file" ? `${material.filename} · ${size(material.size)}` : material.url}</small></div>
    <div className="row-actions">
      {!material.removed_at && (material.kind === "link" ? <Button asChild size="sm" variant="outline"><a href={material.url} target="_blank" rel="noopener noreferrer">Открыть <ExternalLink size={14} /></a></Button> :
        <Button size="sm" variant="outline" disabled={busy} onClick={async () => {
          setBusy(true); try { await download(`/training-materials/${material.id}/download`, material.filename); } catch (e) { toast(errorText(e), true); } finally { setBusy(false); }
        }}><Download size={14} /> Скачать</Button>)}
      {children}
    </div>
  </div>;
}

export function LessonMaterials({ materials = [] }: any) {
  if (!materials.length) return null;
  return <section className="training-materials"><h4>Материалы занятия</h4>{materials.map((m: any) => <MaterialRow key={m.id} material={m} />)}</section>;
}

export function MaterialManager({ lesson }: any) {
  const query = useData(`/training-lessons/${lesson.id}/materials?include_removed=true`);
  const action = useAction();
  const toast = useToast();
  const [link, setLink] = useState({ title: "", url: "" });
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [inputKey, setInputKey] = useState(0);
  const active = (query.data || []).filter((m: any) => !m.removed_at);
  const removed = (query.data || []).filter((m: any) => m.removed_at);
  return <div className="training-material-manager">
    <p className="training-muted">{lesson.topic}. Материалы видны зачисленным спортсменам в карточке занятия. До 20 файлов и ссылок, каждый файл — до 10 МБ.</p>
    <State query={query}>{active.length ? <div>{active.map((m: any) => <MaterialRow key={m.id} material={m}>
      <Button size="sm" variant="ghost" disabled={action.isPending} onClick={() => action.mutate({ method: "delete", url: `/training-materials/${m.id}` })}>Убрать</Button>
    </MaterialRow>)}</div> : <Empty text="Материалы пока не добавлены" hint="Загрузите файл с заданием или добавьте ссылку на ресурс." />}</State>
    <form className="training-material-form" onSubmit={async e => {
      e.preventDefault(); if (!file) return;
      if (file.size > 10 * 1024 * 1024) { toast("Размер файла не должен превышать 10 МБ", true); return; }
      const data = new FormData(); data.append("file", file); data.append("title", fileTitle);
      try { await action.mutateAsync({ url: `/training-lessons/${lesson.id}/materials/files`, data }); setFile(null); setFileTitle(""); setInputKey(k => k + 1); } catch {}
    }}>
      <h3>Прикрепить файл</h3>
      <Field label="Файл с заданием или материалом" hint="PDF, DOCX, XLSX, PPTX, ZIP, изображения, текст и исходный код в UTF-8."><input key={inputKey} required type="file" accept={accept} onChange={e => setFile(e.target.files?.[0] || null)} /></Field>
      <Field label="Название материала (необязательно)"><input maxLength={200} placeholder="Например: Задание № 1 — графы" value={fileTitle} onChange={e => setFileTitle(e.target.value)} /></Field>
      <Button disabled={action.isPending || !file || active.length >= 20}><Upload size={16} /> Загрузить файл</Button>
    </form>
    <form className="training-material-form" onSubmit={async e => {
      e.preventDefault(); try { await action.mutateAsync({ url: `/training-lessons/${lesson.id}/materials/links`, data: link }); setLink({ title: "", url: "" }); } catch {}
    }}>
      <h3>Добавить ссылку</h3>
      <Field label="Название ссылки"><input required maxLength={200} placeholder="Например: Тренировочный контест" value={link.title} onChange={e => setLink({ ...link, title: e.target.value })} /></Field>
      <Field label="Адрес ресурса"><input required type="url" maxLength={2000} placeholder="https://…" value={link.url} onChange={e => setLink({ ...link, url: e.target.value })} /></Field>
      <Button disabled={action.isPending || active.length >= 20}><LinkIcon size={16} /> Добавить ссылку</Button>
    </form>
    {removed.length > 0 && <details className="training-material-removed"><summary>Убранные материалы · {removed.length}</summary>{removed.map((m: any) => <MaterialRow key={m.id} material={m}>
      <Button size="sm" variant="outline" disabled={action.isPending || active.length >= 20} onClick={() => action.mutate({ url: `/training-materials/${m.id}/restore` })}>Восстановить</Button>
    </MaterialRow>)}</details>}
  </div>;
}
