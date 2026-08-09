/* AI Labs Control Room — interaksi ringan (vanilla JS, tanpa build step). */
"use strict";

/* ---------------- toast ---------------- */
(function toast() {
  const el = document.getElementById("toast");
  const params = new URLSearchParams(location.search);
  const msg = params.get("toast");
  if (!el || !msg) return;
  el.textContent = msg;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 3600);
  history.replaceState(null, "", location.pathname + location.search.replace(/[?&]toast=[^&]*/, "").replace(/^\?$/, ""));
})();

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json().catch(() => ({}));
}

function showToast(msg, isError) {
  const el = document.getElementById("toast");
  if (!el) { alert(msg); return; }
  el.textContent = msg;
  el.className = "toast" + (isError ? " is-error" : "");
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 3600);
}

function fmtDT(iso) {
  if (!iso) return "—";
  const MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
  const day = iso.slice(8, 10);
  const month = parseInt(iso.slice(5, 7), 10);
  const time = iso.slice(11, 16);
  return `${day} ${MONTHS[month] || ""} ${time}`;
}

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

/* ---------------- markdown (subset, client) ---------------- */
function mdEscape(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function mdInline(s) {
  s = mdEscape(s);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}
function renderMd(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let inCode = false, codeBuf = [], listOpen = false;
  const closeList = () => { if (listOpen) { out.push("</ul>"); listOpen = false; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i], s = line.trim();
    if (inCode) {
      if (s.startsWith("```")) { out.push("<pre><code>" + mdEscape(codeBuf.join("\n")) + "</code></pre>"); codeBuf = []; inCode = false; }
      else codeBuf.push(line);
      continue;
    }
    if (/^```/.test(s)) { closeList(); codeBuf = []; inCode = true; continue; }
    if (!s) { closeList(); continue; }
    let m = s.match(/^(#{1,4})\s+(.*)$/);
    if (m) { closeList(); out.push(`<h${m[1].length}>${mdInline(m[2])}</h${m[1].length}>`); continue; }
    if (/^([-*_]){3,}\s*$/.test(s)) { closeList(); out.push("<hr>"); continue; }
    m = s.match(/^( {0,3})&gt; ?(.*)$/);
    if (m) { closeList(); out.push(`<blockquote>${mdInline(m[2])}</blockquote>`); continue; }
    m = s.match(/^ {0,3}([-*]|\d+[.)])\s+(.*)$/);
    if (m) {
      if (!listOpen) { out.push("<ul>"); listOpen = true; }
      out.push(`<li>${mdInline(m[2])}</li>`); continue;
    }
    closeList();
    let para = [s];
    while (i + 1 < lines.length && lines[i + 1].trim() && !/^```/.test(lines[i + 1].trim())) {
      para.push(lines[++i].trim());
    }
    out.push(`<p>${mdInline(para.join(" "))}</p>`);
  }
  closeList();
  if (inCode && codeBuf.length) out.push("<pre><code>" + mdEscape(codeBuf.join("\n")) + "</code></pre>");
  return out.join("\n");
}

/* ---------------- task graph ---------------- */
const TG_STATUS_COLOR = {
  done: "#5fcf8b", failed: "#ff6b66", running: "#f0b14b", in_progress: "#f0b14b",
  ready: "#c3f04b", pending: "#6f7a6e",
};

function buildGraph(root, tasks) {
  const byId = new Map(tasks.map(t => [t.id, t]));
  const layer = new Map();
  const assign = id => {
    if (layer.has(id)) return layer.get(id);
    const t = byId.get(id);
    let l = 0;
    (t.depends_on || []).forEach(d => { if (byId.has(d)) l = Math.max(l, assign(d) + 1); });
    layer.set(id, l);
    return l;
  };
  tasks.forEach(t => assign(t.id));

  const cols = new Map();
  tasks.forEach(t => {
    const l = layer.get(t.id);
    if (!cols.has(l)) cols.set(l, []);
    cols.get(l).push(t);
  });
  const sortedCols = [...cols.entries()].sort((a, b) => a[0] - b[0]);

  const nodeW = 190, nodeH = 58, gapX = 70, gapY = 22, pad = 24;
  const pos = new Map();
  sortedCols.forEach(([col, items], colIdx) => {
    const x = pad + colIdx * (nodeW + gapX);
    items.forEach((t, idx) => {
      pos.set(t.id, { x, y: pad + idx * (nodeH + gapY) });
    });
  });

  const width = pad * 2 + sortedCols.length * nodeW + (sortedCols.length - 1) * gapX;
  const height = pad * 2 + (Math.max(1, ...sortedCols.map(([, v]) => v.length))) * (nodeH + gapY);

  let svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  svg += `<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#6f7a6e"/></marker></defs>`;
  svg += `<g class="tg-edges">`;
  tasks.forEach(t => {
    const p = pos.get(t.id);
    (t.depends_on || []).forEach(d => {
      const dp = pos.get(d);
      if (!dp || !p) return;
      const edgeCls = "tg-edge" + (t.status === "done" ? " is-ok" : t.status === "failed" ? " is-bad" : "");
      const dx = dp.x + nodeW, dy = dp.y + nodeH / 2;
      svg += `<path class="${edgeCls}" marker-end="url(#arrow)" d="M${dx},${dy} L${p.x},${p.y + nodeH / 2}"/>`;
    });
  });
  svg += `</g><g class="tg-nodes">`;
  tasks.forEach(t => {
    const p = pos.get(t.id);
    const color = TG_STATUS_COLOR[t.status] || "#6f7a6e";
    const isActive = ["running", "in_progress", "ready"].includes(t.status);
    const retry = t.retry_count ? ` · retry ${t.retry_count}` : "";
    svg += `
      <g class="tg-node" data-tid="${t.id}" data-status="${t.status}" transform="translate(${p.x},${p.y})">
        <rect width="${nodeW}" height="${nodeH}" rx="9" fill="#11150f" stroke="${color}" stroke-width="1.6" ${isActive ? `class="is-active"` : ""}/>
        <text x="12" y="20" fill="#c3f04b" font-size="11">${t.agent_name}</text>
        <text x="12" y="37" fill="#9aa39a" font-size="10">${t.description.slice(0, 24)}</text>
        <text x="${nodeW - 12}" y="20" fill="${color}" font-size="10" text-anchor="end">${t.status}${retry}</text>
      </g>`;
  });
  svg += `</g></svg>`;
  return svg;
}

/* ---------------- job detail page ---------------- */
function jobDetailInit() {
  const host = document.getElementById("job-data");
  if (!host) return;
  let data = JSON.parse(host.textContent);
  const jobId = window.JOB_ID;
  const graphEl = document.getElementById("task-graph");
  const tasksEl = document.getElementById("tasks-table");
  const eventsEl = document.getElementById("events");
  const chip = document.getElementById("job-status-chip");
  const btnRun = document.getElementById("btn-run");
  const btnCancel = document.getElementById("btn-cancel");
  const btnDelete = document.getElementById("btn-delete");
  let eventCount = 0;
  let eventsRendered = false;
  let lastSig = "";
  let polling = false;
  let timer = null;

  const STATUS_LABELS = { pending: "Pending", planning: "Planning", running: "Running", in_progress: "In progress", done: "Done", failed: "Failed", ready: "Ready" };

  function statusChip(s) {
    const label = STATUS_LABELS[s] || s;
    return `<span class="chip chip-${s === "in_progress" ? "running" : s}">${label}</span>`;
  }

  function renderTasks() {
    if (!data.tasks.length) {
      tasksEl.innerHTML = `<div class="empty"><p>Belum ada task (planning berlangsung).</p></div>`;
      return;
    }
    let html = `<table class="table table-tasks"><colgroup><col><col style="width:110px"><col style="width:150px"><col style="width:70px"><col style="width:110px"><col style="width:64px"></colgroup><thead><tr><th>Task</th><th>Agent</th><th>Status</th><th>Retry</th><th>Dibuat</th><th></th></tr></thead><tbody>`;
    data.tasks.forEach(t => {
      html += `
        <tr data-tid="${t.id}">
          <td class="prompt-cell" title="${mdEscape(t.description)}">${t.description}</td>
          <td><code>${t.agent_name}</code></td>
          <td data-status-cell>${statusChip(t.status)}
            ${t.status === "failed" ? `<button class="btn btn-ghost btn-sm-retry" data-retry="${t.id}">retry</button>` : ""}
          </td>
          <td class="mono">${t.retry_count}</td>
          <td class="mono" title="${t.created_at || ""}">${fmtDT(t.created_at)}</td>
          <td><button class="btn btn-ghost btn-expand" data-tid="${t.id}">io ▾</button></td>
        </tr>
        <tr class="io-row" data-io="${t.id}" hidden><td colspan="6"><pre class="preview"></pre></td></tr>`;
    });
    html += `</tbody></table>`;
    tasksEl.innerHTML = html;

    tasksEl.querySelectorAll(".btn-expand").forEach(b => {
      b.addEventListener("click", async () => {
        const tid = b.dataset.tid;
        const row = tasksEl.querySelector(`[data-io="${tid}"]`);
        const pre = row.querySelector("pre");
        const t = (data.tasks || []).find(x => x.id === tid);
        if (!row.hidden && t && !t._ioFetched) {
          pre.textContent = "memuat…";
          try {
            const res = await fetch(`/api/tasks/${tid}`);
            const full = res.ok ? await res.json() : null;
            if (full) {
              t._ioFetched = true;
              t._io = { input: full.input, output: full.output };
              pre.textContent = JSON.stringify(t._io, null, 2);
            } else {
              pre.textContent = "gagal memuat detail task";
            }
          } catch { pre.textContent = "gagal memuat detail task"; }
        }
        row.hidden = !row.hidden;
        b.textContent = row.hidden ? "io ▾" : "io ▴";
      });
    });
    tasksEl.querySelectorAll(".btn-sm-retry").forEach(b => {
      b.addEventListener("click", async () => {
        try {
          await post(`/api/tasks/${b.dataset.retry}/retry`);
          await refresh();
        } catch (e) { showToast("Gagal retry: " + e.message, true); }
      });
    });
  }

  function renderEvents() {
    if (!data.events) return;
    eventsEl.innerHTML = data.events.slice().reverse().map(e =>
      `<div class="event"><span class="mono event-time">${(e.time || "").slice(11, 19)}</span><span class="event-msg">${mdEscape(e.msg)}</span></div>`
    ).join("") || `<div class="empty"><p>Belum ada event.</p></div>`;
    eventsRendered = true;
  }

  function renderNewEvents(events) {
    if (!eventsEl || !events.length) return;
    const empty = eventsEl.querySelector(".empty");
    if (empty) empty.remove();
    if (!eventsRendered) { data.events = events; renderEvents(); return; }
    events.forEach(e => {
      const div = document.createElement("div");
      div.className = "event";
      div.innerHTML = `<span class="mono event-time">${(e.time || "").slice(11, 19)}</span><span class="event-msg">${mdEscape(e.msg)}</span>`;
      eventsEl.prepend(div);
    });
    eventsEl.scrollTop = eventsEl.scrollHeight;
  }

  function updateGraphInPlace() {
    data.tasks.forEach(t => {
      const node = graphEl.querySelector(`.tg-node[data-tid="${t.id}"]`);
      if (!node) return;
      node.dataset.status = t.status;
      const color = TG_STATUS_COLOR[t.status] || "#6f7a6e";
      const rect = node.querySelector("rect");
      rect.setAttribute("stroke", color);
      const statusText = node.querySelector("text[text-anchor=end]");
      statusText.textContent = t.status + (t.retry_count ? ` · retry ${t.retry_count}` : "");
      statusText.setAttribute("fill", color);
      rect.classList.toggle("is-active", ["running", "in_progress", "ready"].includes(t.status));
    });
  }

  async function loadReport() {
    try {
      const res = await fetch(`/api/jobs/${jobId}/report`);
      if (!res.ok) return;
      const r = await res.json();
      const body = document.getElementById("report-body");
      if (body) body.innerHTML = r.html || '<div class="empty"><p>Belum ada laporan.</p></div>';
      const actions = document.getElementById("report-actions");
      if (actions) actions.hidden = !r.html;
      document.querySelectorAll(".js-export-report").forEach(b => { b.disabled = !r.html; });
    } catch { /* laporan opsional */ }
  }

  async function refresh() {
    if (polling) return;
    polling = true;
    let json;
    try {
      const res = await fetch(`/api/jobs/${jobId}/poll?since=${eventCount}`);
      if (res.status === 404) { location.href = "/"; return; }
      json = await res.json();
    } catch { return; }
    finally { polling = false; }
    const prevRunning = data.running;
    const prevStatus = data.job.status;

    // pertahankan input/output task dari snapshot awal (poll ringan tak memuatnya)
    const oldById = new Map((data.tasks || []).map(t => [t.id, t]));
    json.tasks = (json.tasks || []).map(t => {
      const old = oldById.get(t.id);
      return Object.assign(t, old ? { _ioFetched: old._ioFetched, _io: old._io } : {});
    });
    data = json;

    if (chip) {
      chip.className = `chip chip-${data.job.status}${data.running ? " is-live" : ""}`;
      chip.textContent = STATUS_LABELS[data.job.status] || data.job.status;
    }
    if (btnRun) btnRun.disabled = data.running || data.job.is_finished;
    if (btnCancel) btnCancel.disabled = !data.running;

    const sig = data.tasks.map(t => `${t.id}:${t.status}:${t.retry_count}`).join("|");
    if (sig !== lastSig) {
      lastSig = sig;
      if (graphEl.dataset.rendered) updateGraphInPlace(); else { graphEl.innerHTML = buildGraph(graphEl, data.tasks); graphEl.dataset.rendered = "1"; }
      renderTasks();
    }

    if (json.events) {
      eventCount = json.events.total || eventCount;
      renderNewEvents(json.events.events || []);
    }

    if (prevRunning && !data.running) {
      showToast(data.job.status === "failed" ? "Job berhenti" : "Eksekusi selesai");
      await loadReport();
      return;
    }
    if (data.running) {
      clearTimeout(timer);
      timer = setTimeout(() => refresh(), 3000);
    } else if (prevStatus === "done" && data.job.status === "failed") {
      loadReport();
    }
  }

  btnRun && btnRun.addEventListener("click", async () => {
    try { await post(`/api/jobs/${jobId}/run`); showToast("Eksekusi dimulai"); refresh(); }
    catch (e) { showToast(e.message, true); }
  });
  btnCancel && btnCancel.addEventListener("click", async () => {
    try { await post(`/api/jobs/${jobId}/cancel`); showToast("Job dibatalkan"); refresh(); }
    catch (e) { showToast(e.message, true); }
  });
  btnDelete && btnDelete.addEventListener("click", async () => {
    if (!confirm("Hapus job ini beserta task & dokumennya?")) return;
    try { await post(`/api/jobs/${jobId}/delete`); location.href = "/?toast=Job dihapus"; }
    catch (e) { showToast(e.message, true); }
  });

  async function exportReport() {
    try {
      const res = await fetch(`/api/jobs/${jobId}/report.md`);
      if (!res.ok) throw new Error("Laporan belum ada");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `job-${jobId.slice(0, 8)}-report.md`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { showToast(e.message, true); }
  }
  document.querySelectorAll(".js-export-report").forEach(b => b.addEventListener("click", exportReport));

  graphEl && graphEl.addEventListener("click", e => {
    const node = e.target.closest(".tg-node");
    if (!node) return;
    const row = tasksEl.querySelector(`tr[data-tid="${node.dataset.tid}"]`);
    if (row) { row.scrollIntoView({ behavior: "smooth", block: "center" }); row.style.outline = "1px solid var(--accent)"; setTimeout(() => row.style.outline = "", 1200); }
  });

  refresh();
}

/* ---------------- agents page ---------------- */
function agentsInit() {
  document.querySelectorAll("[data-prompt-btn]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const dlg = document.getElementById("prompt-dialog");
      const body = document.getElementById("prompt-body");
      try {
        const res = await fetch(`/system_prompt/${btn.dataset.promptBtn}`);
        body.textContent = await res.text();
        dlg.showModal();
      } catch (e) { showToast(e.message, true); }
    });
  });
  document.querySelectorAll("[data-toggle]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.toggle;
      try {
        const res = await post(`/api/agents/${name}/toggle`);
        showToast(`Agent ${name} sekarang ${res.enabled ? "aktif" : "nonaktif"} (berlaku saat restart)`);
        setTimeout(() => location.reload(), 900);
      } catch (e) { showToast(e.message, true); }
    });
  });
}

