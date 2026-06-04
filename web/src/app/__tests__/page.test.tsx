/**
 * 主页面集成测试
 *
 * 测试主页面的完整功能流程
 */

import { render, screen, waitFor } from '@/__tests__/utils/test-utils'
import Home from '@/app/page'
import userEvent from '@testing-library/user-event'
import { DEMO_SCENARIOS, PRESET_QUESTIONS } from '@/lib/types'
import { vi, describe, it, beforeEach, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/__tests__/mocks/server'

// Mock fetch for SSE
const mockFetch = vi.fn()
global.fetch = mockFetch as unknown as typeof fetch

const createSseResponse = (chunks: string[]) => {
    const encodedChunks = chunks.map((chunk) => new TextEncoder().encode(chunk))
    const queue = [...encodedChunks]
    const reader = {
        read: vi.fn().mockImplementation(async () => {
            if (queue.length === 0) {
                return { done: true, value: undefined }
            }
            return { done: false, value: queue.shift() }
        }),
    }
    return {
        ok: true,
        body: {
            getReader: () => reader,
        },
    }
}

const setupFetchMock = (chatResponse?: unknown, sessions: unknown[] = []) => {
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string'
            ? input
            : input instanceof URL
                ? input.toString()
                : input.url
        const method = (init?.method || 'GET').toUpperCase()

        if (url.includes('/api/sessions') && method === 'GET') {
            return {
                ok: true,
                json: async () => sessions,
            } as Response
        }

        if (url.includes('/api/sessions/') && method === 'PUT') {
            return {
                ok: true,
                json: async () => ({}),
            } as Response
        }

        if (url.includes('/api/sessions/') && method === 'DELETE') {
            return {
                ok: true,
                status: 204,
                json: async () => ({}),
            } as Response
        }

        if (chatResponse) {
            return chatResponse as Response
        }
        return createSseResponse([]) as unknown as Response
    })
}

