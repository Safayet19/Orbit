import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";

type ToastTone = "success" | "error";
interface ToastMessage {
  id: number;
  tone: ToastTone;
  message: string;
}

const ToastContext = createContext<(tone: ToastTone, message: string) => void>(
  () => undefined,
);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, number>());
  useEffect(
    () => () => {
      timers.current.forEach((timer) => window.clearTimeout(timer));
      timers.current.clear();
    },
    [],
  );
  const notify = useCallback((tone: ToastTone, message: string) => {
    const id = ++nextId.current;
    setMessages((current) => [...current.slice(-2), { id, tone, message }]);
    timers.current.set(
      id,
      window.setTimeout(() => {
        setMessages((current) => current.filter((item) => item.id !== id));
        timers.current.delete(id);
      }, 5000),
    );
  }, []);
  const dismiss = (id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    timers.current.delete(id);
    setMessages((current) => current.filter((item) => item.id !== id));
  };
  const value = useMemo(() => notify, [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {messages.map((item) => {
          const Icon = item.tone === "success" ? CheckCircle2 : AlertCircle;
          return (
            <div
              className={`toast toast-${item.tone}`}
              key={item.id}
              role={item.tone === "error" ? "alert" : "status"}
            >
              <Icon size={17} />
              <span>{item.message}</span>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() => dismiss(item.id)}
              >
                <X size={15} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
