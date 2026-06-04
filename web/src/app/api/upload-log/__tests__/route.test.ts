/**
 * /api/upload-log POST 路由测试
 */
import { POST } from '@/app/api/upload-log/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

describe('POST /api/upload-log', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('auth misconfig 时返回 503 且不 fetch backend', async () => {
    vi.stubEnv('WEB_AUTH_ENABLED', 'true')
    vi.stubEnv('AUTH_SESSION_SECRET', '')
    vi.stubEnv('AUTH_LOGIN_PASSWORD', '')
    vi.stubEnv('BACKEND_API_KEY', '')

    const req = {
      formData: vi.fn(),
    } as unknown as import('next/server').NextRequest

    const res = await POST(req)

    expect(res.status).toBe(503)
    const body = await res.json()
    expect(body.error.code).toBe('AUTH_NOT_CONFIGURED')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('转发 multipart 表单数据到后端', async () => {
    mockFetch.mockResolvedValue({
      status: 202,
      text: async () => '{"bundle_id":"b1","status":"queued"}',
    })
    // 直接 mock formData() 避免 undici File 与 JSDOM FormData 不兼容问题
    const mockFile = new File(['log content'], 'test.log', { type: 'text/plain' })
    const req = {
      formData: async () => {
        const fd = new FormData()
        fd.append('file', mockFile)
        return fd
      },
    } as unknown as import('next/server').NextRequest
    const res = await POST(req)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/bundles'),
      expect.objectContaining({ method: 'POST' })
    )
    expect(res.status).toBe(202)
  })

  it('无文件时返回结构化错误且不转发', async () => {
    const formData = new FormData()
    const req = new NextRequest('http://localhost/api/upload-log', {
      method: 'POST',
      body: formData,
    })

    const res = await POST(req)

    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error.code).toBe('MISSING_FILE')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('backend fetch 失败时返回 BACKEND_UNREACHABLE', async () => {
    mockFetch.mockRejectedValue(new Error('connection refused'))
    const mockFile = new File(['log content'], 'test.log', { type: 'text/plain' })
    const req = {
      formData: async () => {
        const fd = new FormData()
        fd.append('file', mockFile)
        return fd
      },
    } as unknown as import('next/server').NextRequest

    const res = await POST(req)

    expect(res.status).toBe(502)
    const body = await res.json()
    expect(body.error.code).toBe('BACKEND_UNREACHABLE')
  })
})
