<template>
  <div class="settings-stack">
    <t-card title="访问限制" subtitle="阻止用户进入指定路径" bordered>
      <template #subtitle>
        支持普通路径和 # 哈希路径；命中路径及其子路径都会被拦截
      </template>
      <div class="section">
        <h4>当前拦截路径</h4>
        <t-tag
          v-for="(path, index) in blockedPaths"
          :key="index"
          closable
          style="margin: 4px"
          theme="danger"
          @close="removePath(index)"
        >
          {{ path }}
        </t-tag>
        <div v-if="blockedPaths.length === 0" class="empty-text">
          暂无拦截路径
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>添加新的拦截路径</h4>
        <t-space style="margin-top: 12px">
          <t-input
            v-model="newPath"
            aria-label="拦截路径"
            placeholder="例如 #settings/Account 或 library"
            :maxlength="512"
            style="width: 300px"
            @keyup.enter="addPath"
          />
          <t-button theme="primary" @click="addPath">添加</t-button>
        </t-space>
        <div class="field-help">
          无需输入开头的 /；不能填写完整 URL 或查询参数；保存后已打开页面会自动同步
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>预设拦截模板</h4>
        <t-space style="margin-top: 12px; flex-wrap: wrap">
          <t-button
            v-for="preset in presets"
            :key="preset"
            variant="outline"
            size="small"
            :disabled="hasPath(preset)"
            @click="addPreset(preset)"
          >
            {{ preset }}
          </t-button>
        </t-space>
      </div>

      <t-divider />

      <t-button theme="primary" :loading="saving" @click="save">
        保存配置
      </t-button>
      <span v-if="saved" class="saved-text">已保存</span>
    </t-card>

    <t-card title="登录人机验证" subtitle="Cloudflare Turnstile" bordered>
      <template #subtitle>
        开启后，每次登录、免费体验和注册都必须先通过验证
      </template>

      <div class="security-status">
        <div>
          <div class="status-title">当前状态</div>
          <div class="status-description">
            生效来源：{{ turnstileSourceLabel }}
          </div>
        </div>
        <t-tag :theme="turnstileCfg.enabled ? 'success' : 'default'" variant="light">
          {{ turnstileCfg.enabled ? '已开启' : '未开启' }}
        </t-tag>
      </div>

      <template v-if="canEditSecurity">
        <div class="section">
          <h4>站点密钥</h4>
          <t-input
            v-model="turnstileForm.turnstile_site_key"
            aria-label="站点密钥"
            placeholder="0x4AAAAAAA..."
            :maxlength="256"
          />
          <div class="field-help">站点密钥是唯一会下发到浏览器的那个，可以随时更换</div>
        </div>

        <div class="section">
          <h4>密钥</h4>
          <t-input
            v-model="turnstileForm.turnstile_secret_key"
            aria-label="密钥"
            type="password"
            :maxlength="256"
            :placeholder="turnstileCfg.secretConfigured ? '已保存，留空表示不修改' : '请输入密钥'"
          />
          <div class="field-help">密钥只留在服务端，不会出现在任何接口响应中</div>
        </div>

        <t-divider />

        <t-button theme="primary" :loading="savingTurnstile" @click="saveTurnstile">
          保存人机验证配置
        </t-button>
        <span v-if="turnstileSaved" class="saved-text">已保存</span>

        <t-alert
          class="security-note"
          message="保存的值优先于 .env；清空站点密钥保存即把这一对交还给 .env，因此由 .env 提供的那一对只能在 .env 里关闭。"
        />
      </template>

      <t-alert
        v-else
        class="security-note"
        message="只有超级管理员可以修改人机验证配置。"
      />
    </t-card>

    <t-card title="OIDC 单点登录" subtitle="OpenID Connect Provider" bordered>
      <template #subtitle>
        开启后，登录页会出现「使用身份提供方登录」按钮
      </template>

      <div class="security-status">
        <div>
          <div class="status-title">当前状态</div>
          <div class="status-description">
            生效来源：{{ oidcSourceLabel }}
          </div>
        </div>
        <t-tag :theme="oidcCfg.enabled ? 'success' : 'default'" variant="light">
          {{ oidcCfg.enabled ? '已开启' : '未开启' }}
        </t-tag>
      </div>

      <template v-if="canEditSecurity">
        <div class="section">
          <h4>Issuer</h4>
          <t-input
            v-model="oidcForm.oidc_issuer"
            aria-label="Issuer"
            placeholder="https://id.example.com/realms/main"
            :maxlength="255"
          />
          <div class="field-help">填到 realm/租户一级；镜像会自动读取其 discovery 文档</div>
        </div>

        <div class="section">
          <h4>Client ID</h4>
          <t-input v-model="oidcForm.oidc_client_id" aria-label="Client ID" :maxlength="256" />
        </div>

        <div class="section">
          <h4>Client Secret</h4>
          <t-input
            v-model="oidcForm.oidc_client_secret"
            aria-label="Client Secret"
            type="password"
            :maxlength="512"
            :placeholder="oidcCfg.secretConfigured ? '已保存，留空表示不修改' : '请输入密钥'"
          />
          <div class="field-help">密钥只留在服务端，不会出现在任何接口响应中</div>
        </div>

        <div class="section">
          <h4>回调地址</h4>
          <t-input
            v-model="oidcForm.oidc_redirect_uri"
            aria-label="回调地址"
            :maxlength="300"
            :placeholder="oidcCfg.redirectUriSuggested || 'https://你的域名/0x/user/oidc/callback'"
          />
          <div class="field-help">
            留空则自动推导为 {{ oidcCfg.redirectUriSuggested || '（当前无法推导，请手动填写）' }}；在 IdP 侧登记的回调地址就是它
          </div>
        </div>

        <div class="section">
          <h4>Scopes</h4>
          <t-input v-model="oidcForm.oidc_scopes" aria-label="Scopes" :maxlength="256" />
          <div class="field-help">必须包含 openid；需要用户名/邮箱时保留 profile email</div>
        </div>

        <div class="section">
          <h4>显示名称</h4>
          <t-input
            v-model="oidcForm.oidc_display_name"
            aria-label="显示名称"
            :maxlength="32"
            placeholder="SSO"
          />
          <div class="field-help">登录页按钮上显示的名字，例如 Keycloak</div>
        </div>

        <div class="section">
          <h4>用户名声明</h4>
          <t-input
            v-model="oidcForm.oidc_username_claim"
            aria-label="用户名声明"
            :maxlength="64"
            placeholder="preferred_username"
          />
          <div class="field-help">用于把身份绑定到镜像用户名；留空按 preferred_username 处理</div>
        </div>

        <div class="section">
          <h4>开通策略</h4>
          <t-space direction="vertical" size="12px">
            <t-checkbox v-model="oidcForm.oidc_auto_provision">
              自动开通新用户（首次登录自动创建，无上游账号，需管理员分号池）
            </t-checkbox>
            <t-checkbox v-model="oidcForm.oidc_auto_link_by_username">
              按用户名自动绑定既有镜像用户
            </t-checkbox>
            <t-checkbox v-model="oidcForm.oidc_link_admins">
              允许自动绑定管理员账号（有接管超管风险，确认 IdP 可信后再开启）
            </t-checkbox>
          </t-space>
        </div>

        <t-divider />

        <t-button theme="primary" :loading="savingOidc" @click="saveOidc">
          保存 OIDC 配置
        </t-button>
        <span v-if="oidcSaved" class="saved-text">已保存</span>

        <t-alert
          class="security-note"
          message="保存的值优先于 .env；清空 Issuer 保存即把整套配置交还给 .env。退出登录只结束镜像会话，不会结束 IdP 的 SSO 会话。"
        />
      </template>

      <t-alert
        v-else
        class="security-note"
        message="只有超级管理员可以修改 OIDC 配置。"
      />
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const blockedPaths = ref<string[]>([])
const newPath = ref('')
const saving = ref(false)
const saved = ref(false)
const turnstileCfg = ref({
  enabled: false,
  siteKeyConfigured: false,
  secretConfigured: false,
  source: '',
  revision: 0
})
const turnstileForm = reactive({
  turnstile_site_key: '',
  turnstile_secret_key: ''
})
const savingTurnstile = ref(false)
const turnstileSaved = ref(false)
const canEditSecurity = computed(() => userStore.isSuperuser)
const oidcCfg = ref({
  enabled: false,
  source: '',
  secretConfigured: false,
  revision: 0,
  redirectUriSuggested: ''
})
const oidcForm = reactive({
  oidc_issuer: '',
  oidc_client_id: '',
  oidc_client_secret: '',
  oidc_scopes: 'openid profile email',
  oidc_display_name: 'SSO',
  oidc_redirect_uri: '',
  oidc_username_claim: 'preferred_username',
  oidc_auto_provision: true,
  oidc_auto_link_by_username: true,
  oidc_link_admins: false
})
const savingOidc = ref(false)
const oidcSaved = ref(false)
const oidcSourceLabel = computed(() => {
  if (!oidcCfg.value.enabled) return '未启用'
  return oidcCfg.value.source === 'panel' ? '面板配置' : '.env 环境变量'
})
const turnstileSourceLabel = computed(() => {
  if (!turnstileCfg.value.enabled) return '未启用'
  return turnstileCfg.value.source === 'panel' ? '面板配置' : '.env 环境变量'
})

