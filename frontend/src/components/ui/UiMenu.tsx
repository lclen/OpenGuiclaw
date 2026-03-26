import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '../../utils/cn';

export type UiMenuSurfaceProps = HTMLAttributes<HTMLDivElement> & {
  backdrop?: boolean;
  onBackdropClick?: () => void;
};

export function UiMenuSurface({
  className,
  children,
  backdrop = false,
  onBackdropClick,
  ...props
}: UiMenuSurfaceProps) {
  return (
    <>
      {backdrop ? <div className="ui-menu__backdrop" aria-hidden="true" onClick={onBackdropClick} /> : null}
      <div className={cn('ui-menu', className)} {...props}>
        {children}
      </div>
    </>
  );
}

export type UiMenuItemProps = HTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
  selected?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
  as?: 'button' | 'div';
};

export function UiMenuItem({
  className,
  active = false,
  selected = false,
  leading,
  trailing,
  children,
  as = 'button',
  ...props
}: UiMenuItemProps) {
  if (as === 'div') {
    return (
      <div className={cn('ui-menu__item', active && 'is-active', selected && 'is-selected', className)}>
        {leading ? <span className="ui-menu__item-leading">{leading}</span> : null}
        <span className="ui-menu__item-copy">{children}</span>
        {trailing ? <span className="ui-menu__item-trailing">{trailing}</span> : null}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={cn('ui-menu__item', active && 'is-active', selected && 'is-selected', className)}
      {...props}
    >
      {leading ? <span className="ui-menu__item-leading">{leading}</span> : null}
      <span className="ui-menu__item-copy">{children}</span>
      {trailing ? <span className="ui-menu__item-trailing">{trailing}</span> : null}
    </button>
  );
}

export function UiMenuDivider() {
  return <div className="ui-menu__divider" role="separator" />;
}
