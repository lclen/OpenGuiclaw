import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type UiStatusPillProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'disabled';
};

export function UiStatusPill({ className, tone = 'neutral', children, ...props }: UiStatusPillProps) {
  return (
    <span className={cn('ui-pill', `ui-pill--${tone}`, className)} {...props}>
      {children}
    </span>
  );
}
