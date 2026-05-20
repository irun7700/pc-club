import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

function StartModal({ computer, clients, tariffs, onConfirm, onCancel }) {
  const [clientId, setClientId] = useState('')
  const [tariffId, setTariffId] = useState(tariffs[0]?.id || '')

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 shadow-xl w-96">
        <h2 className="text-xl font-bold mb-4">Старт сессии — {computer.name}</h2>
        <div className="mb-4">
          <label className="block text-sm text-gray-600 mb-2">Тариф</label>
          <select className="w-full border rounded-lg px-3 py-2" value={tariffId} onChange={e => setTariffId(e.target.value)}>
            {tariffs.map(t => (<option key={t.id} value={t.id}>{t.name} — {t.price_per_hour} ₸/час</option>))}
          </select>
        </div>
        <div className="mb-4">
          <label className="block text-sm text-gray-600 mb-2">Клиент (необязательно)</label>
          <select className="w-full border rounded-lg px-3 py-2" value={clientId} onChange={e => setClientId(e.target.value)}>
            <option value="">— Без клиента —</option>
            {clients.map(c => (<option key={c.id} value={c.id}>{c.name} — {c.balance} ₸</option>))}
          </select>
        </div>
        <div className="flex gap-3">
          <button onClick={() => onConfirm(clientId ? parseInt(clientId) : null, parseInt(tariffId))} className="flex-1 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 font-medium">Начать</button>
          <button onClick={onCancel} className="flex-1 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 font-medium">Отмена</button>
        </div>
      </div>
    </div>
  )
}

function ComputerCard({ computer, onStart, onStop, activeSession, clients, tariffs }) {
  const isOnline = computer.status === 'online'
  const hasSession = activeSession !== null
  const client = activeSession?.client_id ? clients.find(c => c.id === activeSession.client_id) : null
  const tariff = activeSession?.tariff_id ? tariffs.find(t => t.id === activeSession.tariff_id) : null
  return (
    <div className={`rounded-xl p-5 shadow-md border-2 ${isOnline ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'}`}>
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-xl font-bold">{computer.name}</h2>
        <span className={`text-sm px-2 py-1 rounded-full font-medium ${isOnline ? 'bg-green-200 text-green-800' : 'bg-gray-200 text-gray-600'}`}>
          {isOnline ? '🟢 Online' : '⚫ Offline'}
        </span>
      </div>
      {hasSession && (
        <div className="text-sm text-blue-700 mb-3 space-y-1">
          <div>⏱ {activeSession.duration_minutes} мин · {tariff ? tariff.name : ''}</div>
          {client ? <div>👤 {client.name} — {client.balance} ₸</div> : <div>👤 Без клиента</div>}
        </div>
      )}
      <div className="flex gap-2 mt-2">
        {!hasSession ? (
          <button onClick={() => onStart(computer)} disabled={!isOnline} className="flex-1 py-2 rounded-lg bg-blue-500 text-white font-medium disabled:opacity-40 hover:bg-blue-600">Старт</button>
        ) : (
          <button onClick={() => onStop(activeSession.session_id)} className="flex-1 py-2 rounded-lg bg-red-500 text-white font-medium hover:bg-red-600">Стоп</button>
        )}
      </div>
    </div>
  )
}

