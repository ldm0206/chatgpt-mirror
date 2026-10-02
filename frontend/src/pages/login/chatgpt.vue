<template>
  <div class="pick-page">
    <header class="pick-top">
      <div class="pick-brand">
        <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
          <g stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
            <line x1="12" y1="2.6" x2="12" y2="21.4" />
            <line x1="2.6" y1="12" x2="21.4" y2="12" />
            <line x1="5.3" y1="5.3" x2="18.7" y2="18.7" />
            <line x1="18.7" y1="5.3" x2="5.3" y2="18.7" />
          </g>
        </svg>
        <span class="brand-name">ChatGPT Mirror</span>
      </div>
      <nav class="pick-links">
        <router-link v-if="userStore.isAdmin" to="/account/overview" class="top-link">返回管理</router-link>
        <router-link v-else to="/account/profile" class="top-link">账户中心</router-link>
        <span class="top-user">{{ userStore.username }}</span>
        <button class="top-link top-link-btn" type="button" @click="doLogout">退出</button>
      </nav>
    </header>

    <main v-if="tableVisible" class="pick-main">
      <div class="pick-head">
        <div class="pick-head-text">
          <h1>选择账号</h1>
          <p>挑一个上游账号开始对话，拿不准就用智能分配。</p>
        </div>
        <t-button
          theme="primary"
          class="auto-btn"
          :disabled="tableLoading || !tableData.length"
          @click="onSelect(null)"
        >
          智能分配最空闲账号
        </t-button>
      </div>

      <div class="cardgrid">
        <button
          v-for="item in tableData"
          :key="item.id"
          type="button"
          class="card"
          :class="{ 'card--off': !item.auth_status || !item.supported_login_modes.length }"
          :disabled="tableLoading"
          @click="onSelect(item.id)"
        >
          <div class="card-head">
            <span class="card-tile" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="card-mark">
                <g stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
                  <line x1="12" y1="3.4" x2="12" y2="20.6" />
                  <line x1="3.4" y1="12" x2="20.6" y2="12" />
                  <line x1="5.9" y1="5.9" x2="18.1" y2="18.1" />
                  <line x1="18.1" y1="5.9" x2="5.9" y2="18.1" />
                </g>
              </svg>
            </span>
            <span class="plan-pill" :class="{ 'plan-pill--paid': item.plan_type !== 'free' }">
              {{ item.plan_type }}
            </span>
          </div>
          <span class="card-name">{{ item.chatgpt_flag || `账号 ${item.id}` }}</span>
          <span class="card-status" :class="{ live: item.auth_status && item.supported_login_modes.length }">
            <i></i>{{ item.auth_status && item.supported_login_modes.length ? '可用' : '不可用' }}
            <em>被登录 {{ item.login_count || 0 }} 次</em>
          </span>
          <span class="card-chips">
            <span v-if="supportsMode(item, 'api')" class="chip">API</span>
            <span v-if="supportsMode(item, 'web')" class="chip">网页</span>
          </span>
          <span class="card-act">进入对话</span>
        </button>
      </div>

      <div v-if="!tableData.length && !tableLoading" class="pick-empty">
        暂无可用的 ChatGPT 账号，请联系管理员添加
      </div>
    </main>

    <div v-else-if="!announcementVisible && !queued" class="pick-boot">
      <t-loading :loading="tableLoading" size="medium">
        <div class="pick-boot-card">
          <svg class="brand-mark brand-mark--breathe" viewBox="0 0 24 24" aria-hidden="true">
            <g stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <line x1="12" y1="2.6" x2="12" y2="21.4" />
              <line x1="2.6" y1="12" x2="21.4" y2="12" />
              <line x1="5.3" y1="5.3" x2="18.7" y2="18.7" />
              <line x1="18.7" y1="5.3" x2="5.3" y2="18.7" />
            </g>
          </svg>
          <div class="pick-boot-title">正在准备 ChatGPT 会话</div>
          <div class="pick-boot-desc">{{ statusText }}</div>
        </div>
      </t-loading>
    </div>

    <t-dialog
      :visible="announcementVisible"
      header="登录公告"
      :cancel-btn="null"
      :close-btn="false"
      :close-on-overlay-click="false"
      :confirm-btn="{ content: loginBlocked ? '返回账户中心' : '继续选择账号', loading: tableLoading }"
      width="760px"
      @confirm="continueToAccountSelection"
    >
      <div class="announcement-intro">
        {{ loginBlocked ? '当前公告已暂停你的 ChatGPT 登录。你仍可使用站点账户，公告结束后可重新进入。' : '请阅读管理员发布的公告，确认后继续选择 ChatGPT 账号。' }}
      </div>
      <t-tabs v-model="activeAnnouncementTab" class="announcement-tabs">
        <t-tab-panel
          v-if="announcements.global.length"
          value="global"
          :label="`全局公告 (${announcements.global.length})`"
        >
          <div class="announcement-list">
            <article v-for="item in announcements.global" :key="item.id" class="announcement-item">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time>{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <t-tag v-if="item.block_chatgpt_login" theme="danger" variant="light">暂停登录</t-tag>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>
        </t-tab-panel>
        <t-tab-panel
          v-if="announcements.personal.length"
          value="personal"
          :label="`给你的公告 (${announcements.personal.length})`"
        >
          <div class="announcement-list">
            <article v-for="item in announcements.personal" :key="item.id" class="announcement-item">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time>{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <t-tag v-if="item.block_chatgpt_login" theme="danger" variant="light">暂停登录</t-tag>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>
        </t-tab-panel>
        <t-tab-panel
          v-if="announcements.history.length"
          value="history"
          :label="`历史公告 (${announcements.history.length})`"
        >
          <div class="announcement-list">
            <article v-for="item in announcements.history" :key="item.id" class="announcement-item announcement-item--history">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time>{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>
        </t-tab-panel>
      </t-tabs>
    </t-dialog>

    <t-dialog
      :visible="queued"
      header="正在排队"
      :cancel-btn="{ content: '放弃排队' }"
      :confirm-btn="null"
      :on-close="cancelQueue"
      width="440px"
    >
      <div class="queue-body">
        <div class="queue-position">
          前面还有 {{ Math.max((queueInfo?.position ?? 1) - 1, 0) }} 人
        </div>
        <div class="queue-desc">
          当前使用人数已达上限，轮到你时会自动进入。
        </div>
        <div class="queue-meta">
          队列第 {{ queueInfo?.position ?? '-' }} 位 · 共 {{ queueInfo?.queue_size ?? '-' }} 人等待
        </div>
      </div>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { MessagePlugin } from 'tdesign-vue-next'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { detectBrowserIp } from '@/api/browser-ip'
import MarkdownContent from '@/components/MarkdownContent.vue'
import { useUserStore } from '@/store/user'

const tableLoading = ref(false)
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const tableVisible = ref(false)
const announcementVisible = ref(false)
const queued = ref(false)
const queueInfo = ref<any>(null)
const lastSelection = ref<number | null>(null)
let queueTimer: number | null = null
const activeAnnouncementTab = ref<'global' | 'personal' | 'history'>('global')
const statusText = ref('正在加载可用账号...')

type Announcement = {
  id: number
  title: string
  content: string
  updated_at: string
  start_at: string
  end_at: string | null
  display_timezone: string
  block_chatgpt_login: boolean
}

const announcements = reactive<{
  global: Announcement[]
  personal: Announcement[]
  history: Announcement[]
}>({
  global: [],
  personal: [],
  history: [],
})
const loginBlocked = computed(() =>
  [...announcements.global, ...announcements.personal].some(item => item.block_chatgpt_login),
)

interface TableData {
  id: number
  chatgpt_flag: string
  plan_type: string
  auth_status: boolean
  login_count: number
  access_token_valid: boolean
  session_token_valid: boolean
  supported_login_modes: string[]
  default_login_mode: 'api' | 'web'
}
const tableData = ref<TableData[]>([])

onMounted(async () => {
  if (route.query.logout === '1') {
    try {
      await userStore.logout()
      await router.replace('/login')
    } catch (error: any) {
      MessagePlugin.error(error.message || '退出未完成，请重试')
    }
    return
  }
  await prepareAnnouncements()
})

const prepareAnnouncements = async () => {
  statusText.value = '正在加载公告...'
  const data = await request('/0x/user/announcements/current')
  if (!data) {
    statusText.value = '公告暂时无法加载，请刷新页面重试'
    return
  }
  announcements.global = data?.global || []
  announcements.personal = data?.personal || []
  announcements.history = data?.history || []

  if (announcements.global.length || announcements.personal.length || announcements.history.length) {
    activeAnnouncementTab.value = announcements.global.length
      ? 'global'
      : announcements.personal.length ? 'personal' : 'history'
    announcementVisible.value = true
    statusText.value = '请先阅读登录公告'
    return
  }

  await getUserChatGPTAccountList()
}

const continueToAccountSelection = async () => {
  announcementVisible.value = false
  if (loginBlocked.value) {
    await router.push('/account/profile')
    return
  }
  await getUserChatGPTAccountList()
}

const formatAnnouncementSchedule = (item: Announcement) => {
  const timeZone = item.display_timezone || 'Asia/Shanghai'
  const start = new Date(item.start_at).toLocaleString('zh-CN', { hour12: false, timeZone })
  const end = item.end_at
    ? new Date(item.end_at).toLocaleString('zh-CN', { hour12: false, timeZone })
    : '长期'
  return `${start} 至 ${end} · ${timeZone}`
}

const getUserChatGPTAccountList = async () => {
  tableLoading.value = true
  statusText.value = '正在加载可用账号...'
  const data = await request('/0x/user/chatgpt-list')
  tableLoading.value = false

  if (!data) {
    router.push({ name: 'Login' })
    return
  }

  const results = data.results || []
  tableData.value = results

  if (results.length === 0) {
    MessagePlugin.warning('暂无可用的 ChatGPT 账号，请联系管理员添加')
  }
  tableVisible.value = true
}

const doLogout = async () => {
  try {
    await userStore.logout()
  } catch (error: any) {
    MessagePlugin.error(error.message || '退出未完成，请重试')
  }
  router.replace('/login')
}

const supportsMode = (item: TableData, mode: 'api' | 'web') => {
  return Array.isArray(item.supported_login_modes) && item.supported_login_modes.includes(mode)
}

const resolveLoginMode = (item?: TableData) => {
  if (item) {
    if (supportsMode(item, item.default_login_mode)) return item.default_login_mode
    if (supportsMode(item, 'api')) return 'api'
    if (supportsMode(item, 'web')) return 'web'
    return null
  }

  if (tableData.value.some(account => supportsMode(account, 'api'))) return 'api'
  if (tableData.value.some(account => supportsMode(account, 'web'))) return 'web'
  return null
}

const stopQueuePolling = () => {
  if (queueTimer !== null) {
    window.clearInterval(queueTimer)
    queueTimer = null
  }
}

const startQueuePolling = () => {
  stopQueuePolling()
  queueTimer = window.setInterval(async () => {
    const state = await request('/0x/chatgpt/slot')
    if (!state) return

    if (state.state === 'active') {
      // 名额到手：重新走一次登录即可拿到 login_url。
      stopQueuePolling()
      queued.value = false
      await onSelect(lastSelection.value)
      return
    }
    if (state.state === 'none') {
      // 名额被回收（例如排队期间断线太久），回到账号选择。
      stopQueuePolling()
      queued.value = false
      queueInfo.value = null
      tableVisible.value = true
      return
    }
    queueInfo.value = { ...queueInfo.value, ...state }
  }, 5000)
}

const cancelQueue = async () => {
  stopQueuePolling()
  await request('/0x/chatgpt/slot', 'POST', { action: 'leave' })
  queued.value = false
  queueInfo.value = null
  tableVisible.value = true
}

onBeforeUnmount(stopQueuePolling)

const onSelect = async (chatgptId: number | null) => {
  if (loginBlocked.value) {
    MessagePlugin.warning('公告生效期间，暂不能进入 ChatGPT')
    return
  }
  const current = tableData.value.find(item => item.id === chatgptId)
  const loginMode = resolveLoginMode(current)
  if (!loginMode) {
    MessagePlugin.warning('当前没有可登录的账号，请联系管理员更新账号凭据')
    return
  }

  tableLoading.value = true
  statusText.value = '正在登录 ChatGPT，请稍候...'
  tableVisible.value = false
  const data = await request('/0x/chatgpt/login', 'POST', {
    chatgpt_id: chatgptId,
    login_mode: loginMode,
    browser_ip: await detectBrowserIp(),
  })
  tableLoading.value = false

  if (data?.queued) {
    lastSelection.value = chatgptId
    queueInfo.value = data
    queued.value = true
    startQueuePolling()
    return
  }

  if (data) {
    MessagePlugin.success('登录成功')
    if (data.login_url) {
      window.location.replace(data.login_url)
      return
    }
  }

  tableVisible.value = true
  if (!queued.value) {
    statusText.value = '登录失败，请返回重试'
  }
}
</script>

<style scoped>
.pick-page {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--app-bg);
}

/* —— 顶栏 —— */
.pick-top {
  width: min(960px, 100%);
  margin: 0 auto;
  padding: 22px 24px 0;
  display: flex;
  align-items: center;
  gap: 20px;
}

.pick-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-right: auto;
}

.brand-mark {
  width: 19px;
  height: 19px;
  color: var(--app-action);
}

.brand-name {
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.pick-links {
  display: flex;
  align-items: center;
  gap: 18px;
}

.top-link {
  color: var(--app-text-muted);
  font-size: 13.5px;
  font-weight: 500;
  text-decoration: none;
  border-bottom: 1.5px solid transparent;
  padding-bottom: 2px;
  cursor: pointer;
}

.top-link:hover {
  color: var(--app-text);
}

.top-link-btn {
  appearance: none;
  background: none;
  border: 0;
  border-bottom: 1.5px solid transparent;
  font: inherit;
  font-size: 13.5px;
  padding: 0 0 2px;
}

.top-user {
  color: var(--app-text-muted);
  font-size: 13px;
}

/* —— 页头 —— */
.pick-main {
  width: min(960px, 100%);
  margin: 0 auto;
  padding: 0 24px 80px;
  flex: 1;
}

.pick-head {
  display: flex;
  align-items: flex-end;
  gap: 20px;
  margin: 52px 0 36px;
}

.pick-head-text {
  margin-right: auto;
}

.pick-head h1 {
  margin: 0;
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 38px;
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: 0.005em;
}

.pick-head p {
  margin: 10px 0 0;
  color: var(--app-text-muted);
  font-size: 14px;
  line-height: 1.6;
}

.auto-btn {
  flex: none;
  height: 42px;
  padding: 0 20px;
  border-radius: 999px;
}

/* —— 账号卡片 —— */
.cardgrid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.card {
  appearance: none;
  display: flex;
  flex-direction: column;
  padding: 20px;
  color: var(--app-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(41, 38, 31, 0.04);
  transition: box-shadow 0.16s ease, transform 0.16s ease, border-color 0.16s ease;
}

.card:hover:not(:disabled) {
  border-color: var(--app-border-strong);
  box-shadow: 0 10px 28px rgba(41, 38, 31, 0.09);
  transform: translateY(-2px);
}

.card:focus-visible {
  outline: 2px solid var(--app-action);
  outline-offset: 2px;
}

.card:disabled {
  cursor: wait;
}

.card--off,
.card--off:hover:not(:disabled) {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: 0 1px 2px rgba(41, 38, 31, 0.04);
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.card-tile {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  color: var(--app-text);
  background: var(--app-surface-muted);
  border-radius: 12px;
}

.card-mark {
  width: 20px;
  height: 20px;
}

.plan-pill {
  flex: none;
  padding: 3px 11px;
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 500;
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-radius: 999px;
}

.plan-pill--paid {
  color: var(--app-action-contrast);
  background: var(--app-action);
  border-color: var(--app-action);
}

.card-name {
  margin-top: 14px;
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.005em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-status {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 10px;
  color: var(--app-text-muted);
  font-size: 12.5px;
}

.card-status i {
  width: 6px;
  height: 6px;
  flex: none;
  background: #cfccbe;
  border-radius: 50%;
}

.card-status.live {
  color: var(--app-success);
}

.card-status.live i {
  background: var(--app-success);
}

.card-status em {
  margin-left: auto;
  color: var(--app-text-muted);
  font-style: normal;
}

.card-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 27px;
  margin-top: 12px;
  margin-bottom: 14px;
}

.chip {
  padding: 4px 12px;
  color: var(--app-text-muted);
  font-size: 12.5px;
  font-weight: 500;
  background: var(--app-bg);
  border: 1px solid var(--app-border);
  border-radius: 999px;
}

.card-act {
  margin-top: auto;
  padding-top: 14px;
  color: var(--app-action);
  font-size: 13px;
  font-weight: 600;
  border-top: 1px solid var(--app-border);
}

.card:hover:not(:disabled) .card-act {
  color: var(--app-action-hover);
}

.card-act::after {
  content: "→";
  margin-left: 6px;
}

.pick-empty {
  padding: 48px 24px;
  color: var(--app-text-muted);
  font-size: 14px;
  text-align: center;
  background: var(--app-surface);
  border: 1px dashed var(--app-border-strong);
  border-radius: 16px;
}

/* —— 启动加载态 —— */
.pick-boot {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pick-boot-card {
  min-width: 300px;
  padding: 28px 32px;
  text-align: center;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 16px;
  box-shadow: 0 14px 44px rgba(64, 52, 36, 0.1);
}

.brand-mark--breathe {
  width: 28px;
  height: 28px;
  margin: 0 auto 14px;
  animation: breathe 1.6s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 0.35; transform: scale(0.94); }
  50% { opacity: 1; transform: scale(1); }
}

.pick-boot-title {
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 19px;
  font-weight: 600;
}

.pick-boot-desc {
  margin-top: 8px;
  color: var(--app-text-muted);
  font-size: 13.5px;
}

/* —— 排队 —— */
.queue-body {
  text-align: center;
}

.queue-position {
  font-family: var(--app-font-serif);
  font-size: 24px;
  font-weight: 600;
  color: var(--app-text);
}

.queue-desc {
  margin-top: 10px;
  color: var(--app-text-muted);
  font-size: 14px;
  line-height: 1.6;
}

.queue-meta {
  margin-top: 14px;
  color: #9a9484;
  font-size: 13px;
}

/* —— 公告 —— */
.announcement-intro {
  margin-bottom: 16px;
  color: var(--app-text-muted);
  font-size: 14px;
}

.announcement-tabs {
  min-height: 280px;
}

.announcement-list {
  display: grid;
  gap: 12px;
  max-height: 52vh;
  padding: 16px 2px 4px;
  overflow-y: auto;
}

.announcement-item {
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: #fbf9f3;
}

.announcement-heading {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.announcement-heading h2 {
  margin: 0;
  color: var(--app-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
}

.announcement-heading time {
  flex: 0 0 auto;
  color: #9a9484;
  font-size: 12px;
}

.announcement-content {
  margin-top: 12px;
}

@media (max-width: 560px) {
  .pick-top {
    padding: 16px 20px 0;
    gap: 14px;
  }

  .top-user {
    display: none;
  }

  .pick-main {
    padding: 0 20px 64px;
  }

  .pick-head {
    flex-direction: column;
    align-items: stretch;
    margin: 36px 0 26px;
  }

  .pick-head h1 {
    font-size: 30px;
  }

  .cardgrid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .brand-mark--breathe {
    animation: none;
  }

  .card {
    transition: none;
  }
}
</style>
