/* 高架车辆智能识别系统 - 前端逻辑 */
"use strict";

var $ = function (s) { return document.querySelector(s); };
var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function api(path, opts) {
  return fetch(path, opts).then(function (r) {
    if (r.status === 401) {
      window.location.href = "/login";
      throw new Error("登录已过期");
    }
    return r.json().catch(function () { return null; }).then(function (d) {
      if (!r.ok || (d && d.success === false)) {
        throw new Error((d && (d.error || d.message)) || ("请求失败（" + r.status + "）"));
      }
      return d;
    });
  });
}

function toast(msg, type) {
  var t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  t.className = "toast show " + (type || "");
  clearTimeout(t._tm);
  t._tm = setTimeout(function () { t.className = "toast"; }, 3200);
}

/* ---------- 顶部信息 ---------- */
var currentUserRole = "";

function loadInfo() {
  api("/api/info").then(function (d) {
    currentUserRole = (d.user && d.user.role) || "";
    $("#chip-detector").textContent = "检测：" + (d.detector_mode === "yolo" ? "YOLOv8 真实推理" : "模拟模式");
    $("#detect-mode-label").textContent = d.detector_mode === "yolo" ? "YOLOv8n · 实时推理" : "模拟检测模式";
    var statsTab = document.querySelector('.tab[data-tab="stats"]');
    if (statsTab) statsTab.hidden = currentUserRole !== "admin";
    var mineTab = document.querySelector('.tab[data-tab="mine"]');
    if (mineTab) mineTab.hidden = currentUserRole !== "user";
    var usersTab = document.querySelector('.tab[data-tab="users"]');
    if (usersTab) usersTab.hidden = currentUserRole !== "admin";
    if (currentUserRole !== "admin") {
      var statsPage = $("#page-stats");
      if (statsPage && !statsPage.hidden) {
        document.querySelector('.tab[data-tab="detect"]').click();
      }
      var usersPage = $("#page-users");
      if (usersPage && !usersPage.hidden) {
        document.querySelector('.tab[data-tab="detect"]').click();
      }
    }
    if (currentUserRole !== "user") {
      var minePage = $("#page-mine");
      if (minePage && !minePage.hidden) {
        document.querySelector('.tab[data-tab="detect"]').click();
      }
    }
  }).catch(function () {});
}

setInterval(function () {
  var el = $("#chip-clock");
  if (el) el.textContent = new Date().toLocaleString("zh-CN", { hour12: false });
}, 1000);

/* ---------- 退出 ---------- */
function goLogin() {
  try { sessionStorage.removeItem("evs_auth"); } catch (e) { }
  window.location.href = "/login";
}

/* ---------- 个人中心 ---------- */
function openProfile() {
  $("#profile-mask").hidden = false;
  var name = ($("#user-name").textContent || "").trim() || "管理员";
  $("#profile-avatar").textContent = name.slice(0, 1);
  $("#pf-name").textContent = name;
  api("/api/info").then(function (d) {
    var u = d.user || {};
    $("#pf-username").textContent = u.username || "--";
    $("#pf-role").textContent = u.role === "admin" ? "管理员" : (u.role === "user" ? "普通用户" : (u.role || "--"));
    $("#pf-phone").textContent = u.phone || "未绑定";
    $("#pf-email").textContent = u.email || "未绑定";
    $("#pf-detector").textContent = d.detector_mode === "yolo" ? "YOLOv8 真实推理" : "模拟模式";
    $("#pf-plate").textContent = d.plate_mode === "hyperlpr3" ? "HyperLPR3 真实识别"
      : (d.plate_mode === "unavailable" ? "不可用（模拟）" : (d.plate_mode || "--"));
    $("#pf-sms").textContent = d.sms_mode === "simulated" ? "模拟发送" : (d.sms_mode || "--");
    $("#pf-speed").textContent = d.speed_limit ? d.speed_limit + " km/h" : "--";
  }).catch(function (e) { toast(e.message, "err"); });
}

function closeProfile() { $("#profile-mask").hidden = true; }

$("#btn-profile").addEventListener("click", openProfile);
$("#btn-profile-close").addEventListener("click", closeProfile);
$("#btn-profile-cancel").addEventListener("click", closeProfile);
$("#profile-mask").addEventListener("click", function (e) {
  if (e.target === this) closeProfile();
});
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape" && !$("#profile-mask").hidden) closeProfile();
});

$("#btn-profile-logout").addEventListener("click", function () {
  api("/api/logout", { method: "POST" }).then(goLogin).catch(goLogin);
});

