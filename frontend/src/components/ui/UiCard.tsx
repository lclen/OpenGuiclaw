import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type UiCardProps = HTMLAttributes<HTMLElement> & {
  as?: 'article' | 'section' | 'div' | 'aside';
  variant?: 'default' | 'elevated' | 'subtle' | 'status';
};

export function UiCard({
  as = 'div',
  className,
  variant = 'default',
  children,
  ...props
}: UiCardProps) {
  const Component = as;
  return (
    <Component className={cn('ui-card', `ui-card--${variant}`, className)} {...props}>
      {children}
    </Component>
  );
}
