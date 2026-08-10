# AI Labs — Multi-Agent System

Perusahaan tempat **seluruh pekerjanya adalah AI Agent**. Kamu memberi misi,
**Mark (CEO)** memecahnya menjadi to-do list, mendelegasikan ke timnya, meninjau
hasil, dan menyusun laporan akhir.

## Tim

| Agent | Peran | Skill yang dipakai |
|---|---|---|
| **Mark** | CEO & Orchestrator — merencanakan, menugaskan, menyintesis laporan | — |
| **Rita** | Research — riset & pengumpulan informasi | `web_search`, `fetch_url` |
| **Dev** | Code — implementasi & perbaikan kode | `agentic_loop`, `opencode_code`, `code_exec`, `taste_design` (frontend) |
| **Wren** | Writer — menulis dokumen & laporan | `obsidian_writer` |
| **Dara** | Desain/UI — wireframe, style guide, layout | `taste_design`, `image_generate` |
| **Rio** | Data Analyst — analisis data CSV/JSON | `data_analysis`, `code_exec` |
| **Qa** | Tester — verifikasi hasil & laporan pengujian | `code_exec` |
| **Vera** | Reviewer/QA — meninjau hasil sebelum dianggap selesai | — |

Semua agent juga bisa **menyimpan hasil sebagai file lokal** lewat skill `write_file`
(mis. "buat file landing page"). Lihat bagian *Hasil Kerja Menjadi File Lokal*.

### Loop otonom (`agentic_loop`)

Skill ini membuat agent bertindak seperti agent CLI: LLM memutuskan tool
berikutnya (`read_file`, `grep_files`, `edit_file`, `code_exec`, dll), sistem
menjalankannya, hasil dikembalikan ke LLM sebagai konteks, dan berulang sampai
goals task tercapai. **Semua worker agent** (dev, rita, rio, wren, dara, qa)
otomatis memakai jalur ini di awal `execute()` — bila skill tersedia, task
dikerjakan otonom; bila tidak/gagal, agent jatuh ke jalur lamanya (fallback).
Batas iterasi diatur lewat `AGENTIC_MAX_ITERATIONS` di `.env` (default 5).

### Review berbasis bukti file

Saat agent menulis file (lewat `write_file`/`agentic_loop`/`opencode`), executor
otomatis mengumpulkan **isi file tersebut dari workspace** dan menyuntikkannya ke
review Vera (`_collect_evidence`). Reviewer tidak lagi menilai dari narasi teks
saja — ia bisa memverifikasi kode yang benar-benar ada. File yang sama juga
didaftarkan (tanpa duplikat, path dipaksa di dalam workspace project).

### Delegasi koding ke opencode

Dev bisa mendelegasikan task koding ke **opencode** (CLI agent) yang menulis/mengedit
file sendiri di folder project — bukan sekadar output teks. Aktifkan di `.env`
(`ENABLE_OPENCODE=true`). Saat off/gagal, Dev otomatis fallback ke LLM + `code_exec`.

## Struktur

```
ailabs-agent-system/
├── ailabs/                  # package utama
│   ├── cli.py               # antarmuka terminal
│   ├── config/              # settings (.env) + agent_config.yaml
│   ├── llm/                 # client LLM provider-agnostic
│   │   ├── base.py          #   abstract LLMClient
│   │   ├── gemini.py        #   Gemini (default)
│   │   ├── deepseek.py      #   DeepSeek (OpenAI-compatible API)
│   │   ├── openai_compat.py #   proxy OpenAI-compatible (9router/kuroko)
│   │   └── factory.py       #   pilih provider dari env
│   ├── models/              # Pydantic schemas (Job, Task, Document, ...)
│   ├── db/                  # storage: InMemory (dev) + Supabase (prod)
│   ├── orchestrator/        # inti: planner (Mark), executor (state machine), core
│   ├── dashboard/           # web UI (FastAPI): templates/ + static/ + app.py
│   ├── agents/              # ⭐ tambah agent = tambah folder di sini
│   │   ├── registry.py      #   auto-discovery, tanpa ubah core
│   │   ├── ceo/ research/ code/ writer/ reviewer/ design/ analyst/ tester/
│   ├── skills/              # ⭐ tambah skill = tambah file di sini
│   │   ├── registry.py      #   auto-discovery
│   │   ├── opencode_code.py #   delegasi koding ke agent opencode
│   │   └── _taste/          #   dokumen taste-skill (anti-slop UI)
│   └── memory/              # embedding + retrieval (pgvector, opsional)
├── db/schema.sql            # jalankan di Supabase SQL editor
├── tests/
└── pyproject.toml
```

