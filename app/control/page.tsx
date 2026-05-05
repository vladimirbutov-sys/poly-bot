'use client'

import { useEffect, useRef, useState } from 'react'
import { Navbar } from '@/components/navbar'
import { Play, Square, RefreshCw, Wifi, WifiOff } from 'lucide-react'

const API = 'http://localhost:8888'

export default function ControlPage() {
  const [running, setRunning] = useState(false)
  const [connected, setConnected] = useState(false)
  const [logs, setLogs] = useState<string[]>(['Подключение к локальному серверу...'])
  const [loading, setLoading] = useState(false)
  const logsRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  // Проверка статуса и подключение к SSE
  useEffect(() => {
    checkStatus()
    connectLogs()
    const interval = setInterval(checkStatus, 5000)
    return () => {
      clearInterval(interval)
      esRef.current?.close()
    }
  }, [])

  // Автоскролл вниз
  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight
    }
  }, [logs])

  async function checkStatus() {
    try {
      const res = await fetch(`${API}/api/status`)
      const data = await res.json()
      setRunning(data.running)
      setConnected(true)
    } catch {
      setConnected(false)
    }
  }

  function connectLogs() {
    esRef.current?.close()
    const es = new EventSource(`${API}/api/logs`)
    esRef.current = es
    es.onmessage = (e) => {
      setLogs((prev) => [...prev.slice(-200), e.data])
    }
    es.onerror = () => {
      setConnected(false)
    }
  }

  async function handleStart() {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/start`, { method: 'POST' })
      const data = await res.json()
      if (data.ok) {
        setRunning(true)
        setLogs((prev) => [...prev, `▶ Бот запущен (PID: ${data.pid})`])
        connectLogs()
      } else {
        setLogs((prev) => [...prev, `⚠ ${data.msg}`])
      }
    } catch {
      setLogs((prev) => [...prev, '✗ Ошибка — локальный сервер недоступен'])
    }
    setLoading(false)
  }

  async function handleStop() {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/stop`, { method: 'POST' })
      const data = await res.json()
      if (data.ok) {
        setRunning(false)
        setLogs((prev) => [...prev, '■ Бот остановлен'])
      } else {
        setLogs((prev) => [...prev, `⚠ ${data.msg}`])
      }
    } catch {
      setLogs((prev) => [...prev, '✗ Ошибка — локальный сервер недоступен'])
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-[#0a0f1e]">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-blue-500/10 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px]" />
      </div>

      <div className="relative z-10">
        <Navbar />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white mb-1">Управление ботом</h1>
              <p className="text-white/50 text-sm">Запуск и мониторинг 98_sure_bot в реальном времени</p>
            </div>
            {/* Статус подключения */}
            <div className={`glass-card px-4 py-2 flex items-center gap-2 ${connected ? '' : 'border-red-500/30'}`}>
              {connected
                ? <><Wifi className="w-4 h-4 text-green-400" /><span className="text-sm text-green-400">Сервер доступен</span></>
                : <><WifiOff className="w-4 h-4 text-red-400" /><span className="text-sm text-red-400">Сервер недоступен</span></>
              }
            </div>
          </div>

          {/* Кнопки управления */}
          <div className="glass-card p-6">
            <div className="flex items-center gap-6">
              {/* Индикатор статуса */}
              <div className="flex items-center gap-3">
                <div className={`w-4 h-4 rounded-full ${running ? 'bg-green-500 animate-pulse-dot' : 'bg-zinc-600'}`} />
                <span className={`text-lg font-semibold ${running ? 'text-green-400' : 'text-zinc-400'}`}>
                  {running ? 'Бот работает' : 'Бот остановлен'}
                </span>
              </div>

              <div className="flex gap-3 ml-auto">
                <button
                  onClick={handleStart}
                  disabled={running || loading || !connected}
                  className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-green-600 to-green-500 text-white font-semibold text-sm transition-all hover:from-green-500 hover:to-green-400 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Play className="w-4 h-4" />
                  Запустить
                </button>
                <button
                  onClick={handleStop}
                  disabled={!running || loading || !connected}
                  className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-red-600 to-red-500 text-white font-semibold text-sm transition-all hover:from-red-500 hover:to-red-400 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Square className="w-4 h-4" />
                  Остановить
                </button>
                <button
                  onClick={() => { connectLogs(); checkStatus() }}
                  className="flex items-center gap-2 px-4 py-3 rounded-xl glass-card text-white/60 hover:text-white text-sm transition-all"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>

            {!connected && (
              <div className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                Локальный сервер не запущен. Выполни в PowerShell:{' '}
                <code className="bg-red-500/20 px-2 py-0.5 rounded font-mono text-xs">
                  python C:\Users\Honor\Desktop\Polymarket\bot_server.py
                </code>
              </div>
            )}
          </div>

          {/* Логи */}
          <div className="glass-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold flex items-center gap-3">
                <span className="w-1 h-6 bg-gradient-to-b from-blue-500 to-cyan-400 rounded-full" />
                Логи в реальном времени
              </h2>
              <button
                onClick={() => setLogs([])}
                className="text-xs text-white/30 hover:text-white/60 transition-colors"
              >
                очистить
              </button>
            </div>
            <div
              ref={logsRef}
              className="h-96 overflow-y-auto font-mono text-xs text-green-400/80 bg-black/30 rounded-xl p-4 space-y-0.5"
            >
              {logs.length === 0
                ? <span className="text-white/20">Логи пусты</span>
                : logs.map((line, i) => (
                    <div key={i} className={`leading-5 ${line.startsWith('✗') || line.startsWith('⚠') ? 'text-red-400' : line.startsWith('▶') ? 'text-green-400' : line.startsWith('■') ? 'text-yellow-400' : 'text-green-400/70'}`}>
                      {line}
                    </div>
                  ))
              }
            </div>
          </div>

        </main>
      </div>
    </div>
  )
}