const presets = [
  '#settings/Personalization',
  '#settings/Security',
  '#settings/Billing',
  '#settings/Account',
  '#settings/Safety',
  '#pricing',
]

onMounted(async () => {
  const [data, versionResponse] = await Promise.all([
    request('/0x/user/access-control'),
    fetch('/0x/user/version-cfg').then(response => response.json()).catch(() => null)
  ])
  if (data) blockedPaths.value = (data.paths || data.hash_paths || []).map(toDisplayPath)
  if (versionResponse) {
    turnstileCfg.value.enabled = Boolean(versionResponse.turnstile_enabled)
    turnstileCfg.value.siteKeyConfigured = Boolean(versionResponse.turnstile_site_key)
  }
  if (canEditSecurity.value) {
    await loadTurnstileConfig()
    await loadOidcConfig()
  }
})

async function loadOidcConfig() {
  const data = await request('/0x/user/oidc-config')
  if (!data) return
  oidcCfg.value.enabled = Boolean(data.active_enabled)
  oidcCfg.value.source = data.active_source || ''
  oidcCfg.value.secretConfigured = Boolean(data.secret_configured)
  oidcCfg.value.revision = data.revision ?? 0
  oidcCfg.value.redirectUriSuggested = data.redirect_uri_suggested || ''
  oidcForm.oidc_issuer = data.oidc_issuer || ''
  oidcForm.oidc_client_id = data.oidc_client_id || ''
  oidcForm.oidc_scopes = data.oidc_scopes || 'openid profile email'
  oidcForm.oidc_display_name = data.oidc_display_name || 'SSO'
  oidcForm.oidc_redirect_uri = data.oidc_redirect_uri || ''
  oidcForm.oidc_username_claim = data.oidc_username_claim || 'preferred_username'
  oidcForm.oidc_auto_provision = Boolean(data.oidc_auto_provision)
  oidcForm.oidc_auto_link_by_username = Boolean(data.oidc_auto_link_by_username)
  oidcForm.oidc_link_admins = Boolean(data.oidc_link_admins)
  oidcForm.oidc_client_secret = ''
}

