<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div v-if="cfg.notice" class="login-notice" role="status">
        {{ cfg.notice }}
      </div>

      <p v-if="oidcError" class="oidc-error" role="alert">
        {{ oidcError }}
      </p>

      <header class="login-header">
        <router-link class="login-mark-link" to="/login" aria-label="回到登录首页">
          <svg class="login-mark" viewBox="0 0 24 24" aria-hidden="true">
            <g stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
              <line x1="12" y1="2.6" x2="12" y2="21.4" />
              <line x1="2.6" y1="12" x2="21.4" y2="12" />
              <line x1="5.3" y1="5.3" x2="18.7" y2="18.7" />
              <line x1="18.7" y1="5.3" x2="5.3" y2="18.7" />
            </g>
          </svg>
        </router-link>
        <h1 id="login-title">{{ headerTitle }}</h1>
        <p>{{ headerSubtitle }}</p>
      </header>

      <t-loading :loading="loading" class="login-loading">
        <t-form
          v-if="setupNeeded"
          ref="setupFormRef"
          :data="setupForm"
          :label-width="0"
          :rules="setupRules"
          class="login-form"
          @submit="onSetupSubmit"
        >
          <div class="form-field">
            <label for="setup-username">管理员用户名</label>
            <t-form-item name="username">
              <t-input
                id="setup-username"
                :model-value="setupAdminUsername"
                readonly
                disabled
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div class="form-field">
            <label for="setup-password">管理员密码</label>
            <t-form-item name="password">
              <t-input
                id="setup-password"
                v-model="setupForm.password"
                type="password"
                autocomplete="new-password"
                placeholder="请设置高强度密码"
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div class="form-field">
            <label for="setup-confirm-password">确认密码</label>
            <t-form-item name="confirm_password">
              <t-input
                id="setup-confirm-password"
                v-model="setupForm.confirm_password"
                type="password"
                autocomplete="new-password"
                placeholder="请再次输入密码"
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div v-if="turnstileEnabled" class="turnstile-field">
            <div ref="turnstileContainer" class="turnstile-widget"></div>
            <p v-if="turnstileError" class="turnstile-error" role="alert">
              {{ turnstileError }}
            </p>
          </div>

          <t-form-item class="submit-item">
            <t-button
              type="submit"
              size="large"
              class="login-button"
              :disabled="loading || (turnstileEnabled && !turnstileToken)"
            >
              创建管理员并进入
            </t-button>
          </t-form-item>
        </t-form>

        <t-form
          v-else
          ref="loginFormRef"
          :data="loginForm"
          :label-width="0"
          :rules="rules"
          class="login-form"
          @submit="onSubmit"
        >
          <div class="form-field">
            <label for="login-username">用户名</label>
            <t-form-item name="username">
              <t-input
                id="login-username"
                v-model="loginForm.username"
                autocomplete="username"
                placeholder="请输入用户名"
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div class="form-field">
            <label for="login-password">密码</label>
            <t-form-item name="password">
              <t-input
                id="login-password"
                v-model="loginForm.password"
                type="password"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                placeholder="请输入密码"
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div v-if="isRegister" class="form-field">
            <label for="register-upstream-token">上游账号令牌</label>
            <t-form-item name="chatgpt_token">
              <t-textarea
                id="register-upstream-token"
                v-model="loginForm.chatgpt_token"
                placeholder="请粘贴用于绑定的账号令牌"
                :autosize="{ minRows: 3, maxRows: 5 }"
              ></t-textarea>
            </t-form-item>
          </div>

          <div v-if="turnstileEnabled" class="turnstile-field">
            <div ref="turnstileContainer" class="turnstile-widget"></div>
            <p v-if="turnstileError" class="turnstile-error" role="alert">
              {{ turnstileError }}
            </p>
          </div>

          <t-form-item class="submit-item">
            <t-button
              type="submit"
              size="large"
              class="login-button"
              :disabled="loading || (turnstileEnabled && !turnstileToken)"
            >
              {{ isRegister ? '创建账户' : '登录' }}
            </t-button>
          </t-form-item>
        </t-form>
      </t-loading>

      <template v-if="!setupNeeded">
        <p class="account-switch">
          <template v-if="isRegister">
            已有账户？
            <router-link to="/login">登录</router-link>
          </template>
          <template v-else>
            还没有账户？
            <router-link to="/register">创建账户</router-link>
          </template>
        </p>

        <div class="login-divider" aria-hidden="true">
          <span>或</span>
        </div>

        <button
          class="free-button"
          type="button"
          :disabled="loading || (turnstileEnabled && !turnstileToken)"
          @click="goFree"
        >
          免费体验
        </button>

        <button
          v-if="!isRegister && cfg.oidc_enabled"
          class="free-button sso-button"
          type="button"
          :disabled="loading || ssoLoading"
          @click="goOidc"
        >
          {{ ssoLoading ? '正在跳转…' : `使用 ${cfg.oidc_display_name || 'SSO'} 登录` }}
        </button>
      </template>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(false)