describe('Home Page Integration Tests', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        mockFetch.mockClear()
        window.localStorage.clear()
        setupFetchMock()
    })

    describe('初始渲染', () => {
        it('应该渲染 Header 组件', () => {
            render(<Home />)

            expect(screen.getByText(DEMO_SCENARIOS[0].name)).toBeInTheDocument()
        })

        it('应该渲染 WelcomePage', () => {
            render(<Home />)

            expect(screen.getByText('What are you working on?')).toBeInTheDocument()
        })

        it('应该渲染 InputBar', () => {
            render(<Home />)

            expect(screen.getByPlaceholderText('Ask a question')).toBeInTheDocument()
        })

        it('不应渲染 Bundle 摄取状态面板', () => {
            render(<Home />)

            expect(screen.queryByText('Bundle 摄取状态')).not.toBeInTheDocument()
        })

        it('应该显示所有预设问题', () => {
            render(<Home />)

            PRESET_QUESTIONS.forEach(question => {
                expect(screen.getByText(question.text)).toBeInTheDocument()
            })
        })

    })

    describe('发送消息流程', () => {
        it('点击预设问题应该发送消息', async () => {
            const user = userEvent.setup()

            setupFetchMock(
                createSseResponse([
                    'data: {"type":"content_delta","content":"Test"}\n\n',
                ])
            )

            render(<Home />)

            const firstQuestion = PRESET_QUESTIONS[0]
            const questionButton = screen.getByText(firstQuestion.text)

            await user.click(questionButton)

            // 应该显示用户消息
            await waitFor(() => {
                expect(screen.getAllByText(firstQuestion.text).length).toBeGreaterThan(0)
            })
        })

        it('通过输入框发送消息', async () => {
            const user = userEvent.setup()

            setupFetchMock(
                createSseResponse([
                    'data: {"type":"content_delta","content":"Response"}\n\n',
                ])
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            const runButton = screen.getByText('Run')

            await user.type(input, 'Test question')
            await user.click(runButton)

            // 应该显示用户消息
            await waitFor(() => {
                expect(screen.getAllByText('Test question').length).toBeGreaterThan(0)
            })
        })

        it('SSE 正常流结束后关闭 running 状态', async () => {
            const user = userEvent.setup()

            server.use(
                http.post('/api/chat', () => {
                    const encoder = new TextEncoder()
                    const stream = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode('data: {"type":"content_delta","content":"Done response"}\n\n'))
                            controller.enqueue(encoder.encode('data: {"type":"done"}\n\n'))
                            controller.close()
                        },
                    })
                    return new HttpResponse(stream, {
                        headers: { 'Content-Type': 'text/event-stream' },
                    })
                })
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Finish normally{Enter}')

            expect(await screen.findByText(/Done response/)).toBeInTheDocument()
            await waitFor(() => {
                expect(screen.getByRole('button', { name: /Run/ })).toBeInTheDocument()
            })
            expect(screen.queryByRole('button', { name: /Stop/ })).not.toBeInTheDocument()
        })

        it('发送消息后应该隐藏 WelcomePage', async () => {
            const user = userEvent.setup()

            setupFetchMock(createSseResponse([]))

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // WelcomePage 应该消失
            await waitFor(() => {
                expect(screen.queryByText('What are you working on?')).not.toBeInTheDocument()
            })
        })
    })

    describe('场景切换', () => {
        it('切换场景不应清空当前会话消息', async () => {
            const user = userEvent.setup()

            setupFetchMock(createSseResponse([]))

            render(<Home />)

            // 发送消息
            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test message{Enter}')

            await waitFor(() => {
                expect(screen.getAllByText('Test message').length).toBeGreaterThan(0)
            })

            // 切换场景
            const scenarioButton = screen.getByRole('button', { name: new RegExp(DEMO_SCENARIOS[0].name) })
            await user.click(scenarioButton)

            const nextScenario = screen.getByText(DEMO_SCENARIOS[1].name)
            await user.click(nextScenario)

            // 当前会话消息应保留
            await waitFor(() => {
                expect(screen.getAllByText('Test message').length).toBeGreaterThan(0)
            })
        })
    })

    describe('Stop 功能', () => {
        it('运行中应该显示 Stop 按钮', async () => {
            const user = userEvent.setup()

            // 覆盖 /api/chat：返回一个永不结束的流
            server.use(
                http.post('/api/chat', () => {
                    const stream = new ReadableStream({
                        start(controller) {
                            const encoder = new TextEncoder()
                            controller.enqueue(encoder.encode('data: {"type":"content_delta","content":"Test"}\n\n'))
                            // 不调用 controller.close()，流永不结束
                        },
                    })
                    return new HttpResponse(stream, {
                        headers: { 'Content-Type': 'text/event-stream' },
                    })
                }),
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 运行中：Stop 按钮出现，Run 按钮消失
            await waitFor(() => {
                expect(screen.queryByRole('button', { name: /Run/ })).not.toBeInTheDocument()
            }, { timeout: 3000 })
            expect(screen.getByRole('button', { name: /Stop/ })).toBeInTheDocument()
        })

        it('Stop 会 abort pending stream 并恢复 Run 按钮', async () => {
            const user = userEvent.setup()
            let capturedSignal: AbortSignal | undefined

            server.use(
                http.post('/api/chat', ({ request }) => {
                    capturedSignal = request.signal
                    const encoder = new TextEncoder()
                    const stream = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode('data: {"type":"content_delta","content":"still running"}\n\n'))
                        },
                    })
                    return new HttpResponse(stream, {
                        headers: { 'Content-Type': 'text/event-stream' },
                    })
                })
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Stop me{Enter}')

            const stopButton = await screen.findByRole('button', { name: /^Stop$/ })
            await user.click(stopButton)

            expect(capturedSignal?.aborted).toBe(true)
            await waitFor(() => {
                expect(screen.getByRole('button', { name: /Run/ })).toBeInTheDocument()
            })
        })
    })

    describe('错误处理', () => {
        it('应该处理网络错误', async () => {
            const user = userEvent.setup()

            // 仅让 chat API 失败
            server.use(
                http.post('/api/chat', () => HttpResponse.error()),
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 错误消息会显示在助手消息中
            await waitFor(() => {
                expect(screen.queryByText(/抱歉，处理请求时出现错误/)).toBeInTheDocument()
            }, { timeout: 3000 })
        })

        it('应该处理 AbortError', async () => {
            const user = userEvent.setup()

            // 用户主动停止会触发 AbortController，AbortError 不应落成错误消息。
            server.use(
                http.post('/api/chat', () => {
                    const encoder = new TextEncoder()
                    const stream = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode('data: {"type":"content_delta","content":"Test"}\n\n'))
                        },
                    })
                    return new HttpResponse(stream, {
                        headers: { 'Content-Type': 'text/event-stream' },
                    })
                }),
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')
            await user.click(await screen.findByRole('button', { name: /Stop/ }))

            // AbortError 不应该显示错误消息
            await waitFor(() => {
                expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
            })
        })

        it('/api/chat non-ok 结构化错误会显示并重置 running', async () => {
            const user = userEvent.setup()

            server.use(
                http.post('/api/chat', () => HttpResponse.json(
                    { error: { code: 'BACKEND_ERROR', message: '诊断后端忙，请稍后重试' } },
                    { status: 503 }
                ))
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Trigger error{Enter}')

            await waitFor(() => {
                expect(screen.getByText(/诊断后端忙，请稍后重试/)).toBeInTheDocument()
            })
            expect(screen.getByRole('button', { name: /Run/ })).toBeInTheDocument()
        })
    })

    describe('上传流程', () => {
        it('上传返回 bundle_id 后轮询到 done 并渲染 UploadSummaryCard', async () => {
            const user = userEvent.setup()
            const bundleId = '550e8400-e29b-41d4-a716-446655440000'

            server.use(
                http.post('/api/upload-log', () => HttpResponse.json(
                    { bundle_id: bundleId, status: 'queued' },
                    { status: 202 }
                )),
                http.get(`/api/bundle-status/${bundleId}`, () => HttpResponse.json({
                        status: 'done',
                        progress: 1,
                        file_count: 2,
                        files_by_controller: { MPU: 2 },
                        valid_time_range_by_controller: { MPU: { start: 1717200000, end: 1717200060 } },
                    })
                ),
                http.get(`/api/bundle-events/${bundleId}`, () => HttpResponse.json([])),
            )

            render(<Home />)

            const fileInput = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
            const file = new File(['log'], 'mpu.log', { type: 'text/plain' })
            await user.upload(fileInput, file)

            await waitFor(() => {
                expect(screen.getAllByText(/上传文件/).length).toBeGreaterThan(0)
            })

            expect(await screen.findByText('日志上传汇总', {}, { timeout: 5000 })).toBeInTheDocument()
            expect(screen.getByText('上传 Summary · mpu.log')).toBeInTheDocument()
            expect(screen.getByText('共 2 个文件')).toBeInTheDocument()
        }, 15000)

        it('bundle-status 连续结构化错误后展示失败', async () => {
            const user = userEvent.setup()
            const bundleId = '550e8400-e29b-41d4-a716-446655440000'

            server.use(
                http.post('/api/upload-log', () => HttpResponse.json(
                    { bundle_id: bundleId, status: 'queued' },
                    { status: 202 }
                )),
                http.get(`/api/bundle-status/${bundleId}`, () => HttpResponse.json(
                        { error: { code: 'BUNDLE_STATUS_FAILED', message: '状态服务暂不可用' } },
                        { status: 503 }
                    )
                ),
            )

            render(<Home />)

            const fileInput = document.querySelector('input[type="file"][multiple]') as HTMLInputElement
            const file = new File(['log'], 'broken.log', { type: 'text/plain' })
            await user.upload(fileInput, file)

            expect(await screen.findByText('上传和解析结束，部分文件失败', {}, { timeout: 8000 })).toBeInTheDocument()
            expect(screen.getByText('100%')).toBeInTheDocument()
            expect(screen.queryByText('日志上传汇总')).not.toBeInTheDocument()
        }, 15000)
    })

    describe('消息渲染', () => {
        it('应该渲染用户和助手消息', async () => {
            const user = userEvent.setup()

            // 覆盖 /api/chat 返回明确文本
            server.use(
                http.post('/api/chat', () => {
                    const encoder = new TextEncoder()
                    const stream = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode('data: {"type":"content_delta","content":"Assistant response"}\n\n'))
                            controller.enqueue(encoder.encode('data: {"type":"done"}\n\n'))
                            controller.close()
                        },
                    })
                    return new HttpResponse(stream, {
                        headers: { 'Content-Type': 'text/event-stream' },
                    })
                }),
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'User question{Enter}')

            // 应该显示用户消息
            await waitFor(() => {
                expect(screen.getByText('User question')).toBeInTheDocument()
            }, { timeout: 2000 })

            // 应该显示助手响应（等待流处理）
            await waitFor(() => {
                expect(screen.getByText(/Assistant response/)).toBeInTheDocument()
            }, { timeout: 3000 })
        })
    })

    describe('自动滚动', () => {
        it('新消息应该触发滚动', async () => {
            const user = userEvent.setup()

            // 创建 scrollIntoView 的 spy
            const scrollIntoViewSpy = vi.fn()
            Element.prototype.scrollIntoView = scrollIntoViewSpy

            setupFetchMock(createSseResponse([]))

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 等待消息显示
            await waitFor(() => {
                expect(screen.getAllByText('Test').length).toBeGreaterThan(0)
            })

            // scrollIntoView 应该被调用
            await waitFor(() => {
                expect(scrollIntoViewSpy).toHaveBeenCalled()
            }, { timeout: 2000 })
        })
    })

    describe('边界情况', () => {
        it('应该处理空响应体', async () => {
            const user = userEvent.setup()

            setupFetchMock({
                ok: true,
                body: null,
            } as Response)

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')
            await user.type(input, 'Test{Enter}')

            // 应该正常处理，不崩溃
            await waitFor(() => {
                expect(screen.getAllByText('Test').length).toBeGreaterThan(0)
            })
        })

        it('应该处理多条连续消息', async () => {
            const user = userEvent.setup()

            let callCount = 0
            server.use(
                http.post('/api/chat', () => {
                    callCount++
                    const encoder = new TextEncoder()
                    const stream = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode('data: {"type":"content_delta","content":"Response"}\n\n'))
                            controller.enqueue(encoder.encode('data: {"type":"done"}\n\n'))
                            controller.close()
                        },
                    })
                    return new HttpResponse(stream, {
                        headers: { 'Content-Type': 'text/event-stream' },
                    })
                }),
            )

            render(<Home />)

            const input = screen.getByPlaceholderText('Ask a question')

            // 发送第一条消息
            await user.type(input, 'Message 1{Enter}')
            await waitFor(() => expect(screen.getByText('Message 1')).toBeInTheDocument(), { timeout: 2000 })

            // 等待第一条消息完成（Run按钮重新出现）
            await waitFor(() => expect(screen.getByRole('button', { name: /Run/ })).toBeInTheDocument(), { timeout: 5000 })

            // 发送第二条消息
            await user.type(input, 'Message 2{Enter}')
            await waitFor(() => expect(screen.getByText('Message 2')).toBeInTheDocument(), { timeout: 2000 })

            // 等待第二条消息完成
            await waitFor(() => expect(callCount).toBeGreaterThanOrEqual(2), { timeout: 5000 })
        })
    })
})
