const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pill = (s) => `<span class="pill ${esc(s)}">${esc(s)}</span>`;
let token = localStorage.getItem("ft"), me = null, DEPTS = [], page = null;

async function api(url, opts = {}) {
  opts.headers = { ...(opts.headers || {}), ...(token ? { Authorization: "Bearer " + token } : {}) };
  const res = await fetch(url, opts);
  let d = {}; try { d = await res.json(); } catch (_) {}
  if (res.status === 401 && token) { logout(true); }
  if (!res.ok) { const err = new Error(typeof d.detail === "string" ? d.detail : "Request failed"); err.status = res.status; throw err; }
  return d;
}
const form = (obj) => { const f = new FormData(); Object.entries(obj).forEach(([k, v]) => f.append(k, v)); return f; };
function flash(text, bad = true, el = "#msg") { const b = $(el); b.hidden = !text; b.textContent = text || ""; b.style.cssText = bad ? "" : "background:var(--okbg);border-color:var(--ok);color:var(--ok)"; }
function beep() { try { const c = new AudioContext(), o = c.createOscillator(); o.frequency.value = 880; o.connect(c.destination); o.start(); setTimeout(() => { o.stop(); c.close(); }, 180); } catch (_) {} }

/* camera */
async function openCamera(v) {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera needs http://localhost or HTTPS.");
  const s = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720, facingMode: "user" }, audio: false });
  v.srcObject = s; await v.play(); v.parentElement.classList.add("live"); return s;
}
function closeCamera(v, s) { s?.getTracks().forEach((t) => t.stop()); if (v) { v.srcObject = null; v.parentElement.classList.remove("live"); } }
function frameBlob(v) {
  const k = Math.min(1, 960 / v.videoWidth), c = document.createElement("canvas");
  c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
  c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
  return new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
}

/* ---------- auth screen: face login + role based registration ---------- */
let regStream = null, shots = [], loginStream = null, loginTimer = null, loginBusy = false;
function showAuth(mode = "login") {
  $("#shell").hidden = true; $("#auth").hidden = false; flash("", true, "#banner");
  document.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x.dataset.m === mode));
  $("#loginPane").hidden = mode !== "login"; $("#regForm").hidden = mode !== "register";
  if (mode === "login") { stopReg(); startLogin(); } else stopLogin();
}
document.querySelectorAll(".seg button").forEach((b) => b.onclick = () => showAuth(b.dataset.m));

function loginStatus(text, cls = "already") { const r = $("#loginStatus"); r.hidden = !text; r.className = "result " + cls; r.innerHTML = `<div><b>${esc(text)}</b></div>`; }
function stopLogin() {
  clearTimeout(loginTimer); loginTimer = null; closeCamera($("#loginVideo"), loginStream); loginStream = null; loginBusy = false;
  $("#loginCam").textContent = "Start camera";
}
async function startLogin() {
  if (loginStream) return;
  try { loginStream = await openCamera($("#loginVideo")); } catch (e) { flash(e.message, true, "#banner"); return; }
  $("#loginCam").textContent = "Stop camera"; loginStatus("Looking for your face...", "already"); loginLoop();
}
async function loginLoop() {
  if (!loginStream) return;
  const v = $("#loginVideo");
  if (v.videoWidth && !loginBusy) {
    loginBusy = true;
    try {
      const d = await api("/api/face-login", { method: "POST", body: form({ image: await frameBlob(v) }) });
      if (!loginStream) return;               // camera was stopped while the request ran
      stopLogin(); return enter(d);
    } catch (e) {
      if (!loginStream) return;
      if (e.status === 403) { stopLogin(); return loginStatus(e.message, "bad"); }   // terminated account: stop trying
      loginStatus(e.message, e.status === 422 ? "already" : "bad");
    }
    loginBusy = false;
  }
  loginTimer = setTimeout(loginLoop, 1200);
}
$("#loginCam").onclick = () => loginStream ? (stopLogin(), loginStatus("")) : startLogin();