/* ---------- Tab 切换 ---------- */
$$(".tab").forEach(function (btn) {
  btn.addEventListener("click", function () {
    if (btn.dataset.tab === "stats" && currentUserRole !== "admin") {
      toast("仅管理员可以使用数据统计功能", "warn");
      return;
    }
    if (btn.dataset.tab === "users" && currentUserRole !== "admin") {
      toast("仅管理员可以使用用户管理功能", "warn");
      return;
    }
    $$(".tab").forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
    var id = "page-" + btn.dataset.tab;
    $$(".page").forEach(function (p) { p.hidden = p.id !== id; });
    if (btn.dataset.tab === "records") loadRecords();
    if (btn.dataset.tab === "stats") loadStats();
    if (btn.dataset.tab === "mine") loadMine();
    if (btn.dataset.tab === "users") loadUsers();
  });
});

/* ---------- 图片/视频模式切换 ---------- */
$$(".mode-btn").forEach(function (btn) {
  btn.addEventListener("click", function () {
    $$(".mode-btn").forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
    $("#mode-image").hidden = btn.dataset.mode !== "image";
    $("#mode-video").hidden = btn.dataset.mode !== "video";
  });
});

/* ---------- 图片识别 ---------- */
var selectedFile = null;
var dz = $("#dropzone");

dz.addEventListener("click", function () { $("#file-input").click(); });
$("#file-input").addEventListener("change", function (e) {
  if (e.target.files && e.target.files[0]) setFile(e.target.files[0]);
});
["dragover", "dragenter"].forEach(function (ev) {
  dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("drag"); });
});
["dragleave", "drop"].forEach(function (ev) {
  dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("drag"); });
});
dz.addEventListener("drop", function (e) {
  var f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (f && f.type.indexOf("image/") === 0) setFile(f);
});

function setFile(f) {
  selectedFile = f;
  var img = $("#dz-preview");
  img.src = URL.createObjectURL(f);
  img.hidden = false;
  $("#dz-icon").hidden = true;
  $("#dz-text").textContent = f.name + "（点击可重新选择）";
}

$("#btn-detect").addEventListener("click", function () {
  if (!selectedFile) { toast("请先选择一张监控图片", "warn"); return; }
  var btn = $("#btn-detect");
  btn.disabled = true;
  btn.textContent = "识别中…";
  var fd = new FormData();
  fd.append("image", selectedFile);
  api("/api/detect", { method: "POST", body: fd })
    .then(function (d) {
      renderDetect(d);
      toast(d.summary.total ? "识别完成" : "未检测到车辆或行人", "ok");
    })
    .catch(function (e) { toast(e.message, "err"); })
    .then(function () {
      btn.disabled = false;
      btn.textContent = "开始识别";
    });
});

function renderDetect(d) {
  $("#detect-empty").hidden = true;
  $("#detect-result").hidden = false;
  $("#detect-mode-label").textContent = d.detector_mode === "yolo" ? "YOLOv8n · 实时推理" : "模拟检测模式";

  var img = $("#annotated-img");
  if (d.annotated_image) {
    img.src = d.annotated_image + "?t=" + Date.now();
    img.hidden = false;
  } else {
    img.hidden = true;
  }

  if (!d.detections.length) {
    $("#summary-chips").innerHTML = '<span class="chip">未检测到车辆或行人</span>';
    $("#result-cards").innerHTML = "";
    return;
  }

  $("#summary-chips").innerHTML =
    '<span class="chip">识别目标 <strong>' + d.summary.total + "</strong></span>" +
    '<span class="chip ok">允许通行 <strong>' + d.summary.allowed + "</strong></span>" +
    '<span class="chip bad">违规 <strong>' + d.summary.violations + "</strong></span>";

  $("#result-cards").innerHTML = d.detections.map(function (r) {
    return '<div class="result-card ' + (r.allowed ? "" : "bad") + '">' +
      '<div class="rc-head"><span class="rc-type">' + esc(r.vehicle_type) + "</span>" +
      '<span class="badge ' + (r.allowed ? "badge-green" : "badge-red") + '">' +
      (r.allowed ? "允许上高架" : "禁止上高架") + "</span></div>" +
      '<div class="rc-row"><span>车牌</span><b>' + (esc(r.plate_no) || "未识别") + "</b></div>" +
      '<div class="rc-row"><span>车主</span><b>' + esc(r.owner_name) +
      (r.owner_phone ? "（" + esc(r.owner_phone) + "）" : "") + "</b></div>" +
      '<div class="rc-row"><span>检测置信度</span><b>' + (r.confidence * 100).toFixed(0) + "%</b></div>" +
      (r.plate_no ? '<div class="rc-row"><span>车牌置信度</span><b>' + (r.plate_confidence * 100).toFixed(0) + "%</b></div>" : "") +
      '<div class="rc-row"><span>违规项</span><b class="' + (r.violation ? "t-bad" : "") + '">' +
      (r.violation ? esc(r.violation) : "无") + "</b></div>" +
      "</div>";
  }).join("");
}

