import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

function ComputerCard({ computer, onStart, onStop, activeSession }) {
  const isOnline = computer.status === 'online'
  const hasSession = activeSession !== null

  return (
    <div className={`rounded-xl p-5 shadow-md border-2 ${isOnline ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'}`}>
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-xl font-bold">{computer.name}</h2>
        <span className={`text-sm px-2 py-1 rounded-full font-medium ${isOnline ? 'bg-green-200 text-green-800' : 'bg-gray-200 text-gray-600'}`}>
          {isOnline ? '🟢 Online' : '⚫ Offline'}
        </span>
      </div>

      {hasSession && (
        <div className="text-sm text-blue-700 mb-3">
          ⏱ Сессия: {activeSession.duration_minutes} мин
        </div>
      )}

      <div className="flex gap-2 mt-2">
        {!hasSession ? (
          <button
            onClick={() => onStart(computer.id)}
            disabled={!isOnline}
            className="flex-1 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40 hover:bg-blue-600"
          >
            Старт
          </button>
        ) : (
          <button
            onClick={() => onStop(activeSession.session_id)}
            className="flex-1 py-2 rounded-lg bg-red-500 text-white font-medium hover:bg-red-600"
          >
            Стоп
          </button>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [computers, setComputers] = useState([])
  const [sessions, setSessions] = useState([])
  const [lastUpdate, setLastUpdate] = useState('')

  const fetchData = async () => {
    try {
      const [compRes, sessRes] = await Promise.all([
        fetch(`${API}/computers`),
        fetch(`${API}/sessions/active`)
      ])
      setComputers(await compRes.json())
      setSessions(await sessRes.json())
      setLastUpdate(new Date().toLocaleTimeString())
    } catch (e) {
      console.error('Ошибка загрузки:', e)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 3000)
    return () => clearInterval(interval)
  }, [])

  const handleStart = async (computerId) => {
    await fetch(`${API}/sessions/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ computer_id: computerId, tariff_id: 1 })
    })
    fetchData()
  }

  const handleStop = async (sessionId) => {
    const res = await fetch(`${API}/sessions/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    })
    const data = await res.json()
    alert(`Сессия завершена!\nВремя: ${data.duration_minutes} мин\nСумма: ${data.total_amount} ₸`)
    fetchData()
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-gray-800">🖥 PC Club Admin</h1>
          <span className="text-sm text-gray-500">Обновлено: {lastUpdate}</span>
        </div>

        {computers.length === 0 ? (
          <p className="text-gray-500 text-center mt-20">Нет компьютеров...</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {computers.map(computer => (
              <ComputerCard
                key={computer.id}
                computer={computer}
                onStart={handleStart}
                onStop={handleStop}
                activeSession={sessions.find(s => s.computer_id === computer.id) || null}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
