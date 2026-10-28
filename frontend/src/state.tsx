import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorText, refreshSession, endSession } from "./lib";
const AuthContext = createContext<any>(null);
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [token, setToken] = useState(sessionStorage.getItem("token"));
  const [role, setRole] = useState(sessionStorage.getItem("role") || localStorage.getItem("orencode.role") || "athlete");
  const [restoring, setRestoring] = useState(!token);
  useEffect(() => {
    const updated = (event: Event) => {
      if ((event as CustomEvent).detail?.accountChanged) qc.clear();
      setToken(sessionStorage.getItem("token"));
      setRole(sessionStorage.getItem("role") || "athlete");
    };
    const ended = () => { setToken(null); qc.clear(); };
    window.addEventListener("orencode:session-refreshed", updated);
    window.addEventListener("orencode:session-ended", ended);
    if (!sessionStorage.getItem("token")) {
      refreshSession().catch(() => {}).finally(() => setRestoring(false));
    } else setRestoring(false);
    return () => {
      window.removeEventListener("orencode:session-refreshed", updated);
      window.removeEventListener("orencode:session-ended", ended);
    };
  }, [qc]);
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: async () => (await api.get("/auth/me")).data,
    enabled: !!token,
    retry: false,
  });
  function login(data: any) {
    sessionStorage.setItem("orencode.user", String(data.user.id));
    sessionStorage.setItem("token", data.access_token);
    sessionStorage.setItem("role", data.user.roles[0]);
    localStorage.setItem("orencode.role", data.user.roles[0]);
    setRole(data.user.roles[0]);
    setToken(data.access_token);
    qc.clear();
  }
  async function logout() {
    try { await endSession(); } catch {
      window.alert("Не удалось завершить сессию. Проверьте соединение и повторите выход.");
      return;
    }
    localStorage.removeItem("orencode.role");
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("role");
    sessionStorage.removeItem("orencode.user");
    setToken(null);
    qc.clear();
  }
  function switchRole(r: string) {
    sessionStorage.setItem("role", r);
    localStorage.setItem("orencode.role", r);
    setRole(r);
    qc.clear();
  }
  return (
    <AuthContext.Provider
      value={{
        token,
        user: me.data,
        role,
        login,
        logout,
        switchRole,
        restoring,
        loading: restoring || me.isPending,
        error: me.error,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export const useAuth = () => useContext(AuthContext);
const ToastContext = createContext<any>(null);
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [message, setMessage] = useState<any>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function toast(text: string, error = false) {
    // a new message gets its full time: the previous timer must not close it
    clearTimeout(timer.current);
    setMessage({ text, error });
    timer.current = setTimeout(() => setMessage(null), 6000);
  }
  return (
    <ToastContext.Provider value={toast}>
      {children}
      {message && (
        <div
          role="status"
          className={"toast " + (message.error ? "toast-error" : "")}
        >
          {message.text}
          <button
            aria-label="Закрыть уведомление"
            onClick={() => setMessage(null)}
          >
            ×
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);
export function useData(url: string, enabled = true) {
  const { role, token, restoring } = useAuth();
  return useQuery<any>({
    queryKey: [role, url],
    queryFn: async () => (await api.get(url)).data,
    enabled: enabled && !!token && !restoring,
    retry: 1,
  });
}
export function useAction() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: async ({ method = "post", url, data }: any) =>
      (await api.request({ method, url, data })).data,
    onSuccess: () => {
      qc.invalidateQueries();
      toast("Изменения сохранены");
    },
    onError: (e) => toast(errorText(e), true),
  });
}