/* ---------- 用户管理（管理员） ---------- */
var editingUserId = 0;

function loadUsers() {
  api("/api/admin/users").then(function (d) {
    var users = d.users || [];
    $("#users-hint").textContent = "共 " + users.length + " 位注册用户";
    if (!users.length) {
      $("#users-tbody").innerHTML = '<tr><td colspan="6" class="empty-cell">暂无注册用户</td></tr>';
      return;
    }
    $("#users-tbody").innerHTML = users.map(function (u) {
      return "<tr><td><b>" + esc(u.username) + "</b></td>" +
        "<td>" + esc(u.name) + "</td>" +
        "<td>" + (esc(u.phone) || "—") + "</td>" +
        "<td>" + (esc(u.email) || "—") + "</td>" +
        "<td>" + (u.plates.length ? u.plates.map(esc).join("、") : "—") + "</td>" +
        '<td><div class="user-ops">' +
          '<button class="btn btn-ghost btn-sm btn-edit-user" data-id="' + u.id + '">编辑</button>' +
          '<button class="btn btn-ghost btn-sm btn-reset-pwd" data-id="' + u.id + '">重置密码</button>' +
          '<button class="btn-del-record btn-del-user" data-id="' + u.id + '">删除</button>' +
        "</div></td>" +
        "</tr>";
    }).join("");
    $$(".btn-edit-user").forEach(function (b) {
      b.addEventListener("click", function () {
        var u = users.filter(function (x) { return x.id === +b.dataset.id; })[0];
        if (u) openUserEdit(u);
      });
    });
    $$(".btn-reset-pwd").forEach(function (b) {
      b.addEventListener("click", function () {
        var u = users.filter(function (x) { return x.id === +b.dataset.id; })[0];
        if (!u) return;
        var pwd = prompt("请输入 " + u.username + " 的新密码（至少 6 位）");
        if (pwd === null) return;
        pwd = pwd.trim();
        if (pwd.length < 6) { toast("密码至少 6 位", "warn"); return; }
        api("/api/admin/users/" + u.id + "/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: u.phone || "", email: u.email || "", password: pwd })
        }).then(function () { toast("密码已重置", "ok"); })
          .catch(function (e) { toast(e.message, "err"); });
      });
    });
    $$(".btn-del-user").forEach(function (b) {
      b.addEventListener("click", function () {
        var u = users.filter(function (x) { return x.id === +b.dataset.id; })[0];
        if (!u) return;
        if (!confirm("确定删除用户 " + u.username + " 吗？该用户的绑定车牌也会一并删除，且不可恢复。")) return;
        api("/api/admin/users/" + u.id, { method: "DELETE" })
          .then(function (d) { toast(d.message || "已删除", "ok"); loadUsers(); })
          .catch(function (e) { toast(e.message, "err"); });
      });
    });
  }).catch(function (e) { toast(e.message, "err"); });
}

function openUserEdit(u) {
  editingUserId = u.id;
  $("#eu-avatar").textContent = (u.name || u.username || "用").slice(0, 1);
  $("#eu-sub").textContent = "账号：" + u.username;
  $("#eu-phone").value = u.phone || "";
  $("#eu-email").value = u.email || "";
  $("#eu-password").value = "";
  $("#user-mask").hidden = false;
}

function closeUserEdit() { $("#user-mask").hidden = true; editingUserId = 0; }

$("#eu-cancel").addEventListener("click", closeUserEdit);
$("#user-mask").addEventListener("click", function (e) { if (e.target === this) closeUserEdit(); });
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape" && !$("#user-mask").hidden) closeUserEdit();
});
$("#eu-save").addEventListener("click", function () {
  if (!editingUserId) return;
  var btn = $("#eu-save");
  btn.disabled = true;
  api("/api/admin/users/" + editingUserId + "/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone: $("#eu-phone").value.trim(),
      email: $("#eu-email").value.trim(),
      password: $("#eu-password").value.trim()
    })
  }).then(function (d) {
    toast(d.message || "已保存", "ok");
    closeUserEdit();
    loadUsers();
  }).catch(function (e) { toast(e.message, "err"); })
    .then(function () { btn.disabled = false; });
});
$("#btn-refresh-users").addEventListener("click", loadUsers);

