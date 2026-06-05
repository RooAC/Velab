/**
 * /api/bundle-events/[bundleId] GET 路由测试
 */
import { GET } from '@/app/api/bundle-events/[bundleId]/route'
import { NextRequest } from 'next/server'
import { vi, beforeEach, afterEach, describe, it, expect } from 'vitest'

const makeParams = (bundleId: string) =>
  ({ params: Promise.resolve({ bundleId }) }) as { params: Promise<{ bundleId: string }> }
const BUNDLE_ID = '550e8400-e29b-41d4-a716-446655440000'

describe('GET /api/bundle-events/[bundleId]', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('转发到 /api/bundles/{id}/events', async () => {
    mockFetch.mockResolvedValue({ status: 200, text: async () => '[]' })
    const req = new NextRequest(`http://localhost/api/bundle-events/${BUNDLE_ID}`)
    const res = await GET(req, makeParams(BUNDLE_ID))
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining(`/api/bundles/${BUNDLE_ID}/events`),
      expect.objectContaining({ method: 'GET' })
    )
    expect(res.status).toBe(200)
  })

  it('透传查询参数到上游', async () => {
    mockFetch.mockResolvedValue({ status: 200, text: async () => '[]' })
    const req = new NextRequest(`http://localhost/api/bundle-events/${BUNDLE_ID}?type=fota&limit=10`)
    await GET(req, makeParams(BUNDLE_ID))
    const calledUrl: string = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('type=fota')
    expect(calledUrl).toContain('limit=10')
  })

  it('非法 bundleId 直接返回 400', async () => {
    const req = new NextRequest('http://localhost/api/bundle-events/not-a-uuid')
    const res = await GET(req, makeParams('not-a-uuid'))
    expect(res.status).toBe(400)
    expect(mockFetch).not.toHaveBeenCalled()
  })
})
