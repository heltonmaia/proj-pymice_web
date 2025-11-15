import os
import threading
import time
from pathlib import Path

import panel as pn
import torch
from ultralytics import YOLO


class ExtraToolsTab:
    def __init__(self) -> None:
        # Get paths
        self.project_root = Path(__file__).parent.parent
        self.extra_tools_dir = self.project_root / "extra_tools"

        # GPU Basic Test components
        self.gpu_basic_button = pn.widgets.Button(
            name="🔍 Test GPU Availability", button_type="primary", width=200, height=40
        )
        self.gpu_basic_result = pn.pane.Markdown(
            "**GPU Status:** Click button to test",
            styles={"background": "#f8f9fa", "padding": "10px", "border-radius": "5px"},
            width=500,
        )

        # YOLO GPU Test components
        self.yolo_test_button = pn.widgets.Button(
            name="🎯 Test YOLO GPU/CPU", button_type="success", width=200, height=40
        )
        self.yolo_test_result = pn.pane.Markdown(
            "**YOLO Status:** Click button to test",
            styles={"background": "#f8f9fa", "padding": "10px", "border-radius": "5px"},
            width=500,
        )

        # Status indicators
        self.testing_status = pn.pane.Markdown("**Status:** Ready", width=300)

        # Connect events
        self.gpu_basic_button.on_click(self.test_gpu_basic)
        self.yolo_test_button.on_click(self.test_yolo_gpu)

    def test_gpu_basic(self, event):
        """Test basic GPU availability"""
        self.testing_status.object = "**Status:** 🔄 Testing GPU availability..."
        self.gpu_basic_button.disabled = True

        try:
            # Test PyTorch CUDA availability
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                cuda_version = torch.version.cuda
                device_count = torch.cuda.device_count()

                # Test memory allocation
                try:
                    x = torch.randn(100, 100).cuda()
                    memory_allocated = torch.cuda.memory_allocated() / 1024**2  # MB
                    del x
                    torch.cuda.empty_cache()

                    result = (
                        "**GPU Status:** ✅ **Available**"
                        "\n"
                        "**Device Information:**\n"
                        f"- **GPU:** {device_name}\n"
                        f"- **CUDA Version:** {cuda_version}\n"
                        f"- **Device Count:** {device_count}\n"
                        f"- **Memory Test:** ✅ Passed ({memory_allocated:.1f} MB allocated)\n"
                        "\n"
                        "**Verdict:** GPU is ready for PyTorch operations!\n"
                    )

                    color = "#d4edda"  # Light green

                except Exception as mem_error:
                    result = (
                        "**GPU Status:** ⚠️ **Detected but Memory Issues**"
                        "\n"
                        "**Device Information:**\n"
                        f"- **GPU:** {device_name}\n"
                        f"- **CUDA Version:** {cuda_version}\n"
                        f"- **Memory Error:** {str(mem_error)}\n"
                        "\n"
                        "**Verdict:** GPU detected but cannot allocate memory properly.\n"
                    )
                    color = "#fff3cd"  # Light yellow
            else:
                result = (
                    "**GPU Status:** ❌ **Not Available**"
                    "\n"
                    "**Issues:**\n"
                    f"- No CUDA-compatible GPU detected by PyTorch\n"
                    f"- PyTorch may not have CUDA support installed\n"
                    "\n"
                    "**Recommendations:**\n"
                    "1. Check if NVIDIA GPU drivers are installed\n"
                    "2. Install PyTorch with CUDA support\n"
                    "3. Verify GPU is not being used by other processes\n"
                    "\n"
                    "**Verdict:** Will use CPU for computations.\n"
                )
                color = "#f8d7da"  # Light red

            # Update UI directly
            self._update_gpu_result(result, color)

        except Exception as e:
            error_result = (
                "**GPU Status:** ❌ **Error During Test**"
                "\n"
                f"**Error:** {str(e)}\n"
                "\n"
                "**Verdict:** Cannot determine GPU status."
            )
            self._update_gpu_result(error_result, "#f8d7da")

    def _update_gpu_result(self, result: str, color: str) -> None:
        """Update GPU test result in main thread"""
        self.gpu_basic_result.object = result
        self.gpu_basic_result.styles = {
            "background": color,
            "padding": "15px",
            "border-radius": "5px",
        }
        self.testing_status.object = "**Status:** GPU test completed"
        self.gpu_basic_button.disabled = False

    def test_yolo_gpu(self, event) -> None:
        """Test YOLO with GPU/CPU"""
        self.testing_status.object = (
            "**Status:** 🔄 Testing YOLO (may take 30+ seconds)..."
        )
        self.yolo_test_button.disabled = True

        def run_yolo_test() -> None:
            try:
                # Set YOLO model directory to extra_tools_tab folder
                yolo_models_dir = Path(__file__).parent / "models"
                yolo_models_dir.mkdir(exist_ok=True)

                # Set environment variable for YOLO to use our directory
                os.environ["YOLO_CONFIG_DIR"] = str(yolo_models_dir)

                # Model path in our directory (using YOLOv11 nano)
                model_path = yolo_models_dir / "yolo11n.pt"

                # Test image URL
                test_image = "https://ultralytics.com/images/bus.jpg"

                results = []

                # Test GPU first (if available)
                if torch.cuda.is_available():
                    try:
                        start_time = time.time()
                        model_gpu = YOLO(str(model_path))
                        model_gpu.to("cuda")

                        # Run inference
                        detection_results = model_gpu(test_image, verbose=False)
                        gpu_time = time.time() - start_time

                        num_detections = (
                            len(detection_results[0].boxes)
                            if detection_results[0].boxes is not None
                            else 0
                        )

                        results.append(
                            {
                                "device": "GPU",
                                "status": "✅ Success",
                                "time": f"{gpu_time:.2f}s",
                                "detections": num_detections,
                            }
                        )

                    except Exception as gpu_error:
                        results.append(
                            {
                                "device": "GPU",
                                "status": f"❌ Failed: {str(gpu_error)[:50]}...",
                                "time": "N/A",
                                "detections": "N/A",
                            }
                        )

                # Test CPU
                try:
                    start_time = time.time()
                    model_cpu = YOLO(str(model_path))
                    model_cpu.to("cpu")

                    # Run inference
                    detection_results = model_cpu(test_image, verbose=False)
                    cpu_time = time.time() - start_time

                    num_detections = (
                        len(detection_results[0].boxes)
                        if detection_results[0].boxes is not None
                        else 0
                    )

                    results.append(
                        {
                            "device": "CPU",
                            "status": "✅ Success",
                            "time": f"{cpu_time:.2f}s",
                            "detections": num_detections,
                        }
                    )

                except Exception as cpu_error:
                    results.append(
                        {
                            "device": "CPU",
                            "status": f"❌ Failed: {str(cpu_error)[:50]}...",
                            "time": "N/A",
                            "detections": "N/A",
                        }
                    )

                # Format results
                result_text = "**YOLO Test Results:**\n\n"

                for result in results:
                    result_text += f"**{result['device']} Performance:**\n"
                    result_text += f"- Status: {result['status']}\n"
                    result_text += f"- Time: {result['time']}\n"
                    result_text += f"- Objects detected: {result['detections']}\n\n"

                # Determine overall verdict
                gpu_success = any(
                    r["device"] == "GPU" and "✅" in r["status"] for r in results
                )
                cpu_success = any(
                    r["device"] == "CPU" and "✅" in r["status"] for r in results
                )

                if gpu_success:
                    result_text += "**Verdict:** 🚀 GPU acceleration is working! YOLO will run fast."
                    color = "#d4edda"
                elif cpu_success:
                    result_text += (
                        "**Verdict:** ⚠️ Only CPU available. YOLO will work but slower."
                    )
                    color = "#fff3cd"
                else:
                    result_text += "**Verdict:** ❌ YOLO failed on both GPU and CPU. Check installation."
                    color = "#f8d7da"

                # Update UI directly
                self._update_yolo_result(result_text, color)

            except ImportError:
                error_result = (
                    "**YOLO Test Results:**\n"
                    "❌ **YOLO Not Available**\n"
                    "**Error:** ultralytics package not found\n"
                    "**Solution:** Install with: `pip install ultralytics`\n"
                )
                self._update_yolo_result(error_result, "#f8d7da")

            except Exception as e:
                error_result = (
                    "**YOLO Test Results:**\n"
                    "❌ **Unexpected Error**\n"
                    f"**Error:** {str(e)}"
                )
                self._update_yolo_result(error_result, "#f8d7da")

        # Run in separate thread but update UI with direct call
        threading.Thread(target=run_yolo_test, daemon=True).start()

    def _update_yolo_result(self, result: str, color: str) -> None:
        """Update YOLO test result in main thread"""
        self.yolo_test_result.object = result
        self.yolo_test_result.styles = {
            "background": color,
            "padding": "15px",
            "border-radius": "5px",
        }
        self.testing_status.object = "**Status:** YOLO test completed"
        self.yolo_test_button.disabled = False

    def get_panel(self) -> pn.Column:
        """Return the main panel layout"""
        # GPU Availability Test Accordion
        gpu_test_accordion = pn.Accordion(
            ("🔍 GPU Availability Test - Test if your GPU is available and working with PyTorch",
             pn.Column(
                pn.Row(self.gpu_basic_button, pn.Spacer(width=20), self.gpu_basic_result),
                pn.Spacer(height=15),
             )),
            active=[],
            width=900,
        )

        # YOLO Performance Test Accordion
        yolo_test_accordion = pn.Accordion(
            ("🎯 YOLO Performance Test - Test YOLOv11 performance on GPU vs CPU (downloads model if needed)",
             pn.Column(
                pn.Row(self.yolo_test_button, pn.Spacer(width=20), self.yolo_test_result),
                pn.Spacer(height=15),
             )),
            active=[],
            width=900,
        )

        return pn.Column(
            pn.pane.Markdown("# 🛠️ Extra Tools", margin=(0, 0, 20, 0)),
            gpu_test_accordion,
            pn.Spacer(height=10),
            yolo_test_accordion,
            pn.Spacer(height=20),
            # Status
            self.testing_status,
            margin=(20, 20),
        )


def get_tab() -> pn.Column:
    """Create and return the Extra Tools tab"""
    extra_tools = ExtraToolsTab()
    return extra_tools.get_panel()
