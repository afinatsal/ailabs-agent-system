"""taste_design — pedoman "anti-slop" desain frontend untuk agent desain.

Sumber: taste-skill v2 oleh Leon Lin (https://www.tasteskill.dev/), disalin
ke `_taste/design-taste-frontend.md`. Skill ini membuka dokumen asli on-demand
sehingga agent (mis. dara) bisa mengikuti prinsip desain yang konsisten tanpa
menyandarkan selera pada default AI.

Default mengembalikan ringkasan "distilled" (aturan inti) supaya hemat token;
`part="full"` mengembalikan dokumen lengkap untuk konsultasi mendalam.
"""

from __future__ import annotations

from pathlib import Path

from ailabs.skills.base import Skill, SkillResult

_DOC = Path(__file__).parent / "_taste" / "design-taste-frontend.md"

# Ringkasan inti yang diadaptasi untuk output HTML/CSS vanilla (bukan
# React/Tailwind), diambil dari bagian 0-9 SKILL.md asli.
_DISTILLED = """## Pedoman Desain (taste-skill v2 — ringkasan)

### 0. Design Read
- Sebelum membuat apa pun, tentukan: jenis halaman, audiens, mood/vibe, dan
  arah desain. Tuliskan dalam satu kalimat: "Membaca ini sebagai: <jenis>
  untuk <audiens>, bahasa <vibe>, condong ke <sistem/aesthetic>."
- Jangan langsung jatuh ke default AI: gradient ungu, hero tengah di atas
  mesh gelap, tiga kartu fitur sejajar, glassmorphism di mana-mana, Inter +
  slate-900.

### 1. Tiga Dial (variance / motion / density)
- Skala 1-10. Default 8/6/4. Sesuaikan dengan brief: minimalis=5/3/2,
  premium=7/6/3, playful/agensi=9/8/3, trust/public=3/2/5.

### 2. Tipografi
- Sans sebagai default (Geist, Outfit, Satoshi, dsb), BUKAN Inter kecuali
  diminta. Serif HANYA bila brief benar-benar editorial/luxury.
- Headline rapat: tracking tighter, leading dekat. Body: max 65ch, leading
  relax.
- Jangan campur font keluarga berbeda untuk emphasis — pakai italic/bold
  dari font yang sama.

### 3. Warna
- Maks 1 warna aksen, saturasi < 80%. Netral: Zinc/Slate/Stone.
- Hindari "AI purple glow". Kalau brief memang minta ungu, tetap konsisten.
- SATU palet per halaman; aksen ter-lock di seluruh halaman.
- Untuk premium-consumer, JANGAN beige+brass+espresso (default AI) — pilih
  cold luxury, forest, black&tan, cobalt+cream, monochrome+pop.
- No pure #000 / #fff. Gunakan off-black / off-white.

### 4. Layout
- Anti-center bias: hero split/left-aligned bila variance > 4.
- Variasi layout per section — jangan ulang pola yang sama; max 2 section
  image+text split berturut-turut; max 1 marquee.
- Eyebrow (label kecil uppercase di atas headline): max 1 per 3 section.
- Bento grid: jumlah cell SESUAI jumlah konten, minimal 2-3 cell dengan
  visual nyata (bukan putih di atas putih).
- Jangan pakai tabel spec panjang dengan garis di tiap baris.
- Navigasi satu baris, tinggi nav maks 80px.

### 5. Hero
- Harus muat di viewport pertama: headline max 2 baris, subtext max 20 kata,
  CTA terlihat tanpa scroll.
- Top padding max ~6rem. Maks 4 elemen teks di hero (eyebrow, headline,
  subtext, CTA). Jangan taruh tagline/logos/social-proof di dalam hero.

### 6. Komponen
- CTA: label pendek (max 3 kata), satu baris, SATU label per intent di
  seluruh halaman (jangan "Get in touch" + "Contact us" sekaligus).
- Kontras tombol WCAG AA (4.5:1 body, 3:1 teks besar). Tombol putih+teks
  putih = dilarang.
- Form: label di ATAS input, error di bawah, placeholder bukan label.
- Satu skala border-radius per halaman (sharp / soft / pill) yang konsisten.

### 7. Motion & Aksesibilitas
- Animasi hanya bila "mengedukasi" (hierarchy/feedback/state) — bukan asal
  keren. Hormati prefers-reduced-motion.
- Skeleton loader (bukan spinner generik) untuk loading; empty & error state
  di-desain, bukan diabaikan.
- Dark mode: rancang dua-duanya sejak awal, kontras & hierarki setara.

### 8. Gambar & Konten
- Halaman harus punya visual nyata (foto/produk), bukan teks polos atau
  "fake screenshot" dari div.
- Logo wall: logo saja, tanpa label industri di bawah logo.
- Quote max 3 baris; jangan pakai em-dash sebagai ornamen.

### 9. Sebelum Selesai
- Audit: kontras setiap CTA/form, tidak ada teks yang wrap jelek, tidak ada
  layout section yang berulang, semua gambar punya tempat, copy tanpa typo.
"""


def load_taste(part: str = "distilled", **ctx) -> SkillResult:
    if part == "full":
        if not _DOC.exists():
            return SkillResult(ok=False, error=f"dokumen taste tidak ada: {_DOC}")
        return SkillResult(ok=True, value=_DOC.read_text(encoding="utf-8"))
    return SkillResult(ok=True, value=_DISTILLED)


SKILLS = [
    Skill(
        name="taste_design",
        description=(
            "Pedoman desain anti-slop untuk UI/landing page. Argumen: part "
            "('distilled' ringkas | 'full' dokumen lengkap). Wajib dibaca "
            "sebelum menghasilkan desain."
        ),
        fn=load_taste,
        tags=["design", "ui", "frontend"],
    )
]
