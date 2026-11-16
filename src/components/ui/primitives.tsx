import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Check, ChevronDown, Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/* Button                                                                      */
/* -------------------------------------------------------------------------- */
const buttonStyles = cva(
  "inline-flex select-none items-center justify-center gap-1.5 rounded-lg border text-[12.5px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-line bg-elevated text-ink hover:border-accent/40 hover:text-accent",
        primary: "border-accent/45 bg-accent/15 text-accent hover:bg-accent/25",
        danger: "border-danger/45 bg-danger/10 text-danger hover:bg-danger/20",
        ghost: "border-transparent bg-transparent text-muted hover:bg-elevated hover:text-ink",
        teal: "border-teal/45 bg-teal/12 text-teal hover:bg-teal/20",
      },
      size: {
        sm: "h-7 px-2.5",
        md: "h-8.5 px-3 py-1.5",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonStyles> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonStyles({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

/* -------------------------------------------------------------------------- */
/* Surfaces                                                                    */
/* -------------------------------------------------------------------------- */
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  dense,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  dense?: boolean;
}) {
  return (
    <section className={cn("surface flex min-h-0 flex-col overflow-hidden", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            {title ? (
              <h2 className="truncate text-[13px] font-semibold tracking-tight text-ink">{title}</h2>
            ) : null}
            {subtitle ? <p className="truncate text-[11.5px] text-muted">{subtitle}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-1.5">{actions}</div> : null}
        </header>
      )}
      <div className={cn(dense ? "p-0" : "p-4", "min-h-0 flex-1 overflow-auto scroll-thin", bodyClassName)}>
        {children}
      </div>
    </section>
  );
}

export function Kpi({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "default" | "accent" | "teal" | "amber" | "danger";
}) {
  const toneClass = {
    default: "text-ink",
    accent: "text-accent",
    teal: "text-teal",
    amber: "text-amber",
    danger: "text-danger",
  }[tone];
  return (
    <div className="kpi">
      <div className={cn("kpi-value", toneClass)}>{value}</div>
      <div className="kpi-label mt-0.5">{label}</div>
      {hint ? <div className="mt-0.5 text-[10.5px] text-muted/80">{hint}</div> : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Inputs                                                                      */
/* -------------------------------------------------------------------------- */
export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("field", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn("field min-h-[72px] resize-y", className)} {...props} />;
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select className={cn("field appearance-none pr-8", className)} {...props}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
    </div>
  );
}

export function Label({ className, children, hint }: { className?: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className={cn("mb-1 flex items-baseline justify-between gap-2", className)}>
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{children}</span>
      {hint ? <span className="text-[10.5px] text-muted/70">{hint}</span> : null}
    </label>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex w-full items-start justify-between gap-4 rounded-lg border border-line bg-elevated/60 px-3 py-2 text-left transition hover:border-accent/30 disabled:opacity-60"
    >
      <span className="min-w-0">
        <span className="block text-[12.5px] font-medium text-ink">{label}</span>
        {hint ? <span className="mt-0.5 block text-[11px] leading-snug text-muted">{hint}</span> : null}
      </span>
      <span
        className={cn(
          "mt-0.5 flex h-4.5 w-8 shrink-0 items-center rounded-full border px-0.5 transition",
          checked ? "border-accent/60 bg-accent/30" : "border-line bg-panel",
        )}
        style={{ height: 18, width: 32 }}
      >
        <span
          className={cn(
            "h-3.5 w-3.5 rounded-full transition",
            checked ? "ml-auto bg-accent" : "bg-muted/60",
          )}
        />
      </span>
    </button>
  );
}

export function Checkbox({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: React.ReactNode;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label className={cn("flex cursor-pointer items-start gap-2.5 text-[12.5px]", disabled && "opacity-60")}>
      <span
        onClick={() => !disabled && onChange(!checked)}
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition",
          checked ? "border-accent bg-accent/25 text-accent" : "border-line bg-elevated",
        )}
      >
        {checked ? <Check className="h-3 w-3" /> : null}
      </span>
      <span className="min-w-0">
        <span className="text-ink">{label}</span>
        {hint ? <span className="mt-0.5 block text-[11px] text-muted">{hint}</span> : null}
      </span>
    </label>
  );
}

/* -------------------------------------------------------------------------- */
/* Feedback                                                                    */
/* -------------------------------------------------------------------------- */
export function Badge({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: "default" | "accent" | "teal" | "amber" | "danger" | "muted";
  className?: string;
}) {
  const tones = {
    default: "border-line bg-elevated text-muted",
    accent: "border-accent/40 bg-accent/12 text-accent",
    teal: "border-teal/40 bg-teal/12 text-teal",
    amber: "border-amber/40 bg-amber/12 text-amber",
    danger: "border-danger/40 bg-danger/12 text-danger",
    muted: "border-line/70 bg-panel text-muted",
  }[tone];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium", tones, className)}>
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-muted">
      <Loader2 className="h-4 w-4 animate-spin text-accent" />
      {label ?? "Loading…"}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      {icon ? <div className="mb-1 text-muted/70">{icon}</div> : null}
      <p className="text-[13px] font-medium text-ink">{title}</p>
      {description ? <p className="max-w-md text-[12px] leading-relaxed text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="m-4 rounded-xl border border-danger/30 bg-danger/8 p-3">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
        <div className="min-w-0">
          <p className="text-[12.5px] font-medium text-danger">Request failed</p>
          <p className="mt-0.5 break-words text-[11.5px] leading-relaxed text-muted">{error}</p>
          {onRetry ? (
            <Button size="sm" className="mt-2" onClick={onRetry}>
              Retry
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-line/70", className)}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-teal to-accent transition-[width] duration-300"
        style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Tabs                                                                        */
/* -------------------------------------------------------------------------- */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: { value: T; label: React.ReactNode; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1 rounded-lg border border-line bg-panel p-1", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.value}
          onClick={() => onChange(tab.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-[12px] font-medium transition",
            value === tab.value ? "bg-elevated text-ink shadow-card" : "text-muted hover:text-ink",
          )}
        >
          {tab.label}
          {tab.count !== undefined ? (
            <span className="ml-1.5 text-[10.5px] text-muted">{tab.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function Toolbar({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex flex-wrap items-end gap-2", className)}>{children}</div>;
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <Label hint={hint}>{label}</Label>
      {children}
    </div>
  );
}
