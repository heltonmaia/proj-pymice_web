import { useEffect, useState } from 'react'
import { experimentApi } from '@/services/api'
import type { Integration, SerialPort } from '@/types'

export default function IntegrationsPanel() {
  const [items, setItems] = useState<Integration[]>([])
  const [showModal, setShowModal] = useState(false)
  const [testResults, setTestResults] = useState<Record<string, 'ok' | 'err' | 'pending' | undefined>>({})

  const reload = () => experimentApi.listIntegrations().then((r) => setItems(r.data.data?.integrations ?? []))
  useEffect(() => { reload() }, [])

  const onTest = async (id: string) => {
    setTestResults((s) => ({ ...s, [id]: 'pending' }))
    const r = await experimentApi.testIntegration(id)
    setTestResults((s) => ({ ...s, [id]: r.data.success ? 'ok' : 'err' }))
  }

  const onDelete = async (id: string) => {
    if (!confirm(`Delete integration ${id}?`)) return
    try {
      await experimentApi.deleteIntegration(id)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: { error?: string; triggers?: string[] } } } }
      const detail = err.response?.data?.detail
      if (detail?.error === 'in_use') {
        if (!confirm(`In use by triggers ${detail.triggers?.join(', ')}. Force delete?`)) return
        await experimentApi.deleteIntegration(id, true)
      } else {
        alert(`Delete failed: ${JSON.stringify(detail)}`)
        return
      }
    }
    reload()
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Hardware Integrations</h3>
        <button onClick={() => setShowModal(true)} className="text-sm bg-primary-600 text-white px-3 py-1 rounded">
          + Add Integration
        </button>
      </div>
      {items.length === 0 && <p className="text-sm text-gray-500">None configured.</p>}
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={i.id} className="flex items-center gap-3 text-sm">
            <span className={`w-2 h-2 rounded-full ${
              testResults[i.id] === 'ok' ? 'bg-green-500' :
              testResults[i.id] === 'err' ? 'bg-red-500' :
              testResults[i.id] === 'pending' ? 'bg-yellow-500' : 'bg-gray-400'
            }`} />
            <span className="font-medium">{i.name}</span>
            <span className="text-gray-500">
              [{i.kind}{' '}
              {i.kind === 'serial'
                ? (i.config as { port: string }).port
                : (i.config as { base_url: string }).base_url}]
            </span>
            <button onClick={() => onTest(i.id)} className="ml-auto text-xs border px-2 py-1 rounded">Test</button>
            <button onClick={() => onDelete(i.id)} className="text-xs text-red-600">Delete</button>
          </li>
        ))}
      </ul>
      {showModal && <AddModal onClose={() => { setShowModal(false); reload() }} />}
    </div>
  )
}

function AddModal({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<'serial' | 'http'>('serial')
  const [name, setName] = useState('')
  const [ports, setPorts] = useState<SerialPort[]>([])
  const [port, setPort] = useState('')
  const [baud, setBaud] = useState(115200)
  const [baseUrl, setBaseUrl] = useState('http://localhost:9000')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (kind === 'serial') {
      experimentApi.listSerialPorts().then((r) => {
        const list = r.data.data?.ports ?? []
        setPorts(list)
        if (list.length > 0) setPort(list[0].device)
      })
    }
  }, [kind])

  const submit = async () => {
    setErr(null)
    const id = `i-${Date.now().toString(36)}`
    const integration: Integration =
      kind === 'serial'
        ? { id, name, kind, config: { port, baud, newline: '\n' } }
        : { id, name, kind, config: { base_url: baseUrl, default_method: 'POST', default_timeout_sec: 2, headers: {} } }
    try {
      await experimentApi.createIntegration(integration)
      onClose()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: unknown } } }
      setErr(String(err.response?.data?.detail ?? e))
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 p-6 rounded-lg w-full max-w-md space-y-3">
        <h4 className="font-semibold">Add Integration</h4>
        <label className="block text-sm">
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value as 'serial' | 'http')} className="block w-full border rounded px-2 py-1 mt-1">
            <option value="serial">Serial (Arduino / ESP32 USB)</option>
            <option value="http">HTTP (ESP32 WiFi / LAN)</option>
          </select>
        </label>
        <label className="block text-sm">
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1" />
        </label>
        {kind === 'serial' ? (
          <>
            <label className="block text-sm">
              Port
              <select value={port} onChange={(e) => setPort(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1">
                {ports.map((p) => (
                  <option key={p.device} value={p.device}>{p.device} — {p.description}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Baud
              <select value={baud} onChange={(e) => setBaud(Number(e.target.value))} className="block w-full border rounded px-2 py-1 mt-1">
                {[9600, 19200, 57600, 115200, 230400, 921600].map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
          </>
        ) : (
          <label className="block text-sm">
            Base URL
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1" />
            <span className="text-xs text-gray-500">localhost or RFC1918 LAN only</span>
          </label>
        )}
        {err && <p className="text-sm text-red-600">{err}</p>}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1 border rounded">Cancel</button>
          <button onClick={submit} disabled={!name} className="px-3 py-1 bg-primary-600 text-white rounded disabled:opacity-50">Save</button>
        </div>
      </div>
    </div>
  )
}
