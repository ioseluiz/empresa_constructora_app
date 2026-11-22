import type { Project, Role } from '@/api/generated/model'
import { Checkbox } from '@/components/ui/checkbox'
import { Select } from '@/components/ui/select'

/** rol → alcance. `scoped: false` = toda la empresa. */
export type AssignmentDraft = Record<string, { scoped: boolean; projects: string[] }>

export function AssignmentEditor({
  roles,
  projects,
  value,
  onChange,
}: {
  roles: Role[]
  projects: Project[]
  value: AssignmentDraft
  onChange: (next: AssignmentDraft) => void
}) {
  const toggleRole = (id: string) => {
    const next = { ...value }
    if (id in next) delete next[id]
    else next[id] = { scoped: false, projects: [] }
    onChange(next)
  }
  const setScope = (id: string, scoped: boolean) =>
    onChange({ ...value, [id]: { scoped, projects: scoped ? (value[id]?.projects ?? []) : [] } })
  const toggleProject = (roleId: string, projectId: string) => {
    const current = value[roleId]?.projects ?? []
    const next = current.includes(projectId)
      ? current.filter((p) => p !== projectId)
      : [...current, projectId]
    onChange({ ...value, [roleId]: { scoped: true, projects: next } })
  }

  return (
    <fieldset className="space-y-1">
      <legend className="mb-2 text-sm font-medium">Roles y alcance</legend>
      <div className="max-h-[26rem] space-y-1 overflow-y-auto rounded-md border p-1">
        {roles.map((role) => {
          const checked = role.id in value
          const scopedProjects = value[role.id]?.projects ?? []
          const scoped = checked && !!value[role.id]?.scoped
          return (
            <div key={role.id} className="hover:bg-muted/60 rounded-md px-3 py-2">
              <label className="flex cursor-pointer items-start gap-3">
                <Checkbox
                  className="mt-0.5"
                  checked={checked}
                  onChange={() => toggleRole(role.id)}
                />
                <span className="flex-1">
                  <span className="block text-sm font-medium">{role.name}</span>
                  {role.description && (
                    <span className="text-muted-foreground block text-xs">{role.description}</span>
                  )}
                </span>
              </label>
              {checked && (
                <div className="mt-2 ml-7 space-y-2">
                  <Select
                    className="h-8 text-xs"
                    value={scoped ? 'projects' : 'all'}
                    onChange={(e) => setScope(role.id, e.target.value === 'projects')}
                    aria-label={`Alcance de ${role.name}`}
                    disabled={projects.length === 0}
                  >
                    <option value="all">Toda la empresa</option>
                    <option value="projects">Solo proyectos seleccionados</option>
                  </Select>
                  {scoped && scopedProjects.length === 0 && (
                    <p className="text-danger text-xs">Selecciona al menos un proyecto.</p>
                  )}
                  {scoped && (
                    <div className="grid gap-1 sm:grid-cols-2">
                      {projects.map((p) => (
                        <label key={p.id} className="flex items-center gap-2 text-xs">
                          <Checkbox
                            checked={scopedProjects.includes(p.id)}
                            onChange={() => toggleProject(role.id, p.id)}
                          />
                          <span className="text-muted-foreground font-mono">{p.code}</span>
                          <span className="truncate">{p.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </fieldset>
  )
}
