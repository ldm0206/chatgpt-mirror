<template>
  <div class="overview">
    <div class="overview-actions">
      <t-button variant="outline" :loading="backingUp" @click="downloadBackup">下载加密备份</t-button>
      <t-button variant="outline" :loading="restoring" @click="backupInput?.click()">恢复备份</t-button>
      <input ref="backupInput" type="file" accept="application/json" hidden @change="restoreBackup" />
    </div>
    <t-loading :loading="loading">
      <div class="metric-grid">
        <t-card
          v-for="(metric, index) in metrics"
          :key="metric.label"
          :bordered="false"
          class="metric-card"
          :style="{ '--stagger': index }"
        >
          <div class="metric-label">{{ metric.label }}</div>
          <div class="metric-value">{{ metric.value }}</div>
          <div class="metric-detail">{{ metric.detail }}</div>
        </t-card>
      </div>
      <t-card title="运行状态" subtitle="用户、上游账号和今日活动的实时汇总" :bordered="false">
        <t-descriptions v-if="overview" :column="2" bordered>
          <t-descriptions-item label="启用用户">{{ overview.users.active }}</t-descriptions-item>
          <t-descriptions-item label="过期用户">{{ overview.users.expired }}</t-descriptions-item>
          <t-descriptions-item label="健康上游">{{ overview.upstream.healthy }}</t-descriptions-item>
          <t-descriptions-item label="异常上游">{{ overview.upstream.unhealthy }}</t-descriptions-item>
          <t-descriptions-item label="今日登录">{{ overview.activity.today_logins }}</t-descriptions-item>
          <t-descriptions-item label="今日代理请求">{{ overview.activity.today_requests }}</t-descriptions-item>
          <t-descriptions-item label="活跃镜像会话">{{ overview.activity.active_sessions }}</t-descriptions-item>
        </t-descriptions>
      </t-card>

      <t-card
        title="会话占用与排队"
        subtitle="成员进入上游账号时占用名额；达到上限的会话自动排队，名额释放后按先后顺序补位"
        :bordered="false"
      >
        <template #actions>
          <t-space>
            <t-tag :theme="sessions.usage.waiting ? 'warning' : 'default'" variant="light">
              使用中 {{ sessions.usage.active }} · 排队 {{ sessions.usage.waiting }}
            </t-tag>
            <t-button v-if="userStore.isSuperuser" size="small" @click="openLimits">并发设置</t-button>
          </t-space>
        </template>

        <h4 class="section-title">使用中</h4>
        <t-table
          v-if="sessions.active.length"
          :data="sessions.active"
          :columns="activeColumns"
          row-key="subject"
          size="small"
        >
          <template #op="{ row }">
            <t-popconfirm
              content="断开只释放名额，不会让该用户退出登录。"
              @confirm="releaseSeat(row)"
            >
              <t-link theme="warning">断开</t-link>
            </t-popconfirm>
          </template>
        </t-table>
        <div v-else class="empty-text">当前没有成员在占用账号</div>

        <h4 class="section-title">排队中</h4>
        <t-table
          v-if="sessions.waiting.length"
          :data="sessions.waiting"
          :columns="waitingColumns"
          row-key="subject"
          size="small"
        />
        <div v-else class="empty-text">没有等待中的会话</div>

        <div class="limits-hint">
          并发上限：全局 {{ sessions.limits.max_active_sessions || '不限' }} ·
          单账号 {{ sessions.limits.max_sessions_per_account || '不限' }} ·
          空闲 {{ sessions.limits.session_idle_seconds }} 秒回收
        </div>
      </t-card>
    </t-loading>

    <t-dialog
      :visible="limitsVisible"
      header="并发与排队设置"
      :confirm-btn="{ loading: savingLimits }"
      @confirm="saveLimits"
      @close="limitsVisible = false"
      width="500px"
    >
      <t-form label-width="140px">
        <t-form-item label="全局并发上限">
          <t-input-number v-model="limitsForm.max_active_sessions" :min="0" :max="100000" />
          <div class="field-help">同时使用镜像的会话总数，0 表示不限制</div>
        </t-form-item>
        <t-form-item label="单账号并发上限">
          <t-input-number v-model="limitsForm.max_sessions_per_account" :min="0" :max="100000" />
          <div class="field-help">同一个上游账号允许几人同时使用，0 表示不限制</div>
        </t-form-item>
        <t-form-item label="空闲回收秒数">
          <t-input-number v-model="limitsForm.session_idle_seconds" :min="60" :max="86400" />
          <div class="field-help">超过这个时间没有任何请求的会话会被释放，并把名额让给队列</div>
        </t-form-item>
      </t-form>
      <t-alert message="管理员进入账号时不占名额。" />
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(false)
const overview = ref<any>(null)
const backingUp = ref(false)
const restoring = ref(false)
const backupInput = ref<HTMLInputElement | null>(null)
const metrics = computed(() => [
  { label: '用户总数', value: overview.value?.users.total ?? '-', detail: `${overview.value?.users.active ?? 0} 个启用` },
  { label: '上游账号', value: overview.value?.upstream.total ?? '-', detail: `${overview.value?.upstream.healthy ?? 0} 个健康` },
  { label: '今日登录', value: overview.value?.activity.today_logins ?? '-', detail: '按自然日统计' },
  { label: '今日请求', value: overview.value?.activity.today_requests ?? '-', detail: '计入配额的代理请求' }
])

