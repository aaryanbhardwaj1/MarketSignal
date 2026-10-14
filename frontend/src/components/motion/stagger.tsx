import { Children, cloneElement, isValidElement, type CSSProperties, type ElementType, type ReactElement, type ReactNode } from "react";
import { cx } from "@/lib/cx";

/** Inline style that positions one child in a staggered reveal (40ms steps, capped at 10). */
export function staggerStyle(index: number): CSSProperties {
  return { "--ms-i": Math.max(0, index) } as CSSProperties;
}

/**
 * Staggered list reveal: each direct child fades and rises 4px, 40ms after the previous one.
 * Use for lists that arrive together (insight rows, stages), not for long paginated lists.
 */
export function Stagger({
  as: Tag = "div",
  className,
  children,
  ...rest
}: {
  as?: ElementType;
  className?: string;
  children: ReactNode;
} & Record<string, unknown>) {
  let i = 0;
  const items = Children.map(children, (child) => {
    if (!isValidElement(child)) return child;
    const el = child as ReactElement<{ style?: CSSProperties }>;
    return cloneElement(el, { style: { ...el.props.style, ...staggerStyle(i++) } });
  });
  return (
    <Tag className={cx("ms-stagger", className)} {...rest}>
      {items}
    </Tag>
  );
}
