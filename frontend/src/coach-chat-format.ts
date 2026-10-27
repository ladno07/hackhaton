import petrovich from "petrovich";

export function chatPerson(fullName: string, sex?: string) {
  const demo = /^Демо\s*·\s*/u.test(fullName);
  const parts = fullName.replace(/^Демо\s*·\s*/u, "").trim().split(/\s+/u);
  // Registration uses surname, first name, patronymic; demo cards use first name, surname.
  const first = (demo ? parts[0] : parts[1] || parts[0]) || "";
  const last = demo ? parts[1] || "" : parts.length > 1 ? parts[0] : "";
  const gender = sex === "male" || sex === "female" ? sex
    : parts[2] ? petrovich.detect_gender(parts[2]) : "androgynous";
  const instrumental = first ? petrovich[gender].first.instrumental(first) : "";
  const preposition = /^(?:Льв|С[втлн])/iu.test(instrumental) ? "со" : "с";
  return { label: [last, first].filter(Boolean).join(" "), title: first ? `Чат ${preposition} ${instrumental}` : "Чат" };
}

export function chatDay(timestamp: string) {
  const date = new Date(timestamp);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function chatDayLabel(day: string, today = new Date()) {
  const date = new Date(`${day}T12:00:00`);
  return date.toLocaleDateString("ru-RU", {
    day: "numeric", month: "long",
    ...(date.getFullYear() !== today.getFullYear() ? { year: "numeric" } : {}),
  }).replace(/\s*г\.$/u, "");
}
