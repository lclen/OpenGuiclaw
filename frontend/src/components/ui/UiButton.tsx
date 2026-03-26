import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../utils/cn';

export type UiButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'icon';
  size?: 'sm' | 'md' | 'lg';
  active?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
};

export function UiButton({
  className,
  variant = 'secondary',
  size = 'md',
  active = false,
  leading,
  trailing,
  children,
  type = 'button',
  ...props
}: UiButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'ui-btn',
        `ui-btn--${variant}`,
        `ui-btn--${size}`,
        active && 'is-active',
        className
      )}
      {...props}
    >
      {leading ? <span className="ui-btn__icon">{leading}</span> : null}
      {children ? <span className="ui-btn__label">{children}</span> : null}
      {trailing ? <span className="ui-btn__icon ui-btn__icon--trail">{trailing}</span> : null}
    </button>
  );
}
