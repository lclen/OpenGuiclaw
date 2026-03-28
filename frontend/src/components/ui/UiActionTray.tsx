import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type UiActionTrayProps = HTMLAttributes<HTMLDivElement>;

export function UiActionTray({ className, children, ...props }: UiActionTrayProps) {
  return (
    <div className={cn('ui-action-tray', className)} {...props}>
      {children}
    </div>
  );
}
