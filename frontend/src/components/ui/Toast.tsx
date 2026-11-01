import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
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
  const notify = useCallback((tone: ToastTone, message: string) => {
    const id = Date.now() + Math.random();
    setMessages((current) => [...current, { id, tone, message }]);
    window.setTimeout(
      () => setMessages((current) => current.filter((item) => item.id !== id)),
      5000,
    );
  }, []);
  const value = useMemo(() => notify, [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {messages.map((item) => {
          const Icon = item.tone === "success" ? CheckCircle2 : AlertCircle;
          return (
            <div className={`toast toast-${item.tone}`} key={item.id} role="status">
              <Icon size={17} />
              <span>{item.message}</span>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() =>
                  setMessages((current) =>
                    current.filter((entry) => entry.id !== item.id),
                  )
                }
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
