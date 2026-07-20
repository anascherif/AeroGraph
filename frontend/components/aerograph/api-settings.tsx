"use client"

import { Settings2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { getApiBase, getDefaultBase, setApiBase } from "@/lib/aerograph/config"

export function ApiSettings() {
  const [value, setValue] = useState("")
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (open) setValue(getApiBase())
  }, [open])

  function save() {
    setApiBase(value)
    toast.success("API endpoint updated", { description: value || getDefaultBase() })
    setOpen(false)
  }

  function reset() {
    setApiBase("")
    setValue(getDefaultBase())
    toast.success("Reset to default endpoint", { description: getDefaultBase() })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="icon"
            aria-label="Configure backend API endpoint"
          />
        }
      >
        <Settings2 className="size-4" aria-hidden />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <div className="flex flex-col gap-3">
          <div>
            <h3 className="font-bold">Backend endpoint</h3>
            <p className="text-xs text-muted-foreground">
              REST base URL of the AeroGraph server. The WebSocket URL is
              derived automatically.
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="api-base">API base URL</Label>
            <Input
              id="api-base"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={getDefaultBase()}
              spellCheck={false}
              autoComplete="off"
              className="font-mono text-sm"
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <Button variant="ghost" size="sm" onClick={reset}>
              Reset
            </Button>
            <Button size="sm" onClick={save}>
              Save
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