/* ---------- 我的记录（普通用户） ---------- */
function loadMine() {
  api("/api/my/profile").then(function (p) {
    $("#my-phone").value = p.phone || "";
    $("#my-email").value = p.email || "";
    renderPlates(p.plates || []);
  }).catch(function (e) { toast(e.message, "err"); });
  loadMyViolations();
}

function renderPlates(plates) {
  var box = $("#my-plates");
  if (!plates.length) {
    box.innerHTML = '<span class="hint">暂未绑定车牌</span>';
    return;
  }
  box.innerHTML = plates.map(function (p) {
    return '<span class="plate-chip">' + esc(p) +
      '<button type="button" class="plate-x" data-plate="' + esc(p) + '" title="解绑">×</button></span>';
  }).join("");
  $$("#my-plates .plate-x").forEach(function (b) {
    b.addEventListener("click", function () {
      if (!confirm("确定解绑车牌 " + b.dataset.plate + " 吗？")) return;
      api("/api/my/plates/" + encodeURIComponent(b.dataset.plate), { method: "DELETE" })
        .then(function () { toast("已解绑", "ok"); loadMine(); })
        .catch(function (e) { toast(e.message, "err"); });
    });
  });
}

function loadMyViolations() {
  api("/api/my/violations").then(function (d) {
    $("#mine-hint").textContent = d.plates.length ? "已绑定 " + d.plates.length + " 块车牌" : "请先绑定车牌";
    if (!d.plates.length) {
      $("#mine-summary").innerHTML = "";
      $("#mine-list").innerHTML = '<div class="stats-empty">请先在左侧绑定车牌</div>';
      return;
    }
    $("#mine-summary").innerHTML =
      '<span class="chip">违章记录 <strong>' + d.violations.length + "</strong></span>" +
      '<span class="chip bad">合计罚款 <strong>¥' + d.total_fine + "</strong></span>" +
      (d.cooling_count ? '<span class="chip">冷却中免罚 <strong>' + d.cooling_count + "</strong></span>" : "");
    if (!d.violations.length) {
      $("#mine-list").innerHTML = '<div class="stats-empty">暂无违章记录</div>';
      return;
    }
    $("#mine-list").innerHTML = d.violations.map(function (v) {
      var img = v.image
        ? '<img class="vio-thumb" src="' + esc(v.image) + '" alt="违章照片">'
        : '<div class="vio-thumb vio-noimg">无照片</div>';
      var fine = v.cooling
        ? '<div class="vio-fine cooling">冷却中<span>24 小时内重复违规，本次免罚</span></div>'
        : '<div class="vio-fine">¥' + v.fine + "</div>";
      return '<div class="vio-item">' + img +
        '<div class="vio-info">' +
          '<div class="vio-head"><b>' + esc(v.plate_no) + "</b>" +
          '<span class="badge badge-red">' + esc(v.violation) + "</span></div>" +
          '<div class="vio-meta">' + esc(v.created_at) + " · " + (v.source === "video" ? "视频识别" : "图片识别") + "</div>" +
        "</div>" + fine + "</div>";
    }).join("");
  }).catch(function (e) { toast(e.message, "err"); });
}

$("#btn-save-contact").addEventListener("click", function () {
  api("/api/my/contact", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: $("#my-phone").value.trim(), email: $("#my-email").value.trim() })
  }).then(function (d) { toast(d.message || "已保存", "ok"); })
    .catch(function (e) { toast(e.message, "err"); });
});

$("#btn-add-plate").addEventListener("click", function () {
  var plate = $("#my-plate").value.trim();
  if (!plate) { toast("请输入车牌号", "warn"); return; }
  api("/api/my/plates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plate_no: plate })
  }).then(function () {
    $("#my-plate").value = "";
    toast("绑定成功", "ok");
    loadMine();
  }).catch(function (e) { toast(e.message, "err"); });
});

/* ---------- 视频识别 ---------- */
var videoFile = null;
var pollTimer = null;
var vdz = $("#video-dropzone");

vdz.addEventListener("click", function () { $("#video-input").click(); });
$("#video-input").addEventListener("change", function (e) {
  if (e.target.files && e.target.files[0]) setVideo(e.target.files[0]);
});
["dragover", "dragenter"].forEach(function (ev) {
  vdz.addEventListener(ev, function (e) { e.preventDefault(); vdz.classList.add("drag"); });
});
["dragleave", "drop"].forEach(function (ev) {
  vdz.addEventListener(ev, function (e) { e.preventDefault(); vdz.classList.remove("drag"); });
});
vdz.addEventListener("drop", function (e) {
  var f = e.dataTransfer.files && e.dataTransfer.files[0];
  if (f && f.type.indexOf("video/") === 0) setVideo(f);
});

