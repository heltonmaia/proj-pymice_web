import { useEffect, useState } from 'react'
import { experimentApi } from '@/services/api'
import type { Integration, TriggerRule } from '@/types'

interface Props { expId?: string; disabled?: boolean }

export default function TriggersPanel({ expId, disabled }: Props) {
  const [rules, setRules] = useState<TriggerRule[]>([])
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [showAdd, setShowAdd] = useState(false)

  const reload = async () => {
    if (!expId || disabled) return
    const r = await experimentApi.listTriggers()
    setRules(r.data.data?.triggers ?? [])
  }
  useEffect(() => {
    reload()
    experimentApi.listIntegrations().then((r) => setIntegrations(r.data.data?.integrations ?? []))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expId])

  const onDelete = async (id: string) => {
    if (!confirm(`Delete trigger ${id}?`)) return
    await experimentApi.deleteTrigger(id)
    reload()
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Triggers</h3>
        {!disabled && expId && (
          <button onClick={() => setShowAdd(true)} className="text-sm bg-primary-600 text-white px-3 py-1 rounded">
            + Add Trigger
          </button>
        )}
      </div>
      {disabled && (
        <p className="text-sm text-gray-500">Start an experiment to attach triggers. Configure Integrations first.</p>
      )}
      {!disabled && rules.length === 0 && <p className="text-sm text-gray-500">No triggers.</p>}
      <ul className="space-y-1 text-sm">
        {rules.map((r) => (
          <li key={r.id} className="flex items-center gap-2">
            <span className="font-medium">{r.name}</span>
            <span className="text-gray-500">
              on {r.match.event_type}{r.match.roi_name ? `(${r.match.roi_name})` : ''} →{' '}
              {r.action.kind === 'log' ? `log:${r.action.label}` : `int:${r.action.integration_id}`}
            </span>
            <button onClick={() => onDelete(r.id)} className="ml-auto text-xs text-red-600">Delete</button>
          </li>
        ))}
      </ul>
      {showAdd && expId && (
        <AddTrigger
          integrations={integrations}
          onClose={() => { setShowAdd(false); reload() }}
        />
      )}
    </div>
  )
}

function AddTrigger({ integrations, onClose }: { integrations: Integration[]; onClose: () => void }) {
  const [name, setName] = useState('')
  const [evtType, setEvtType] = useState<'roi_entry' | 'roi_exit' | 'tick' | 'frame_drop'>('roi_entry')
  const [roiName, setRoiName] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const [minDwell, setMinDwell] = useState(0)
  const [actionKind, setActionKind] = useState<'integration' | 'log'>('integration')
  const [integrationId, setIntegrationId] = useState(integrations[0]?.id ?? '')
  const [payload, setPayload] = useState('')
  const [label, setLabel] = useState('')

  const submit = async () => {
    const rule: TriggerRule = {
      id: `t-${Date.now().toString(36)}`,
      name,
      match: {
        event_type: evtType,
        roi_name: roiName || null,
        cooldown_sec: cooldown || null,
        min_dwell_sec: evtType === 'roi_exit' ? (minDwell || null) : null,
      },
      action: actionKind === 'log'
        ? { kind: 'log', label }
        : { kind: 'integration', integration_id: integrationId, payload, timeout_sec: 2 },
    }
    await experimentApi.createTrigger(rule)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 p-6 rounded-lg w-full max-w-md space-y-3">
        <h4 className="font-semibold">Add Trigger</h4>
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} className="block w-full border rounded px-2 py-1" />
        <label className="block text-sm">
          Event
          <select value={evtType} onChange={(e) => setEvtType(e.target.value as 'roi_entry' | 'roi_exit' | 'tick' | 'frame_drop')} className="block w-full border rounded px-2 py-1 mt-1">
            <option value="roi_entry">roi_entry</option>
            <option value="roi_exit">roi_exit</option>
            <option value="tick">tick</option>
            <option value="frame_drop">frame_drop</option>
          </select>
        </label>
        <input placeholder="ROI name (blank = any)" value={roiName} onChange={(e) => setRoiName(e.target.value)} className="block w-full border rounded px-2 py-1" />
        <label className="block text-sm">
          Cooldown (s)
          <input type="number" min={0} step={0.1} value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))} className="block w-full border rounded px-2 py-1 mt-1" />
        </label>
        {evtType === 'roi_exit' && (
          <label className="block text-sm">
            Min dwell (s)
            <input type="number" min={0} step={0.1} value={minDwell} onChange={(e) => setMinDwell(Number(e.target.value))} className="block w-full border rounded px-2 py-1 mt-1" />
          </label>
        )}
        <label className="block text-sm">
          Action
          <select value={actionKind} onChange={(e) => setActionKind(e.target.value as 'integration' | 'log')} className="block w-full border rounded px-2 py-1 mt-1">
            <option value="integration">Integration</option>
            <option value="log">Log marker</option>
          </select>
        </label>
        {actionKind === 'integration' ? (
          <>
            <label className="block text-sm">
              Send to
              <select value={integrationId} onChange={(e) => setIntegrationId(e.target.value)} className="block w-full border rounded px-2 py-1 mt-1">
                {integrations.map((i) => <option key={i.id} value={i.id}>{i.name} ({i.kind})</option>)}
              </select>
            </label>
            <input placeholder="Payload (e.g. DROP)" value={payload} onChange={(e) => setPayload(e.target.value)} className="block w-full border rounded px-2 py-1" />
          </>
        ) : (
          <input placeholder="Log label" value={label} onChange={(e) => setLabel(e.target.value)} className="block w-full border rounded px-2 py-1" />
        )}
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1 border rounded">Cancel</button>
          <button onClick={submit} disabled={!name} className="px-3 py-1 bg-primary-600 text-white rounded disabled:opacity-50">Save</button>
        </div>
      </div>
    </div>
  )
}