const sessions = reactive<any>({
  active: [],
  waiting: [],
  limits: { max_active_sessions: 0, max_sessions_per_account: 0, session_idle_seconds: 1800 },
  usage: { active: 0, waiting: 0 }
})
const limitsVisible = ref(false)
const savingLimits = ref(false)
const limitsForm = reactive({
  max_active_sessions: 0,
  max_sessions_per_account: 0,
  session_idle_seconds: 1800
})
let sessionsTimer: number | null = null

const activeColumns = [
  { colKey: 'username', title: '成员', width: 160 },
  { colKey: 'chatgpt_username', title: '上游账号', ellipsis: true },
  { colKey: 'acquired_at', title: '进入时间', width: 200 },
  { colKey: 'last_seen_at', title: '最近活动', width: 200 },
  { colKey: 'op', title: '操作', cell: 'op', width: 90 }
]

const waitingColumns = [
  { colKey: 'position', title: '队列位次', width: 100 },
  { colKey: 'username', title: '成员', width: 160 },
  { colKey: 'chatgpt_username', title: '目标账号', ellipsis: true },
  { colKey: 'queued_at', title: '开始排队', width: 200 }
]

const loadSessions = async () => {
  const data = await request('/0x/user/sessions')
  if (!data) return
  sessions.active = data.active || []
  sessions.waiting = data.waiting || []
  sessions.limits = data.limits || sessions.limits
  sessions.usage = data.usage || { active: 0, waiting: 0 }
}

onMounted(async () => {
  loading.value = true
  overview.value = await request('/0x/user/overview')
  await loadSessions()
  loading.value = false
  sessionsTimer = window.setInterval(loadSessions, 10000)
})

onBeforeUnmount(() => {
  if (sessionsTimer !== null) window.clearInterval(sessionsTimer)
})

const releaseSeat = async (row: any) => {
  const data = await request('/0x/user/sessions/release', 'POST', { subject: row.subject })
  if (data) {
    MessagePlugin.success(data.message || '已断开')
    await loadSessions()
  }
}

const openLimits = () => {
  limitsForm.max_active_sessions = sessions.limits.max_active_sessions
  limitsForm.max_sessions_per_account = sessions.limits.max_sessions_per_account
  limitsForm.session_idle_seconds = sessions.limits.session_idle_seconds
  limitsVisible.value = true
}

const saveLimits = async () => {
  savingLimits.value = true
  const data = await request('/0x/user/sessions/limits', 'PUT', {
    ...limitsForm,
    revision: sessions.limits.revision ?? 0
  })
  savingLimits.value = false
  if (data) {
    MessagePlugin.success(data.message || '设置已保存')
    limitsVisible.value = false
    await loadSessions()
  }
}

const downloadBackup = async () => {
  backingUp.value = true
  const data = await request('/0x/user/backup')
  backingUp.value = false
  if (!data?.archive) return
  const blob = new Blob([JSON.stringify(data)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `chatgpt-mirror-backup-${Date.now()}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

const restoreBackup = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  restoring.value = true
  try {
    const parsed = JSON.parse(await file.text())
    const data = await request('/0x/user/backup', 'POST', {
      archive: parsed.archive,
      confirm: 'RESTORE'
    })
    if (data) MessagePlugin.success(data.message)
  } catch {
    MessagePlugin.error('备份文件格式无效')
  } finally {
    restoring.value = false
    input.value = ''
  }
}
</script>

<style scoped>
.overview { display: grid; gap: 20px; }
.overview-actions { display: flex; justify-content: flex-end; gap: 10px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.metric-card {
  min-height: 132px;
  animation: metric-in 0.36s cubic-bezier(0.22, 0.9, 0.32, 1) backwards;
  animation-delay: calc(var(--stagger, 0) * 55ms);
}
@keyframes metric-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}
.metric-label { color: var(--app-text-muted); font-size: 13px; }
.metric-value { margin-top: 14px; color: var(--app-text); font-family: var(--app-font-serif); font-size: 34px; font-weight: 600; letter-spacing: 0; }
.metric-detail { margin-top: 8px; color: var(--app-text-muted); font-size: 13px; }
.section-title { margin: 4px 0 10px; color: var(--app-text); font-size: 14px; font-weight: 600; }
.section-title + .empty-text { margin-bottom: 16px; }
.empty-text { padding: 8px 0 16px; color: var(--app-text-muted); font-size: 13px; }
.limits-hint { margin-top: 12px; color: var(--app-text-muted); font-size: 13px; }
.field-help { margin-top: 4px; color: var(--app-text-muted); font-size: 12px; }
@media (max-width: 900px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
