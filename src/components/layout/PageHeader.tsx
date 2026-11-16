import * as React from "react";
import { cn } from "@/lib/format";

export function PageHeader({
  title,
  description,
  actions,
  badges,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  badges?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3", className)}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h1>
          {badges}
        </div>
        {description ? (
          <p className="mt-0.5 max-w-3xl text-[11.5px] leading-relaxed text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-1.5">{actions}</div> : null}
    </header>
  );
}

export function PageBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("h-full overflow-y-auto scroll-thin", className)}>{children}</div>
  );
}

export function SplitPage({
  header,
  children,
  className,
}: {
  header: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      {header}
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
