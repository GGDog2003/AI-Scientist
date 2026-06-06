<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

type ProgressStatus = "running" | "completed" | "waiting";

interface ProgressEvent {
  timestamp: string;
  thread_id: string;
  step_key: string;
  label: string;
  agent: string;
  status: ProgressStatus;
  artifact_path?: string | null;
  detail?: string | null;
  current_stage?: string | null;
}

interface WorkflowSnapshot {
  thread_id: string | null;
  workflow_status: string | null;
  current_stage: string | null;
  active_agent: string | null;
  waiting_for_agent: string | null;
  final_summary: string | null;
  manuscript_path: string | null;
  experiment_plan_path: string | null;
  experiment_result_path: string | null;
  advisor_review_path: string | null;
  reviewer_review_path: string | null;
  artifacts: Array<Record<string, unknown>>;
  messages_log: Array<Record<string, unknown>>;
  interrupt: Record<string, unknown> | null;
  progress_events: ProgressEvent[];
}

interface ProgressRow extends ProgressEvent {
  clickable: boolean;
}

const paperDir = ref("");
const threadId = ref("");
const snapshot = ref<WorkflowSnapshot | null>(null);
const isLaunching = ref(false);
const isResuming = ref(false);
const isPolling = ref(false);
const notice = ref("");
let pollTimer: number | null = null;

const canStart = computed(() => Boolean(paperDir.value) && !isLaunching.value && !threadId.value);

const progressRows = computed<ProgressRow[]>(() => {
  const events = snapshot.value?.progress_events ?? [];
  const latestByStep = new Map<string, ProgressRow>();
  const order: string[] = [];
  for (const event of events) {
    if (!latestByStep.has(event.step_key)) {
      order.push(event.step_key);
    }
    latestByStep.set(event.step_key, {
      ...event,
      clickable: Boolean(event.artifact_path),
    });
  }
  return order.map((stepKey) => latestByStep.get(stepKey)!).filter(Boolean);
});

const latestProgress = computed(() => {
  const rows = progressRows.value;
  return rows.length ? rows[rows.length - 1] : null;
});

const needsExperimentImport = computed(() => {
  const row = progressRows.value.find((item) => item.step_key === "human_experiment");
  return Boolean(row && row.status === "waiting");
});

const isCompleted = computed(() => snapshot.value?.workflow_status === "completed");
const finalPaperPath = computed(() => snapshot.value?.manuscript_path ?? "");

const phaseLabel = computed(() => {
  if (!snapshot.value) {
    return "尚未启动";
  }
  if (isCompleted.value) {
    return "已完成";
  }
  if (needsExperimentImport.value) {
    return "等待实验结果";
  }
  return snapshot.value.current_stage ?? "运行中";
});

async function choosePaperDirectory() {
  try {
    const selected = await open({
      directory: true,
      multiple: false,
      title: "选择论文目录",
    });
    if (typeof selected === "string") {
      paperDir.value = selected;
      notice.value = "";
    }
  } catch (error) {
    notice.value = `打开论文目录选择框失败：${String(error)}`;
  }
}

async function startWorkflow() {
  if (!paperDir.value || isLaunching.value) {
    return;
  }
  isLaunching.value = true;
  notice.value = "";
  try {
    const launchedThreadId = await invoke<string>("start_workflow", {
      paperDir: paperDir.value,
    });
    threadId.value = launchedThreadId;
    startPolling();
    await pollState();
  } catch (error) {
    notice.value = String(error);
  } finally {
    isLaunching.value = false;
  }
}

async function importExperimentResult() {
  if (!threadId.value || isResuming.value) {
    return;
  }
  try {
    const selected = await open({
      directory: false,
      multiple: false,
      filters: [{ name: "JSON", extensions: ["json"] }],
      title: "选择实验结果 JSON",
    });
    if (typeof selected !== "string") {
      return;
    }
    const confirmed = window.confirm("确定导入这个实验结果并继续执行吗？");
    if (!confirmed) {
      return;
    }
    isResuming.value = true;
    notice.value = "";
    await invoke("resume_workflow", {
      threadId: threadId.value,
      resumeFile: selected,
    });
    startPolling();
    await pollState();
  } catch (error) {
    notice.value = `导入实验结果失败：${String(error)}`;
  } finally {
    isResuming.value = false;
  }
}

