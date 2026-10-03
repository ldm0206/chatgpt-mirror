<template>
  <div class="layout">
    <t-layout class="layout-shell">
      <t-aside class="sidebar" width="248px">
        <router-link class="sidebar-brand" :to="brandHome" aria-label="回到首页">
          <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
            <g stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <line x1="12" y1="2.6" x2="12" y2="21.4" />
              <line x1="2.6" y1="12" x2="21.4" y2="12" />
              <line x1="5.3" y1="5.3" x2="18.7" y2="18.7" />
              <line x1="18.7" y1="5.3" x2="5.3" y2="18.7" />
            </g>
          </svg>
          <span class="brand-text">
            <span class="brand-name">ChatGPT Mirror</span>
            <span class="brand-caption">管理面板</span>
          </span>
        </router-link>
        <t-menu
          class="nav-menu"
          :value="activeMenu"
          :collapsed="isSidebarCollapsed"
          :width="['248px', '100%']"
          theme="light"
          @change="handleMenuChange"
        >
          <t-menu-item v-if="userStore.isAdmin" value="/account/overview">
            <template #icon><t-icon name="dashboard" /></template>
            <span class="menu-label">运维概览</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/user">
            <template #icon><t-icon name="user" /></template>
            <span class="menu-label">用户</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/chatgpt">
            <template #icon><t-icon name="root-list" /></template>
            <span class="menu-label">上游账号</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/gptcar">
            <template #icon><t-icon name="server" /></template>
            <span class="menu-label">账号池</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/logs">
            <template #icon><t-icon name="file" /></template>
            <span class="menu-label">日志</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/announcements">
            <template #icon><t-icon name="notification" /></template>
            <span class="menu-label">公告</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/proxy">
            <template #icon><t-icon name="internet" /></template>
            <span class="menu-label">代理</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/scripts">
            <template #icon><t-icon name="code" /></template>
            <span class="menu-label">脚本</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/access">
            <template #icon><t-icon name="secured" /></template>
            <span class="menu-label">访问与安全</span>
          </t-menu-item>
          <t-menu-item v-if="userStore.isAdmin" value="/account/political-moderation">
            <template #icon><t-icon name="secured" /></template>
            <span class="menu-label">政治内容屏蔽</span>
          </t-menu-item>
          <t-menu-item v-if="!userStore.isAdmin" value="/account/profile">
            <template #icon><t-icon name="user-circle" /></template>
            <span class="menu-label">账户中心</span>
          </t-menu-item>
        </t-menu>
      </t-aside>
      <t-layout class="workspace">
        <t-header class="header">
          <transition name="page-title" mode="out-in">
            <h1 :key="pageTitle">{{ pageTitle }}</h1>
          </transition>
          <div class="header-right">
            <t-dropdown :options="userOptions" @click="handleUserAction">
              <t-button class="user-button" variant="text">
                <t-icon name="user-circle" />
                {{ username }}
                <t-icon name="chevron-down" />
              </t-button>
            </t-dropdown>
          </div>
        </t-header>
        <t-content class="content">
          <div class="content-inner">
            <router-view v-slot="{ Component }">
              <transition name="page" mode="out-in">
                <component :is="Component" />
              </transition>
            </router-view>
          </div>
        </t-content>
      </t-layout>
    </t-layout>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const isSidebarCollapsed = ref(false)

let sidebarMediaQuery: MediaQueryList | null = null

const syncSidebarState = (event?: MediaQueryListEvent) => {
  isSidebarCollapsed.value = event?.matches ?? sidebarMediaQuery?.matches ?? false
}

onMounted(() => {
  sidebarMediaQuery = window.matchMedia('(max-width: 900px)')
  syncSidebarState()
  sidebarMediaQuery.addEventListener('change', syncSidebarState)
})

onBeforeUnmount(() => {
  sidebarMediaQuery?.removeEventListener('change', syncSidebarState)
})

const activeMenu = computed(() => route.path)
const username = computed(() => userStore.username || '管理员')
const pageTitle = computed(() => String(route.meta.title || '管理'))
const brandHome = computed(() => (userStore.isAdmin ? '/account/overview' : '/account/profile'))

const userOptions = computed(() => {
  const options = [{ content: '退出登录', value: 'logout' }]
  if (!userStore.isAdmin) {
    options.unshift({ content: '账户中心', value: 'profile' })
  }
  return options
})

const handleMenuChange = (value: string) => {
  router.push(value)
}

const handleUserAction = async (data: { value: string }) => {
  if (data.value === 'profile') {
    router.push('/account/profile')
    return
  }
  if (data.value === 'logout') {
    try {
      await userStore.logout()
      await router.replace('/login')
    } catch (error: any) {
      const { MessagePlugin } = await import('tdesign-vue-next')
      MessagePlugin.error(error.message || '退出未完成，请重试')
    }
  }
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  min-height: 100dvh;
}

