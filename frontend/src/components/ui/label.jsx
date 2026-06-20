import { cn } from '../../lib/utils.js'

export function Label({ className, ...props }) {
  return <label className={cn('text-xs font-medium text-muted-foreground', className)} {...props} />
}
