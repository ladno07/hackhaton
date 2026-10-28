import { roleNames, stateNames } from "./lib";

const entityNames: Record<string, string> = {
  users: "Пользователь",
  roles: "Роль",
  user_roles: "Роль пользователя",
  organizations: "Организация",
  disciplines: "Дисциплина",
  athletes: "Спортсмен",
  athlete_disciplines: "Дисциплина спортсмена",
  athlete_organizations: "Организация спортсмена",
  coaches: "Тренер",
  judges: "Судья",
  coach_disciplines: "Дисциплина тренера",
  judge_disciplines: "Дисциплина судьи",
  athlete_coaches: "Связь спортсмена с тренером",
  link_history: "История связи с тренером",
  competition_types: "Тип соревнования",
  competitions: "Соревнование",
  age_groups: "Возрастная группа",
  competition_age_groups: "Возрастная группа соревнования",
  competition_regulations: "Положение о соревновании",
  competition_applications: "Заявка на соревнование",
  competition_judges: "Назначение судьи",
  competition_results: "Результат соревнования",
  protocol_versions: "Редакция протокола",
  sports_ranks: "Спортивный разряд",
  judge_categories: "Судейская категория",
  rank_applications: "Заявка на разряд или категорию",
  rating_rules: "Правило рейтинга",
  ratings: "Рейтинг",
  team_members: "Участник сборной",
  evsk_rules: "Условие ЕВСК",
  notifications: "Уведомление",
  audit_logs: "Запись журнала",
  deadlines: "Срок отчётности",
  competition_teams: "Команда соревнования",
  competition_team_members: "Участник команды",
  passport_publications: "Настройки видимости профиля",
  passport_guardian_consents: "Согласие представителя",
  public_protocol_proofs: "Проверка протокола",
  login_sessions: "Сеанс пользователя",
};

export function auditEntity(entity: string, id: string | number | null): string {
  const name = entityNames[entity] || "Запись";
  return id === null || id === undefined || id === "" ? name : `${name} №${id}`;
}

const labels: Record<string, string> = {
  version: "Редакция протокола",
  roles: "Роли",
  state: "Состояние",
  status: "Статус",
  comment: "Комментарий",
  reason: "Основание",
  consent_version: "Версия согласия",
  enabled: "Публикация включена",
  show_rating: "Показывать рейтинг",
  show_results: "Показывать результаты",
  show_rusada: "Показывать сведения РУСАДА",
  show_team: "Показывать сборную",
  participants: "Участников",
  position: "Должность",
  judge_id: "Номер судьи",
  athlete_id: "Номер спортсмена",
  athlete_ids: "Номера спортсменов",
  coach_id: "Номер тренера",
  discipline_id: "Номер дисциплины",
  season: "Сезон",
  assigned_on: "Дата присвоения",
  expires_on: "Действует до",
  order_number: "Номер приказа",
  order_date: "Дата приказа",
  rank_name: "Разряд",
  category_name: "Категория",
  name: "Название",
  full_name: "ФИО",
  title: "Название",
  due_on: "Срок",
  done: "Выполнено",
  archived_at: "Дата архивации",
  archive_reason: "Причина архивации",
  platform: "Площадка",
  contest: "Контест",
  count: "Записей",
  bound_logins: "Привязанные логины",
};

function label(key: string): string {
  return labels[key] || key.replaceAll("_", " ");
}

function valueText(value: unknown, key: string): string {
  if (value === null || value === undefined || value === "") return "Не указано";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => valueText(item, key)).join("; ") : "Нет";
  }
  if (typeof value === "object") {
    return Object.entries(value).map(([k, v]) => `${label(k)}: ${valueText(v, k)}`).join("; ") || "Нет";
  }
  const text = String(value);
  if (key === "roles") return roleNames[text] || text;
  if (key === "status" || key === "state") return stateNames[text] || text;
  return text;
}

export function auditDetails(details: unknown): [string, string][] {
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return details == null ? [] : [["Сведения", valueText(details, "")]];
  }
  return Object.entries(details).map(([key, value]) => [label(key), valueText(value, key)]);
}
