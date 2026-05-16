import { useEffect, useState } from 'react'
import { ChevronUp, Home, Folder, FolderLock } from 'lucide-react'
import { systemApi } from '@/services/api'

interface Props {
  initialPath?: string
  onSelect: (path: string) => void
  onClose: () => void
}

export default function FolderPickerModal({ initialPath, onSelect, onClose }: Props) {
  const [currentPath, setCurrentPath] = useState<string>('')
  const [parent, setParent] = useState<string | null>(null)
  const [home, setHome] = useState<string>('')
  const [dirs, setDirs] = useState<{ name: string; writable: boolean }[]>([])
  const [writable, setWritable] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const browse = (path: string) => {
    setError(null)
    systemApi
      .browse(path)
      .then((r) => {
        const d = r.data.data
        if (!d) return
        setCurrentPath(d.current_path)
        setParent(d.parent)
        setHome(d.home)
        setDirs(d.directories)
        setWritable(d.writable)
      })
      .catch((e) => {
        const detail = e?.response?.data?.detail
        setError(typeof detail === 'string' ? detail : String(e))
      })
  }

  useEffect(() => {
    browse(initialPath ?? '')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg w-full max-w-2xl p-6 space-y-3">
        <h4 className="font-semibold text-lg">Choose Output Folder</h4>

        <div className="flex items-center gap-2">
          <button
            onClick={() => parent && browse(parent)}
            disabled={!parent}
            className="px-2 py-1 text-sm border rounded disabled:opacity-40 inline-flex items-center gap-1"
          >
            <ChevronUp className="w-4 h-4" /> Up
          </button>
          <button
            onClick={() => browse(home)}
            className="px-2 py-1 text-sm border rounded inline-flex items-center gap-1"
          >
            <Home className="w-4 h-4" /> Home
          </button>
          <code className="ml-2 text-xs text-gray-700 dark:text-gray-300 truncate flex-1" title={currentPath}>
            {currentPath || '...'}
          </code>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="border rounded max-h-80 overflow-y-auto divide-y dark:divide-gray-700">
          {dirs.length === 0 && !error && (
            <p className="text-sm text-gray-500 p-3">No subdirectories.</p>
          )}
          {dirs.map((d) => (
            <button
              key={d.name}
              onClick={() => browse(`${currentPath}/${d.name}`)}
              className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700/40 inline-flex items-center gap-2 text-sm"
            >
              {d.writable
                ? <Folder className="w-4 h-4 text-primary-500" />
                : <FolderLock className="w-4 h-4 text-gray-400" />}
              <span>{d.name}</span>
              {!d.writable && <span className="text-xs text-gray-500 ml-auto">read-only</span>}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between gap-2 pt-2">
          <span className={`text-xs ${writable ? 'text-green-600' : 'text-amber-600'}`}>
            {writable ? '✓ This folder is writable' : '⚠ This folder is NOT writable'}
          </span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1 border rounded">Cancel</button>
            <button
              onClick={() => onSelect(currentPath)}
              disabled={!writable}
              className="px-3 py-1 bg-primary-600 text-white rounded disabled:opacity-50"
            >
              Select this folder
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