function setVideo(f) {
  videoFile = f;
  var v = $("#video-preview");
  v.src = URL.createObjectURL(f);
  v.hidden = false;
  $("#video-dz-icon").hidden = true;
  $("#video-dz-text").textContent = f.name + "（" + (f.size / 1024 / 1024).toFixed(1) + " MB）";
}

$("#btn-video").addEventListener("click", function () {
  if (!videoFile) { toast("请先选择一个监控视频", "warn"); return; }
  var btn = $("#btn-video");
  btn.disabled = true;
  btn.textContent = "上传中…";
  $("#video-progress").hidden = false;
  $("#video-bar").style.width = "2%";
  $("#video-progress-text").textContent = "正在上传视频…";

  var fd = new FormData();
  fd.append("video", videoFile);
  api("/api/detect_video", { method: "POST", body: fd })
    .then(function (d) {
      btn.textContent = "识别中…";
      pollJob(d.job_id, btn);
    })
    .catch(function (e) {
      toast(e.message, "err");
      btn.disabled = false;
      btn.textContent = "开始识别视频";
      $("#video-progress").hidden = true;
    });
});

function pollJob(jobId, btn) {
  clearInterval(pollTimer);
  pollTimer = setInterval(function () {
    api("/api/video_status/" + jobId).then(function (job) {
      $("#video-bar").style.width = Math.max(2, job.progress) + "%";
      $("#video-progress-text").textContent = job.message || "处理中…";
      if (job.status === "done") {
        clearInterval(pollTimer);
        $("#video-bar").style.width = "100%";
        $("#video-progress-text").textContent = "识别完成";
        renderVideo(job.result);
        toast("视频识别完成", "ok");
        btn.disabled = false;
        btn.textContent = "开始识别视频";
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        $("#video-progress-text").textContent = job.error || "识别失败";
        toast(job.error || "视频识别失败", "err");
        btn.disabled = false;
        btn.textContent = "开始识别视频";
      }
    }).catch(function (e) {
      clearInterval(pollTimer);
      toast(e.message, "err");
      btn.disabled = false;
      btn.textContent = "开始识别视频";
    });
  }, 1200);
}

function renderVideo(res) {
  $("#video-empty").hidden = true;
  $("#video-result").hidden = false;

  var info = res.video_info || {};
  $("#video-meta").textContent = "时长 " + (info.duration || 0) + "s · 处理 " + (info.processed || 0) +
    " 帧 · 耗时 " + (res.elapsed || 0) + "s";

  var v = $("#annotated-video");
  v.src = res.video_url + "?t=" + Date.now();
  v.load();

  $("#video-summary").innerHTML =
    '<span class="chip">识别车辆 <strong>' + res.summary.vehicles + "</strong></span>" +
    '<span class="chip ok">允许通行 <strong>' + res.summary.allowed + "</strong></span>" +
    '<span class="chip bad">违规 <strong>' + res.summary.violations + "</strong></span>" +
    (info.truncated ? '<span class="chip">仅处理前 60 秒</span>' : "");

  $("#video-tbody").innerHTML = (res.tracks || []).map(function (r) {
    return "<tr class=\"" + (r.violation ? "row-bad" : "") + "\">" +
      "<td><b>" + (esc(r.plate_no) || "未识别") + "</b></td>" +
      "<td>" + esc(r.vehicle_type) + "</td>" +
      "<td>" + (r.allowed ? '<span class="badge badge-green">允许上高架</span>'
        : '<span class="badge badge-red">禁止上高架</span>') + "</td>" +
      "<td>" + esc(r.owner_name) + (r.owner_phone ? "<br><span class=\"hint\">" + esc(r.owner_phone) + "</span>" : "") + "</td>" +
      '<td class="' + (r.violation ? "t-bad" : "") + '">' + (r.violation ? esc(r.violation) : "—") + "</td>" +
      '<td class="td-mono">' + r.first_seen + "s – " + r.last_seen + "s</td></tr>";
  }).join("") || '<tr><td colspan="6" class="td-empty">未识别到有效车辆</td></tr>';
}

/* ---------- 识别记录 ---------- */
var recordFilter = "all";

$$(".seg-btn").forEach(function (btn) {
  btn.addEventListener("click", function () {
    $$(".seg-btn").forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
    recordFilter = btn.dataset.filter;
    loadRecords();
  });
});

var recordOrder = "desc";

