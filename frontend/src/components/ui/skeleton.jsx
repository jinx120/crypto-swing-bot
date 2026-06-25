import { cn } from '../../lib/utils.js'

export function Skeleton({ className }) {
  return <div className={cn('animate-pulse rounded-md bg-muted/60', className)} />
}
