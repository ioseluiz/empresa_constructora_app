import { ShieldAlert } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function MfaRequired() {
  const navigate = useNavigate()
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
      <span className="bg-accent/20 flex size-12 items-center justify-center rounded-full">
        <ShieldAlert className="text-accent size-6" />
      </span>
      <h1 className="text-lg font-semibold">Activa la verificación en dos pasos</h1>
      <p className="text-muted-foreground text-sm">
        Tu empresa exige verificación en dos pasos para acceder a sus datos. Actívala en tu cuenta;
        solo toma un minuto.
      </p>
      <Button onClick={() => navigate('/cuenta/seguridad')}>Activar ahora</Button>
    </div>
  )
}