function loadRecords() {
  var params = [];
  if (recordFilter === "violation") params.push("violation=1");
  else if (recordFilter === "image" || recordFilter === "video") params.push("source=" + recordFilter);
  var d = $("#records-date");
  var recDate = d ? d.value : "";
  if (recDate) params.push("date=" + recDate);
  params.push("order=" + recordOrder);
  var qs = params.length ? "?" + params.join("&") : "";

  api("/api/records" + qs).then(function (list) {
    var isAdmin = currentUserRole === "admin";
    var th = $("#th-action");
    if (th) th.hidden = !isAdmin;
    $("#records-count").textContent = "共 " + list.length + " 条";
    $("#records-tbody").innerHTML = list.map(function (r) {
      var thumb = r.image
        ? '<a href="/static/uploads/' + esc(r.image) + '" target="_blank"><img class="thumb" src="/static/uploads/' + esc(r.image) + '" alt=""></a>'
        : "—";
      var state = r.violation
        ? '<span class="badge badge-red">违规通行</span>'
        : '<span class="badge badge-green">正常通行</span>';
      return '<tr class="' + (r.violation ? "row-bad" : "") + '">' +
        '<td class="td-mono">' + esc(r.created_at) + "</td>" +
        "<td>" + thumb + "</td>" +
        "<td><b>" + (esc(r.plate_no) || "未识别") + "</b></td>" +
        "<td>" + esc(r.vehicle_type) + "</td>" +
        "<td>" + esc(r.owner_name || "未登记") + "</td>" +
        '<td><span class="badge badge-gray">' + (r.source === "video" ? "视频" : "图片") + "</span></td>" +
        '<td class="' + (r.violation ? "t-bad" : "") + '">' + (r.violation ? esc(r.violation) : "—") + "</td>" +
        "<td>" + state + "</td>" +
        (isAdmin ? '<td><button type="button" class="btn-del-record" data-id="' + r.id + '">删除</button></td>' : "") +
        "</tr>";
    }).join("") || '<tr><td colspan="' + (isAdmin ? 9 : 8) + '" class="td-empty">暂无识别记录</td></tr>';
  }).catch(function (e) { toast(e.message, "err"); });
}

$("#records-tbody").addEventListener("click", function (e) {
  var btn = e.target.closest(".btn-del-record");
  if (!btn) return;
  if (!window.confirm("确定删除这条识别记录吗？删除后不可恢复。")) return;
  api("/api/records/" + btn.dataset.id, { method: "DELETE" })
    .then(function () { toast("记录已删除", "ok"); loadRecords(); })
    .catch(function (e2) { toast(e2.message, "err"); });
});

$("#btn-refresh-records").addEventListener("click", loadRecords);
$("#records-date").addEventListener("change", loadRecords);
$("#btn-order").addEventListener("click", function () {
  recordOrder = recordOrder === "desc" ? "asc" : "desc";
  this.textContent = recordOrder === "desc" ? "时间：新→旧" : "时间：旧→新";
  loadRecords();
});

/* ---------- 数据统计 ---------- */
var PIE_COLORS = ["#2563eb", "#ef4444", "#f59e0b", "#10b981", "#8b5cf6", "#ec4899"];
var typeColorMap = {};

function todayStr() {
  var d = new Date();
  return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
}

function pad2(n) { return ("0" + n).slice(-2); }

function hourLabel(h) {
  return pad2(h) + ":00 – " + (h + 1 === 24 ? "24:00" : pad2(h + 1) + ":00");
}

function statCard(label, value, unit, tone) {
  return '<div class="stat-card ' + (tone || "") + '">' +
    '<span class="stat-label">' + label + '</span>' +
    '<div class="stat-value">' + value +
    (unit ? '<small>' + unit + '</small>' : "") + '</div></div>';
}

var STATS_REFRESH_SEC = 60;
var statsLeft = STATS_REFRESH_SEC;

function loadStats() {
  statsLeft = STATS_REFRESH_SEC;
  var day = $("#stats-date").value || todayStr();
  api("/api/stats/day?date=" + encodeURIComponent(day)).then(function (d) {
    renderStats(d);
  }).catch(function (e) { toast(e.message, "err"); });
}

