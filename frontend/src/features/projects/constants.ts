export const PROJECT_STATUS: Record<
  string,
  { label: string; variant: 'success' | 'neutral' | 'danger' }
> = {
  planning: { label: 'En planificación', variant: 'neutral' },
  active: { label: 'En ejecución', variant: 'success' },
  suspended: { label: 'Suspendido', variant: 'danger' },
  finished: { label: 'Terminado', variant: 'neutral' },
}

export const PROVINCES: [string, string][] = [
  ['bocas_del_toro', 'Bocas del Toro'],
  ['cocle', 'Coclé'],
  ['colon', 'Colón'],
  ['chiriqui', 'Chiriquí'],
  ['darien', 'Darién'],
  ['herrera', 'Herrera'],
  ['los_santos', 'Los Santos'],
  ['panama', 'Panamá'],
  ['panama_oeste', 'Panamá Oeste'],
  ['veraguas', 'Veraguas'],
  ['guna_yala', 'Comarca Guna Yala'],
  ['embera_wounaan', 'Comarca Emberá-Wounaan'],
  ['ngabe_bugle', 'Comarca Ngäbe-Buglé'],
  ['naso_tjer_di', 'Comarca Naso Tjër Di'],
]
