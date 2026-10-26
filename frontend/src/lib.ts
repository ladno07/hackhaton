import axios from "axios";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
export const api = axios.create({ baseURL: "/api" });
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const role = sessionStorage.getItem("role");
  if (role) config.headers["X-Active-Role"] = role;
  return config;
});
export const errorText = (err: any) => {
  const d = err?.response?.data?.detail;
  return typeof d === "string"
    ? d
    : Array.isArray(d)
      ? d.map((x) => `${x.loc?.slice(1).join(".")}: ${x.msg}`).join("; ")
      : err.message || "Не удалось выполнить запрос";
};
export const date = (s: string) =>
  s
    ? new Date(s.slice(0, 10) + "T12:00:00").toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";
export const today = () => new Date().toLocaleDateString("en-CA");
export const roleNames: Record<string, string> = {
  admin: "Федерация",
  athlete: "Спортсмен",
  coach: "Тренер",
  judge: "Судья",
};
export const stateNames: Record<string, string> = {
  draft: "Черновик",
  open: "Приём заявок",
  closed: "Приём закрыт",
  published: "Результаты",
  pending: "На рассмотрении",
  approved: "Одобрено",
  rejected: "Отклонено",
  active: "Активна",
  paused: "Приостановлена",
  ended: "Завершена",
};
export const levels: Record<string, string> = {
  regional: "Региональное",
  interregional: "Межрегиональное",
  russian_championship: "Чемпионат России",
  russian_junior: "Первенство России",
};
export const formats: Record<string, string> = {
  onsite: "Очно",
  online: "Онлайн",
  hybrid: "Смешанный",
};
export const ranks = [
  "Без разряда",
  "III юношеский",
  "II юношеский",
  "I юношеский",
  "III",
  "II",
  "I",
  "КМС",
  "МС",
  "МСМК",
];
export async function download(url: string, name: string) {
  const res = await api.get(url, { responseType: "blob" });
  const obj = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = obj;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(obj), 1000);
}
