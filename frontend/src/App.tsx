import { useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bell,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronDown,
  FileCheck2,
  FileText,
  Gavel,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings2,
  ShieldCheck,
  Trophy,
  Users,
  X,
  ClipboardList,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { api, errorText, roleNames, sexNames } from "./lib";
import { useAuth, useData, useToast } from "./state";
import { Button } from "./components/ui/button";
import { Field } from "./components/shared";
import { FspLogo } from "./components/logo";
import {
  Overview,
  History,
  Profile,
  Coaching,
  Notifications,
  Audit,
} from "./pages";
import { Competitions, CompetitionDetail } from "./competitions";
import { Registry, Ranks, Ratings, Reports, Settings } from "./management";

import {
  AthleteProfileView,
  PrivateCertificate,
  LegacyPublicProfile,
} from "./public-passport";
import { AthleteSummary } from "./athlete-summary";
import { Assignments, JudgingHistory } from "./judging";
import { Navigator } from "./navigator";

import { CertificateVerification } from "./certificate-verification";

function Login() {
  const auth = useAuth();
  const loginLocation = useLocation();
  const returnTo =
    new URLSearchParams(loginLocation.search).get("returnTo") || "/";
  const safeReturn =
    /^\/(?:competitions(?:\/[0-9]+)?|certificates\/[0-9]+(?:\?version=[0-9]+)?|athletes\/[0-9]+\/profile)$/.test(
      returnTo,
    )
      ? returnTo
      : "/";
  const [params] = useSearchParams();
  const [register, setRegister] = useState(params.get("register") === "1");
  const [error, setError] = useState("");
  const [form, setForm] = useState<any>({
    email: "",
    password: "",
    role: "athlete",
    consent: false,
    guardian_consent: false,
  });
  const change = (k: string, v: any) => setForm({ ...form, [k]: v });
  const mutation = useMutation({
    mutationFn: async () => {
      setError("");
      return (
        await api.post(
          "/auth/" + (register ? "register" : "login"),
          register
            ? {
                ...form,
                sex: form.role === "athlete" ? form.sex || null : null,
                guardian_name: form.guardian_name || null,
              }
            : { email: form.email, password: form.password },
        )
      ).data;
    },
    onSuccess: auth.login,
    onError: (e) => setError(errorText(e)),
  });
  if (auth.restoring) return <div className="state full-screen">Восстанавливаем вход…</div>;
  if (auth.token) return <Navigate to={safeReturn} replace />;
  return (
    <div className="auth-page">
      <section className="auth-story">
        <Link to="/" className="brand">
          <FspLogo className="brand-logo" />
        </Link>
        <div>
          <div className="eyebrow">ОРЕНБУРГСКАЯ ОБЛАСТЬ · 2026</div>
          <h1>
            Ваша следующая
            <br />
            победа начинается
            <br />
            <em>с одной платформы.</em>
          </h1>
          <p>
            Соревнования, команда и спортивный рост.
            <br />
            Всё, что объединяет программирование и спорт.
          </p>
          <div className="auth-disciplines">
            <span>01 / Алгоритмы</span>
            <span>02 / Продукты</span>
            <span>03 / Инфобезопасность</span>
            <span>04 / Искусственный интеллект</span>
            <span>05 / Робототехника</span>
            <span>06 / Беспилотные системы</span>
          </div>
        </div>
        <footer>Единая цифровая платформа региональной федерации</footer>
      </section>
      <section className="auth-form">
        <div className="auth-form-inner">
          <span className="auth-label">
            <ShieldCheck size={16} /> Личный кабинет ФСП
          </span>
          <h2>{register ? "Создать аккаунт" : "С возвращением"}</h2>
          <p>
            {register
              ? "Присоединяйтесь к спортивному сообществу региона."
              : "Войдите, чтобы продолжить работу на платформе."}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate();
            }}
          >
            {register && (
              <>
                <Field label="Фамилия, имя, отчество">
                  <input
                    required
                    minLength={3}
                    value={form.full_name || ""}
                    onChange={(e) => change("full_name", e.target.value)}
                  />
                </Field>
                <div className="form-grid">
                  <Field label="Дата рождения">
                    <input
                      required
                      type="date"
                      value={form.birth_date || ""}
                      onChange={(e) => change("birth_date", e.target.value)}
                    />
                  </Field>
                  <Field label="Ваша роль">
                    <select
                      value={form.role}
                      onChange={(e) => change("role", e.target.value)}
                    >
                      {["athlete", "coach", "judge"].map((r) => (
                        <option value={r} key={r}>
                          {roleNames[r]}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                {form.role === "athlete" && (
                  <Field label="Пол">
                    <select
                      value={form.sex || ""}
                      onChange={(e) => change("sex", e.target.value)}
                    >
                      <option value="">Не указан</option>
                      {Object.entries(sexNames).map(([k, s]) => (
                        <option value={k} key={k}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
              </>
            )}
            <Field label="Электронная почта">
              <input
                autoComplete="email"
                type="email"
                required
                placeholder="name@example.com"
                value={form.email}
                onChange={(e) => change("email", e.target.value)}
              />
            </Field>
            <Field label="Пароль">
              <input
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                minLength={register ? 10 : 1}
                required
                placeholder={
                  register ? "Не менее 10 символов" : "Введите пароль"
                }
                value={form.password}
                onChange={(e) => change("password", e.target.value)}
              />
            </Field>
            {register && (
              <>
                <label className="check-line">
                  <input
                    type="checkbox"
                    required
                    checked={form.consent}
                    onChange={(e) => change("consent", e.target.checked)}
                  />
                  Я согласен на обработку данных профиля, заявок и результатов
                  Федерацией для ведения спортивного учёта (версия 2026-01).
                </label>
                <details>
                  <summary>Для несовершеннолетнего</summary>
                  <Field label="ФИО законного представителя">
                    <input
                      value={form.guardian_name || ""}
                      onChange={(e) => change("guardian_name", e.target.value)}
                    />
                  </Field>
                  <label className="check-line">
                    <input
                      type="checkbox"
                      checked={form.guardian_consent}
                      onChange={(e) =>
                        change("guardian_consent", e.target.checked)
                      }
                    />
                    Законный представитель согласен на обработку данных
                    несовершеннолетнего.
                  </label>
                </details>
              </>
            )}
            {error && (
              <div className="inline-error" role="alert">
                {error}
              </div>
            )}
            <Button className="w-full" disabled={mutation.isPending}>
              {mutation.isPending
                ? "Подождите…"
                : register
                  ? "Зарегистрироваться"
                  : "Войти в кабинет"}
              <ArrowRight size={17} />
            </Button>
          </form>
          <div className="auth-toggle">
            {register ? "Уже есть аккаунт?" : "Впервые на платформе?"}{" "}
            <button
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {" "}
              {register ? "Войти" : "Регистрация"}
            </button>
          </div>
          <Link className="auth-navigator" to="/start">
            Новичкам: дисциплины, где заниматься и ближайшие старты{" "}
            <ArrowRight size={14} />
          </Link>
          <div className="demo-note">
            <strong>Демонстрационный доступ</strong>
            <span>admin@demo.example / DemoPass2026!</span>
            <small>После загрузки демоданных. Все данные вымышлены.</small>
          </div>
        </div>
      </section>
    </div>
  );
}
const navigation = [
  {
    to: "/",
    label: "Обзор",
    icon: LayoutDashboard,
    roles: ["admin", "athlete", "coach", "judge"],
  },
  {
    to: "/competitions",
    label: "Соревнования",
    icon: CalendarDays,
    roles: ["admin", "athlete", "coach", "judge"],
  },
  { to: "/registry", label: "Реестр", icon: Users, roles: ["admin", "coach"] },
  {
    to: "/coaching",
    label: "Связи с тренерами",
    icon: Users,
    roles: ["admin", "coach", "athlete"],
  },
  {
    to: "/history",
    label: "Результаты",
    icon: ChartNoAxesCombined,
    roles: ["admin", "athlete", "coach"],
  },
  {
    to: "/assignments",
    label: "Назначения",
    icon: Gavel,
    roles: ["judge"],
  },
  {
    to: "/judging",
    label: "Мои соревнования",
    icon: ClipboardList,
    roles: ["judge"],
  },
  {
    to: "/ranks",
    label: "Разряды и категории",
    icon: FileCheck2,
    roles: ["admin", "athlete", "coach", "judge"],
  },
  {
    to: "/ratings",
    label: "Рейтинг и сборная",
    icon: Trophy,
    roles: ["admin", "athlete", "coach", "judge"],
  },
  {
    to: "/reports",
    label: "Аналитика и отчёты",
    icon: FileText,
    roles: ["admin"],
  },
  { to: "/audit", label: "Журнал действий", icon: Activity, roles: ["admin"] },
  { to: "/settings", label: "Управление", icon: Settings2, roles: ["admin"] },
  {
    to: "/profile",
    label: "Мой профиль",
    icon: ShieldCheck,
    roles: ["athlete", "coach", "judge"],
  },
];
function Layout() {
  const auth = useAuth();
  const [mobile, setMobile] = useState(false);
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  const navigate = useNavigate();
  const notices = useData("/notifications");
  if (auth.restoring) return <div className="state full-screen">Восстанавливаем вход…</div>;
  if (!auth.token)
    return (
      <Navigate
        to={
          "/login?returnTo=" +
          encodeURIComponent(location.pathname + location.search)
        }
        replace
      />
    );
  if (auth.loading)
    return <div className="state full-screen">Открываем кабинет…</div>;
  if (auth.error)
    return (
      <div className="state full-screen">
        <p>Сессия недоступна</p>
        <Button onClick={auth.logout}>Войти снова</Button>
      </div>
    );
  const unread = (notices.data || []).filter((n: any) => !n.read_at).length;
  const current = navigation.find((n) =>
    n.to === "/"
      ? location.pathname === "/"
      : location.pathname.startsWith(n.to),
  );
  return (
    <div className="app-shell">
      {mobile && (
        <div className="sidebar-backdrop" onClick={() => setMobile(false)} />
      )}
      <aside className={"sidebar " + (mobile ? "sidebar-visible" : "")}>
        <Link className="brand" to="/">
          <FspLogo className="brand-logo" />
        </Link>
        <div className="region-label">
          Оренбургская область <span>2026</span>
        </div>
        <div className="nav-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav>
          {navigation
            .filter((n) => n.roles.includes(auth.role))
            .map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                onClick={() => setMobile(false)}
              >
                <n.icon size={18} />
                {n.label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="federation-mark">
            <FspLogo variant="mark" className="federation-logo" />
            <div>
              Федерация спортивного
              <br />
              программирования<small>Оренбургская область</small>
            </div>
          </div>
          <div className="sidebar-status">
            <i /> Единая система учёта
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-btn mobile-menu"
              aria-label="Открыть меню"
              onClick={() => setMobile(true)}
            >
              <Menu />
            </button>
            <span>Платформа ФСП</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{current?.label || (location.pathname.startsWith("/athletes/") ? "Профиль спортсмена" : location.pathname.startsWith("/certificates/") ? "Справка об участии" : "Уведомления")}</strong>
          </div>
          <div className="topbar-right">
            <label className="role-switch">
              <span>Кабинет</span>
              <select
                aria-label="Активная роль"
                value={auth.role}
                onChange={(e) => {
                  auth.switchRole(e.target.value);
                  navigate("/");
                }}
              >
                {auth.user.roles.map((r: string) => (
                  <option key={r} value={r}>
                    {roleNames[r]}
                  </option>
                ))}
              </select>
            </label>
            <Link
              to="/notifications"
              className="notification-bell"
              aria-current={
                location.pathname === "/notifications" ? "page" : undefined
              }
              aria-label={`Уведомления: ${unread} непрочитанных`}
              onClick={(event) => {
                if (
                  location.pathname !== "/notifications" ||
                  event.button !== 0 ||
                  event.ctrlKey ||
                  event.metaKey ||
                  event.shiftKey ||
                  event.altKey
                ) {
                  return;
                }
                event.preventDefault();
                if (window.history.state?.idx > 0) {
                  navigate(-1);
                } else {
                  navigate("/", { replace: true });
                }
              }}
            >
              <Bell size={20} />
              {unread > 0 && <i>{unread > 9 ? "9+" : unread}</i>}
            </Link>
            <div className="topbar-user">
              <span className="avatar">
                {auth.user.full_name.replace("Демо · ", "").slice(0, 1)}
              </span>
              <div>
                <strong>{auth.user.full_name.replace("Демо · ", "")}</strong>
                <small>{roleNames[auth.role]}</small>
              </div>
            </div>
            <button
              onClick={auth.logout}
              className="icon-btn"
              aria-label="Выйти"
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main>
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>© 2026 · ФСП Оренбургской области</span>
          <span>
            ОренКод <i /> Демонстрационный контур
          </span>
        </footer>
      </div>
    </div>
  );
}
function Guard({ roles, children }: any) {
  const { role } = useAuth();
  return roles.includes(role) ? children : <Navigate to="/" replace />;
}
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/check-certificate/:checkToken" element={<CertificateVerification />} />
      <Route path="/p/:slug" element={<LegacyPublicProfile />} />
      <Route path="/verify/:digest" element={<LegacyPublicProfile />} />
      <Route path="/passport-preview" element={<LegacyPublicProfile />} />
      <Route path="/start" element={<Navigator />} />
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="athletes/:id/profile" element={<AthleteProfileView />} />
        <Route
          path="certificates/:id"
          element={
            <Guard roles={["athlete", "coach", "admin"]}>
              <PrivateCertificate />
            </Guard>
          }
        />
        <Route path="competitions" element={<Competitions />} />
        <Route path="competitions/:id" element={<CompetitionDetail />} />
        <Route
          path="registry"
          element={
            <Guard roles={["admin", "coach"]}>
              <Registry />
            </Guard>
          }
        />
        <Route
          path="history"
          element={
            <Guard roles={["admin", "athlete", "coach"]}>
              <History />
            </Guard>
          }
        />
        <Route
          path="coaching"
          element={
            <Guard roles={["admin", "athlete", "coach"]}>
              <Coaching />
            </Guard>
          }
        />
        <Route
          path="coaching/athletes/:id"
          element={
            <Guard roles={["coach", "admin"]}>
              <AthleteSummary />
            </Guard>
          }
        />
        <Route
          path="assignments"
          element={
            <Guard roles={["judge"]}>
              <Assignments />
            </Guard>
          }
        />
        <Route
          path="judging"
          element={<Guard roles={["judge"]}><JudgingHistory /></Guard>}
        />
        <Route path="ranks" element={<Ranks />} />
        <Route path="ratings" element={<Ratings />} />
        <Route
          path="reports"
          element={
            <Guard roles={["admin"]}>
              <Reports />
            </Guard>
          }
        />
        <Route
          path="settings"
          element={
            <Guard roles={["admin"]}>
              <Settings />
            </Guard>
          }
        />
        <Route
          path="audit"
          element={
            <Guard roles={["admin"]}>
              <Audit />
            </Guard>
          }
        />
        <Route
          path="profile"
          element={
            <Guard roles={["athlete", "coach", "judge"]}>
              <Profile />
            </Guard>
          }
        />
        <Route path="notifications" element={<Notifications />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
