import type { Role } from '@/api/generated/model'
import { Checkbox } from '@/components/ui/checkbox'

export function RolePicker({
  roles,
  value,
  onChange,
}: {
  roles: Role[]
  value: string[]
  onChange: (ids: string[]) => void
}) {
  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  return (
    <fieldset className="space-y-1">
      <legend className="mb-2 text-sm font-medium">Roles</legend>
      <div className="space-y-1 rounded-md border p-1">
        {roles.map((role) => (
          <label
            key={role.id}
            className="hover:bg-muted flex cursor-pointer items-start gap-3 rounded-md px-3 py-2"
          >
            <Checkbox
              className="mt-0.5"
              checked={value.includes(role.id)}
              onChange={() => toggle(role.id)}
            />
            <span>
              <span className="block text-sm font-medium">{role.name}</span>
              {role.description && (
                <span className="text-muted-foreground block text-xs">{role.description}</span>
              )}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
