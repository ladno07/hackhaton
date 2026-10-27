import { useState } from "react";
import { Link } from "react-router-dom";
import { useAction, useData } from "./state";
import { Button } from "./components/ui/button";
import { State } from "./components/shared";

export function PassportPanel({ user }: any) {
  const query = useData("/my/profile-visibility");
  return (
    <section className="panel info-card section-gap">
      <h2>Результаты</h2>
      <p>
        Выберите, что другие пользователи увидят в вашем профиле после входа.
        Справки, контакты, дата рождения и документы всегда закрыты.
      </p>
      <State query={query}>
        {query.data && (
          <VisibilityForm
            key={JSON.stringify(query.data)}
            initial={query.data}
            athleteId={user.athlete_id}
          />
        )}
      </State>
    </section>
  );
}
function VisibilityForm({ initial, athleteId }: any) {
  const [values, setValues] = useState(initial);
  const action = useAction();
  const labels: Record<string, string> = {
    show_results: "История выступлений и статистика",
    show_rating: "Рейтинг",
    show_ranks: "Спортивные разряды",
    show_disciplines: "Дисциплины",
    show_training_years: "Годы занятий (в разделе дисциплин)",
    show_organization: "Организация",
    show_municipality: "Муниципалитет",
    show_training_stage: "Этап подготовки",
    show_team: "Участие в сборной",
    show_rusada: "Прохождение курса РУСАДА",
  };
  return (
    <div className="passport-controls">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action.mutate({
            method: "put",
            url: "/my/profile-visibility",
            data: values,
          });
        }}
      >
        {Object.entries(labels).map(([key, label]) => (
          <label className="check-line" key={key}>
            <input
              type="checkbox"
              checked={!!values[key]}
              onChange={(e) =>
                setValues({ ...values, [key]: e.target.checked })
              }
            />
            {label}
          </label>
        ))}
        <Button disabled={action.isPending}>Сохранить видимость</Button>
      </form>
      <Button size="sm" variant="outline" asChild>
        <Link to={`/athletes/${athleteId}/profile`}>
          Посмотреть свой профиль
        </Link>
      </Button>
    </div>
  );
}
