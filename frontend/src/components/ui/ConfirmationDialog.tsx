import { useEffect, useId, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { userFacingError } from "../../services/api";
import { Button } from "./Primitives";

export interface ConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void | Promise<void>;
  cancelLabel?: string;
  pendingLabel?: string;
  variant?: "warning" | "destructive";
  errorFallback?: string;
  confirmationText?: string;
  confirmDisabled?: boolean;
}

export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  cancelLabel = "Cancel",
  pendingLabel = "Working…",
  variant = "warning",
  errorFallback = "Unable to complete this action. Please try again.",
  confirmationText,
  confirmDisabled = false,
}: ConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const previousBodyOverflow = useRef("");
  const confirmationLock = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typedText, setTypedText] = useState("");
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!open) {
      if (dialog.open) dialog.close();
      return;
    }

    previouslyFocused.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    previousBodyOverflow.current = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();
    setError(null);
    setTypedText("");

    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousBodyOverflow.current;
      if (previouslyFocused.current?.isConnected) {
        previouslyFocused.current.focus();
      }
      previouslyFocused.current = null;
    };
  }, [open]);

  const closeIfIdle = () => {
    if (!pending && !confirmationLock.current) onOpenChange(false);
  };

  const confirm = async () => {
    if (
      pending ||
      confirmationLock.current ||
      (confirmationText !== undefined && typedText !== confirmationText)
    ) {
      return;
    }

    confirmationLock.current = true;
    setPending(true);
    setError(null);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (reason) {
      setError(userFacingError(reason, errorFallback));
    } finally {
      confirmationLock.current = false;
      setPending(false);
    }
  };

  return (
    <dialog
      ref={dialogRef}
      className={`confirmation-dialog confirmation-${variant}`}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        closeIfIdle();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) closeIfIdle();
      }}
    >
      <div className="confirmation-heading">
        <span className="confirmation-icon" aria-hidden="true">
          <AlertTriangle size={19} />
        </span>
        <h2 id={titleId}>{title}</h2>
      </div>
      <p className="confirmation-description" id={descriptionId}>
        {description}
      </p>
      {confirmationText !== undefined && (
        <label className="confirmation-input-label">
          Type <strong>{confirmationText}</strong> to confirm
          <input
            className="control"
            autoComplete="off"
            value={typedText}
            onChange={(event) => setTypedText(event.target.value)}
            disabled={pending}
          />
        </label>
      )}
      {error && (
        <p className="confirmation-error" role="alert">
          {error}
        </p>
      )}
      <div className="confirmation-actions">
        <Button
          ref={cancelRef}
          type="button"
          variant="secondary"
          disabled={pending}
          onClick={closeIfIdle}
        >
          {cancelLabel}
        </Button>
        <Button
          type="button"
          variant={variant === "destructive" ? "danger" : "primary"}
          disabled={
            pending ||
            confirmDisabled ||
            (confirmationText !== undefined && typedText !== confirmationText)
          }
          onClick={() => void confirm()}
        >
          {pending ? pendingLabel : confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
