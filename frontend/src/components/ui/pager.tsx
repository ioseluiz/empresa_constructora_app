import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from './button'

const PAGE_SIZE = 50 // igual que PAGE_SIZE del backend

/** Total y paginación de listas paginadas por la API. */
export function Pager({
  total,
  page,
  onPage,
  noun,
}: {
  total: number
  page: number
  onPage: (page: number) => void
  noun: [singular: string, plural: string]
}) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  return (
    <div className="text-muted-foreground flex items-center justify-between text-sm">
      <span>
        {total} {total === 1 ? noun[0] : noun[1]}
      </span>
      {pages > 1 && (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="Página anterior"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span>
            Página {page} de {pages}
          </span>
          <Button
            variant="outline"
            size="icon"
            aria-label="Página siguiente"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