const route = useRoute()
const router = useRouter()
type TurnstileApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string
  reset: (widgetId: string) => void
  remove: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

const cfg = ref({
  show_github: true,
  notice: '',
  turnstile_enabled: false,
  turnstile_site_key: '',
  oidc_enabled: false,
  oidc_display_name: 'SSO'
})

const OIDC_ERROR_MESSAGES: Record<string, string> = {
  disabled: 'OIDC 登录未启用',
  config: '回调地址未正确配置，请联系管理员',
  provider: '无法连接身份提供方，请稍后重试',
  state: '登录会话已失效，请重新登录',
  token: '身份验证失败，请重新登录',
  no_account: '该账号尚未开通镜像权限，请联系管理员',
  conflict: '该账号不能自动绑定，请联系管理员',
  inactive: '账号已停用，请联系管理员',
  expired: '账号已过期，请联系管理员'
}
const oidcError = ref('')
const ssoLoading = ref(false)
const setupNeeded = ref(false)
const setupAdminUsername = ref('')
const setupFormRef = ref()
const setupForm = reactive({
  password: '',
  confirm_password: ''
})
const loginFormRef = ref()
const turnstileContainer = ref<HTMLElement | null>(null)
const turnstileToken = ref('')
const turnstileError = ref('')
const turnstileWidgetId = ref<string | null>(null)
let turnstileInvalidationRevision = 0

const loginForm = reactive({
  username: '',
  password: '',
  chatgpt_token: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  chatgpt_token: [{ required: true, message: '请输入上游账号令牌', trigger: 'blur' }]
}

const isRegister = computed(() => {
  return route.path.endsWith('/register')
})
const turnstileEnabled = computed(() => {
  return cfg.value.turnstile_enabled && Boolean(cfg.value.turnstile_site_key)
})
const turnstileAction = computed(() => {
  if (setupNeeded.value) return 'setup'
  return isRegister.value ? 'register' : 'login'
})
const headerTitle = computed(() => {
  if (setupNeeded.value) return '创建管理员'
  return isRegister.value ? '创建账户' : '欢迎回来'
})
const headerSubtitle = computed(() => {
  if (setupNeeded.value) return '首次使用，请先创建管理员账号'
  return isRegister.value ? '填写账号信息以完成注册' : '输入账号信息以继续'
})
const setupRules = {
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  confirm_password: [{ required: true, message: '请再次输入密码', trigger: 'blur' }]
}

let turnstileScriptPromise: Promise<void> | null = null

const loadTurnstileScript = () => {
  if (window.turnstile) return Promise.resolve()
  if (turnstileScriptPromise) return turnstileScriptPromise

  turnstileScriptPromise = new Promise<void>((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>('script[data-turnstile-script]')
    if (existingScript) {
      existingScript.remove()
    }

    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.dataset.turnstileScript = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('load failed'))
    document.head.appendChild(script)
  }).catch((error) => {
    turnstileScriptPromise = null
    throw error
  })

  return turnstileScriptPromise
}

const removeTurnstile = () => {
  turnstileInvalidationRevision += 1
  if (turnstileWidgetId.value && window.turnstile) {
    window.turnstile.remove(turnstileWidgetId.value)
  }
  turnstileWidgetId.value = null
  turnstileToken.value = ''
}

