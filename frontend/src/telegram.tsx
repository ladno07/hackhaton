import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./lib";
import { useAction } from "./state";
import { Button } from "./components/ui/button";
import { State } from "./components/shared";

export function TelegramConnection() {
  const query = useQuery({ queryKey: ["telegram-link"], queryFn: async () => (await api.get("/telegram/link")).data,
    refetchInterval: 5000 });
  const action = useAction();
  const [invite, setInvite] = useState<any>(null);
  const [clock, setClock] = useState(Date.now());
  const [copyStatus, setCopyStatus] = useState("");
  const state = query.data;
  useEffect(() => {
    if (!invite) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [invite]);
  useEffect(() => { if (state?.connected) setInvite(null); }, [state?.connected]);
  const remaining = invite ? Math.max(0, Math.ceil((new Date(invite.expires_at).getTime() - clock) / 1000)) : 0;
  const countdown = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`;
  return <section className="panel panel-padding telegram-connection">
    <h2>Telegram</h2>
    <State query={query}>
      {state && <>
        <p>{state.connected ? "Аккаунт подключён. Новые уведомления будут приходить в Telegram."
          : state.blocked ? "Бот заблокирован в Telegram. Разблокируйте его, отключите старую привязку и подключите заново."
          : state.available ? "Подключите бота, чтобы получать события и напоминания о соревнованиях."
          : "Telegram-бот пока не настроен администратором."}</p>
        {(state.connected || state.blocked) ? <Button variant="outline" disabled={action.isPending}
          onClick={async () => { try { await action.mutateAsync({ method: "delete", url: "/telegram/link" }); setInvite(null); } catch {} }}>
          Отключить Telegram</Button> : state.available && <>
          <Button disabled={action.isPending} onClick={async () => {
            try {
              const result = await action.mutateAsync({ url: "/telegram/link-code" });
              setClock(Date.now()); setCopyStatus(""); setInvite(result);
            } catch {}
          }}>{invite ? "Получить новый код" : "Привязать Telegram"}</Button>
          {invite && <div className="telegram-pairing" aria-live="polite">
            <p>1. Скопируйте код привязки:</p>
            <input className="telegram-pairing-code" aria-label="Одноразовый код привязки Telegram" readOnly
              value={invite.code} onFocus={e => e.currentTarget.select()} />
            <Button variant="outline" disabled={!remaining} onClick={async () => {
              try { await navigator.clipboard.writeText(invite.code); setCopyStatus("Код скопирован"); }
              catch { setCopyStatus("Выделите код и скопируйте его вручную"); }
            }}>Скопировать код</Button>
            <p>{remaining ? `Код действует ещё ${countdown}.` : "Код истёк. Получите новый."} {copyStatus}</p>
            <p>2. <a href={invite.bot_url} target="_blank" rel="noreferrer">Откройте бота в Telegram</a> и отправьте ему эти 8 цифр.</p>
            <p>3. Проверьте имя аккаунта и нажмите в боте «Подтвердить подключение».</p>
            <small>Не передавайте код другим людям. Новый код отменяет предыдущий.</small>
          </div>}
        </>}
      </>}
    </State>
  </section>;
}

export function TelegramDeliveryStatus({ delivery }: { delivery: any }) {
  if (!delivery) return null;
  const labels: Record<string, string> = { sent: "доставлено", pending: delivery.last_error ? "ошибка, повторим" : "в очереди",
    cancelled: "доставка отменена", blocked: "бот заблокирован", failed: "ошибка отправки" };
  return <><br />Telegram: {labels[delivery.status] || delivery.status}</>;
}
