import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { renderWithProviders } from '@/test/utils'
import { LoginPage } from './login-page'

describe('LoginPage', () => {
  it('valida los campos antes de enviar', async () => {
    const { auth } = renderWithProviders(<LoginPage />, { status: 'anonymous' })
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByText('Ingresa un correo válido.')).toBeInTheDocument()
    expect(screen.getByText('Ingresa tu contraseña.')).toBeInTheDocument()
    expect(auth.login).not.toHaveBeenCalled()
  })

  it('envía las credenciales', async () => {
    const login = vi.fn().mockResolvedValue(undefined)
    renderWithProviders(<LoginPage />, { status: 'anonymous', login })
    await userEvent.type(screen.getByLabelText('Correo electrónico'), 'ana@constructora.pa')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'secreta')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(login).toHaveBeenCalledWith('ana@constructora.pa', 'secreta')
  })

  it('muestra el error del servidor', async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, 'Correo o contraseña incorrectos.'))
    renderWithProviders(<LoginPage />, { status: 'anonymous', login })
    await userEvent.type(screen.getByLabelText('Correo electrónico'), 'ana@constructora.pa')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'mala')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Correo o contraseña incorrectos.')
  })
})
