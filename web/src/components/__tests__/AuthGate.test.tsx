import { render, screen, waitFor } from '@/__tests__/utils/test-utils'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AuthGate from '../AuthGate'

describe('AuthGate', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('renders children when client auth is disabled', () => {
    vi.stubEnv('NEXT_PUBLIC_WEB_AUTH_ENABLED', 'false')

    render(<AuthGate><div>Protected app</div></AuthGate>)

    expect(screen.getByText('Protected app')).toBeInTheDocument()
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('shows password form when status is anonymous', async () => {
    vi.stubEnv('NEXT_PUBLIC_WEB_AUTH_ENABLED', 'true')
    mockFetch.mockResolvedValueOnce({
      json: async () => ({ enabled: true, authenticated: false }),
    })

    render(<AuthGate><div>Protected app</div></AuthGate>)

    expect(screen.getByRole('button', { name: '检查中...' })).toBeDisabled()
    await waitFor(() => {
      expect(screen.getByLabelText('访问密码')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '进入诊断平台' })).toBeEnabled()
    expect(screen.queryByText('Protected app')).not.toBeInTheDocument()
  })

  it('displays structured login error message', async () => {
    vi.stubEnv('NEXT_PUBLIC_WEB_AUTH_ENABLED', 'true')
    mockFetch
      .mockResolvedValueOnce({
        json: async () => ({ enabled: true, authenticated: false }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          error: {
            code: 'INVALID_CREDENTIALS',
            message: '密码错误',
          },
        }),
      })

    render(<AuthGate><div>Protected app</div></AuthGate>)

    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('访问密码'), 'wrong')
    await user.click(screen.getByRole('button', { name: '进入诊断平台' }))

    expect(await screen.findByText('密码错误')).toBeInTheDocument()
    expect(screen.queryByText('Protected app')).not.toBeInTheDocument()
  })

  it('renders children after successful login', async () => {
    vi.stubEnv('NEXT_PUBLIC_WEB_AUTH_ENABLED', 'true')
    mockFetch
      .mockResolvedValueOnce({
        json: async () => ({ enabled: true, authenticated: false }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true }),
      })

    render(<AuthGate><div>Protected app</div></AuthGate>)

    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('访问密码'), 'secret')
    await user.click(screen.getByRole('button', { name: '进入诊断平台' }))

    await waitFor(() => {
      expect(screen.getByText('Protected app')).toBeInTheDocument()
    })
  })
})
