# ChatGPT Mirror

### 仅适合个人学习和个人研究用图


项目重点关注多用户使用、共享账号隔离、移动端兼容、弱网体验和日常运维，**仅适合个人学习、内部研究及其他获得合法授权的非商业场景。**

---

## 目录

- [技术栈](#技术栈)
- [功能概览](#功能概览)
- [效果展示](#效果展示)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [管理后台](#管理后台)
- [安全与使用边界](#安全与使用边界)
- [使用许可](#使用许可)
- [更新日志](#更新日志)

## 技术栈

- 管理后台：Vue 3、TypeScript、Vite、Pinia、TDesign Vue Next
- 管理服务：Python、Django 5.1、Django REST Framework
- 数据存储：SQLite
- 部署方式：Docker Compose

## 功能概览

- **用户与权限**：管理用户状态、访问权限、可用模型和使用限制。
- **账号管理**：集中维护 ChatGPT 账号，支持 Cookie 和 Refresh Token 两种录入方式。
- **号池分配**：通过账号池组织可用账号，并按用户分配访问范围。
- **共享账号隔离**：不同镜像用户共用上游账号时，尽可能隔离普通对话、归档、搜索、标题和删除操作 & MCP & skills。支持：**模型隔离**，**模型频率限制**
- **使用记录**：查看访问记录、使用次数和运行状态，便于日常管理与排查。
- **站点配置**：管理代理、连通性测试、自定义脚本和禁止访问路径。
- **多端兼容**：持续适配桌面浏览器、iPhone Safari 和 iPhone Chrome 等访问环境。
- **会话占用与排队**：成员进入上游账号时占用名额，可设置全局与单账号并发上限；达到上限的会话自动排队，名额释放后按先后顺序补位，空闲会话自动回收。
- **部署运维**：提供本地及 VPS 的 Docker Compose 编排，便于启动、更新和查看日志。支持通过邮件`SMTP`为定时检测到的已经失效的账号进行邮件推送服务。容器内常驻调度进程负责刷新上游凭据与每日清理过期数据。
- **OIDC 单点登录**：可接入外部身份提供方登录镜像（授权码 + PKCE），支持按用户名绑定既有用户与自动开通新用户。

## 效果展示

### 登录界面

![登录界面](./imageandvideo/登录界面.png)

### ChatGPT 界面

![ChatGPT 界面](./imageandvideo/gpt界面1.png)

### 禁止访问路径

![禁止访问路径示例](./imageandvideo/禁止访问路径示例.png)

### 操作演示


https://github.com/user-attachments/assets/07069457-27af-4b66-91ec-735703340abf


[▶ 查看演示视频](./imageandvideo/演示1.mp4)

> GitHub 页面无法直接播放视频时，可点击链接查看或下载原始文件。


### 最新版本降智情况（原生日本 IP）

![降智情况 2026-08-26](./imageandvideo/Snapzy_2026-08-26_12-43-58_266.png)


#### 降智及降智复测

![复测01](./imageandvideo/复测%2001.png)

![复测02](./imageandvideo/复测%2002.png)

#### GPT-Astra 降智复测

![复测03-GPT-Astra](./imageandvideo/复测-20160905-GPT-Astra.png)

添加项目隔离后降智复测

![添加项目隔离后降智复测](./imageandvideo/Snapzy_2026-08-27复测.png)

> 本降智测试已在最新版本中的“代理“界面开启**实验性**的“curl-impersonate“，实验模式造成的后果需自行承担


![实验模式](./imageandvideo/方案.png)


## 项目结构

```text
chatgpt-mirror/
├── backend/                 # 管理服务
├── frontend/                # 管理后台
├── imageandvideo/           # README 图片与演示视频
├── docker-compose.yml       # VPS 部署编排
└── FAQ.md                   # 常见问题
```

> 非开源组件未在项目结构中展开。

## 快速开始

### 环境要求

- Docker Engine
- Docker Compose v2
- 可用的 HTTPS 域名（生产环境推荐）

### 配置与启动

先在项目根目录复制示例配置：

```bash
cp .env.example .env
```


然后编辑 `.env`，至少替换以下示例值：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请替换为管理员强密码

GATEWAY_ADMIN_SECRET=请替换为独立随机密钥
DJANGO_SECRET_KEY=请替换为独立随机密钥
CREDENTIAL_ENCRYPTION_KEY=请替换为至少32位的独立随机密钥

DJANGO_ALLOW_ALL_ORIGINS=disable
DJANGO_ALLOWED_HOSTS=example.com,django,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com
LOCAL_NETWORK_ACCESS=disable

CLOUDFLARE_TURNSTILE=disable
CLOUDFLARE_TURNSTILE_SITE_KEY=
CLOUDFLARE_TURNSTILE_SECRET_KEY=
```

需要直接通过 `http://localhost:端口` 或 `http://局域网IP:端口` 访问时，可设置：

```env
LOCAL_NETWORK_ACCESS=enable
```

该开关会让 Gateway 允许任意 Django Host/Origin/Referer，并强制关闭
`DJANGO_SESSION_COOKIE_SECURE`、`DJANGO_CSRF_COOKIE_SECURE` 和 `COOKIE_SECURE`，因此不需要再分别设置这三个变量。
CSRF token 和登录鉴权仍然保留。此模式允许 Cookie 经明文 HTTP 传输，理论只应在可信本地或局域网使用；公网 HTTPS 部署须保持 `disable`。
除 `enable`、`disable` 外的值会导致服务拒绝启动。


请勿将真实密码、Cookie、Token 或 `.env` 文件提交到版本库。



常用命令

```bash
docker compose ps
docker compose logs -f
docker compose down
```

### 更新管理台前端

官方网关镜像里自带的管理台是上游那份旧构建，本仓库的前端改动不会出现在部署里。CI 会在每次提交时于官方网关镜像之上覆盖本仓库构建的管理台，发布为 `ghcr.io/ldm0206/chatgpt-mirror/frontend`（标签规则与 backend 镜像一致，main 分支为 `latest`），`docker-compose.yml` 默认就用它，部署时拉取即可：

```bash
docker compose pull chatgpt-mirror
```

```bash
docker compose up -d chatgpt-mirror
```

想固定某个版本时，在 `.env` 里设置 `FRONTEND_IMAGE=ghcr.io/ldm0206/chatgpt-mirror/frontend:sha-提交号`。需要本地构建镜像时：

```bash
cd frontend && npm ci && npm run build && cd .. && docker build -f frontend/Dockerfile -t chatgpt-mirror-frontend:local .
```

`frontend/Dockerfile` 只是在官方网关镜像上追加 `COPY gateway/static`，基础镜像可用 `--build-arg BASE_IMAGE=...` 覆盖。

### 使用 NGINX/Cloudflare 时记得开启 websocket 支持。并且 NGINX 要求填入以下内容，实现最大化的减少错误
### 错误出现
##### (400 Request Header Or Cookie Too Large、414 Request-URI Too Large)&(upstream sent too big header while reading response header from upstream)

### 解决方案：

``` 
proxy_buffer_size 128k;
proxy_buffers 8 128k;
proxy_busy_buffers_size 256k;
large_client_header_buffers 8 64k;
client_header_buffer_size 64k;
```


## 管理后台

登录后可以使用以下管理功能：

| 功能 | 说明 |
| --- | --- |
| 用户管理 | 维护用户状态、访问权限、使用限制 |
| ChatGPT 账号 | 添加、更新和检查账号状态，并在需要时手动刷新凭据 |
| 号池管理 | 对账号进行分组，并配置账号池与镜像用户的关联关系 |
| 访问日志 | 查看用户访问记录和运行情况，辅助定位异常问题 |
| 运维概览 | 查看会话占用与排队情况，断开指定会话，调整并发上限 |
| 代理管理 | 维护代理配置并执行连通性测试，支持按账号批量绑定代理节点 |
| 脚本管理 | 维护站点所需的自定义脚本配置 |
| 访问限制 | 配置不允许镜像用户访问的页面或功能范围，以及登录人机验证、OIDC 单点登录 |
| 外联防护 | 一键注入浏览器外联拦截脚本，阻断镜像页面直连官方/遥测端点导致的 IP 与指纹泄漏 |

### 首次访问创建管理员

`ADMIN_PASSWORD` 留空时，容器启动会跳过管理员初始化，改为首次访问网页时由向导创建（用户名取 `ADMIN_USERNAME`）。
此时**务必先在本地或内网完成创建再开放公网访问**，否则任何能打开页面的人都可以抢注管理员。填了 `ADMIN_PASSWORD` 则保持原有的启动时初始化行为。

### 登录人机验证

Cloudflare Turnstile 既可以用 `.env` 配置，也可以由超级管理员在“访问与安全”页面里保存。面板里有一个「启用人机验证」开关，它优先于 `.env`：打开时用面板里保存的那一对，面板没填则沿用 `.env` 那一对；关掉则强制关闭，即使 `.env` 里有一对密钥也不生效。把站点密钥清空保存，就把这一对交还给 `.env`。密钥只留在服务端，不会出现在任何接口响应里。

### OIDC 单点登录

超级管理员可在「访问与安全 → OIDC 单点登录」里配置一个 OpenID Connect Provider，也可以直接用 `.env` 的 `OIDC_*` 变量配置；启用后登录页出现「使用 xxx 登录」按钮。流程为标准授权码 + PKCE，回调地址固定为：

```text
https://你的域名/0x/user/oidc/callback
```

在 IdP 侧登记这一条，再按面板提示填写 Issuer / Client ID / Client Secret 即可。面板保存的值优先于 `.env`；清空 Issuer 保存就把整套配置交还 `.env`，因此由 `.env` 提供的配置只能在 `.env` 里关闭。密钥只留在服务端，不会出现在任何接口响应里。反向代理没有透传 Host 时，自动推导的回调地址会不可用，需在面板显式填写。

绑定与开通策略（面板可改，`.env` 同名变量为默认值）：

- **按用户名自动绑定**（默认开）：IdP 声明的用户名与镜像用户名一致时直接登录既有账号，既有用户无需迁移。
- **自动开通新用户**（默认开）：没有匹配账号时自动建号（不可用密码）。新用户没有上游账号，需要管理员在「用户」页分配号池后才能使用。
- **允许绑定管理员账号**（默认关）：关闭时，IdP 用户声明管理员用户名会被直接拒绝，避免 IdP 侧改名即接管超管；只有确认 IdP 本身可信时才开启。
- 绑定关系以 IdP 的 `sub` 为准落库，之后在 IdP 或镜像侧改名都不影响已建立的绑定。

注意：退出登录只结束镜像会话，不会结束 IdP 的 SSO 会话；切换账号需要先在 IdP 侧退出或改用无痕窗口。

### 浏览器外联泄漏防护

镜像页面里的上游前端脚本如果调用未被网关重写的官方或遥测端点（如 arkose、sentry、statsig/featuregates、`cdn.oaistatic.com` 等），会从用户浏览器**直连**并暴露真实 IP 与设备指纹。执行下面的命令，可以把内置的“外联防护”脚本通过网关的自定义脚本机制注入到镜像页面（`head` 最先执行）：

```bash
docker compose exec django python manage.py install_egress_guard
```

- 默认只放行镜像自身域名与 `challenges.cloudflare.com`（Turnstile / Cloudflare 挑战需要），其余跨源请求一律拦截：`fetch`、XHR、WebSocket、EventSource、`sendBeacon`、Service Worker、`window.open`，以及各类资源加载属性（`src`/`srcset`/`data`/`poster`/`action` 等），并注入 `<meta name="referrer" content="no-referrer">`。
- 被拦截的目标会聚合上报并在“访问日志 → 外联拦截”中留痕，方便确认是网关漏改写，还是需要放行的正常资源。
- “脚本管理”中的可信 CDN 源会自动并入放行名单；修改后重新执行一次安装命令即可同步。也可临时放行个别域名（可重复）：

```bash
docker compose exec django python manage.py install_egress_guard --allow-host extra.example.com
```

- 移除防护：`--remove`；预览不落盘：`--dry-run`。配置了 `MIRROR_API_PREFIX` 的部署需相应修改脚本内 `REPORT_URL`。
- 拦截是“失败即关闭”的：若某资源因此加载失败，说明它本来就会把用户 IP 暴露给外部站点。请先在访问日志核实目标，确认无害后再放行，不建议直接放行 OpenAI 所属域名。
- 如需在注入脚本之外再加一层硬性约束，可在 NGINX / Cloudflare 边缘为镜像页面配置 `Content-Security-Policy`（把 `connect-src`、`script-src`、`img-src` 等限制到 `self` 与可信 CDN）。注意 ChatGPT 前端依赖 inline/eval 脚本，需保留 `'unsafe-inline'` / `'unsafe-eval'` 并充分测试后再启用。


## 安全与使用边界

- 仅在你拥有授权的账号、网络和部署环境中使用本项目。
- 使用者应自行遵守 OpenAI 服务条款及所在地法律法规。
- 不要共享账号凭据、访问令牌、Cookie 或其他敏感信息。
- 生产环境应使用独立强密钥和 HTTPS，并限制管理端的网络暴露范围。
- 共享账号隔离只作用于镜像站可控制的范围，不能替代上游账号本身的安全隔离。
- 上游页面和接口可能变化；本地测试通过不代表部署后的浏览器流程一定可用。
- 管理员进行任何用户操作（包括但不限于权限，密码）都可能导致正在使用的用户掉线！

## 使用许可

本项目仅允许用于个人学习、研究及其他非商业用途。禁止将本项目或其修改版本用于收费服务、商业运营、商业部署、转售、托管收费或其他直接或间接营利活动。如需商业使用，须事先取得作者的书面许可。

## 更新日志

### 2026-10

- OIDC 单点登录：支持接入外部 Identity Provider（授权码 + PKCE，state/nonce 与 ID Token 签名校验），面板或 `.env` 配置，按用户名绑定既有用户、可自动开通新用户；自动绑定管理员账号需显式开启
- 浏览器外联泄漏防护：新增 `install_egress_guard` 命令注入拦截脚本，阻断镜像页面直连官方/遥测端点，拦截记录进入访问日志（外联拦截）
- 首次访问创建管理员向导：`ADMIN_PASSWORD` 留空时改由网页向导创建管理员
- 登录人机验证可在管理面板配置，并优先于 `.env`
- 登录失败限流：同一 `IP + 用户名` 在 15 分钟内失败 10 次后拒绝登录，登录成功即清零
- 会话滑动续期：剩余寿命不足一半时自动延长，并受 `API_TOKEN_MAX_LIFETIME_SECONDS` 硬上限约束
- 会话占用与排队：可设置全局/单账号并发上限，超出上限自动排队，空闲会话自动回收
- 上游账号支持批量绑定代理节点，并按使用热度排序节点
- 用容器内常驻调度进程替换此前在 Docker 中从未生效的 django-crontab，并新增每日过期数据清理
- 修复：缺少 User-Agent 时写入访问日志会触发数据库约束错误
- 修复：OIDC 流程状态改存服务端（原来靠流程 Cookie，网关只放行自带 Cookie 时登录会一直报「登录会话已失效」）

### 2026-09

- 增加大量安全性功能
- 复测
- 修复错误
- 修复错误 x 2
- MCP & skills 隔离
- 添加：**模型隔离**，**模型频率限制**
- 添加防止恶意用户通过`//`路径绕过获取 Session Token & Access Token
- 支持通过邮件`SMTP`为定时检测到的**已经失效的账号进行邮件推送服务**

### 2026-08

- 针对 iPhone Safari 和 iPhone Chrome 偶发请求失败、页面资源解析警告等现象进行兼容性调整。
- 保持桌面端原有访问行为不变.
- 增加敏感词（主要用于政治内容）机制检测和验证
- 增加新的方案，位于代理界面（reqwest/wreq）
- 优化 bypass 请求
- 优化代理分流
- 添加公告功能
- 细节优化
- 公告支持 markdown
- 增加可信域名直接配置列表（脚本）
- 增加新的实验性最终方案（curl-impersonate）
- 优化降智检测和必要的应对方案
- 大幅度减少 Pro 模型的降智几率
- 添加项目隔离功能

### 2026-07

- 完成一轮安全加固，重点收紧凭据输出、管理权限、跳转边界、敏感日志和生产环境安全配置。
- 增加共享上游账号时的镜像用户隔离，覆盖普通对话、归档、搜索、标题和删除等常用操作，并限制共享记忆功能带来的交叉影响。
- 优化页面静态资源和图表内容的加载表现，减少资源缺失、重复加载和卡片显示异常。
- 修复容器构建过程中偶发的依赖缓存与产物缺失问题，提高重复构建的稳定性。

### 2026-06

- 增加凭据定时更新、并发保护、立即刷新和剩余有效时间展示，降低凭据过期造成的中断。
- 持续修复移动端对话加载和实时连接兼容问题

### 2026-05 及以前
- 开发


## Star History

![Star History](./imageandvideo/star-history-2026911.png)