.layout-shell {
  min-height: 100vh;
  min-height: 100dvh;
}

.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  height: 100dvh;
  color: var(--app-text);
  background: var(--app-bg-deep);
  border-right: 1px solid var(--app-border);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 64px;
  padding: 0 20px;
  border-bottom: 1px solid var(--app-border);
  text-decoration: none;
  transition: background 0.18s ease;
}

.sidebar-brand:hover {
  background: rgba(255, 255, 255, 0.4);
}

.brand-mark {
  flex: none;
  width: 22px;
  height: 22px;
  color: var(--app-action);
  transition: transform 0.35s cubic-bezier(0.22, 0.9, 0.32, 1);
}

.sidebar-brand:hover .brand-mark {
  transform: rotate(45deg);
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.brand-name {
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.brand-caption {
  color: var(--app-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.nav-menu {
  width: 100% !important;
  box-sizing: border-box;
  padding: 14px 12px;
  background: transparent;
}

.nav-menu :deep(.t-menu__item) {
  position: relative;
  height: 42px;
  margin-bottom: 2px;
  color: #5c574a;
  border-radius: 9px;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-menu :deep(.t-menu__item)::before {
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 18px;
  background: var(--app-action);
  border-radius: 2px;
  transform: translateY(-50%) scaleY(0);
  transform-origin: center;
  transition: transform 0.18s ease;
  content: "";
}

.nav-menu :deep(.t-menu__item.t-is-active)::before {
  transform: translateY(-50%) scaleY(1);
}

.nav-menu :deep(.t-menu__item:hover) {
  color: var(--app-text);
  background: #e5e1d2;
}

.nav-menu :deep(.t-menu__item.t-is-active) {
  color: var(--app-text);
  font-weight: 600;
  background: #dcd6c2;
}

.nav-menu :deep(.t-menu__item.t-is-active .t-icon) {
  color: var(--app-action);
}

.workspace {
  min-width: 0;
  background: var(--app-bg);
}

.header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 64px;
  padding: 0 32px;
  background: rgba(245, 243, 236, 0.92);
  border-bottom: 1px solid var(--app-border);
}

@supports ((-webkit-backdrop-filter: blur(8px)) or (backdrop-filter: blur(8px))) {
  .header {
    background: rgba(245, 243, 236, 0.78);
    -webkit-backdrop-filter: blur(8px);
    backdrop-filter: blur(8px);
  }
}

.header h1 {
  margin: 0;
  color: var(--app-text);
  font-family: var(--app-font-serif);
  font-size: 21px;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-button {
  color: #5c574a;
  border-radius: 9px;
}

.user-button:hover {
  color: var(--app-text);
  background: var(--app-surface-muted);
}

.content {
  padding: 32px;
  background: var(--app-bg);
  min-height: calc(100vh - 64px);
}

.content-inner {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
}

/* —— 页面切换与标题过渡 —— */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.page-title-enter-active,
.page-title-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.page-title-enter-from {
  opacity: 0;
  transform: translateY(5px);
}

.page-title-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}

@media (max-width: 900px) {
  .sidebar {
    width: 76px !important;
    flex-basis: 76px !important;
  }

  .sidebar-brand {
    justify-content: center;
    padding: 0;
  }

  .brand-name,
  .brand-caption {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    white-space: nowrap;
    clip-path: inset(50%);
  }

  .nav-menu {
    padding: 14px 8px;
  }

  .nav-menu :deep(.t-menu__item) {
    position: relative;
    display: flex !important;
    align-items: center;
    justify-content: center;
    min-width: 44px;
    padding: 0 !important;
  }

  .nav-menu :deep(.t-menu__item-icon),
  .nav-menu :deep(.t-menu__item > .t-icon),
  .nav-menu :deep(.t-menu__item .t-icon) {
    display: inline-flex !important;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    margin: 0 !important;
    font-size: 20px;
    opacity: 1;
    visibility: visible;
  }

  .menu-label {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    white-space: nowrap;
    clip-path: inset(50%);
  }

  .header {
    padding: 0 20px;
  }

  .content {
    padding: 20px;
  }
}

@media (max-width: 560px) {
  .sidebar {
    width: 64px !important;
    flex-basis: 64px !important;
  }

  .header {
    padding: 0 16px;
  }

  .header h1 {
    font-size: 18px;
  }

  .user-button {
    font-size: 0;
  }

  .user-button :deep(.t-icon) {
    font-size: 18px;
  }

  .content {
    padding: 16px 12px;
  }
}
</style>
