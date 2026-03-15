"""첨부 입력을 멀티모달 전처리해 LLM 태스크에 주입한다."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any
import urllib.request

from core.attachment_manager import AttachmentContext


class AttachmentAnalyzer:
    async def analyze(self, attachment: AttachmentContext) -> str:
        if attachment.kind == "photo":
            summary = self._analyze_image_with_bridge(attachment.local_path, attachment.mime_type)
            if summary:
                return summary
            summary = self._analyze_image_with_gemini(attachment.local_path, attachment.mime_type)
            if summary:
                return summary
        if attachment.mime_type == "application/pdf":
            summary = self._extract_pdf_text(attachment.local_path)
            if summary:
                return summary
        return attachment.preview_text

    def _analyze_image_with_bridge(self, path: Path, mime_type: str) -> str:
        raw_cmd = os.environ.get("ATTACHMENT_VISION_BRIDGE_CMD", "").strip()
        if not raw_cmd or not path.exists():
            return ""
        try:
            cmd = shlex.split(raw_cmd) + [str(path), mime_type or "image/jpeg"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("ATTACHMENT_VISION_BRIDGE_TIMEOUT_SEC", "60")),
                check=False,
            )
            if proc.returncode != 0:
                return ""
            return (proc.stdout or "").strip()
        except Exception:
            return ""

    def _analyze_image_with_gemini(self, path: Path, mime_type: str) -> str:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key or not path.exists():
            return ""
        try:
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Analyze this image for a coding/task assistant. Describe key visual contents, readable text, UI/layout, diagrams, tables, or actionable details in Korean. Keep it concise but specific."},
                        {
                            "inline_data": {
                                "mime_type": mime_type or "image/jpeg",
                                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                            }
                        },
                    ]
                }]
            }
            req = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
                f"?key={api_key}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
        except Exception:
            return ""

    def _extract_pdf_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            return ""
        try:
            reader = PdfReader(str(path))
            texts: list[str] = []
            for page in reader.pages[:5]:
                text = (page.extract_text() or "").strip()
                if text:
                    texts.append(text)
            joined = "\n\n".join(texts).strip()
            if len(joined) > 2000:
                joined = joined[:2000].rstrip() + "\n..."
            return joined
        except Exception:
            return ""
