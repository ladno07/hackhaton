import { createContext, useContext, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "./lib";
const AuthContext = createContext<any>(null);
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [token, setToken] = useState(sessionStorage.getItem("token"));
  const [role, setRole] = useState(sessionStorage.getItem("role") || "athlete");
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: async () => (await api.get("/auth/me")).data,
    enabled: !!token,
    retry: false,
  });
  function login(data: any) {
    sessionStorage.setItem("token", data.access_token);
    sessionStorage.setItem("role", data.user.roles[0]);
    setRole(data.user.roles[0]);
    setToken(data.access_token);
    qc.clear();
  }
  function logout() {
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("role");
    setToken(null);
    qc.clear();
  }
  function switchRole(r: string) {
    sessionStorage.setItem("role", r);
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
        loading: me.isPending,
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
  function toast(text: string, error = false) {
    setMessage({ text, error });
    setTimeout(() => setMessage(null), 6000);
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
  const { role } = useAuth();
  return useQuery<any>({
    queryKey: [role, url],
    queryFn: async () => (await api.get(url)).data,
    enabled,
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
