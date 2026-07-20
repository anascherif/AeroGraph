import type { LucideIcon } from "lucide-react"

interface Props {
  icon: LucideIcon
  title: string
  description: string
  children?: React.ReactNode
}

export function EmptyState({ icon: Icon, title, description, children }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-card/50 px-6 py-16 text-center">
      <span
        className="flex size-14 items-center justify-center rounded-full bg-secondary text-muted-foreground"
        aria-hidden
      >
        <Icon className="size-7" />
      </span>
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="max-w-md text-pretty text-sm text-muted-foreground">
        {description}
      </p>
      {children}
    </div>
  )
}
