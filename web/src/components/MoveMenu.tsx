import { useEffect, useId, useRef, useState } from 'react';

export interface MoveOption {
  label: string;
  onSelect: () => void;
}

/** "Move to…": the keyboard-accessible alternative to dragging. */
export function MoveMenu({ label, options }: { label: string; options: MoveOption[] }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    const outside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!menu.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('mousedown', outside);
    return () => document.removeEventListener('mousedown', outside);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const items = Array.from(
      menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [],
    );
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      items[(at + 1) % items.length]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      items[(at - 1 + items.length) % items.length]?.focus();
    }
  };

  return (
    <span className="relative inline-block">
      <button
        ref={button}
        type="button"
        aria-label={`Move ${label}`}
        title="Move to…"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        className="rounded px-1 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
      >
        ⇄
      </button>
      {open && (
        <div
          ref={menu}
          id={menuId}
          role="menu"
          aria-label={`Move ${label} to`}
          onKeyDown={onKeyDown}
          className="absolute right-0 z-20 mt-1 min-w-36 rounded-md border border-neutral-300 bg-white py-1 shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
        >
          {options.map((o) => (
            <button
              key={o.label}
              type="button"
              role="menuitem"
              onClick={() => {
                close();
                o.onSelect();
              }}
              className="block w-full px-3 py-1 text-left text-sm hover:bg-neutral-100 focus:bg-neutral-100 focus:outline-none dark:hover:bg-neutral-800 dark:focus:bg-neutral-800"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