const renderTurnstile = async () => {
  if (!turnstileEnabled.value) return

  turnstileError.value = ''
  try {
    await loadTurnstileScript()
    await nextTick()
    if (!window.turnstile || !turnstileContainer.value) return

    removeTurnstile()
    turnstileWidgetId.value = window.turnstile.render(turnstileContainer.value, {
      sitekey: cfg.value.turnstile_site_key,
      action: turnstileAction.value,
      theme: 'light',
      size: 'flexible',
      appearance: 'always',
      callback: (token: string) => {
        turnstileToken.value = token
        turnstileError.value = ''
      },
      'expired-callback': () => {
        turnstileInvalidationRevision += 1
        turnstileToken.value = ''
        turnstileError.value = '验证已过期，请重新验证'
      },
      'error-callback': () => {
        turnstileInvalidationRevision += 1
        turnstileToken.value = ''
        turnstileError.value = '人机验证加载失败，请刷新页面'
      }
    })
  } catch {
    turnstileError.value = '人机验证加载失败，请刷新页面'
  }
}

onMounted(async () => {
  readOidcError()
  if (route.query.logout === '1') {
    try {
      await userStore.logout()
    } catch (error: any) {
      MessagePlugin.error(error.message || '退出未完成，请重试')
    }
  }
  await getVersionCfg()
  await getSetupStatus()
  await renderTurnstile()
})

const getSetupStatus = async () => {
  try {
    const response = await fetch('/0x/user/setup-status')
    const data = await response.json()
    setupNeeded.value = Boolean(data.needed)
    setupAdminUsername.value = data.admin_username || ''
  } catch (e) {
    console.error('Failed to get setup status')
  }
}

const onSetupSubmit = async ({ validateResult }: any) => {
  if (validateResult !== true) return
  if (loading.value) return
  if (turnstileEnabled.value && !turnstileToken.value) {
    MessagePlugin.warning('请完成人机验证')
    return
  }

  if (setupForm.password !== setupForm.confirm_password) {
    MessagePlugin.error('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    await userStore.setupAdmin({
      password: setupForm.password,
      confirm_password: setupForm.confirm_password,
      turnstile_token: turnstileToken.value
    })
    router.push({ name: 'User' })
  } catch (error: any) {
    MessagePlugin.error(error.message || '初始化失败')
    await renderTurnstile()
  }
  loading.value = false
}

watch(isRegister, async () => {
  if (turnstileEnabled.value) {
    removeTurnstile()
    await renderTurnstile()
  }
})

onBeforeUnmount(() => {
  removeTurnstile()
})

const getVersionCfg = async () => {
  try {
    const response = await fetch('/0x/user/version-cfg')
    const data = await response.json()
    Object.assign(cfg.value, data)
  } catch (e) {
    console.error('Failed to get version config')
  }
}

const readOidcError = () => {
  const code = String(route.query.oidc_error || '')
  if (!code) return
  // Keep the code in the address bar so it can be read out while troubleshooting.
  oidcError.value = `${OIDC_ERROR_MESSAGES[code] || '登录失败，请稍后重试'}（${code}）`
}

