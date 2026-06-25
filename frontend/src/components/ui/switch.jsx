import { cn } from '../../lib/utils.js'

export function Switch({ checked, onCheckedChange, disabled }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
        checked ? 'bg-primary' : 'bg-muted',
        disabled && 'opacity-50',
      )}
    >
      <span className={cn(
        'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
        checked ? 'translate-x-4' : 'translate-x-0.5',
      )} />
    </button>
  )
}
