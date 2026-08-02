"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  icon?: React.ReactNode;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", invalid, icon, ...props }, ref) => {
    const field = (
      <input
        ref={ref}
        type={type}
        aria-invalid={invalid || undefined}
        className={cn(
          "h-9 w-full rounded-lg border border-line bg-elevated/60 px-3 text-sm text-ink transition-colors placeholder:text-ink-faint",
          "focus:border-primary/60 focus:bg-elevated focus:outline-none focus:ring-2 focus:ring-primary/25",
          "disabled:cursor-not-allowed disabled:opacity-50",
          invalid && "border-loss/60 focus:border-loss focus:ring-loss/25",
          icon && "pl-9",
          className,
        )}
        {...props}
      />
    );
    if (!icon) return field;
    return (
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint [&_svg]:size-4">
          {icon}
        </span>
        {field}
      </div>
    );
  },
);
Input.displayName = "Input";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-lg border border-line bg-elevated/60 px-3 py-2 text-sm text-ink transition-colors placeholder:text-ink-faint",
      "focus:border-primary/60 focus:bg-elevated focus:outline-none focus:ring-2 focus:ring-primary/25",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-xs font-medium text-ink-muted", className)} {...props} />;
}

function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <p className="mt-1 text-2xs text-loss">{children}</p>;
}

export { Input, Textarea, Label, FieldError };
