"""
Agent 10: Le Superviseur
Quality control and validation for all production outputs
"""

import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

import soundfile as sf

from agents.base import StudioAgent, AgentTask
from config import config


class Superviseur(StudioAgent):
    """Le Superviseur — Quality control and validation specialist"""

    # Broadcast / streaming standards
    QUALITY_STANDARDS = {
        "streaming": {"lufs_min": -16.0, "lufs_max": -12.0, "peak_max_dbfs": -1.0},
        "broadcast": {"lufs_min": -23.0, "lufs_max": -18.0, "peak_max_dbfs": -3.0},
        "club":      {"lufs_min": -10.0, "lufs_max": -6.0,  "peak_max_dbfs": -0.3},
    }

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=10,
            name="Le Superviseur",
            role="Quality Control & Validation",
            model_manager=model_manager
        )

    async def initialize(self):
        """Initialize QC tools"""
        logger.info("✅ Superviseur initialized (QC pipeline)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Run quality control checks"""
        task.status = "processing"

        try:
            audio_files = task.input_data.get("audio_files", [])
            standard = task.input_data.get("standard", "streaming")

            if not audio_files:
                audio_path = task.input_data.get("audio_path")
                if audio_path:
                    audio_files = [audio_path]

            if not audio_files:
                raise ValueError("No audio_files provided for QC")

            reports = []
            for file_path in audio_files:
                report = await self.check_quality(Path(file_path), standard)
                reports.append(report)

            overall = self._summarize_reports(reports)
            task.output_data = {
                "reports": reports,
                "overall": overall,
                "all_passed": all(r["passed"] for r in reports),
            }
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def check_quality(
        self,
        audio_path: Path,
        standard: str = "streaming"
    ) -> Dict[str, Any]:
        """Run comprehensive quality checks on an audio file"""
        logger.info(f"🔍 QC check: {audio_path.name} [{standard}]")

        if not audio_path.exists():
            return {"file": str(audio_path), "error": "File not found", "passed": False}

        audio, sr = sf.read(str(audio_path))

        checks = {}
        checks["lufs"]          = self._check_lufs(audio, sr, standard)
        checks["peak"]          = self._check_peak(audio, standard)
        checks["dynamic_range"] = self._check_dynamic_range(audio)
        checks["clipping"]      = self._check_clipping(audio)
        checks["silence"]       = self._check_silence(audio, sr)
        checks["sample_rate"]   = self._check_sample_rate(sr)
        checks["stereo_field"]  = self._check_stereo_field(audio)

        all_passed = all(c["passed"] for c in checks.values())
        issues = [c["message"] for c in checks.values() if not c["passed"]]

        result = {
            "file": str(audio_path),
            "standard": standard,
            "passed": all_passed,
            "checks": checks,
            "issues": issues,
            "duration_s": round(len(audio) / sr, 2),
            "sample_rate": sr,
        }

        status_icon = "✅" if all_passed else "⚠️"
        logger.info(f"{status_icon} QC {'PASSED' if all_passed else 'FAILED'}: {audio_path.name}")
        if issues:
            for issue in issues:
                logger.warning(f"  → {issue}")

        return result

    def _check_lufs(self, audio: np.ndarray, sr: int, standard: str) -> Dict:
        """Check integrated LUFS level"""
        try:
            import pyloudnorm as pyln

            meter = pyln.Meter(sr)
            a = audio if audio.ndim > 1 else audio[:, np.newaxis]
            lufs = meter.integrated_loudness(a)

            std = self.QUALITY_STANDARDS.get(standard, self.QUALITY_STANDARDS["streaming"])
            passed = std["lufs_min"] <= lufs <= std["lufs_max"]

            return {
                "value": round(lufs, 2),
                "passed": passed,
                "message": (
                    "" if passed else
                    f"LUFS {lufs:.1f} outside range [{std['lufs_min']}, {std['lufs_max']}]"
                ),
            }
        except ImportError:
            return {"value": None, "passed": True, "message": "pyloudnorm not available"}

    def _check_peak(self, audio: np.ndarray, standard: str) -> Dict:
        """Check peak level in dBFS"""
        peak_dbfs = 20 * np.log10(np.abs(audio).max() + 1e-9)
        std = self.QUALITY_STANDARDS.get(standard, self.QUALITY_STANDARDS["streaming"])
        passed = peak_dbfs <= std["peak_max_dbfs"]

        return {
            "value": round(peak_dbfs, 2),
            "passed": passed,
            "message": "" if passed else f"Peak {peak_dbfs:.1f} dBFS exceeds {std['peak_max_dbfs']} dBFS",
        }

    def _check_dynamic_range(self, audio: np.ndarray) -> Dict:
        """Check dynamic range (should be > 6 dB)"""
        peak_dbfs = 20 * np.log10(np.abs(audio).max() + 1e-9)
        rms_dbfs = 20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-9)
        dr = peak_dbfs - rms_dbfs
        passed = dr >= 6.0

        return {
            "value": round(dr, 2),
            "passed": passed,
            "message": "" if passed else f"Dynamic range {dr:.1f} dB is too low (min 6 dB)",
        }

    def _check_clipping(self, audio: np.ndarray) -> Dict:
        """Detect digital clipping"""
        clipped_samples = int(np.sum(np.abs(audio) >= 0.9999))
        clipping_ratio = clipped_samples / len(audio)
        passed = clipping_ratio < 0.001  # less than 0.1% clipped

        return {
            "value": clipped_samples,
            "passed": passed,
            "message": "" if passed else f"Clipping detected: {clipped_samples} samples",
        }

    def _check_silence(self, audio: np.ndarray, sr: int) -> Dict:
        """Check for excessive silence at start/end"""
        threshold = 0.001
        non_silent = np.where(np.abs(audio).max(axis=-1) > threshold)[0]

        if len(non_silent) == 0:
            return {"value": "fully_silent", "passed": False, "message": "Audio is completely silent"}

        leading_silence_s = non_silent[0] / sr
        trailing_silence_s = (len(audio) - non_silent[-1]) / sr
        passed = leading_silence_s < 2.0 and trailing_silence_s < 3.0

        return {
            "value": {
                "leading_silence_s": round(leading_silence_s, 2),
                "trailing_silence_s": round(trailing_silence_s, 2),
            },
            "passed": passed,
            "message": "" if passed else (
                f"Excessive silence: {leading_silence_s:.1f}s leading, "
                f"{trailing_silence_s:.1f}s trailing"
            ),
        }

    def _check_sample_rate(self, sr: int) -> Dict:
        """Check sample rate is professional standard"""
        professional_rates = [44100, 48000, 88200, 96000]
        passed = sr in professional_rates

        return {
            "value": sr,
            "passed": passed,
            "message": "" if passed else f"Non-standard sample rate: {sr} Hz",
        }

    def _check_stereo_field(self, audio: np.ndarray) -> Dict:
        """Check stereo field (mono compatibility)"""
        if audio.ndim < 2 or audio.shape[1] < 2:
            return {"value": "mono", "passed": True, "message": ""}

        left, right = audio[:, 0], audio[:, 1]
        correlation = float(np.corrcoef(left, right)[0, 1]) if len(left) > 1 else 1.0
        passed = correlation > -0.3  # Negative correlation risks phase cancellation

        return {
            "value": round(correlation, 3),
            "passed": passed,
            "message": "" if passed else f"Stereo phase issues (correlation={correlation:.2f})",
        }

    def _summarize_reports(self, reports: List[Dict]) -> Dict[str, Any]:
        """Summarize multiple QC reports"""
        total = len(reports)
        passed = sum(1 for r in reports if r.get("passed", False))
        all_issues = [issue for r in reports for issue in r.get("issues", [])]

        return {
            "total_files": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "common_issues": list(set(all_issues))[:10],
        }

    async def approve_for_release(self, audio_path: Path) -> Dict[str, Any]:
        """Final release approval check"""
        streaming_report = await self.check_quality(audio_path, "streaming")

        approval = {
            "file": str(audio_path),
            "approved": streaming_report["passed"],
            "streaming_ready": streaming_report["passed"],
            "issues": streaming_report.get("issues", []),
            "recommendation": (
                "✅ Ready for release" if streaming_report["passed"]
                else "❌ Requires fixes before release"
            ),
        }

        return approval