async function pollState() {
  if (!threadId.value || isPolling.value) {
    return;
  }
  isPolling.value = true;
  try {
    const nextSnapshot = await invoke<WorkflowSnapshot>("inspect_workflow", {
      threadId: threadId.value,
    });
    snapshot.value = nextSnapshot;
    if (nextSnapshot.workflow_status === "completed" || needsExperimentImport.value) {
      stopPolling();
    }
  } catch (error) {
    notice.value = String(error);
  } finally {
    isPolling.value = false;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(() => {
    void pollState();
  }, 1500);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function openArtifact(path: string | null | undefined) {
  if (!path) {
    return;
  }
  try {
    await invoke("open_artifact", { path });
  } catch (error) {
    notice.value = String(error);
  }
}

function progressIcon(status: ProgressStatus): string {
  if (status === "completed") {
    return "√";
  }
  if (status === "waiting") {
    return "!";
  }
  return "○";
}

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<template>
  <main class="app-shell">
    <section class="app-card">
      <header class="hero">
        <span class="eyebrow">AI Scientist Desktop</span>
        <h1 class="title">科研流程可视化控制台</h1>
        <p class="subtitle">
          保留当前命令行工作流不变，在桌面端用单页界面启动、观察、恢复和打开论文产物。
        </p>
      </header>

      <div class="toolbar">
        <button class="secondary-button" type="button" @click="choosePaperDirectory">
          导入论文目录
        </button>
        <button class="primary-button" type="button" :disabled="!canStart" @click="startWorkflow">
          {{ isLaunching ? "正在启动..." : "开始撰写" }}
        </button>
      </div>

      <section class="meta-grid">
        <article class="meta-card">
          <p class="meta-label">论文目录</p>
          <p class="meta-value">{{ paperDir || "尚未选择" }}</p>
        </article>
        <article class="meta-card">
          <p class="meta-label">线程 ID</p>
          <p class="meta-value">{{ threadId || "尚未生成" }}</p>
        </article>
        <article class="meta-card">
          <p class="meta-label">当前阶段</p>
          <p class="meta-value">{{ phaseLabel }}</p>
        </article>
      </section>

      <section class="progress-section">
        <h2 class="section-title">当前进度</h2>

        <div v-if="!progressRows.length" class="empty-state">
          尚未开始执行。导入论文目录后，“开始撰写”按钮才会可用。
        </div>

        <ul v-else class="progress-list">
          <li v-for="row in progressRows" :key="row.step_key">
            <button
              class="progress-item"
              :class="{ clickable: row.clickable }"
              type="button"
              :disabled="!row.clickable"
              @click="openArtifact(row.artifact_path)"
            >
              <span class="progress-icon" :class="row.status">{{ progressIcon(row.status) }}</span>
              <span class="progress-content">
                <span class="progress-title">{{ row.label }}</span>
                <span class="progress-detail">
                  {{ row.detail || `角色：${row.agent}` }}
                </span>
              </span>
            </button>
          </li>
        </ul>

        <div v-if="snapshot" class="status-banner">
          <strong>流程状态</strong>
          <p>
            {{
              latestProgress?.status === "running"
                ? "当前流程仍在执行中，界面会自动轮询最新进度。"
                : latestProgress?.status === "waiting"
                  ? "流程已经暂停，等待你导入实验结果后再继续。"
                  : isCompleted
                    ? "流程已经完成，可以直接打开最终论文。"
                    : "当前线程状态已同步。"
            }}
          </p>

          <div class="status-actions">
            <button
              v-if="needsExperimentImport"
              class="primary-button"
              type="button"
              :disabled="isResuming"
              @click="importExperimentResult"
            >
              {{ isResuming ? "正在恢复..." : "导入实验结果" }}
            </button>

            <button
              v-if="isCompleted && finalPaperPath"
              class="primary-button"
              type="button"
              @click="openArtifact(finalPaperPath)"
            >
              阅读最终论文成稿
            </button>

            <button
              v-if="threadId"
              class="ghost-button"
              type="button"
              @click="pollState"
            >
              刷新状态
            </button>
          </div>
        </div>
      </section>

      <div v-if="notice" class="toast">
        {{ notice }}
      </div>
    </section>
  </main>
</template>
