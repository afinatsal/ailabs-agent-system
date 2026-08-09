"""Mock LLM — deterministic, tanpa API key.

Dipakai untuk demo & test alur orchestrator (submit -> plan -> execute -> review
-> synthesize) tanpa mengeluarkan token. Deteksi tugas dari isi system prompt.
"""

from __future__ import annotations

import json

from ailabs.llm.base import LLMClient


class MockClient(LLMClient):
    provider = "mock"

    def __init__(self, model: str = "mock-model"):
        self._model = model

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        user_lower = user.lower()
        sys_lower = system.lower()

        # Dispatch berbasis marker di user prompt (lebih deterministik
        # daripada isi system prompt yang kadang tumpang-tindih).
        if "task yang direview" in user_lower:
            return json.dumps({"approved": True, "feedback": "Sesuai kriteria."})
        if "ringkasan hasil tim" in user_lower:
            return (
                "## Laporan Akhir AI Labs\n\n"
                "Semua subtask telah diselesaikan oleh tim. Tujuan tercapai: "
                f"{user[:200]}"
            )
        if "buat rencana kerja" in user_lower:
            return self._plan(user)
        # Marker khusus prompt Rio (Data Analyst) — deterministik.
        if "hasil analisis data" in user_lower:
            return (
                "HASIL ANALISIS (mock):\n"
                "# Ringkasan Data\n\n"
                "Data berhasil dianalisis: 3 baris, 2 kolom, "
                "mean kolom 'nilai' = 42.0."
            )
        if "tulis kode" in user_lower:
            return (
                "```python\n"
                "import json\n"
                "print(json.dumps({'rows': 3, 'columns': ['nama', 'nilai'], "
                "'stats': {'nilai': {'mean': 42.0}}}))\n"
                "```"
            )
        return self._worker(sys_lower, user)

    # ---------- helper ----------

    @staticmethod
    def _plan(user: str) -> str:
        prompt = user.strip()
        return json.dumps(
            {
                "title": "Plan untuk misi user",
                "summary": f"Tujuan: {prompt[:120]}",
                "goals": [
                    "Output jelas dan mudah dipahami",
                    "Mengikuti task yang diminta tanpa fitur tambahan",
                ],
                "tasks": [
                    {
                        "id": "t1",
                        "description": f"Riset: {prompt[:160]}",
                        "agent_name": "rita",
                        "depends_on": [],
                        "input": {
                            "topic": prompt[:160],
                            "goals": [
                                "Riset terstruktur dengan sumber jelas",
                                "Ringkasan actionable yang bisa dipakai tim",
                            ],
                        },
                    },
                    {
                        "id": "t2",
                        "description": f"Implementasi: {prompt[:160]}",
                        "agent_name": "dev",
                        "depends_on": ["t1"],
                        "input": {
                            "topic": prompt[:160],
                            "goals": [
                                "File output lengkap dan valid",
                                "Kode bebas placeholder / contoh",
                            ],
                        },
                    },
                    {
                        "id": "t3",
                        "description": f"Tulis laporan: {prompt[:160]}",
                        "agent_name": "wren",
                        "depends_on": ["t2"],
                        "input": {
                            "topic": prompt[:160],
                            "goals": [
                                "Laporan lengkap dan mudah dibaca",
                                "Kesimpulan mengikuti hasil task sebelumnya",
                            ],
                        },
                    },
                ],
            }
        )

    @staticmethod
    def _worker(sys_lower: str, user: str) -> str:
        if "desain" in sys_lower or "ui agent" in sys_lower:
            return (
                "HASIL DESAIN (mock):\n"
                "# Style Guide\n\n"
                "Palet Indigo-Fuchsia, tipografi system-ui.\n\n"
                "```file:design/style-guide.md\n"
                "# Style Guide\n\n"
                "## Palet Warna\n"
                "- Primary: #6366f1\n"
                "- Secondary: #a855f7\n\n"
                "## Tipografi\n"
                "- Heading: system-ui bold\n"
                "- Body: system-ui regular\n"
                "```\n"
                "```file:design/wireframe.html\n"
                "<!DOCTYPE html>\n"
                "<html><body><header>Hero</header>"
                "<main><h1>Landing</h1></main></body></html>\n"
                "```"
            )
        if "tester" in sys_lower or "qa agent" in sys_lower:
            return "```python\nprint('QA PASS')\n```"
        if "data analyst" in sys_lower:
            return (
                "```python\n"
                "import json\n"
                "print(json.dumps({'rows': 3, 'columns': ['nama', 'nilai']}))\n"
                "```"
            )
        if "terjemah" in sys_lower:
            return f"HASIL TERJEMAHAN (mock): {user[:120]}"
        if "research" in sys_lower:
            return f"HASIL RISET (mock):\n{user}\n\nKesimpulan: langkah awal sudah dipetakan."
        if "code" in sys_lower:
            return (
                "HASIL IMPLEMENTASI (mock):\n"
                "```file:index.html\n"
                "<!DOCTYPE html>\n"
                "<html>\n"
                "<head><meta charset=\"utf-8\"><title>Landing Page Kampanye</title>"
                "<link rel=\"stylesheet\" href=\"style.css\"></head>\n"
                "<body><main><h1>Ice Cream Kampanye</h1><p>Landing page mock.</p>"
                "</main></body>\n"
                "</html>\n"
                "```\n"
                "```file:style.css\n"
                "body { margin: 0; font-family: system-ui; }\n"
                "main { max-width: 720px; margin: auto; padding: 4rem 1rem; }\n"
                "h1 { color: #c2410c; }\n"
                "```\n"
                "```python\n"
                "def main():\n    print('selesai')\n\nmain()\n"
                "```"
            )
        if "writer" in sys_lower:
            return f"HASIL TULISAN (mock):\n# Dokumen\n\n{user}\n\nKesimpulan dan rekomendasi."
        return f"OUTPUT (mock):\n{user}"