function TariffsTab() {
  const [tariffs, setTariffs] = useState([])
  const [name, setName] = useState('')
  const [price, setPrice] = useState('')

  const fetchTariffs = async () => { const res = await fetch(`${API}/tariffs`); setTariffs(await res.json()) }
  useEffect(() => { fetchTariffs() }, [])

  const handleCreate = async () => {
    if (!name || !price) return
    await fetch(`${API}/tariffs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, price_per_hour: parseFloat(price) }) })
    setName(''); setPrice(''); fetchTariffs()
  }

  const handleDelete = async (id) => {
    if (!confirm('Удалить тариф?')) return
    await fetch(`${API}/tariffs/${id}`, { method: 'DELETE' })
    fetchTariffs()
  }

  return (
    <div>
      <div className="bg-white rounded-xl p-5 shadow-md mb-6">
        <h2 className="text-lg font-bold mb-4">➕ Новый тариф</h2>
        <div className="flex gap-3">
          <input className="flex-1 border rounded-lg px-3 py-2" placeholder="Название (напр. Стандарт)" value={name} onChange={e => setName(e.target.value)} />
          <input className="w-40 border rounded-lg px-3 py-2" placeholder="₸ за час" type="number" value={price} onChange={e => setPrice(e.target.value)} />
          <button onClick={handleCreate} className="px-5 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">Создать</button>
        </div>
      </div>
      <div className="bg-white rounded-xl shadow-md overflow-hidden">
        <div className="p-4 border-b font-bold text-gray-700">Список тарифов</div>
        {tariffs.length === 0 ? (
          <p className="text-gray-500 text-center p-6">Нет тарифов</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr><th className="text-left px-4 py-2">Название</th><th className="text-left px-4 py-2">Цена за час</th><th className="px-4 py-2"></th></tr>
            </thead>
            <tbody>
              {tariffs.map(t => (
                <tr key={t.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{t.name}</td>
                  <td className="px-4 py-3">{t.price_per_hour} ₸</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => handleDelete(t.id)} className="text-red-500 hover:text-red-700">Удалить</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ClientsTab() {
  const [clients, setClients] = useState([])
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [depositAmount, setDepositAmount] = useState('')
  const [selectedClient, setSelectedClient] = useState(null)
  const fetchClients = async () => { const res = await fetch(`${API}/clients`); setClients(await res.json()) }
  useEffect(() => { fetchClients() }, [])
  const handleCreate = async () => {
    if (!name) return
    await fetch(`${API}/clients`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, phone }) })
    setName(''); setPhone(''); fetchClients()
  }
  const handleDeposit = async (clientId) => {
    if (!depositAmount) return
    await fetch(`${API}/clients/${clientId}/deposit`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ amount: parseFloat(depositAmount) }) })
    setDepositAmount(''); setSelectedClient(null); fetchClients()
  }
  return (
    <div>
      <div className="bg-white rounded-xl p-5 shadow-md mb-6">
        <h2 className="text-lg font-bold mb-4">➕ Новый клиент</h2>
        <div className="flex gap-3">
          <input className="flex-1 border rounded-lg px-3 py-2" placeholder="Имя" value={name} onChange={e => setName(e.target.value)} />
          <input className="flex-1 border rounded-lg px-3 py-2" placeholder="Телефон" value={phone} onChange={e => setPhone(e.target.value)} />
          <button onClick={handleCreate} className="px-5 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">Создать</button>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {clients.map(client => (
          <div key={client.id} className="bg-white rounded-xl p-5 shadow-md border border-gray-200">
            <div className="flex justify-between items-center mb-2">
              <div><div className="font-bold text-lg">{client.name}</div><div className="text-sm text-gray-500">{client.phone || 'Телефон не указан'}</div></div>
              <div className="text-right"><div className="text-2xl font-bold text-green-600">{client.balance} ₸</div><div className="text-xs text-gray-400">баланс</div></div>
            </div>
            {selectedClient === client.id ? (
              <div className="flex gap-2 mt-3">
                <input className="flex-1 border rounded-lg px-3 py-2" placeholder="Сумма" type="number" value={depositAmount} onChange={e => setDepositAmount(e.target.value)} />
                <button onClick={() => handleDeposit(client.id)} className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600">✓</button>
                <button onClick={() => setSelectedClient(null)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">✕</button>
              </div>
            ) : (
              <button onClick={() => setSelectedClient(client.id)} className="mt-3 w-full py-2 bg-green-50 text-green-700 border border-green-300 rounded-lg hover:bg-green-100">+ Пополнить баланс</button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function CashTab({ clients }) {
  const [report, setReport] = useState(null)
  const fetchReport = async () => { const res = await fetch(`${API}/reports/today`); setReport(await res.json()) }
  useEffect(() => { fetchReport(); const i = setInterval(fetchReport, 10000); return () => clearInterval(i) }, [])
  if (!report) return <p className="text-gray-500">Загрузка...</p>
  return (
    <div>
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-xl p-5 shadow-md text-center">
          <div className="text-4xl font-bold text-green-600">{report.total_amount} ₸</div>
          <div className="text-gray-500 mt-1">Выручка сегодня</div>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-md text-center">
          <div className="text-4xl font-bold text-blue-600">{report.sessions_count}</div>
          <div className="text-gray-500 mt-1">Сессий сегодня</div>
        </div>
      </div>
      <div className="bg-white rounded-xl shadow-md overflow-hidden">
        <div className="p-4 border-b font-bold text-gray-700">История сессий</div>
        {report.sessions.length === 0 ? <p className="text-gray-500 text-center p-6">Сессий пока нет</p> : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr><th className="text-left px-4 py-2">ПК</th><th className="text-left px-4 py-2">Клиент</th><th className="text-left px-4 py-2">Время</th><th className="text-right px-4 py-2">Сумма</th></tr>
            </thead>
            <tbody>
              {report.sessions.slice().reverse().map(s => {
                const client = s.client_id ? clients.find(c => c.id === s.client_id) : null
                return (
                  <tr key={s.session_id} className="border-t hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">ПК-{s.computer_id}</td>
                    <td className="px-4 py-3">{client ? client.name : '—'}</td>
                    <td className="px-4 py-3">{s.duration_minutes} мин</td>
                    <td className="px-4 py-3 text-right font-bold text-green-600">{s.total_amount} ₸</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState('computers')
  const [computers, setComputers] = useState([])
  const [sessions, setSessions] = useState([])
  const [clients, setClients] = useState([])
  const [tariffs, setTariffs] = useState([])
  const [lastUpdate, setLastUpdate] = useState('')
  const [startModal, setStartModal] = useState(null)

  const fetchData = async () => {
    try {
      const [compRes, sessRes, clientRes, tariffRes] = await Promise.all([
        fetch(`${API}/computers`), fetch(`${API}/sessions/active`), fetch(`${API}/clients`), fetch(`${API}/tariffs`)
      ])
      setComputers(await compRes.json()); setSessions(await sessRes.json())
      setClients(await clientRes.json()); setTariffs(await tariffRes.json())
      setLastUpdate(new Date().toLocaleTimeString())
    } catch (e) { console.error('Ошибка загрузки:', e) }
  }

  useEffect(() => { fetchData(); const i = setInterval(fetchData, 3000); return () => clearInterval(i) }, [])

  const handleStart = (computer) => setStartModal(computer)
  const handleConfirmStart = async (clientId, tariffId) => {
    await fetch(`${API}/sessions/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ computer_id: startModal.id, tariff_id: tariffId, client_id: clientId }) })
    setStartModal(null); fetchData()
  }
  const handleStop = async (sessionId) => {
    const res = await fetch(`${API}/sessions/stop`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId }) })
    const data = await res.json()
    alert(`Сессия завершена!\nВремя: ${data.duration_minutes} мин\nСумма: ${data.total_amount} ₸`)
    fetchData()
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      {startModal && <StartModal computer={startModal} clients={clients} tariffs={tariffs} onConfirm={handleConfirmStart} onCancel={() => setStartModal(null)} />}
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-gray-800">🖥 PC Club Admin</h1>
          <span className="text-sm text-gray-500">Обновлено: {lastUpdate}</span>
        </div>
        <div className="flex gap-2 mb-6 flex-wrap">
          <button onClick={() => setTab('computers')} className={`px-5 py-2 rounded-lg font-medium ${tab === 'computers' ? 'bg-blue-500 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>🖥 Компьютеры</button>
          <button onClick={() => setTab('clients')} className={`px-5 py-2 rounded-lg font-medium ${tab === 'clients' ? 'bg-blue-500 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>👤 Клиенты</button>
          <button onClick={() => setTab('cash')} className={`px-5 py-2 rounded-lg font-medium ${tab === 'cash' ? 'bg-blue-500 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>💰 Касса</button>
          <button onClick={() => setTab('tariffs')} className={`px-5 py-2 rounded-lg font-medium ${tab === 'tariffs' ? 'bg-blue-500 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>⚙️ Тарифы</button>
        </div>
        {tab === 'computers' && (computers.length === 0 ? <p className="text-gray-500 text-center mt-20">Нет компьютеров...</p> : <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">{computers.map(computer => <ComputerCard key={computer.id} computer={computer} onStart={handleStart} onStop={handleStop} activeSession={sessions.find(s => s.computer_id === computer.id) || null} clients={clients} tariffs={tariffs} />)}</div>)}
        {tab === 'clients' && <ClientsTab />}
        {tab === 'cash' && <CashTab clients={clients} />}
        {tab === 'tariffs' && <TariffsTab />}
      </div>
    </div>
  )
}