async function saveOidc() {
  savingOidc.value = true
  oidcSaved.value = false
  const payload: Record<string, unknown> = {
    revision: oidcCfg.value.revision,
    oidc_issuer: oidcForm.oidc_issuer.trim(),
    oidc_client_id: oidcForm.oidc_client_id.trim(),
    oidc_scopes: oidcForm.oidc_scopes.trim(),
    oidc_display_name: oidcForm.oidc_display_name.trim(),
    oidc_redirect_uri: oidcForm.oidc_redirect_uri.trim(),
    oidc_username_claim: oidcForm.oidc_username_claim.trim(),
    oidc_auto_provision: oidcForm.oidc_auto_provision,
    oidc_auto_link_by_username: oidcForm.oidc_auto_link_by_username,
    oidc_link_admins: oidcForm.oidc_link_admins
  }
  if (oidcForm.oidc_client_secret) {
    payload.oidc_client_secret = oidcForm.oidc_client_secret
  }

  const data = await request('/0x/user/oidc-config', 'PUT', payload)
  if (data) {
    oidcCfg.value.enabled = Boolean(data.active_enabled)
    oidcCfg.value.source = data.active_source || ''
    oidcCfg.value.secretConfigured = Boolean(data.secret_configured)
    oidcCfg.value.revision = data.revision ?? oidcCfg.value.revision
    oidcCfg.value.redirectUriSuggested = data.redirect_uri_suggested || ''
    oidcForm.oidc_client_secret = ''
    oidcSaved.value = true
    MessagePlugin.success('OIDC 配置已保存')
  }
  savingOidc.value = false
}

async function loadTurnstileConfig() {
  const data = await request('/0x/user/turnstile-config')
  if (!data) return
  turnstileCfg.value.enabled = Boolean(data.active_enabled)
  turnstileCfg.value.source = data.active_source || ''
  turnstileCfg.value.secretConfigured = Boolean(data.secret_configured)
  turnstileCfg.value.revision = data.revision ?? 0
  turnstileForm.turnstile_site_key = data.turnstile_site_key || ''
}