## Quickstart

```bash
cd ailabs-agent-system
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

ailabs init          # buat .env dari template
# isi GEMINI_API_KEY, SUPABASE_URL, dan salah satu key Supabase di .env

ailabs agents        # cek tim terdaftar
ailabs skills        # cek skill terdaftar
ailabs serve         # buka dashboard web di http://127.0.0.1:8000
```

Tanpa API key/Supabase pun tetap bisa dicoba dengan **mock provider**:

```bash
export LLM_PROVIDER=mock
ailabs ask "Riset tren AI lalu tulis ringkasannya"
```

Output mock adalah placeholder; ganti `LLM_PROVIDER=gemini` (dan isi key di `.env`) untuk hasil nyata.

**Catatan storage:** selama `SUPABASE_URL`/`SUPABASE_ANON_KEY` belum diset, data disimpan ke file lokal `data/ailabs.json` (persisten antar perintah CLI). Begitu env Supabase diisi, sistem otomatis memakai Supabase; hapus `data/` jika ingin mulai bersih.

## Perintah CLI

```bash
ailabs ask "<misi>"        # submit + rencana + eksekusi + laporan, sekaligus
ailabs submit "<misi>"     # hanya rencana (Mark), simpan job
ailabs run <job_id>        # eksekusi job yang sudah direncanakan
ailabs status <job_id>     # status job + task list
ailabs tasks <job_id>      # task list saja
ailabs report <job_id>     # laporan akhir
ailabs agents | skills     # roster tim / daftar skill
```

### Operasional / maintenance

```bash
ailabs jobs                # semua job + ringkasan task (done/failed)
ailabs retry <task_id>     # ulangi task yang gagal (reset ke ready)
ailabs cancel <job_id>     # batalkan job yang belum selesai
ailabs delete <job_id>     # hapus job beserta task & dokumennya (--yes utk lewat konfirmasi)
ailabs delete ALL --yes    # hapus semua job
ailabs clear --yes         # hapus semua data (job, task, dokumen)
ailabs logs                # aktivitas skill pada sesi ini
```

## Dashboard Web (Control Room)

Dashboard visual berbasis FastAPI — buka di browser untuk memantau & mengendalikan semua misi:

```bash
ailabs serve               # default http://127.0.0.1:8000
ailabs serve --host 0.0.0.0 --port 8080   # akses dari perangkat lain
```

Fitur per halaman:

| Halaman | Isi |
|---|---|
| **Overview** | ringkasan job per status, statistik (hari ini/minggu, rata-rata waktu, task gagal), umpan aktivitas, form kirim misi cepat |
| **Job detail** | **task graph visual** (node + garis dependency + warna status), tabel task dengan detail input/output, polling live saat `running`, plan & laporan akhir (markdown), export .md / PDF (print), tombol run/cancel/retry/hapus |
| **Agents** | kartu tiap agent + statistik performa (task, success rate, rata-rata waktu), toggle aktif/nonaktif (`agent_config.yaml`), lihat system prompt |
| **Skills** | daftar skill, agent pemakainya, log pemanggilan terakhir |
| **Workspace** | file tree per project, preview isi, download, link balik ke job yang menghasilkannya |
| **Settings** | status LLM provider + test koneksi, status storage (JSON lokal vs Supabase) + tombol migrate, health check, danger zone (clear) |
| **Logs** | aliran event per job + detail error task gagal |

Catatan desain:

- Satu process = satu orchestrator. Data, event log, dan skill log dibagi antar request di dalam sesi dashboard.
- Job dieksekusi di thread background — halaman detail otomatis polling (`/api/jobs/<id>` & `/api/jobs/<id>/events`) selama job `running`.
- Mengganti agent aktif lewat UI akan menulis `agent_config.yaml`; berlaku penuh saat process berikutnya (restart).
- Toggle **embedding semantik** aktif otomatis jika `sentence-transformers` terinstall; kalau tidak, pencarian dokumen memakai keyword.

## Setup Supabase

