-- ============================================================
-- AI Labs — Supabase / PostgreSQL schema
-- SEMUA objek ditaruh di schema khusus `ailabs`, TERPISAH dari
-- tabel user di schema `public`. Jalankan di Supabase SQL editor.
-- ============================================================

-- 0. Schema khusus AI Labs
create schema if not exists ailabs;

-- Pastikan objek di bawah masuk ke schema ailabs
set search_path to ailabs, public;

-- Beri akses ke role PostgREST (dipakai anon/authenticated/service_role key)
grant usage on schema ailabs to anon, authenticated, service_role;
alter default privileges in schema ailabs
    grant all on tables to anon, authenticated, service_role;
alter default privileges in schema ailabs
    grant all on functions to anon, authenticated, service_role;

-- ============================================================
-- 1. JOBS — satu row per misi/prompt dari user
-- ============================================================
create table if not exists jobs (
    id            uuid primary key default gen_random_uuid(),
    user_prompt   text not null,
    project       text,                     -- slug folder project (workspace/<project>/)
    status        text not null default 'pending',
                  -- pending | planning | running | done | failed
    created_by    text,
    final_report  text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- Idempoten: tambahkan kolom jika tabel sudah pernah dibuat sebelumnya
alter table jobs add column if not exists project text;

-- ============================================================
-- 2. TASKS — sub-task hasil breakdown CEO (Mark)
-- ============================================================
create table if not exists tasks (
    id            uuid primary key default gen_random_uuid(),
    job_id        uuid not null references jobs(id) on delete cascade,
    description   text not null,
    agent_name    text not null,           -- 'rita' | 'dev' | 'wren' | 'vera'
    status        text not null default 'pending',
                  -- pending | ready | in_progress | done | failed
    depends_on    uuid[] default '{}',     -- array of tasks.id (DAG sederhana)
    input         jsonb default '{}',
    output        jsonb,
    error         text,
    retry_count   int not null default 0,
    review_count  int not null default 0,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists idx_tasks_job_id on tasks(job_id);
create index if not exists idx_tasks_status on tasks(status);

-- ============================================================
-- 3. DOCUMENTS — plan naratif (markdown) + embedding untuk retrieval
-- CATATAN: di Supabase, ekstensi vector berada di schema `extensions`,
-- jadi tipe & operator-nya harus di-qualify sebagai `extensions.vector`.
-- ============================================================
create extension if not exists vector with schema extensions;

create table if not exists documents (
    id            uuid primary key default gen_random_uuid(),
    job_id        uuid references jobs(id) on delete cascade,
    task_id       uuid references tasks(id) on delete set null,
    title         text,
    content       text not null,               -- markdown mentah
    doc_type      text not null default 'plan', -- plan | report | note | log
    agent         text,
    metadata      jsonb default '{}',
    embedding     extensions.vector(768),      -- dimensi multilingual-e5-base
    synced_to_obsidian boolean default false,
    created_at    timestamptz not null default now()
);

create index if not exists idx_documents_embedding on documents
    using ivfflat (embedding extensions.vector_cosine_ops) with (lists = 100);

-- ============================================================
-- 4. AGENT_REGISTRY — opsional, daftar agent dinamis via DB
-- ============================================================
create table if not exists agent_registry (
    agent_name    text primary key,
    role          text,
    description   text,
    model         text not null default 'gemini-2.5-flash',
    system_prompt text not null,
    is_active     boolean default true,
    created_at    timestamptz not null default now()
);

-- ============================================================
-- Helper: semantic search via pgvector (dipakai kalau embedding aktif)
-- `SET search_path` membuat fungsi mandiri dari schema pemanggil.
-- ============================================================
create or replace function match_documents (
    query_embedding extensions.vector(768),
    match_count     int default 5,
    filter_job_id   uuid default null
)
returns table (
    id        uuid,
    job_id    uuid,
    title     text,
    content   text,
    doc_type  text,
    similarity real
)
language plpgsql
set search_path = ailabs
as $$
begin
    return query
    select
        d.id,
        d.job_id,
        d.title,
        d.content,
        d.doc_type,
        1 - (d.embedding <=> query_embedding) as similarity
    from ailabs.documents d
    where
        (d.embedding is not null)
        and (filter_job_id is null or d.job_id = filter_job_id)
    order by d.embedding <=> query_embedding
    limit match_count;
end;
$$;

-- ============================================================
-- 5. Expose schema ke PostgREST (supaya API bisa akses `ailabs`)
-- Setara dengan: Settings > API > Exposed schemas > tambahkan `ailabs`
-- ============================================================
do $$
begin
    alter role authenticator set pgrst.db_schemas = 'public, graphql_public, ailabs';
    notify pgrst, 'reload config';
    raise notice 'Schema ailabs ditambahkan ke pgrst.db_schemas.';
exception when others then
    raise notice 'Gagal set pgrst.db_schemas otomatis. Lakukan manual: Settings > API > Exposed schemas -> tambahkan ailabs (format: public, graphql_public, ailabs).';
end $$;

-- Kembalikan search_path default
reset search_path;

-- ============================================================
-- 6. RLS (opsional, HANYA kalau pakai SUPABASE_PUBLISHABLE_KEY)
-- Aplikasi ini memakai SUPABASE_SECRET_KEY (bypass RLS), jadi RLS
-- tidak wajib. Kalau nanti ganti ke publishable key, aktifkan ini.
-- ============================================================
-- alter table jobs enable row level security;
-- alter table tasks enable row level security;
-- alter table documents enable row level security;
-- create policy "all access" on jobs for all using (true) with check (true);
-- create policy "all access" on tasks for all using (true) with check (true);
-- create policy "all access" on documents for all using (true) with check (true);