const goOidc = async () => {
  if (loading.value || ssoLoading.value) return
  ssoLoading.value = true
  try {
    const response = await fetch('/0x/user/oidc/login', { cache: 'no-store' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || !data.authorize_url) {
      throw new Error(data.message || 'SSO 登录暂不可用')
    }
    window.location.assign(data.authorize_url)
  } catch (error: any) {
    MessagePlugin.error(error.message || 'SSO 登录暂不可用')
    ssoLoading.value = false
  }
}

const onSubmit = async ({ validateResult }: any) => {
  if (validateResult === true) {
    if (loading.value) return
    if (turnstileEnabled.value && !turnstileToken.value) {
      MessagePlugin.warning('请完成人机验证')
      return
    }

    loading.value = true
    const submittedTurnstileToken = turnstileToken.value
    const submittedInvalidationRevision = turnstileInvalidationRevision
    try {
      const url = isRegister.value ? '/0x/user/register' : '/0x/user/login'
      const credentials = isRegister.value
        ? {
            username: loginForm.username,
            password: loginForm.password,
            chatgpt_token: loginForm.chatgpt_token
          }
        : {
            username: loginForm.username,
            password: loginForm.password
          }
      const data = await userStore.login(url, {
        ...credentials,
        turnstile_token: submittedTurnstileToken
      }, () => {
        if (turnstileEnabled.value && turnstileInvalidationRevision !== submittedInvalidationRevision) {
          throw new Error('人机验证已失效，请重新验证')
        }
        // The verified challenge has been accepted; the server now checks the short-lived ticket.
        removeTurnstile()
      })

      if (data.authenticated && data.is_admin) {
        router.push({ name: 'User' })
      } else if (data.authenticated) {
        router.push({ name: 'LoginChatgpt' })
      }
    } catch (error: any) {
      MessagePlugin.error(error.message || '操作失败')
      await renderTurnstile()
    }
    loading.value = false
  }
}

const goFree = async () => {
  if (loading.value) return
  if (turnstileEnabled.value && !turnstileToken.value) {
    MessagePlugin.warning('请完成人机验证')
    return
  }

  loading.value = true
  const submittedTurnstileToken = turnstileToken.value
  const submittedInvalidationRevision = turnstileInvalidationRevision
  try {
    const data = await userStore.login('/0x/user/login-free', {
      turnstile_token: submittedTurnstileToken
    }, () => {
      if (turnstileEnabled.value && turnstileInvalidationRevision !== submittedInvalidationRevision) {
        throw new Error('人机验证已失效，请重新验证')
      }
      removeTurnstile()
    })
    if (data.authenticated) {
      router.push({ name: 'LoginChatgpt' })
    }
  } catch (error: any) {
    MessagePlugin.error(error.message || '免费体验暂不可用')
    await renderTurnstile()
  }
  loading.value = false
}
</script>

<style scoped>
.login-page {
  --login-bg: #f5f3ec;
  --login-surface: #ffffff;
  --login-text: #29261f;
  --login-muted: #736f62;
  --login-border: #ddd7c4;
  --login-border-hover: #b8b19d;
  --login-action: #c15f3c;

  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 48px 24px;
  color: var(--login-text);
  background:
    radial-gradient(1100px 520px at 85% -12%, rgba(193, 95, 60, 0.07), transparent 62%),
    radial-gradient(900px 480px at 6% 112%, rgba(82, 122, 91, 0.06), transparent 62%),
    var(--login-bg);
}

.login-panel {
  width: 100%;
  max-width: 380px;
  animation: login-in 0.45s cubic-bezier(0.22, 0.9, 0.32, 1) both;
}

@keyframes login-in {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}

.login-notice {
  margin-bottom: 24px;
  padding: 12px 14px;
  color: #6b6656;
  font-size: 14px;
  line-height: 1.5;
  background: #f2efe4;
  border: 1px solid #e5e0d0;
  border-radius: 10px;
}

.login-header {
  margin-bottom: 32px;
  text-align: center;
}

.login-mark-link {
  display: inline-block;
  margin-bottom: 18px;
  border-radius: 10px;
}

.login-mark {
  display: block;
  width: 34px;
  height: 34px;
  color: var(--login-action);
  transition: transform 0.35s cubic-bezier(0.22, 0.9, 0.32, 1);
}

.login-mark-link:hover .login-mark {
  transform: rotate(45deg);
}

.login-header h1 {
  margin: 0;
  font-family: var(--app-font-serif);
  font-size: 34px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: 0.01em;
  text-wrap: balance;
}

.login-header p {
  margin: 12px 0 0;
  color: var(--login-muted);
  font-size: 15px;
  line-height: 1.6;
}

.login-loading {
  display: block;
  width: 100%;
}

.form-field {
  margin-bottom: 20px;
}

.form-field label {
  display: inline-block;
  margin-bottom: 8px;
  color: #4a463c;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.form-field :deep(.t-form__item) {
  margin-bottom: 0;
}

.form-field :deep(.t-input) {
  min-height: 50px;
  padding: 0 14px;
  color: var(--login-text);
  background: var(--login-surface);
  border-color: var(--login-border);
  border-radius: 12px;
  box-shadow: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.form-field :deep(.t-textarea) {
  padding: 12px 14px;
  background: var(--login-surface);
  border-color: var(--login-border);
  border-radius: 12px;
  box-shadow: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.form-field :deep(.t-textarea:hover) {
  border-color: var(--login-border-hover);
}

.form-field :deep(.t-textarea--focused) {
  border-color: var(--login-action);
  box-shadow: 0 0 0 3px rgba(193, 95, 60, 0.16);
}

.form-field :deep(.t-textarea__inner) {
  color: var(--login-text);
  font-size: 15px;
  line-height: 1.6;
}

.form-field :deep(.t-input:hover) {
  border-color: var(--login-border-hover);
}

.form-field :deep(.t-input--focused) {
  border-color: var(--login-action);
  box-shadow: 0 0 0 3px rgba(193, 95, 60, 0.16);
}

.form-field :deep(.t-input__inner) {
  color: var(--login-text);
  font-size: 16px;
}

.form-field :deep(.t-form__controls-content) {
  display: block;
}

.form-field :deep(.t-form__status) {
  margin-top: 7px;
  font-size: 13px;
}

.submit-item {
  margin: 28px 0 0;
}

.submit-item :deep(.t-form__controls-content) {
  display: block;
}

.turnstile-field {
  min-height: 65px;
  margin-top: 4px;
}

.turnstile-widget {
  width: 100%;
  min-height: 65px;
}

.turnstile-error {
  margin: 8px 0 0;
  color: #b5402f;
  font-size: 13px;
  line-height: 1.5;
}

.login-button {
  width: 100%;
  height: 50px;
  color: #fbf7f0;
  font-size: 15px;
  font-weight: 600;
  background: var(--login-action);
  border-color: var(--login-action);
  border-radius: 999px;
  box-shadow: none;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.login-button:hover {
  color: #fbf7f0;
  background: #ac5232;
  border-color: #ac5232;
  transform: translateY(-1px);
}

.login-button:active {
  background: #96452a;
  border-color: #96452a;
  transform: translateY(1px);
}

.login-button:focus-visible,
.free-button:focus-visible,
.account-switch a:focus-visible {
  outline: 2px solid var(--login-action);
  outline-offset: 3px;
}

.account-switch {
  margin: 22px 0 0;
  text-align: center;
  color: var(--login-muted);
  font-size: 14px;
  line-height: 22px;
}

.account-switch a {
  color: var(--login-action);
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: #dfc3b3;
  text-underline-offset: 3px;
}

.account-switch a:hover {
  color: #ac5232;
  text-decoration-color: #ac5232;
}

.login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 24px 0;
  color: #9a9484;
  font-size: 13px;
}

.login-divider::before,
.login-divider::after {
  flex: 1;
  height: 1px;
  background: #e0dac6;
  content: "";
}

.free-button {
  width: 100%;
  height: 50px;
  padding: 0 16px;
  color: var(--login-text);
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  background: var(--login-surface);
  border: 1px solid var(--login-border);
  border-radius: 999px;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.free-button:hover:not(:disabled) {
  background: #f3f0e6;
  border-color: var(--login-border-hover);
  transform: translateY(-1px);
}

.free-button:active:not(:disabled) {
  transform: translateY(1px);
}

.free-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.sso-button {
  margin-top: 12px;
}

.oidc-error {
  margin: 0 0 24px;
  padding: 12px 14px;
  color: #a3413a;
  font-size: 14px;
  line-height: 1.5;
  background: #fbeeea;
  border: 1px solid #f0d6cd;
  border-radius: 10px;
}

@media (max-width: 520px) {
  .login-page {
    align-items: flex-start;
    padding: 72px 24px 40px;
  }

  .login-header {
    margin-bottom: 28px;
  }

  .login-header h1 {
    font-size: 30px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-page *,
  .login-page *::before,
  .login-page *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
