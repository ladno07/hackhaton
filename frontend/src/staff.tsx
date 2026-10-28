import { useState } from "react";
import { useAction, useData } from "./state";
import { date, sexNames, plain } from "./lib";
import { Button } from "./components/ui/button";
import { Field } from "./components/shared";

export const staffKinds: Record<string, { url: string; title: string }> = {
  coach: { url: "/coaches", title: "тренера" },
  judge: { url: "/judges", title: "судьи" },
};

const optional = [
  "phone",
  "contact_email",
  "qualification",
  "about",
  "organization_id",
  "experience_since",
];

// card without id is a new one: the admin also gives email and a password
export function StaffEditor({ kind, card, onSaved, disabled }: any) {
  const meta = useData("/metadata");
  const action = useAction();
  const creating = !card.id;
  const [v, setV] = useState<any>({
    email: "",
    password: "",
    full_name: card.full_name || "",
    sex: card.sex || "",
    birth_date: card.birth_date || "",
    organization_id: card.organization_id || null,
    municipality: card.municipality || "Оренбург",
    phone: card.phone || "",
    contact_email: card.contact_email || "",
    qualification: card.qualification || "",
    experience_since: card.experience_since || "",
    about: card.about || "",
    discipline_ids: card.discipline_ids || [],
  });
  const change = (k: string, val: any) => setV({ ...v, [k]: val });
  const { url } = staffKinds[kind];
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        const { email, password, ...data } = v;
        for (const k of optional) data[k] = data[k] || null;
        if (data.experience_since)
          data.experience_since = +data.experience_since;
        data.sex = data.sex || null;
        try {
          await action.mutateAsync({
            method: creating ? "post" : "put",
            url: url + (creating ? "" : "/" + card.id),
            data: creating
              ? { ...data, email, password: password || null }
              : data,
          });
          onSaved?.();
        } catch {}
      }}
    >
      <fieldset disabled={disabled} className="plain-fieldset">
        {creating && (
          <div className="form-grid">
            <Field
              label="Email для входа"
              hint="Если пользователь уже есть, ему добавится роль"
            >
              <input
                required
                type="email"
                value={v.email}
                onChange={(e) => change("email", e.target.value)}
              />
            </Field>
            <Field
              label="Временный пароль"
              hint="Только для новой учётной записи, от 10 символов"
            >
              <input
                type="text"
                minLength={10}
                autoComplete="new-password"
                value={v.password}
                onChange={(e) => change("password", e.target.value)}
              />
            </Field>
          </div>
        )}
        <div className="form-grid">
          <Field label="ФИО">
            <input
              required
              minLength={3}
              value={v.full_name}
              onChange={(e) => change("full_name", e.target.value)}
            />
          </Field>
          <Field label="Дата рождения">
            <input
              required
              type="date"
              value={v.birth_date}
              onChange={(e) => change("birth_date", e.target.value)}
            />
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Пол">
            <select
              value={v.sex}
              onChange={(e) => change("sex", e.target.value)}
            >
              <option value="">Не указан</option>
              {Object.entries(sexNames).map(([k, s]) => (
                <option key={k} value={k}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Муниципалитет">
            <input
              required
              minLength={2}
              value={v.municipality}
              onChange={(e) => change("municipality", e.target.value)}
            />
          </Field>
        </div>
        <Field label="Организация">
          <select
            value={v.organization_id || ""}
            onChange={(e) =>
              change("organization_id", e.target.value ? +e.target.value : null)
            }
          >
            <option value="">Без организации</option>
            {meta.data?.organizations.map((o: any) => (
              <option key={o.id} value={o.id}>
                {plain(o.name)}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="Телефон">
            <input
              type="tel"
              placeholder="+7 900 000-00-00"
              value={v.phone}
              onChange={(e) => change("phone", e.target.value)}
            />
          </Field>
          <Field label="Контактный email">
            <input
              type="email"
              value={v.contact_email}
              onChange={(e) => change("contact_email", e.target.value)}
            />
          </Field>
        </div>
        <div className="form-grid">
          <Field
            label="Квалификация"
            hint={
              kind === "coach"
                ? "Категория, звание"
                : "Категории ведутся через заявки"
            }
          >
            <input
              value={v.qualification}
              onChange={(e) => change("qualification", e.target.value)}
            />
          </Field>
          <Field label="Стаж с года">
            <input
              type="number"
              min="1950"
              max={new Date().getFullYear()}
              value={v.experience_since}
              onChange={(e) => change("experience_since", e.target.value)}
            />
          </Field>
        </div>
        <div className="form-section">
          <h3>Дисциплины</h3>
          {meta.data?.disciplines.map((d: any) => (
            <label key={d.id} className="check-line">
              <input
                type="checkbox"
                checked={v.discipline_ids.includes(d.id)}
                onChange={(e) =>
                  change(
                    "discipline_ids",
                    e.target.checked
                      ? [...v.discipline_ids, d.id]
                      : v.discipline_ids.filter((x: number) => x !== d.id),
                  )
                }
              />
              {d.short_name}
            </label>
          ))}
        </div>
        <Field label="О себе">
          <textarea
            maxLength={2000}
            value={v.about}
            onChange={(e) => change("about", e.target.value)}
          />
        </Field>
        {kind === "judge" && !creating && (
          <div className="form-section">
            <h3>Судейские категории</h3>
            {card.categories?.length ? (
              card.categories.map((c: any) => (
                <p key={c.id} className="inline-note">
                  {c.name} · приказ {c.order_number} · до {date(c.expires_on)}
                </p>
              ))
            ) : (
              <p className="inline-note">Категорий пока нет</p>
            )}
          </div>
        )}
        <div className="form-footer">
          <Button disabled={action.isPending}>
            {creating ? "Создать карточку" : "Сохранить карточку"}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}

export function ArchiveForm({ kind, card, onDone }: any) {
  const action = useAction();
  const [reason, setReason] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await action.mutateAsync({
            url: staffKinds[kind].url + "/" + card.id + "/archive",
            data: { reason },
          });
          onDone();
        } catch {}
      }}
    >
      <p className="inline-note">
        {plain(card.full_name)} пропадёт из реестра и списков выбора. История связей,
        назначений и протоколов сохранится.
        {kind === "coach"
          ? " Активные связи со спортсменами будут приостановлены, неподтверждённые запросы — завершены."
          : " Назначить судью на новые соревнования будет нельзя."}
      </p>
      <Field label="Причина">
        <textarea
          required
          minLength={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <Button disabled={action.isPending}>В архив</Button>
    </form>
  );
}