/* ---------------- workspace page ---------------- */
function workspaceInit() {
  const preview = document.getElementById("preview");
  if (!preview) return;
  document.querySelectorAll(".tree-file").forEach(el => {
    el.addEventListener("click", async () => {
      const path = el.dataset.path;
      const name = el.querySelector(".tree-name").textContent;
      try {
        const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(path)}`);
        if (!res.ok) throw new Error("Gagal membaca file");
        const text = await res.text();
        const isMd = /\.md$/i.test(name);
        const isBin = /\.(png|jpe?g|gif|pdf|zip|pyc)$/i.test(name);
        preview.classList.remove("empty");
        preview.innerHTML = `
          <div class="preview-file">
            <span class="mono">${mdEscape(path)}</span>
            <a class="btn" href="/api/workspace/download?path=${encodeURIComponent(path)}" download>Download</a>
          </div>
          ${isBin ? `<div class="empty">File biner — gunakan tombol download.</div>`
                  : `<pre><code>${isMd ? renderMd(text) : mdEscape(text)}</code></pre>`}`;
      } catch (e) {
        preview.classList.add("empty");
        preview.innerHTML = `<p>${mdEscape(e.message)}</p>`;
      }
    });
  });
}

/* ---------------- settings page ---------------- */
function settingsInit() {
  const testBtn = document.getElementById("btn-llm-test");
  const testResult = document.getElementById("llm-test-result");
  testBtn && testBtn.addEventListener("click", async () => {
    testResult.textContent = "mengetes…";
    try {
      const res = await post("/api/settings/llm-test");
      testResult.textContent = res.ok ? "OK — koneksi berhasil" : "Gagal: " + res.error;
      testResult.style.color = res.ok ? "var(--ok)" : "var(--bad)";
    } catch (e) { testResult.textContent = "Gagal: " + e.message; testResult.style.color = "var(--bad)"; }
  });

  const migrateBtn = document.getElementById("btn-migrate");
  const migrateResult = document.getElementById("migrate-result");
  migrateBtn && migrateBtn.addEventListener("click", async () => {
    if (!confirm("Salin semua data storage lokal ke Supabase? Data lokal tidak dihapus.")) return;
    migrateResult.textContent = "memigrasi…";
    try {
      const res = await post("/api/settings/migrate");
      if (res.ok) {
        const c = res.counts;
        migrateResult.textContent = c ? `Selesai: ${c.jobs} job, ${c.tasks} task, ${c.documents} dokumen. Restart pakai Supabase.` : res.message;
        migrateResult.style.color = "var(--ok)";
      } else {
        migrateResult.textContent = "Gagal: " + res.error;
        migrateResult.style.color = "var(--bad)";
      }
    } catch (e) { migrateResult.textContent = "Gagal: " + e.message; migrateResult.style.color = "var(--bad)"; }
  });

  const clearFailed = document.getElementById("btn-clear-failed");
  clearFailed && clearFailed.addEventListener("click", async () => {
    if (!confirm("Hapus semua job berstatus failed?")) return;
    try { const r = await post("/api/settings/clear-failed"); showToast(`${r.removed} job failed dihapus`); setTimeout(() => location.reload(), 800); }
    catch (e) { showToast(e.message, true); }
  });
  const clearAll = document.getElementById("btn-clear-all");
  clearAll && clearAll.addEventListener("click", async () => {
    if (!confirm("RESET TOTAL: hapus SEMUA job, task, dokumen? Aksi ini permanen.")) return;
    try { await post("/api/settings/clear"); showToast("Semua data dihapus"); setTimeout(() => location.reload(), 800); }
    catch (e) { showToast(e.message, true); }
  });
}

/* ---------------- logs page ---------------- */
function logsInit() {
  const stream = document.getElementById("event-stream");
  if (!stream) return;
  const job = window.LOGS_JOB || "";
  if (!job) return;
  let since = null; // null = poll pertama: baseline (jangan render ulang yg sudah server-render)
  let timer = null;
  const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
  async function poll() {
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(job)}/events?since=${since ?? 0}`);
      if (res.status === 404) { stop(); return; }
      const data = await res.json();
      if (since === null) {
        since = data.total;
        if (data.running === false) stop();
        return;
      }
      const fresh = data.events || [];
      since = data.total;
      if (fresh.length) {
        const prev = stream.querySelector(".empty");
        if (prev) prev.remove();
        fresh.slice().reverse().forEach(e => {
          const div = document.createElement("div");
          div.className = "event";
          div.innerHTML = `<span class="mono event-time">${(e.time || "").slice(11, 19)}</span><span class="event-msg">${mdEscape(e.msg)}</span>`;
          stream.prepend(div);
        });
        while (stream.children.length > 300) stream.lastElementChild.remove();
      }
      if (data.running === false) stop();
    } catch { /* polling diam-diam */ }
  }
  timer = setInterval(poll, 3000);
  poll();
}

/* ---------------- boot ---------------- */
/* ---------------- global dialog open/close ---------------- */
function dialogsInit() {
  document.querySelectorAll("[data-open]").forEach(btn => {
    btn.addEventListener("click", () => {
      const dlg = document.getElementById(btn.dataset.open);
      if (dlg) dlg.showModal();
    });
  });
  document.querySelectorAll("[data-close]").forEach(btn => {
    btn.addEventListener("click", () => {
      const dlg = btn.closest("dialog");
      if (dlg) dlg.close();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  dialogsInit();
  jobDetailInit();
  agentsInit();
  workspaceInit();
  settingsInit();
  logsInit();
});