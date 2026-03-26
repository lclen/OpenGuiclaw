import type { SelectHTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export type UiSelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function UiSelect({ className, children, ...props }: UiSelectProps) {
  return (
    <span className={cn('ui-select', className)}>
      <select className="ui-select__native" {...props}>
        {children}
      </select>
      <span className="ui-select__chevron" aria-hidden="true">▾</span>
    </span>
  );
}
