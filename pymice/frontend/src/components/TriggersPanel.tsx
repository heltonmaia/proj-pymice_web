interface Props { expId?: string; disabled?: boolean }
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export default function TriggersPanel(_props: Props) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border">
      <h3 className="font-semibold mb-2">Triggers</h3>
      <p className="text-sm text-gray-500">(wired in Task 16)</p>
    </div>
  )
}
