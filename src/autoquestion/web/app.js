"use strict";

const $ = (id) => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
const loopback = location.hostname === "127.0.0.1";
let token = loopback
  ? fragment.get("session") || sessionStorage.getItem("aq-session")
  : "";
if (token && loopback) {
  sessionStorage.setItem("aq-session", token);
  history.replaceState(null, "", location.pathname);
}
const preview =
  !token && (!loopback || location.pathname.includes("/preview/"));
const locked = !token && !preview;
const appDownload =
  "https://github.com/billstar0128-jpg/AutoQuestion/releases/download/v0.3.0/AutoQuestion-0.3.0-Windows-x64.zip";
let providers = [];
let state = {
  config: null,
  active: false,
  status: "STOPPED",
  history: [],
  events: [],
  route: "",
};
let pollTimer, toastTimer, pairTimer;
let pending = false;
let selectedResult = 0;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 5000);
}
function view(name) {
  if (!["workspace", "settings", "guide"].includes(name)) return;
  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.id !== `view-${name}`;
  });
  document.querySelectorAll(".nav-link").forEach((button) => {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  $("page-label").textContent = {
    workspace: "答题工作台",
    settings: "模型与配置",
    guide: "开始使用",
  }[name];
}
document
  .querySelectorAll("[data-view]")
  .forEach((button) =>
    button.addEventListener("click", () => view(button.dataset.view)),
  );
document.querySelector(".brand").addEventListener("click", (event) => {
  event.preventDefault();
  view("workspace");
});

async function api(path, body) {
  const headers = { "X-AutoQuestion-Token": token };
  const options = { headers, cache: "no-store" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.method = "POST";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "本机操作未完成。");
  return result;
}
async function action(fn) {
  if (pending) return;
  pending = true;
  try {
    await fn();
  } catch (error) {
    toast(error.message || "无法连接本机程序，请重新双击启动入口。");
  } finally {
    pending = false;
  }
}
function selectedProvider() {
  return providers.find((provider) => provider.id === $("provider").value);
}
function examples(reset = false) {
  const provider = selectedProvider();
  if (!provider) return;
  const offline = provider.id === "offline_demo";
  $("api-fields").hidden = offline;
  $("base-url").required = $("model").required = !offline && !preview;
  $("offline-note").hidden = !offline;
  $("example-provider").textContent = offline
    ? "无需配置，直接体验"
    : `拿 ${provider.name.split(" / ")[0]} 举个例子`;
  $("example-url").textContent =
    provider.base_url || "http://127.0.0.1:8000/v1";
  $("use-url").disabled = offline || state.active;
  $("example-models").replaceChildren();
  $("model-options").replaceChildren();
  provider.models.forEach((model) => {
    const chip = node("button", "", model);
    chip.type = "button";
    chip.disabled = state.active;
    chip.addEventListener("click", () => {
      $("model").value = model;
      $("model").focus();
    });
    $("example-models").append(chip);
    const option = node("option");
    option.value = model;
    $("model-options").append(option);
  });
  if (!provider.models.length)
    $("example-models").append(
      node(
        "span",
        "field-help",
        offline ? "固定离线示例" : "请填写服务商提供的模型 ID",
      ),
    );
  $("vision-notes").textContent = offline
    ? provider.notes
    : provider.vision_notes;
  $("provider-docs").hidden = !provider.docs_url;
  $("provider-docs").href = provider.docs_url || "#";
  if (reset) {
    $("base-url").value = provider.base_url;
    $("model").value = "";
    $("vision").checked = false;
    $("api-key").value = "";
    $("mode").value = "auto";
    $("key-help").textContent = "Key 不进入普通配置文件、答题记录或 GitHub。";
  }
}
$("provider").addEventListener("change", () => examples(true));
$("use-url").addEventListener("click", () => {
  $("base-url").value = $("example-url").textContent;
  $("base-url").focus();
});
$("toggle-key").addEventListener("click", () => {
  const visible = $("api-key").type === "password";
  $("api-key").type = visible ? "text" : "password";
  $("toggle-key").textContent = visible ? "隐藏" : "显示";
  $("toggle-key").setAttribute("aria-pressed", String(visible));
  $("toggle-key").setAttribute(
    "aria-label",
    visible ? "隐藏 API Key" : "显示 API Key",
  );
});
function fillSettings(config) {
  if (config) {
    $("provider").value = config.provider_profile;
    $("base-url").value = config.base_url;
    $("model").value = config.model;
    $("vision").checked = config.supports_vision;
    $("mode").value = config.input_mode;
    $("request-timeout").value = config.timeout_seconds ?? 180;
    $("storage").value =
      config.credential_mode === "session" ? "session" : "stored";
    $("key-help").textContent = config.has_key
      ? "已配置；留空保留同一地址的安全凭据。更换地址或保存方式时请重新输入。"
      : "请填写本次 API Key。不会显示或回传保存的 Key。";
  } else {
    $("provider").value = "deepseek";
    $("base-url").value = selectedProvider()?.base_url || "";
  }
  $("setup-heading").textContent = config
    ? "模型配置"
    : "欢迎使用，先连接一个模型";
  examples();
}
function answerLabel(answer) {
  if (answer.question_type === "multiple_choice") {
    return answer.selected_texts
      .map((text, index) =>
        answer.selected_labels[index]
          ? `${answer.selected_labels[index]} · ${text}`
          : text,
      )
      .join("、");
  }
  return answer.selected_label
    ? `${answer.selected_label} · ${answer.selected_text}`
    : answer.selected_text;
}
function showResult(result) {
  $("empty-result").hidden = !!result;
  $("answer-result").hidden = !result;
  if (!result) {
    $("result-source").textContent = "等待输入";
    return;
  }
  const batch = result.batch_total > 1
    ? state.history.filter((item) => item.batch_id === result.batch_id)
    : [];
  $("batch-results").replaceChildren();
  $("batch-results").hidden = !batch.length;
  if (batch.length) {
    $("batch-results").append(node("h3", "batch-heading", `同屏识别 · ${result.batch_total} 道题`));
    batch.forEach((item) => {
      const card = node("button", "batch-result-card");
      card.type = "button";
      card.setAttribute("aria-pressed", String(item === result));
      card.append(
        node("span", "batch-question", `第 ${item.batch_index} 题 · ${item.question.question_text}`),
        node("strong", "batch-answer", answerLabel(item.answer)),
        node("span", "batch-reason", item.answer.short_reason),
      );
      card.addEventListener("click", () => {
        selectedResult = state.history.indexOf(item);
        showResult(item);
      });
      $("batch-results").append(card);
    });
  }
  const { question, answer } = result;
  $("question-text").textContent = question.question_text;
  $("result-source").textContent =
    question.source_type === "MANUAL"
      ? result.offline
        ? "离线预置 Demo"
        : "固定文本 Demo"
      : `${question.source_type} 输入`;
  $("question-options").replaceChildren();
  const indices = answer.selected_indices.length
    ? answer.selected_indices
    : [answer.selected_index];
  question.options.forEach((option) => {
    const row = node(
      "div",
      `question-option${indices.includes(option.index) ? " selected" : ""}`,
    );
    row.append(
      node("span", "option-label", option.label || "·"),
      node("span", "option-text", option.text),
    );
    $("question-options").append(row);
  });
  $("answer-text").textContent = answerLabel(answer);
  $("answer-reason").textContent = answer.short_reason;
  $("answer-confidence").textContent =
    `模型给出的置信度 ${Math.round(answer.confidence * 100)}% · 不代表实际正确率`;
}
function render() {
  const config = state.config;
  const offline =
    (state.active_protocol || config?.protocol_provider) === "fake";
  const label =
    {
      STOPPED: "尚未启动",
      STARTING: "正在启动",
      READY: "READY · 等待 F8",
      ROUTING: "选择输入方式",
      EXTRACTING: "读取题目",
      CAPTURING: "读取前台窗口",
      ANALYZING: "正在分析",
      WORKING: "正在处理",
      BUSY: "BUSY · 请稍候",
      STOPPING: "正在停止",
      ERROR: "遇到问题",
    }[state.status] || state.status;
  $("status-text").textContent = label;
  $("status-pill").classList.toggle(
    "running",
    state.active && state.status === "READY",
  );
  $("status-pill").classList.toggle(
    "busy",
    state.active && state.status !== "READY",
  );
  $("version").textContent = "v" + (state.version || "0.3.0");
  $("start-button").textContent = preview
    ? "下载 App 后开始 →"
    : state.active
      ? "停止答题 ⏸"
      : !config && !preview
        ? "完成首次配置 →"
        : "启动答题 ↗";
  $("start-button").disabled =
    state.status === "STOPPING" || state.status === "STARTING";
  $("demo-button").disabled = state.active;
  $("provider-name").textContent =
    state.active_profile ||
    providers.find((provider) => provider.id === config?.provider_profile)
      ?.name ||
    "先连接你的模型";
  $("provider-initial").textContent =
    state.active_profile || config ? $("provider-name").textContent[0] : "◇";
  $("provider-model").textContent = offline
    ? "预置示例 · 无 API 请求"
    : config?.model || "也可以先体验离线 Demo";
  $("input-mode").textContent = (
    state.active_mode ||
    config?.input_mode ||
    "auto"
  ).toUpperCase();
  $("vision-capability").textContent = offline
    ? "不支持图片"
    : !config
      ? "待配置"
      : config.supports_vision
        ? "已启用"
        : "未启用";
  $("key-status").textContent = offline
    ? "无需 Key"
    : !config
      ? "待配置"
      : config.protocol_provider === "fake"
        ? "无需 Key"
        : config.has_key
          ? config.credential_mode === "stored"
            ? "安全保存"
            : "仅本次"
          : "需要输入";
  $("runtime-error").hidden = !state.error;
  $("runtime-error").textContent = state.error || "";
  $("history-count").textContent = String(state.history.length);
  $("history-list").replaceChildren();
  if (!state.history.length)
    $("history-list").append(
      node("p", "muted", "完成的题目会出现在这里，退出后清空。"),
    );
  state.history.forEach((result, index) => {
    const row = node("div", "history-item");
    const button = node("button", "", (result.batch_total > 1 ? `第 ${result.batch_index} 题 · ` : "") + result.question.question_text);
    button.addEventListener("click", () => {
      selectedResult = index;
      showResult(result);
    });
    row.append(
      node("time", "", result.time),
      button,
      node("span", "history-answer", answerLabel(result.answer)),
    );
    $("history-list").append(row);
  });
  showResult(state.history[selectedResult] || state.history[0]);
  ["flow-capture", "flow-analyze", "flow-result"].forEach((id) =>
    $(id).classList.remove("current"),
  );
  if (["ROUTING", "CAPTURING", "EXTRACTING", "WORKING"].includes(state.status))
    $("flow-capture").classList.add("current");
  if (state.status === "ANALYZING") $("flow-analyze").classList.add("current");
  if (state.history.length && state.status === "READY")
    $("flow-result").classList.add("current");
  document
    .querySelectorAll(
      "#settings-form input, #settings-form select, #settings-form button",
    )
    .forEach((input) => {
      input.disabled = state.active;
    });
  if (preview) {
    $("api-key").disabled = true;
    $("toggle-key").disabled = true;
  }
  $("settings-lock").textContent = state.active
    ? "请先停止答题再修改配置。"
    : preview
      ? "预览模式不保存设置，也不接收 API Key。"
      : "设置只在本机生效。";
  $("pair-button").disabled = preview || !state.bridge_available;
  $("use-url").disabled =
    state.active || selectedProvider()?.id === "offline_demo";
  document.querySelectorAll("#example-models button").forEach((button) => {
    button.disabled = state.active;
  });
  if (!state.active) hidePair();
}
function hidePair() {
  $("pair-code").value = "";
  $("pair-result").hidden = true;
  clearTimeout(pairTimer);
}
$("hide-pair").addEventListener("click", hidePair);
$("pair-button").addEventListener("click", () =>
  action(async () => {
    const result = await api("/api/pair", {});
    $("pair-code").value = result.code;
    $("pair-result").hidden = false;
    clearTimeout(pairTimer);
    pairTimer = setTimeout(hidePair, 30000);
  }),
);
async function refresh() {
  const next = await api("/api/state");
  if (next.history[0]?.batch_id !== state.history[0]?.batch_id) selectedResult = 0;
  state = next;
  render();
}
const demoResult = {
  time: "示例",
  offline: true,
  question: {
    question_text: "法国的首都是哪里？",
    question_type: "single_choice",
    source_type: "MANUAL",
    options: ["巴黎", "伦敦", "柏林", "罗马"].map((text, index) => ({
      text,
      index,
      label: "ABCD"[index],
    })),
  },
  answer: {
    question_type: "single_choice",
    selected_index: 0,
    selected_label: "A",
    selected_text: "巴黎",
    selected_indices: [],
    selected_labels: [],
    selected_texts: [],
    confidence: 0.99,
    short_reason: "离线预置演示答案，不代表模型推理。",
  },
};
function previewDemo() {
  state.active = true;
  state.active_protocol = "fake";
  state.active_mode = "demo";
  state.active_profile = "Offline Demo";
  state.status = "ANALYZING";
  view("workspace");
  render();
  setTimeout(() => {
    if (!state.active) return;
    state.history.unshift(structuredClone(demoResult));
    state.status = "READY";
    selectedResult = 0;
    render();
  }, 700);
}
$("demo-button").addEventListener("click", () =>
  action(async () => {
    if (preview) {
      previewDemo();
      return;
    }
    await api("/api/start", { offline_demo: true });
    selectedResult = 0;
    view("workspace");
    await refresh();
    toast("离线 Demo 已启动。按 F8 体验预置答案；不会改变你保存的模型配置。");
  }),
);
$("start-button").addEventListener("click", () =>
  action(async () => {
    if (preview) {
      location.href = appDownload;
      return;
    }
    if (state.active) {
      await api("/api/stop", {});
      await refresh();
      return;
    }
    if (!state.config || !state.config.has_key) {
      fillSettings(state.config);
      view("settings");
      return;
    }
    await api("/api/start", {});
    selectedResult = 0;
    await refresh();
    toast("把题目窗口放到前台后按 F8。完成后回到工作台查看答案。");
  }),
);
$("clear-button").addEventListener("click", () =>
  action(async () => {
    if (preview) {
      state.history = [];
      render();
      return;
    }
    await api("/api/clear", {});
    selectedResult = 0;
    await refresh();
  }),
);
$("settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(async () => {
    $("save-message").hidden = true;
    if (preview) {
      location.href = appDownload;
      return;
    }
    const body = {
      provider_profile: $("provider").value,
      base_url: $("base-url").value,
      model: $("model").value,
      supports_vision: $("vision").checked,
      input_mode: $("mode").value,
      timeout_seconds: Number($("request-timeout").value),
      credential_mode: $("storage").value,
      api_key: $("api-key").value,
    };
    try {
      await api("/api/config", body);
      await refresh();
      fillSettings(state.config);
      $("save-message").textContent = "配置已保存。可以回工作台启动答题了。";
      $("save-message").className = "message";
      $("save-message").hidden = false;
      toast("配置保存成功。");
      view("workspace");
    } catch (error) {
      $("save-message").textContent = error.message;
      $("save-message").className = "message error";
      $("save-message").hidden = false;
    } finally {
      body.api_key = "";
      $("api-key").value = "";
      $("api-key").type = "password";
      $("toggle-key").textContent = "显示";
      $("toggle-key").setAttribute("aria-pressed", "false");
    }
  });
});
$("exit-button").addEventListener("click", () =>
  action(async () => {
    if (
      !confirm(
        "退出 AutoQuestion？正在处理的任务将停止，内存中的答题记录会清空。",
      )
    )
      return;
    clearTimeout(pollTimer);
    await api("/api/shutdown", {});
    sessionStorage.removeItem("aq-session");
    token = "";
    $("connection-label").textContent = "已退出";
    toast("AutoQuestion 已退出。下次双击桌面入口重新打开。");
  }),
);
async function poll() {
  try {
    await refresh();
  } catch (error) {
    $("connection-label").textContent = "连接已断开";
    toast(error.message || "本机程序已停止，请重新双击打开。");
    return;
  }
  pollTimer = setTimeout(poll, 1200);
}
async function initialize() {
  try {
    if (locked) {
      $("preview-banner").hidden = false;
      $("preview-banner").textContent =
        "这个标签没有本机会话。请双击 AutoQuestion.exe 重新打开，便可正常配置。";
      $("connection-label").textContent = "需要从 App 打开";
      $("start-button").disabled =
        $("demo-button").disabled =
        $("pair-button").disabled =
          true;
      $("exit-button").hidden = true;
      return;
    }
    if (preview) {
      $("preview-banner").hidden = false;
      $("connection-label").textContent = "界面预览";
      $("exit-button").hidden = true;
      $("api-key").placeholder = "在 Windows 本机版中填写";
      $("save-button").textContent = "下载 App 后配置 →";
      const response = await fetch("providers.json", { cache: "no-store" });
      if (!response.ok) throw new Error("配置示例加载失败。");
      providers = (await response.json()).providers;
    } else {
      providers = (await api("/api/providers")).providers;
      state = await api("/api/state");
    }
    providers.forEach((provider) => {
      const option = node("option", "", provider.name);
      option.value = provider.id;
      $("provider").append(option);
    });
    fillSettings(state.config);
    render();
    if (!state.config && !preview) view("settings");
    if (!preview) pollTimer = setTimeout(poll, 1200);
  } catch (error) {
    $("connection-label").textContent = "App 连接失败";
    $("preview-banner").hidden = false;
    $("preview-banner").textContent =
      "请双击 AutoQuestion.exe 重新打开本机工作台，再填写配置。";
    toast(error.message || "界面加载失败，请重新打开。");
  }
}
document
  .querySelectorAll(
    "#settings-form input, #settings-form select, #settings-form button",
  )
  .forEach((field) => {
    field.disabled = true;
  });
initialize();
