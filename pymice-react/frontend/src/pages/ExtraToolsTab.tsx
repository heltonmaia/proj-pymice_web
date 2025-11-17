import { useState } from 'react'
import { Cpu, Zap, CheckCircle, XCircle } from 'lucide-react'
import { systemApi } from '@/services/api'

export default function ExtraToolsTab() {
  const [gpuStatus, setGpuStatus] = useState<{
    cuda: boolean
    mps: boolean
    device: string
  } | null>(null)
  const [yoloTest, setYoloTest] = useState<{
    gpuTime: number
    cpuTime: number
    speedup: number
  } | null>(null)
  const [testing, setTesting] = useState(false)

  const checkGPU = async () => {
    setTesting(true)
    try {
      const response = await systemApi.checkGPU()
      if (response.data.success) {
        setGpuStatus({
          cuda: response.data.data.cuda_available,
          mps: response.data.data.mps_available,
          device: response.data.data.device,
        })
      }
    } catch (error) {
      console.error('Error checking GPU:', error)
      setGpuStatus({
        cuda: false,
        mps: false,
        device: 'cpu',
      })
    } finally {
      setTesting(false)
    }
  }

  const testYOLO = async () => {
    setTesting(true)
    try {
      const response = await systemApi.testYOLO('yolov11n.pt')
      if (response.data.success) {
        setYoloTest({
          gpuTime: response.data.data.gpu_time,
          cpuTime: response.data.data.cpu_time,
          speedup: response.data.data.speedup,
        })
      }
    } catch (error) {
      console.error('Error testing YOLO:', error)
      setYoloTest({
        gpuTime: 0,
        cpuTime: 0,
        speedup: 0,
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-primary-500" />
          System Diagnostics
        </h2>

        {/* GPU Check */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold mb-3">GPU Availability</h3>
          <p className="text-gray-400 mb-4">
            Check if CUDA (NVIDIA) or MPS (Apple Silicon) acceleration is available for faster processing.
          </p>

          <button
            onClick={checkGPU}
            disabled={testing}
            className="px-6 py-3 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Zap className="w-5 h-5" />
            {testing ? 'Checking...' : 'Check GPU Status'}
          </button>

          {gpuStatus && (
            <div className="mt-4 bg-gray-700/50 rounded-lg p-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center gap-3">
                  {gpuStatus.cuda ? (
                    <CheckCircle className="w-5 h-5 text-green-400" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-400" />
                  )}
                  <div>
                    <div className="font-medium">CUDA (NVIDIA)</div>
                    <div className="text-sm text-gray-400">
                      {gpuStatus.cuda ? 'Available' : 'Not Available'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {gpuStatus.mps ? (
                    <CheckCircle className="w-5 h-5 text-green-400" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-400" />
                  )}
                  <div>
                    <div className="font-medium">MPS (Apple Silicon)</div>
                    <div className="text-sm text-gray-400">
                      {gpuStatus.mps ? 'Available' : 'Not Available'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Cpu className="w-5 h-5 text-blue-400" />
                  <div>
                    <div className="font-medium">Active Device</div>
                    <div className="text-sm text-gray-400 uppercase">{gpuStatus.device}</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* YOLO Performance Test */}
        <div>
          <h3 className="text-lg font-semibold mb-3">YOLO Performance Test</h3>
          <p className="text-gray-400 mb-4">
            Compare inference speed between GPU and CPU for YOLO model processing.
          </p>

          <button
            onClick={testYOLO}
            disabled={testing}
            className="px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            <Zap className="w-5 h-5" />
            {testing ? 'Testing...' : 'Run Performance Test'}
          </button>

          {yoloTest && (
            <div className="mt-4 bg-gray-700/50 rounded-lg p-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <div className="text-gray-400 mb-1">GPU Inference Time</div>
                  <div className="text-2xl font-bold text-green-400">
                    {yoloTest.gpuTime > 0 ? `${yoloTest.gpuTime.toFixed(2)}ms` : 'N/A'}
                  </div>
                </div>

                <div>
                  <div className="text-gray-400 mb-1">CPU Inference Time</div>
                  <div className="text-2xl font-bold text-blue-400">
                    {yoloTest.cpuTime.toFixed(2)}ms
                  </div>
                </div>

                <div>
                  <div className="text-gray-400 mb-1">Speedup</div>
                  <div className="text-2xl font-bold text-yellow-400">
                    {yoloTest.speedup > 0 ? `${yoloTest.speedup.toFixed(1)}x` : 'N/A'}
                  </div>
                </div>
              </div>

              {yoloTest.gpuTime === 0 && (
                <div className="mt-4 p-3 bg-yellow-900/20 border border-yellow-600 rounded-lg text-yellow-400 text-sm">
                  No GPU acceleration available. Processing will use CPU only.
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* System Info */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-lg font-semibold mb-4">System Information</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Platform:</span>
            <span className="font-medium">Web Browser</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Backend:</span>
            <span className="font-medium">FastAPI + PyTorch</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Frontend:</span>
            <span className="font-medium">React + TypeScript</span>
          </div>
        </div>
      </div>
    </div>
  )
}
