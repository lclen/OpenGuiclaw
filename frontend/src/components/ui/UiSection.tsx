import type { ReactNode } from 'react';
import { CaretDownIcon } from '../icons/ShellIcons';
import { cn } from '../../utils/cn';

export type UiSectionProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  open?: boolean;
  onToggle?: () => void;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
};

export function UiSection({
  title,
  subtitle,
  right,
  open = false,
  onToggle,
  children,
  className,
  bodyClassName
}: UiSectionProps) {
  return (
    <section className={cn('ui-section', open && 'is-open', className)}>
      <button type="button" className="ui-section__header" onClick={onToggle} aria-expanded={open}>
        <span className="ui-section__heading">
          <CaretDownIcon className={cn('ui-section__chevron', open && 'is-open')} />
          <span className="ui-section__copy">
            <span className="ui-section__title">{title}</span>
            {subtitle ? <span className="ui-section__subtitle">{subtitle}</span> : null}
          </span>
        </span>
        {right ? <span className="ui-section__right">{right}</span> : null}
      </button>
      {open ? <div className={cn('ui-section__body', bodyClassName)}>{children}</div> : null}
    </section>
  );
}
