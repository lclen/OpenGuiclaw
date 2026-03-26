import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '../../utils/cn';

export type UiInputShellProps = HTMLAttributes<HTMLDivElement> & {
  dragOver?: boolean;
  overlay?: ReactNode;
  header?: ReactNode;
  leading?: ReactNode;
  trailing?: ReactNode;
  footer?: ReactNode;
};

export function UiInputShell({
  className,
  dragOver = false,
  overlay,
  header,
  leading,
  trailing,
  footer,
  children,
  ...props
}: UiInputShellProps) {
  return (
    <div className={cn('ui-input-shell', dragOver && 'is-dragover', className)} {...props}>
      {header ? <div className="ui-input-shell__header">{header}</div> : null}
      {overlay ? <div className="ui-input-shell__overlay">{overlay}</div> : null}
      <div className="ui-input-shell__main">
        {leading ? <div className="ui-input-shell__leading">{leading}</div> : null}
        <div className="ui-input-shell__content">{children}</div>
        {trailing ? <div className="ui-input-shell__trailing">{trailing}</div> : null}
      </div>
      {footer ? <div className="ui-input-shell__footer">{footer}</div> : null}
    </div>
  );
}
