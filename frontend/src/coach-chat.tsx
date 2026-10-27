import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorText } from "./lib";
import { useAuth, useData, useToast } from "./state";
import { chatDay, chatDayLabel, chatPerson } from "./coach-chat-format";
import { CoachChatHistory } from "./coach-chat-history";
import { Dialog } from "./components/ui/dialog";
import { Button } from "./components/ui/button";
import { State } from "./components/shared";

function resizeComposer(input: HTMLTextAreaElement) {
  const style = getComputedStyle(input);
  const lineHeight = parseFloat(style.lineHeight);
  const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
  const maximum = lineHeight * 4 + padding + border;
  input.style.height = "auto";
  const height = input.scrollHeight + border;
  input.style.height = `${Math.min(height, maximum)}px`;
  input.style.overflowY = height > maximum ? "auto" : "hidden";
}

export function CoachChat({ linkId, onClose }: { linkId: number; onClose: () => void }) {
  const { role, user } = useAuth();
  const links = useData("/links");
  const link = links.data?.find((item: any) => item.id === linkId);
  const person = chatPerson((role === "athlete" ? link?.coach : link?.athlete) || "",
    role === "athlete" ? link?.coach_sex : link?.athlete_sex);
  const toast = useToast();
  const qc = useQueryClient();
  const [body, setBody] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    if (input.current) resizeComposer(input.current);
  }, [body]);
  useEffect(() => {
    const element = input.current;
    if (!element) return;
    let width = element.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const nextWidth = element.getBoundingClientRect().width;
      if (nextWidth !== width) {
        width = nextWidth;
        resizeComposer(element);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const key = [role, "coach-chat", linkId];
  const messages = useInfiniteQuery({
    queryKey: key,
    initialPageParam: undefined as number | undefined,
    queryFn: async ({ pageParam }) => (await api.get(`/links/${linkId}/messages`, {
      params: pageParam ? { before: pageParam } : {},
    })).data as any[],
    getNextPageParam: (last: any[]) => last.length === 100 ? last[last.length - 1].id : undefined,
    refetchInterval: 5000,
    retry: false,
  });
  const send = useMutation({
    mutationFn: async (text: string) => api.post(`/links/${linkId}/messages`, { body: text }),
    onSuccess: () => {
      setBody("");
      qc.invalidateQueries({ queryKey: key });
      requestAnimationFrame(() => input.current?.focus({ preventScroll: true }));
    },
    onError: (error) => toast(errorText(error), true),
  });
  const items = messages.data?.pages.flat().slice().reverse() || [];
  const canSend = !!body.trim() && !send.isPending && !messages.error && !messages.isPending;
  const submit = () => { if (canSend) send.mutate(body.trim()); };
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }} title={person.title} wide>
      <p className="muted">Уведомления о сообщениях тренера приходят в Telegram только спортсмену, если он подключил бота.</p>
      <State query={messages}>
        <CoachChatHistory newestId={items.at(-1)?.id} oldestId={items[0]?.id}
          ownLatest={items.at(-1)?.sender_id === user?.id}>
          {messages.hasNextPage && <Button variant="ghost" disabled={messages.isFetchingNextPage}
            onClick={() => messages.fetchNextPage()}>Загрузить предыдущие сообщения</Button>}
          {!items.length && <p className="muted">Сообщений пока нет. Начните переписку.</p>}
          {items.map((message: any, index: number) => (
            <Fragment key={message.id}>
              {(index === 0 || chatDay(items[index - 1].created_at) !== chatDay(message.created_at)) && (
                <div className="coach-chat-day" data-chat-day={chatDay(message.created_at)}>
                  <span>{chatDayLabel(chatDay(message.created_at))}</span>
                </div>
              )}
            <article data-chat-day={chatDay(message.created_at)} className={`coach-chat-message ${message.sender_id === user?.id ? "coach-chat-own" : ""}`}>
              <small>{message.sender_id === user?.id ? "Вы" : person.label}
                {" · "}<time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString("ru-RU", {
                  hour: "2-digit", minute: "2-digit",
                })}</time></small>
              <p>{message.body}</p>
            </article>
            </Fragment>
          ))}
        </CoachChatHistory>
      </State>
      <form className="coach-chat-composer" onSubmit={(event) => { event.preventDefault(); submit(); }}>
        <textarea ref={input} id="coach-chat-body" aria-label="Сообщение" value={body}
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          maxLength={4000} rows={1} required autoFocus disabled={send.isPending} placeholder="Напишите сообщение…" />
        {!!body.trim() && (
          <button type="submit" className="coach-chat-send" disabled={!canSend}
            aria-label={send.isPending ? "Отправляем сообщение" : "Отправить сообщение"}>
            {send.isPending ? <Loader2 size={22} className="spin" /> : <ArrowUp size={24} strokeWidth={2.5} />}
          </button>
        )}
      </form>
    </Dialog>
  );
}