1. Buat project di [supabase.com](https://supabase.com).
2. Jalankan isi `db/schema.sql` di **SQL Editor**. Script ini otomatis:
   - membuat schema terpisah **`ailabs`** (tabel kamu yang ada di `public` tidak disentuh),
   - membuat tabel `jobs`, `tasks`, `documents`, `agent_registry`,
   - memberikan akses ke role anon/authenticated/service_role,
   - menambahkan schema ke PostgREST (setara `Settings → API → Exposed schemas`).
3. Isi `.env`: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` *atau* `SUPABASE_SECRET_KEY`.

> App memakai key **SECRET** (bypass RLS) karena dijalankan lokal/server-side.
> Kalau pakai **PUBLISHABLE**, aktifkan blok RLS di `schema.sql`.

Semua tabel AI Labs berada di schema **`ailabs`**, terpisah dari tabel pribadimu di
`public`. Aplikasi terhubung lewat `ClientOptions(schema="ailabs")`.

## Menambah Agent Baru

1. Buat folder `ailabs/agents/<nama>/` berisi `agent.py` + `system_prompt.md`.
2. `agent.py` mengekspos `create(llm, skills, settings, config)` → instance `BaseAgent`.
3. Selesai — orchestrator otomatis mendeteksinya. (Atau matikan via `agent_config.yaml`.)

Contoh `agent.py`:

```python
from ailabs.agents.base import BaseAgent

class MyAgent(BaseAgent):
    name = "nama"
    role = "Role"
    description = "..."

def create(llm, skills=None, settings=None, config=None):
    return MyAgent(llm=llm, skills=skills)
```

## Menambah Skill Baru

1. Buat file `ailabs/skills/<nama>.py` dengan variabel `SKILLS = [Skill(...)]`.
2. Selesai — agent bisa memanggilnya via `self.skills.get("<nama>")`.

## Hasil Kerja Menjadi File Lokal

Semua hasil utama tetap tersimpan di database (Supabase schema `ailabs`), tapi
agent juga bisa **menulis file langsung ke folder lokal** (`workspace/` di
project, atau atur `LOCAL_WORKSPACE_PATH` di `.env`).

**Setiap project punya folder terpisah** di `workspace/`:

```bash
ailabs ask "Buat landing page" --project "Project A"
ailabs ask "Buat API python"   --project "Project B"
# → workspace/project-a/...  dan  workspace/project-b/...
```

- Folder ditentukan dari `--project` (mis. `Project A` → `project-a`).
- Tanpa `--project`, folder dibuat dari judul rencana Mark (slug), contoh
  `workspace/proyek-a/`.
- Dua project berbeda tidak akan saling menimpa file.

Cara kerja: saat agent diminta membuat file, dia mengeluarkan blok
```` ```file:path/relatif/nama.ext `` ``, lalu sistem menuliskannya ke
`workspace/<project>/`. Skill terkait: `write_file`, `read_file`, `list_files`,
`glob_files`, `grep_files`, `edit_file`, `code_exec` (path dipaksa tetap di
dalam workspace — path traversal ditolak).

## Ganti LLM Provider

Semua agent bicara lewat abstraksi `LLMClient` (`ailabs/llm/base.py`).
Ganti provider cukup dengan mengubah `LLM_PROVIDER` di `.env`:

```bash
# DeepSeek (OpenAI-compatible API)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...

# Proxy OpenAI-compatible (mis. 9router/kuroko lokal)
LLM_PROVIDER=openai_compat
OPENAI_COMPAT_BASE_URL=http://localhost:20128/v1
OPENAI_COMPAT_API_KEY=sk-...
OPENAI_COMPAT_MODEL=kr/auto

# Mock (tanpa API key, output deterministic — untuk demo/test)
LLM_PROVIDER=mock
```

Provider baru: buat file di `ailabs/llm/` + daftarkan satu cabang di `factory.py`.

## Catatan Desain

- **Orchestrator = state machine deterministik** — LLM hanya dipanggil saat planning (Mark), eksekusi tiap worker, review (Vera), dan sintesis.
- **Registry-based** — menambah agent/skill tidak menyentuh core.
- **Memory terpisah per fungsi**: structured (tabel `tasks`) vs narrative (markdown `documents`) vs semantic recall (pgvector, opsional).
- **Provider-agnostic LLM** — aman berpindah Gemini ↔ DeepSeek tanpa ubah kode agent.

## Testing

```bash
pip install -e ".[dev]"
pytest
```
