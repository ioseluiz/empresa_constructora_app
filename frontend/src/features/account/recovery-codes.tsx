import { Copy, Download } from 'lucide-react'
import { useState } from 'react'
import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

export function RecoveryCodes({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false)
  const text = codes.join('\n')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      /* portapapeles no disponible */
    }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([text + '\n'], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'codigos-recuperacion.txt'
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="space-y-4">
      <Alert variant="success">
        Guarda estos códigos en un lugar seguro. Cada uno sirve una sola vez si pierdes el teléfono.
        No se volverán a mostrar.
      </Alert>
      <ul className="bg-muted/40 grid grid-cols-2 gap-2 rounded-md border p-4 font-mono text-sm">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => void copy()}>
          <Copy className="size-3.5" /> {copied ? 'Copiados' : 'Copiar'}
        </Button>
        <Button variant="outline" size="sm" onClick={download}>
          <Download className="size-3.5" /> Descargar
        </Button>
      </div>
    </div>
  )
}