function stopReg() { closeCamera($("#regVideo"), regStream); regStream = null; $("#regCam").textContent = "Open camera"; $("#regShot").disabled = true; }
function drawShots() { $("#regSamples").innerHTML = shots.map((s) => `<div class="sample"><img src="${s.url}" alt=""></div>`).join(""); $("#regSubmit").disabled = !shots.length; }
// Fields depend on the role: employees pick a department, HR/admin enter the registration key instead.
function applyRole() {
  const emp = $("#regRole").value === "employee";
  $("#deptLabel").hidden = !emp; $("#regDept").disabled = !emp;
  $("#keyLabel").hidden = emp; $("#keyLabel input").required = !emp; $("#keyLabel input").disabled = emp;
}
$("#regRole").onchange = applyRole; applyRole();
$("#regCam").onclick = async () => {
  if (regStream) return stopReg();
  try { regStream = await openCamera($("#regVideo")); $("#regCam").textContent = "Close camera"; $("#regShot").disabled = false; } catch (e) { flash(e.message, true, "#banner"); }
};
$("#regShot").onclick = async () => { if (shots.length >= 3) return; const blob = await frameBlob($("#regVideo")); shots.push({ blob, url: URL.createObjectURL(blob) }); drawShots(); };
async function enter(d) { token = d.token; localStorage.setItem("ft", token); stopReg(); stopLogin(); shots = []; drawShots(); await boot(); }
$("#regForm").onsubmit = async (e) => {
  e.preventDefault(); const fd = new FormData(e.target); shots.forEach((s, i) => fd.append("images", s.blob, `f${i}.jpg`));
  $("#regSubmit").disabled = true;
  try { await enter(await api("/api/register", { method: "POST", body: fd })); } catch (x) { flash(x.message, true, "#banner"); $("#regSubmit").disabled = false; }
};
function logout(silent) {
  if (!silent) api("/api/logout", { method: "POST" }).catch(() => {});
  token = null; me = null; localStorage.removeItem("ft"); kioskStop(); showAuth("login");
}
$("#logout").onclick = () => logout();