function renderStats(d) {
  var total = d.total || 0;
  var peak = d.peak_hours || [];
  var hourly = d.hourly || [];

  $("#stats-cards").innerHTML =
    statCard("当日识别总数", total, "次") +
    statCard("允许通行", d.allowed || 0, "次", "ok") +
    statCard("违规记录", d.violations || 0, "次", "bad") +
    statCard("违规高峰时段", peak.length ? hourLabel(peak[0].hour) : "—", "", "time");

  var types = d.types || [];
  types.forEach(function (t, i) { typeColorMap[t.type] = PIE_COLORS[i % PIE_COLORS.length]; });
  var typed = types.reduce(function (s, t) { return s + t.count; }, 0);
  $("#stats-pie-hint").textContent = d.date + " · 共 " + total + " 次识别";
  renderPie(types, typed);

  if (!peak.length) {
    $("#stats-peak").innerHTML = '<div class="stats-empty">该日期暂无违规记录，暂无违规高峰时段</div>';
  } else {
    var peakMax = peak[0].count || 1;
    $("#stats-peak").innerHTML = peak.map(function (p, i) {
      return '<div class="peak-row' + (i === 0 ? " top" : "") + '">' +
        '<span class="peak-rank">' + (i + 1) + '</span>' +
        '<span class="peak-time">' + hourLabel(p.hour) + '</span>' +
        '<span class="peak-bar"><i style="width:' + Math.round(p.count / peakMax * 100) + '%"></i></span>' +
        '<span class="peak-count">' + p.count + ' 次</span></div>';
    }).join("");
  }

  var maxHour = Math.max.apply(null, hourly.length ? hourly : [0]);
  var peakSet = {};
  peak.forEach(function (p) { peakSet[p.hour] = true; });
  $("#stats-hourly").innerHTML = hourly.map(function (n, h) {
    var barH = maxHour && n ? Math.max(3, Math.round(n / maxHour * 80)) : 0;
    return '<div class="hour-col' + (peakSet[h] ? " peak" : "") + '" data-h="' + h + '" title="' + pad2(h) + ':00 · ' + n + ' 次">' +
      '<span class="hour-bar" style="height:' + barH + 'px"></span>' +
      '<span class="hour-label">' + pad2(h) + '</span></div>';
  }).join("");

  var selHour = $("#stats-hour").value;
  if (selHour !== "") {
    var selCol = document.querySelector('#stats-hourly .hour-col[data-h="' + selHour + '"]');
    if (selCol) selCol.classList.add("sel");
    loadHourStats(+selHour);
  }
  $$("#stats-hourly .hour-col").forEach(function (c) {
    c.addEventListener("click", function () {
      $$("#stats-hourly .hour-col").forEach(function (x) { x.classList.remove("sel"); });
      c.classList.add("sel");
      $("#stats-hour").value = c.dataset.h;
      loadHourStats(+c.dataset.h);
    });
  });
}

function loadHourStats(hour) {
  var day = $("#stats-date").value || todayStr();
  api("/api/stats/hour?date=" + encodeURIComponent(day) + "&hour=" + hour)
    .then(renderHourStats)
    .catch(function (e) { toast(e.message, "err"); });
}

function renderMiniPie(types, total) {
  var c = 64, r = 56, angle = 0, parts = "";
  types.forEach(function (t) {
    var color = typeColorMap[t.type] || "#999999";
    var sweep = t.count / total * 360;
    if (sweep >= 359.99) {
      parts += '<circle cx="' + c + '" cy="' + c + '" r="' + r + '" fill="' + color + '"/>';
      return;
    }
    var a1 = (angle - 90) * Math.PI / 180;
    var a2 = (angle + sweep - 90) * Math.PI / 180;
    var x1 = c + r * Math.cos(a1), y1 = c + r * Math.sin(a1);
    var x2 = c + r * Math.cos(a2), y2 = c + r * Math.sin(a2);
    parts += '<path d="M' + c + "," + c + " L" + x1.toFixed(2) + "," + y1.toFixed(2) +
      " A" + r + "," + r + " 0 " + (sweep > 180 ? 1 : 0) + " 1 " + x2.toFixed(2) + "," + y2.toFixed(2) +
      ' Z" fill="' + color + '"/>';
    angle += sweep;
  });
  return '<svg viewBox="0 0 128 128" class="hour-pie-svg">' + parts + "</svg>";
}

function renderHourStats(d) {
  var body = $("#stats-hour-body");
  if (!d.total) {
    body.innerHTML = '<div class="stats-empty">' + hourLabel(d.hour) + ' 暂无识别记录</div>';
    return;
  }
  var rows = d.types.map(function (t) {
    var color = typeColorMap[t.type] || "#999999";
    return '<div class="hour-row"><span class="hour-dot" style="background:' + color + '"></span>' +
      '<span class="hour-type" style="color:' + color + '">' + esc(t.type) + "</span>" +
      '<span class="hour-count">' + t.count + " 次</span>" +
      '<span class="hour-allow">允许 ' + t.allowed_count + " / 违规 " + (t.count - t.allowed_count) + "</span></div>";
  }).join("");
  body.innerHTML =
    '<div class="hour-sum">' + hourLabel(d.hour) + " 共识别 <b>" + d.total + "</b> 次 · 允许 <b>" + d.allowed + "</b> · 违规 <b>" + d.violations + "</b></div>" +
    '<div class="hour-detail-flex">' +
      '<div class="hour-pie">' + renderMiniPie(d.types, d.total) + "</div>" +
      '<div class="hour-rows">' + rows + "</div>" +
    "</div>";
}

