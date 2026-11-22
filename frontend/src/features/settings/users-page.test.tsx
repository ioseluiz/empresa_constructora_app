import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, renderWithProviders } from '@/test/utils'
import { UsersPage } from './users-page'

const roles = [
  {
    id: 'r1',
    name: 'Planillero',
    description: '',
    permissions: [],
    is_system: true,
    member_count: 1,
  },
  { id: 'r2', name: 'Auditor', description: '', permissions: [], is_system: true, member_count: 0 },
]
const members = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 'm1',
      user: {
        id: 'u1',
        email: 'ana@constructora.pa',
        full_name: 'Ana Pérez',
        last_login: null,
        mfa_enabled: true,
      },
      is_owner: true,
      is_active: true,
      assignments: [],
      created_at: '2026-11-01T00:00:00Z',
    },
    {
      id: 'm2',
      user: {
        id: 'u2',
        email: 'luis@constructora.pa',
        full_name: 'Luis Gómez',
        last_login: null,
        mfa_enabled: false,
      },
      is_owner: false,
      is_active: true,
      assignments: [{ role: { id: 'r1', name: 'Planillero' }, projects: [] }],
      created_at: '2026-11-02T00:00:00Z',
    },
  ],
}

function mockApi() {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/iam/me/'))
      return Promise.resolve(
        jsonResponse({
          is_owner: true,
          permissions: ['users.view', 'users.manage'],
          roles: [],
          require_mfa: false,
        }),
      )
    if (url.includes('/iam/members/')) return Promise.resolve(jsonResponse(members))
    if (url.includes('/iam/roles/')) return Promise.resolve(jsonResponse(roles))
    if (url.includes('/projects/'))
      return Promise.resolve(
        jsonResponse({
          count: 1,
          next: null,
          previous: null,
          results: [{ id: 'p1', code: 'P-001', name: 'Torre Istmo' }],
        }),
      )
    if (url.includes('/iam/members/') && init?.method === 'PATCH')
      return Promise.resolve(jsonResponse(members.results[1]))
    if (url.includes('/iam/invitations/') && init?.method === 'POST')
      return Promise.resolve(jsonResponse({ id: 'i1' }, 201))
    if (url.includes('/iam/invitations/')) return Promise.resolve(jsonResponse([]))
    return Promise.resolve(jsonResponse({}, 404))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('UsersPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lista miembros y no permite editarse a sí mismo ni al propietario', async () => {
    mockApi()
    renderWithProviders(<UsersPage />)
    const row = (await screen.findByText('Luis Gómez')).closest('tr')!
    expect(within(row).getByText('Planillero')).toBeInTheDocument()
    expect(screen.getByText('Administrador principal')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar luis@constructora.pa' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Editar ana@constructora.pa' }),
    ).not.toBeInTheDocument()
  })

  it('limita un rol a proyectos y exige elegir al menos uno', async () => {
    const fetchMock = mockApi()
    renderWithProviders(<UsersPage />)
    await userEvent.click(
      await screen.findByRole('button', { name: 'Editar luis@constructora.pa' }),
    )
    const scope = await screen.findByLabelText('Alcance de Planillero')
    await userEvent.selectOptions(scope, 'projects')
    expect(screen.getByText('Selecciona al menos un proyecto.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Guardar roles' }))
    expect(screen.getByRole('alert')).toHaveTextContent('sin ningún proyecto')

    await userEvent.click(screen.getByLabelText(/Torre Istmo/))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar roles' }))
    const call = fetchMock.mock.calls.find(
      ([url, init]) => url.includes('/iam/members/m2/') && init?.method === 'PATCH',
    )!
    expect(JSON.parse(call[1]!.body as string)).toEqual({
      set_assignments: [{ role_id: 'r1', project_ids: ['p1'] }],
    })
  })

  it('invita a un usuario con roles', async () => {
    const fetchMock = mockApi()
    renderWithProviders(<UsersPage />)
    await userEvent.click(await screen.findByRole('button', { name: /Invitar usuario/ }))
    await userEvent.type(screen.getByLabelText('Correo electrónico'), 'nuevo@obra.pa')
    await userEvent.click(await screen.findByLabelText(/Auditor/))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar invitación' }))

    const call = fetchMock.mock.calls.find(
      ([url, init]) => url.includes('/iam/invitations/') && init?.method === 'POST',
    )!
    expect(JSON.parse(call[1]!.body as string)).toEqual({
      email: 'nuevo@obra.pa',
      role_ids: ['r2'],
    })
  })
})