/* ---------- shell: each role only sees its own pages ---------- */
const PAGES = {
  employee: [["attendance", "My attendance"], ["leaves", "Leave"], ["rules", "Company rules"]],
  hr: [["today", "Today"], ["camera", "Attendance camera"], ["offs", "Off announcements"], ["leaves", "Leave requests"], ["attendance", "My attendance"], ["rules", "Company rules"]],
  admin: [["today", "Overview"], ["staff", "Staff control"], ["leaves", "Leaves"], ["offs", "Off announcements"], ["rules", "Company rules"]],
};
async function boot() {
  try { const d = await api("/api/me"); me = d.user; me.warnings = d.warnings; me.offs = d.offs; me.today = d.today; } catch (_) { return logout(true); }
  $("#auth").hidden = true; $("#shell").hidden = false;
  $("#meImg").src = me.photo; $("#meName").textContent = me.name; $("#meRole").textContent = me.role + (me.role === "employee" ? " · " + me.department : "") + " · " + me.staff_code;
  $("#nav").innerHTML = PAGES[me.role].map(([k, l]) => `<button data-p="${k}">${l}</button>`).join("");
  $("#nav").querySelectorAll("button").forEach((b) => b.onclick = () => show(b.dataset.p));
  show(PAGES[me.role][0][0]);
}
function show(p) {
  page = p; flash("");
  $("#nav").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.p === p));
  ({ attendance, leaves, rules, today, offs, staff, camera }[p])();
}
const table = (heads, rows, empty = "Nothing here yet.") => rows.length
  ? `<div class="table-wrap"><table><thead><tr>${heads.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
  : `<p class="muted">${empty}</p>`;

/* ---------- pages ---------- */
/* ---------- HR attendance camera: stays on, marks everyone it recognises ---------- */
const kiosk = { stream: null, timer: null, busy: false, results: [], log: [], logged: new Set(), day: "", note: "Camera is off." };
const LABEL = { checkin: "Checked in", checkout: "Checked out", already: "Marked", late: "Late - no attendance", off: "Day off", leave: "On leave", blocked: "Terminated", unknown: "Unknown", skip: "" };
async function kioskStart() {
  if (kiosk.stream) return;
  kiosk.stream = await openCamera($("#kioskVideo"));
  kiosk.note = "Watching for faces..."; $("#camBadge").hidden = false; kioskLoop(); paintKiosk();
}
function kioskStop() {
  clearTimeout(kiosk.timer); kiosk.timer = null; closeCamera($("#kioskVideo"), kiosk.stream);
  kiosk.stream = null; kiosk.busy = false; kiosk.results = []; kiosk.note = "Camera is off."; $("#camBadge").hidden = true; paintKiosk();
}
async function kioskLoop() {
  if (!kiosk.stream) return;
  const v = $("#kioskVideo");
  if (v.videoWidth && !kiosk.busy) {
    kiosk.busy = true;
    try {
      const d = await api("/api/camera/scan", { method: "POST", body: form({ image: await frameBlob(v) }) });
      if (!kiosk.stream) return;
      kiosk.results = d.results; kiosk.note = d.results.length ? `${d.results.length} face(s) in view` : "Watching for faces...";
      kioskEvents(d.results);
    } catch (e) { if (!kiosk.stream) return; kiosk.results = []; kiosk.note = "Scan problem: " + e.message; }
    kiosk.busy = false; paintKiosk();
  }
  kiosk.timer = setTimeout(kioskLoop, 1000);
}
function kioskEvents(rs) {
  const day = new Date().toDateString();
  if (kiosk.day !== day) { kiosk.day = day; kiosk.logged.clear(); }
  let marked = false;
  rs.forEach((r) => {
    if (!["checkin", "checkout", "late", "off", "leave", "blocked"].includes(r.status)) return;
    const k = r.user_id + ":" + r.status; if (kiosk.logged.has(k)) return;   // log each person/event once a day
    kiosk.logged.add(k); kiosk.log.unshift({ ...r, at: new Date().toLocaleTimeString([], { hour12: false }) });
    if (r.status === "checkin" || r.status === "checkout") { beep(); marked = true; }
  });
  kiosk.log = kiosk.log.slice(0, 50);
  if (marked && page === "today") today();
}
function paintKiosk() {
  const box = $("#camBox"); if (!box) return;                       // camera page is not open
  const v = $("#camVideo");
  if (kiosk.stream && v.srcObject !== kiosk.stream) { v.srcObject = kiosk.stream; v.play().catch(() => {}); }
  v.parentElement.classList.toggle("live", !!kiosk.stream);
  $("#kStart").disabled = !!kiosk.stream; $("#kStop").disabled = !kiosk.stream;
  $("#kStatus").textContent = kiosk.note;
  const w = box.width = v.clientWidth, h = box.height = v.clientHeight, g = box.getContext("2d"); g.clearRect(0, 0, w, h);
  if (kiosk.stream && v.videoWidth) {
    // the video is shown mirrored and cropped to fill its frame (object-fit: cover), so map the boxes the same way
    const k = Math.max(w / v.videoWidth, h / v.videoHeight), dw = v.videoWidth * k, dh = v.videoHeight * k, ox = (w - dw) / 2, oy = (h - dh) / 2;
    kiosk.results.forEach((r) => {
      const [bx, by, bw, bh] = r.box, x = w - (ox + (bx + bw) * dw), y = oy + by * dh, ok = ["checkin", "checkout", "already"].includes(r.status);
      g.lineWidth = 3; g.strokeStyle = ok ? "#2ecc71" : r.status === "unknown" ? "#e74c3c" : "#f0b429"; g.strokeRect(x, y, bw * dw, bh * dh);
      const label = [r.name, LABEL[r.status]].filter(Boolean).join(" · "); g.font = "600 14px system-ui"; const tw = g.measureText(label).width + 12;
      g.fillStyle = g.strokeStyle; g.fillRect(x, Math.max(0, y - 24), tw, 24); g.fillStyle = "#111"; g.fillText(label, x + 6, Math.max(0, y - 24) + 17);
    });
  }
  $("#kLog").innerHTML = kiosk.log.length ? table(["Time", "Name", "Code", "Department", "Event"], kiosk.log.map((r) => [r.at, esc(r.name), esc(r.staff_code), esc(r.department), r.status === "checkin" || r.status === "checkout" ? `${LABEL[r.status]} ${esc(r.time)}` : esc(r.message || LABEL[r.status])])) : `<p class="muted">Nobody recognised yet.</p>`;
}
function camera() {
  $("#view").innerHTML = `<div class="stack"><h2>Attendance camera</h2><div class="card">
    <div class="clock" id="clock"></div>
    <p class="muted">Only HR can start or stop this camera. While it is on, anyone who appears in front of it is marked automatically: check-in until 09:15, check-out from 16:45. Keep this tab open; it keeps running while you use the other pages.</p>
    <div class="video-wrap"><video id="camVideo" playsinline muted></video><canvas id="camBox" class="overlay"></canvas><div class="video-idle"><svg class="ic big"><use href="#i-camera"/></svg><p>Camera is off</p></div></div>
    <div class="row"><button class="btn primary" id="kStart">Start camera</button><button class="btn danger" id="kStop">Stop camera</button></div>
    <div class="result already" id="kStatus"></div></div>
    <div class="card"><h3>Recognised today</h3><div id="kLog"></div></div></div>`;
  const tick = () => { const c = $("#clock"); if (c && page === "camera") { c.textContent = new Date().toLocaleTimeString([], { hour12: false }); setTimeout(tick, 1000); } }; tick();
  $("#kStart").onclick = async () => { try { await kioskStart(); } catch (e) { flash(e.message); } };
  $("#kStop").onclick = kioskStop;
  paintKiosk();
}

/* ---------- employee / HR own pages ---------- */
async function attendance() {
  const [d, m] = await Promise.all([api("/api/my-attendance"), api("/api/me")]); me.today = m.today; me.warnings = m.warnings; me.offs = m.offs;
  const t = me.today, state = t.off ? esc(t.off) : t.on_leave ? "On approved leave" : t.check_in ? "Present" : "Not marked yet";
  $("#view").innerHTML = `<div class="stack"><h2>My attendance</h2>
  <div class="card"><h3>Today</h3><div class="stat-row"><div class="stat"><b>${state}</b><span>Status</span></div><div class="stat"><b>${t.check_in || "--"}</b><span>Checked in</span></div><div class="stat"><b>${t.check_out || "--"}</b><span>Checked out</span></div></div>
  <p class="muted">Attendance is marked automatically when the office camera sees you. Check-in closes at 09:15.</p>
  ${me.warnings.length ? `<h3>Warnings</h3>` + me.warnings.map((w) => `<div class="banner">${esc(w.reason)} <small>${esc(w.created_at.slice(0, 10))}</small></div>`).join("") : ""}
  ${me.offs.length ? `<h3>Upcoming offs</h3>` + me.offs.map((o) => `<p class="muted">${esc(o.day)} · ${esc(o.title)} (${esc(o.department)})</p>`).join("") : ""}</div>
  <div class="card">${table(["Date", "Check-in", "Check-out"], d.records.map((r) => [r.day, r.check_in, r.check_out || "--"]), "No attendance yet.")}</div></div>`;
}
async function rules() {
  const d = await api("/api/rules");
  $("#view").innerHTML = `<h2>Company rules</h2><div class="grid two"><div class="card"><h3>Timings</h3><p>Check-in: until <b>${d.checkin_last}</b> (later = no attendance)</p><p>Check-out: from <b>${d.checkout_from}</b></p><p>Weekly off: <b>${d.weekly_off}</b></p>
  <h3>Yearly holidays</h3>${table(["Date", "Holiday"], d.holidays.map((h) => [h.date, esc(h.name)]))}<p class="muted">${esc(d.note)}</p></div>
  <div class="card"><h3>Leave policy</h3><ul>${d.leave_rules.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>`;
}
async function leaves() {
  const d = await api("/api/leaves"), canApply = me.role !== "admin", canDecide = me.role !== "employee";
  const row = (l) => [esc(l.name) + (l.role !== "employee" ? " (HR)" : ""), esc(l.department), esc(l.title), esc(l.reason), `${l.from_day} → ${l.to_day}`, pill(l.status) + (l.decided_name ? `<br><small>${esc(l.decided_name)}</small>` : ""),
    canDecide && l.status === "pending" && l.user_id !== me.id ? `<div class="actions"><button class="btn" data-d="approved" data-id="${l.id}">Approve</button><button class="btn danger" data-d="rejected" data-id="${l.id}">Reject</button></div>` : ""];
  $("#view").innerHTML = `<div class="stack"><h2>${canDecide ? "Leave requests" : "Leaves"}</h2>
  ${canApply ? `<div class="card"><h3>Apply for leave</h3><form id="leaveForm"><label>Title<input name="title" required maxlength="120" placeholder="e.g. Family function"></label><label>Reason<textarea name="reason" required maxlength="1000"></textarea></label>
  <div class="row wrap"><label>From<input type="date" name="from_day" required></label><label>To<input type="date" name="to_day" required></label></div><button class="btn primary">Send to ${me.role === "hr" ? "admin" : "HR"}</button></form></div>` : ""}
  <div class="card">${table(["Name", "Department", "Title", "Reason", "Dates", "Status", ""], d.leaves.map(row), "No leave requests.")}</div></div>`;
  $("#leaveForm")?.addEventListener("submit", async (e) => { e.preventDefault(); try { await api("/api/leaves", { method: "POST", body: new FormData(e.target) }); flash("Leave request sent.", false); leaves(); } catch (x) { flash(x.message); } });
  document.querySelectorAll("[data-d]").forEach((b) => b.onclick = async () => { try { await api(`/api/leaves/${b.dataset.id}/decide`, { method: "POST", body: form({ decision: b.dataset.d }) }); leaves(); } catch (x) { flash(x.message); } });
}
async function today() {
  const d = await api("/api/today"), c = (s) => d.rows.filter((r) => r.status === s).length;
  $("#view").innerHTML = `<div class="stack"><h2>${me.role === "admin" ? "Overview" : "Today"} · ${d.day}</h2>
  <div class="stat-row">${["Present", "Not yet", "Absent", "On leave", "Off"].map((s) => `<div class="stat"><b>${c(s)}</b><span>${s}</span></div>`).join("")}</div>
  <div class="card">${table(["", "Name", "Role", "Department", "Check-in", "Check-out", "Status"], d.rows.map((r) => [`<img src="${r.photo}" width="32" height="32" style="border-radius:50%">`, esc(r.name), r.role, esc(r.department), r.check_in || "--", r.check_out || "--", pill(r.status)]))}</div></div>`;
}
async function offs() {
  const [o, dp] = await Promise.all([api("/api/offs"), api("/api/departments")]);
  $("#view").innerHTML = `<div class="stack"><h2>Off announcements</h2><div class="card"><form id="offForm"><div class="row wrap"><label>Date<input type="date" name="day" required></label>
  <label>Department<select name="department"><option>All</option>${dp.departments.map((x) => `<option>${esc(x)}</option>`).join("")}</select></label></div>
  <label>Title<input name="title" required placeholder="e.g. Eid holiday"></label><button class="btn primary">Announce off</button></form></div>
  <div class="card">${table(["Date", "Department", "Title", "By", ""], o.offs.map((x) => [x.day, esc(x.department), esc(x.title), esc(x.by || ""), `<button class="btn danger" data-del="${x.id}">Remove</button>`]))}</div></div>`;
  $("#offForm").onsubmit = async (e) => { e.preventDefault(); try { await api("/api/offs", { method: "POST", body: new FormData(e.target) }); offs(); } catch (x) { flash(x.message); } };
  document.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => { await api("/api/offs/" + b.dataset.del, { method: "DELETE" }); offs(); });
}
async function staff() {
  const d = await api("/api/users");
  $("#view").innerHTML = `<h2>Staff control</h2><div class="card">${table(["", "Name", "Role", "Department", "Status", "Warnings", "Leave decisions", "Actions"], d.users.map((u) => [`<img src="${u.photo}" width="32" height="32" style="border-radius:50%">`, esc(u.name) + `<br><small>${esc(u.staff_code)}</small>`, u.role, esc(u.department), pill(u.status), u.warnings, u.role === "hr" ? u.decisions : "--",
    `<div class="actions"><button class="btn" data-a="warn" data-id="${u.id}">Warn</button>${u.status === "fired" ? "" : `<button class="btn danger" data-a="fire" data-id="${u.id}">Fire</button>`}${u.status !== "active" ? `<button class="btn" data-a="retain" data-id="${u.id}">Retain</button>` : ""}</div>`]))}</div>`;
  document.querySelectorAll("[data-a]").forEach((b) => b.onclick = async () => {
    const a = b.dataset.a; let reason = "";
    if (a === "warn") { reason = prompt("Reason for the warning:"); if (!reason) return; }
    if (a === "fire" && !confirm("Fire this person? They will lose access immediately.")) return;
    try { await api(`/api/users/${b.dataset.id}/action`, { method: "POST", body: form({ action: a, reason }) }); staff(); } catch (x) { flash(x.message); }
  });
}

/* ---------- init ---------- */
(async () => {
  try { const h = await api("/api/health"); if (!h.models_ready) flash("Face models are missing. Run: python download_models.py", true, "#banner"); } catch (_) {}
  try { const d = await api("/api/departments"); DEPTS = d.departments; $("#regDept").innerHTML = DEPTS.map((x) => `<option>${esc(x)}</option>`).join(""); } catch (_) {}
  if (token) await boot(); else showAuth("login");
})();
