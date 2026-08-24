"use client";

import { useId } from "react";
import { cn } from "./cn";

const CONTROL =
  "h-9 w-full rounded-control border border-line-strong bg-surface px-2.5 text-sm text-ink " +
  "placeholder:text-ink-faint disabled:bg-surface-sunken disabled:text-ink-muted";

export function Field({
  label,
  hint,
  htmlFor,
  className,
  children,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  htmlFor?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <label htmlFor={htmlFor} className="label-caps mb-1 block">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[12px] text-ink-muted">{hint}</p>}
    </div>
  );
}

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  fieldClassName?: string;
};

export function Input({ label, hint, fieldClassName, className, ...rest }: InputProps) {
  const generated = useId();
  const id = rest.id || generated;
  const control = <input {...rest} id={id} className={cn(CONTROL, className)} />;
  if (!label) return control;
  return (
    <Field label={label} hint={hint} htmlFor={id} className={fieldClassName}>
      {control}
    </Field>
  );
}

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  fieldClassName?: string;
};

export function Select({ label, hint, fieldClassName, className, children, ...rest }: SelectProps) {
  const generated = useId();
  const id = rest.id || generated;
  const control = (
    <select {...rest} id={id} className={cn(CONTROL, "cursor-pointer pr-7", className)}>
      {children}
    </select>
  );
  if (!label) return control;
  return (
    <Field label={label} hint={hint} htmlFor={id} className={fieldClassName}>
      {control}
    </Field>
  );
}

type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  fieldClassName?: string;
};

export function Textarea({ label, hint, fieldClassName, className, ...rest }: TextareaProps) {
  const generated = useId();
  const id = rest.id || generated;
  const control = (
    <textarea
      {...rest}
      id={id}
      className={cn(
        "w-full rounded-control border border-line-strong bg-surface px-3 py-2 text-sm leading-6",
        "text-ink placeholder:text-ink-faint",
        className
      )}
    />
  );
  if (!label) return control;
  return (
    <Field label={label} hint={hint} htmlFor={id} className={fieldClassName}>
      {control}
    </Field>
  );
}

/** The filter bar that sits above a screen's content. */
export function Toolbar({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-end gap-3 rounded-card border border-line bg-surface px-4 py-3 shadow-card",
        className
      )}
    >
      {children}
    </div>
  );
}