(function () {
  var sel = $("#stats-hour");
  for (var h = 0; h < 24; h++) {
    var o = document.createElement("option");
    o.value = h;
    o.textContent = hourLabel(h);
    sel.appendChild(o);
  }
  sel.addEventListener("change", function () {
    $$("#stats-hourly .hour-col").forEach(function (x) { x.classList.remove("sel"); });
    if (sel.value === "") return;
    var col = document.querySelector('#stats-hourly .hour-col[data-h="' + sel.value + '"]');
    if (col) col.classList.add("sel");
    loadHourStats(+sel.value);
  });
})();

function renderPie(types, total) {
  var el = $("#stats-pie");
  var legend = $("#stats-legend");
  if (!total || !types.length) {
    el.innerHTML = '<div class="stats-empty">该日期暂无识别记录</div>';
    legend.innerHTML = "";
    return;
  }

  var size = 240, cx = 120, cy = 120, r = 92;
  var parts = "";
  var lg = "";
  var angle = 0;

  types.forEach(function (t, i) {
    var sweep = t.count / total * 360;
    var color = PIE_COLORS[i % PIE_COLORS.length];
    if (sweep >= 359.99) {
      parts += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="' + color + '"/>';
    } else if (sweep > 0) {
      var a0 = (angle - 90) * Math.PI / 180;
      var a1 = (angle + sweep - 90) * Math.PI / 180;
      parts += '<path d="M' + cx + ' ' + cy +
        ' L' + (cx + r * Math.cos(a0)).toFixed(2) + ' ' + (cy + r * Math.sin(a0)).toFixed(2) +
        ' A' + r + ' ' + r + ' 0 ' + (sweep > 180 ? 1 : 0) + ' 1 ' +
        (cx + r * Math.cos(a1)).toFixed(2) + ' ' + (cy + r * Math.sin(a1)).toFixed(2) +
        ' Z" fill="' + color + '"/>';
    }
    angle += sweep;
    lg += '<div class="legend-row">' +
      '<span class="legend-dot" style="background:' + color + '"></span>' +
      '<span class="legend-name">' + esc(t.type) + '</span>' +
      '<span class="legend-count">' + t.count + ' 次</span>' +
      '<span class="legend-pct">' + (t.count / total * 100).toFixed(1) + '%</span></div>';
  });

  el.innerHTML = '<svg viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="各类型车辆占比饼图">' +
    parts + '<circle cx="' + cx + '" cy="' + cy + '" r="42" fill="rgba(255,255,255,.9)"/></svg>' +
    '<div class="pie-center"><b>' + total + '</b><span>识别目标</span></div>';
  legend.innerHTML = lg;
}

$("#stats-date").value = todayStr();
$("#stats-date").addEventListener("change", loadStats);
$("#btn-refresh-stats").addEventListener("click", loadStats);

/* 跨天时自动切换到新的一天（数据按自然日重置） */
var lastStatsDay = todayStr();
setInterval(function () {
  var now = todayStr();
  if (now === lastStatsDay) return;
  var dateEl = $("#stats-date");
  if (dateEl.value === lastStatsDay) dateEl.value = now;
  lastStatsDay = now;
  if (!$("#page-stats").hidden) loadStats();
}, 30000);

/* 刷新倒计时：停留在统计页时每 60 秒自动刷新一次 */
function tickStatsCountdown() {
  var el = $("#stats-countdown");
  if (!el) return;
  if ($("#page-stats").hidden) {
    statsLeft = STATS_REFRESH_SEC;
    el.textContent = "每 " + STATS_REFRESH_SEC + " 秒自动刷新";
    return;
  }
  if (statsLeft <= 0) {
    loadStats();
    el.textContent = STATS_REFRESH_SEC + " 秒后自动刷新";
    return;
  }
  el.textContent = statsLeft + " 秒后自动刷新";
  statsLeft -= 1;
}
setInterval(tickStatsCountdown, 1000);

/* ---------- 初始化 ---------- */
loadInfo();
