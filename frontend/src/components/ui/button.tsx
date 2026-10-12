import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "border-accent bg-accent text-white hover:border-accent-hover hover:bg-accent-hover",
  secondary: "border-border-strong bg-surface text-primary hover:bg-surface-muted",
  ghost: "border-transparent bg-transparent text-secondary hover:bg-surface-muted hover:text-primary",
  danger: "border-danger bg-danger text-white hover:opacity-90",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-sm",
  md: "h-9 px-3.5 text-base",
};

/** Class string for any element that should look like a button (links, summary, label). */
export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md"): string {
  return cx(
    "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50",
    SIZES[size],
    VARIANTS[variant],
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="h-3.5 w-3.5 rounded-full border-2 border-current border-r-transparent motion-safe:animate-spin"
    />
  );
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  iconLeft,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  iconLeft?: ReactNode;
}) {
  return (
    <button
      type={type}
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(buttonClass(variant, size), className)}
    >
      {loading ? <Spinner /> : iconLeft}
      {children}
    </button>
  );
}

export function LinkButton({
  href,
  variant = "secondary",
  size = "md",
  iconLeft,
  className,
  children,
  ...rest
}: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconLeft?: ReactNode;
}) {
  return (
    <Link href={href} {...rest} className={cx(buttonClass(variant, size), className)}>
      {iconLeft}
      {children}
    </Link>
  );
}
