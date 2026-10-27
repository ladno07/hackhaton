import axios from "axios";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
// Цвета графиков: recharts пишет их в SVG-атрибуты, где var() не работает
export const chartColors = {
  primary: "#402fff",
  grid: "#ededed",
};
export const api = axios.create({ baseURL: "/api" });
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const role = sessionStorage.getItem("role");
  if (role) config.headers["X-Active-Role"] = role;
  return config;
});
let refreshingSession: Promise<any> | null = null;
export function refreshSession() {
  if (!refreshingSession) {
    refreshingSession = axios.post("/api/auth/refresh").then(({ data }) => {
      const previousUser = sessionStorage.getItem("orencode.user");
      sessionStorage.setItem("orencode.user", String(data.user.id));
      sessionStorage.setItem("token", data.access_token);
      const savedRole = localStorage.getItem("orencode.role") || sessionStorage.getItem("role");
      const role = data.user.roles.includes(savedRole) ? savedRole : data.user.roles[0];
      sessionStorage.setItem("role", role);
      window.dispatchEvent(new CustomEvent("orencode:session-refreshed", { detail: { accountChanged: !!previousUser && previousUser !== String(data.user.id) } }));
      return data;
    }).finally(() => { refreshingSession = null; });
  }
  return refreshingSession;
}
export async function endSession() {
  // Let an in-flight refresh finish before revoking its browser session.
  await refreshingSession?.catch(() => {});
  await axios.post("/api/auth/logout");
}
api.interceptors.response.use((response) => response, async (error) => {
  const config = error.config;
  if (error.response?.status !== 401 || !config || config._sessionRetry || ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"].includes(config.url)) {
    return Promise.reject(error);
  }
  config._sessionRetry = true;
  try {
    const data = await refreshSession();
    config.headers.Authorization = `Bearer ${data.access_token}`;
    return api.request(config);
  } catch (refreshError: any) {
    if (refreshError.response?.status === 401) {
      sessionStorage.removeItem("token");
      window.dispatchEvent(new Event("orencode:session-ended"));
    }
    return Promise.reject(refreshError);
  }
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
    ? s.slice(0, 10).split("-").reverse().join(".")
    : "—";
export const today = () => new Date().toLocaleDateString("en-CA");
export const roleNames: Record<string, string> = {
  admin: "Федерация",
  athlete: "Спортсмен",
  coach: "Тренер",
  judge: "Судья",
  ministry: "Минспорт",
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
export const statuses: Record<string, string> = {
  regional: "Региональное",
  interregional: "Межрегиональное",
  national: "Всероссийское",
};
// rating levels: derived on the backend from status + rating class of the type
export const levels: Record<string, string> = {
  regional: "Региональный",
  interregional: "Межрегиональный",
  russian_championship: "Чемпионат России",
  russian_junior: "Первенство России",
};
export const ratingClasses: Record<string, string> = {
  main: "Основной",
  junior: "Юниорский",
  other: "Прочий",
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
export const fileSize = (n: number) =>
  n < 1024 * 1024
    ? Math.max(1, Math.round(n / 1024)) + " КБ"
    : (n / 1024 / 1024).toFixed(1).replace(".", ",") + " МБ";
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
export const sexNames: Record<string, string> = {
  male: "Мужской",
  female: "Женский",
};
// training stages of the FSSP in order; athletes.training_stage holds the name
export const trainingStages = [
  "Этап начальной подготовки",
  "Учебно-тренировочный этап",
  "Этап совершенствования спортивного мастерства",
  "Этап высшего спортивного мастерства",
];
export const ageRules: Record<string, string> = {
  year: "По году рождения",
  start: "На дату старта",
};
export const ageRange = (min: number, max: number) =>
  max >= 100 ? `от ${min} лет` : `${min}–${max} лет`;
export const groupLabel = (g: any) =>
  `${g.name} · ${ageRange(g.min_age, g.max_age)}`;
// Competition age limits: groups from the directory, or the plain age range.
export const ageLimits = (c: any) =>
  c.age_groups?.length
    ? c.age_groups.map((g: any) => g.name).join(", ")
    : ageRange(c.min_age, c.max_age);
export function ageHint(check: any, self: boolean) {
  if (!check) return null;
  const years = (n: number) =>
    n +
    " " +
    (n % 10 === 1 && n % 100 !== 11
      ? "год"
      : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)
        ? "года"
        : "лет");
  const age = `На дату старта ${self ? "вам" : "спортсмену"} ${years(check.age)}, в году соревнований исполняется ${years(check.year_age)}.`;
  if (check.eligible)
    return {
      ok: true,
      title: (self ? "Вы проходите" : "Спортсмен проходит") + " по возрасту",
      text: check.groups.length
        ? "Группа: " + check.groups.map(groupLabel).join("; ") + ". " + age
        : age,
    };
  return {
    ok: false,
    title:
      check.reason === "sex_missing"
        ? "Укажите пол в профиле"
        : (self ? "Вы не проходите" : "Спортсмен не проходит") +
          (check.reason === "sex" ? " по составу групп" : " по возрасту"),
    text:
      check.reason === "sex_missing"
        ? "Возрастные группы соревнования разделены на юношей и девушек. " + age
        : age,
  };
}