async function saveTurnstile() {
  savingTurnstile.value = true
  turnstileSaved.value = false
  const payload: Record<string, unknown> = {
    revision: turnstileCfg.value.revision,
    turnstile_site_key: turnstileForm.turnstile_site_key.trim()
  }
  if (turnstileForm.turnstile_secret_key) {
    payload.turnstile_secret_key = turnstileForm.turnstile_secret_key
  }

  const data = await request('/0x/user/turnstile-config', 'PUT', payload)
  if (data) {
    turnstileCfg.value.enabled = Boolean(data.active_enabled)
    turnstileCfg.value.source = data.active_source || ''
    turnstileCfg.value.secretConfigured = Boolean(data.secret_configured)
    turnstileCfg.value.revision = data.revision ?? turnstileCfg.value.revision
    turnstileForm.turnstile_site_key = data.turnstile_site_key || ''
    turnstileForm.turnstile_secret_key = ''
    turnstileSaved.value = true
    MessagePlugin.success('人机验证配置已保存')
  }
  savingTurnstile.value = false
}

function addPath() {
  const rawPath = newPath.value.trim()
  const validationError = validatePath(rawPath)
  if (validationError) {
    MessagePlugin.warning(validationError)
    return
  }
  const p = toDisplayPath(rawPath)
  if (!p) return
  if (blockedPaths.value.length >= 200) {
    MessagePlugin.warning('拦截路径最多允许 200 条')
    return
  }
  if (hasPath(p)) {
    MessagePlugin.warning('路径已存在')
    return
  }
  blockedPaths.value.push(p)
  newPath.value = ''
  saved.value = false
}

function removePath(index: number) {
  blockedPaths.value.splice(index, 1)
  saved.value = false
}

function addPreset(p: string) {
  if (!hasPath(p)) {
    blockedPaths.value.push(p)
    saved.value = false
  }
}

function pathKey(path: string) {
  return toDisplayPath(path).replace(/\/+$/, '')
}

function toDisplayPath(path: string) {
  return path.trim().replace(/^\/+/, '')
}

function validatePath(path: string) {
  if (path.length > 512) return '单条拦截路径不能超过 512 个字符'
  if (!path || path === '/') return '不能拦截站点根路径'
  if (/[^\x21-\x7e]/.test(path)) return '拦截路径只能包含不带空白的 ASCII 字符'
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(path) || path.startsWith('//')) {
    return '请填写站内路径，不能填写完整 URL'
  }
  const normalized = toDisplayPath(path)
  if (normalized.includes('\\') || normalized.split('/').some(segment => segment === '.' || segment === '..')) {
    return '拦截路径不能包含反斜杠或相对路径段'
  }
  if (normalized.includes('?')) return '拦截路径不能包含查询参数'
  if (normalized.includes('#') && !normalized.startsWith('#')) return '# 只能用于开头的哈希路径'
  if (normalized === '#') return '哈希路径不能只有 #'
  const lower = normalized.toLowerCase()
  if (lower === '#settings/plugins' || lower.startsWith('#settings/plugins/')) {
    return '#settings/Plugins 是系统保留路径，不能拦截'
  }
  return ''
}

function hasPath(path: string) {
  const key = pathKey(path)
  return blockedPaths.value.some(item => pathKey(item) === key)
}

async function save() {
  saving.value = true
  saved.value = false
  const data = await request('/0x/user/access-control', 'POST', { paths: blockedPaths.value })
  if (data) {
    blockedPaths.value = (data.paths || data.hash_paths || blockedPaths.value).map(toDisplayPath)
    saved.value = true
    MessagePlugin.success('配置已保存')
  } else {
    MessagePlugin.error('保存失败')
  }
  saving.value = false
}
</script>

<style scoped>
.settings-stack {
  display: grid;
  gap: 20px;
}

.section {
  padding: 8px 0;
}

.section h4 {
  margin: 0 0 8px 0;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 600;
}

.empty-text,
.field-help {
  color: var(--app-text-muted);
  font-size: 13px;
}

.empty-text {
  padding: 12px 0;
}

.field-help {
  margin-top: 6px;
}

.saved-text {
  margin-left: 10px;
  color: var(--app-success);
  font-size: 13px;
}

.security-status {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.status-title {
  color: var(--app-text);
  font-size: 15px;
  font-weight: 600;
}

.status-description {
  margin-top: 6px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.env-list {
  margin-top: 22px;
  overflow: hidden;
  border: 1px solid var(--app-border);
  border-radius: 9px;
}

.env-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 48px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-border);
}

.env-row:last-child {
  border-bottom: 0;
}

.env-row code {
  color: var(--app-text);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.env-row span {
  flex: none;
  color: var(--app-text-muted);
  font-size: 13px;
}

.security-note {
  margin-top: 18px;
}

@media (max-width: 640px) {
  .security-status,
  .env-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
