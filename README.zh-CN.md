# Claude Code Desktop

一个长在 **Hermes Desktop** 里的图形化 Claude Code 工作区——不用终端，不用手改
`settings.json`，会话也不会丢。它把真正的 `claude` CLI 当子进程驱动，所以每一个启动参数、
每一个 `settings.json` 键都照旧生效；同时把 CLI 指向你在 Hermes 里已经配好的模型，本地的、
远端的都行。

[English](README.md) · **简体中文**

- 107 项设置，全部由 CLI 自己的启动参数和 `settings.json` 键生成
- 工具审批在面板里点，也可以在同一个 Wi-Fi 下的手机上点
- 附件、实时思考/工具链、带归档与回收站的会话历史
- 输入框右下角就能选 Hermes 已认证的全部模型
- 一键升级 CLI，带备份和回滚
- 中英文界面，侧栏切换

---

## 目录

- [为什么不直接用终端](#为什么不直接用终端)
- [它是怎么工作的](#它是怎么工作的)
- [你需要什么](#你需要什么)
- [从零开始安装](#从零开始安装)
- [唯一可能需要你配置的东西](#唯一可能需要你配置的东西)
- [怎么用](#怎么用)
- [工具审批](#工具审批)
- [手机访问](#手机访问)
- [语言](#语言)
- [装进 Claude Code 本身](#装进-claude-code-本身)
- [安全模型](#安全模型)
- [故障排查](#故障排查)
- [仓库结构](#仓库结构)
- [开发](#开发)
- [许可证与商标](#许可证与商标)

---

## 为什么不直接用终端

CLI 本身很优秀，本插件没有重写它。它补的是终端给不了的那部分：

| | 终端 | 本插件 |
| :- | :- | :- |
| 每一次的启动参数 | 每次手打 | 一张由 schema 驱动的设置页，记住 |
| `settings.json` 键 | 手写 JSON | 按官方键名生成，用 `--settings` 注入 |
| 工具审批 | 在提示符处敲 `y` / `a` / `n` | 面板里一张卡片，或者手机上点 |
| 思考与工具调用 | 和文本混在一起 | 一条可以折叠的时间线 |
| 会话 | `--resume` 加记性 | 一个列表，可改名、归档、恢复、彻底删除 |
| 附件 | 粘一个路径 | 拖进去，变成 CLI 能读的 `@路径` |
| 换模型 | 改环境变量再重启 | 输入框里一个选择器 |
| 升级 | npm 加运气 | 一个按钮，带备份和回滚 |

## 它是怎么工作的

```
┌──────────────────────────────┐
│ Hermes Desktop               │
│  ┌────────────────────────┐  │
│  │ Claude Code 面板       │  │   desktop/plugin.js
│  │ （React，跑在宿主里）   │  │
│  └───────────┬────────────┘  │
│              │ HTTP          │
│  ┌───────────▼────────────┐  │
│  │ dashboard/plugin_api.py│  │   插件的后端
│  └───────────┬────────────┘  │
└──────────────┼───────────────┘
               │ 每一轮 spawn 一个进程
      ┌────────▼─────────┐
      │ claude CLI       │   --output-format stream-json --settings <运行时文件>
      └────────┬─────────┘
               │ ANTHROPIC_BASE_URL=http://127.0.0.1:<桥>
      ┌────────▼─────────┐
      │ 本机回环协议桥    │   Anthropic 协议  ⇄  OpenAI 协议
      └────────┬─────────┘
               │
      ┌────────▼─────────┐
      │ 你选的 Hermes 模型│   你认证过的任何端点：Anthropic、OpenAI 兼容、
      └──────────────────┘   8080 上的本地 Qwen、各种网关，都行
```

由此带来三个必须知道的后果：

1. **不需要 Anthropic 账号。** CLI 被 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、
   `ANTHROPIC_MODEL` 指向本机协议桥，除非你选的模型本身是 Anthropic 的，否则它根本不会
   去调 Anthropic。
2. **一轮就是一个进程。** MCP 服务和后台 bash 每轮重建。这是代价，也是本插件没有复刻
   「长驻 MCP 连接」的原因。
3. **协议桥同时会说两种协议。** CLI 说 Anthropic，几乎所有其他厂商说 OpenAI，桥在每一轮
   做转换，包括工具调用。

## 你需要什么

| | |
| :- | :- |
| 操作系统 | Windows 10 1809+、macOS 13+，或 Linux（glibc） |
| Hermes Agent | **0.21 或更新**，且带 Hermes Desktop |
| Claude Code CLI | 较新的版本即可——只要那个二进制，不需要登录 |
| 一个模型 | 至少一个已经在 Hermes 里配好的模型 |
| 网络 | 安装时需要联网；之后除非你用的模型在远端，否则不需要 |

## 从零开始安装

五步，大约十分钟。别跳步——第 1 步就是最常被跳过的那步。

### 第 1 步——安装 Claude Code CLI

本插件**不附带** Claude Code 二进制。它去找你机器上的那份来跑，所以先把 CLI 装上。任选一种：

**Windows 原生安装（推荐，不需要 Node）：**

```powershell
irm https://claude.ai/install.ps1 | iex
```

**Windows 用 npm（需要 Node.js 22 或更新；千万不要加 `sudo`）：**

```powershell
npm install -g @anthropic-ai/claude-code@latest
```

**Windows 用 WinGet：**

```powershell
winget install Anthropic.ClaudeCode
```

**macOS / Linux / WSL 原生安装：**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**macOS / Linux / WSL 用 npm：**

```bash
npm install -g @anthropic-ai/claude-code@latest
```

**macOS 用 Homebrew：**

```bash
brew install --cask claude-code
```

验证——请**新开**一个终端，让 `PATH` 刷新：

```bash
claude --version
```

应该看到类似 `2.1.325 (Claude Code)`。如果提示找不到命令，说明安装目录不在 `PATH` 上：
重新开终端，或者自己找到那个二进制的路径记下来——插件的「设置 → 升级与诊断」里可以直接
指定它。

> **你不需要登录。** 单独运行 `claude` 会引导你登录、买 Anthropic 订阅，跳过就行：本插件
> 会自己设置 base URL 和 token。如果你在 Windows 上想确认装的是真二进制、而不是 160 字节
> 的 npm 占位脚本，去看
> `…/node_modules/@anthropic-ai/claude-code/bin/claude.exe` 是否存在。

### 第 2 步——安装 Hermes Agent

**Windows 原生（PowerShell）：**

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

**Linux / macOS / WSL：**

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

**或者**直接从 Hermes 官网下载对应平台的桌面安装包，那就已经包含 agent 了，可以直接跳到第 3 步。

检查一下：

```bash
hermes --version
```

本插件声明 `requires_hermes: ">=0.21.0"`，更老的版本会拒绝安装。

### 第 3 步——给 Hermes 配一个模型

面板列出的是 Hermes 能摸到的模型，所以至少配一个：

```bash
hermes model
```

也可以直接往 `config.yaml` 里加一个 OpenAI 兼容端点：

```yaml
providers:
  local-qwen:
    name: Local Qwen
    base_url: http://127.0.0.1:8080/v1
    api_key: local
    api_mode: chat_completions
    default_model: Qwen3.8-Flash-Next-EXL3-4.05bpw
```

### 第 4 步——安装本插件

```bash
hermes plugins install MnemosyneOS/claude-code-parity --enable
```

`--enable` 跳过确认提示。然后**重启网关**，Python 后端才会被挂载——用户插件的
`dashboard/plugin_api.py` 只有在「插件已启用」且「网关重启过」两个条件同时成立时才会加载：

```bash
hermes gateway restart
```

确认两半都落地了：

```bash
hermes plugins list
```

应该看到 `claude-code-parity` 是 `enabled`。磁盘上则是
`<hermes-home>/plugins/claude-code-parity/`（后端）和
`<hermes-home>/desktop-plugins/claude-code-parity/`（面板）。

### 第 5 步——打开面板

启动 Hermes Desktop，在侧栏选 **Claude Code Desktop**。第一屏是健康检查；如果 CLI 被找到了，
就完事了，随手打一句话试试。

如果面板提示后端未连接，看[故障排查](#故障排查)——几乎总是「没重启网关」或「插件不在
`plugins.enabled` 里」。

## 唯一可能需要你配置的东西

**请求头，以及两个行为开关，属于配置，不属于代码。**

这个仓库里没有任何厂商相关的东西被硬编码。如果你的模型网关要求客户端自报身份（有些网关确实
这样），或者在没有这些头的时候报 *"Illegal API invocation"* / HTTP 400，或者会吞掉普通的
`system` 轮，那就按模型分别声明：

```yaml
plugins:
  entries:
    claude-code-parity:
      providers:
        <你的模型 slug>:
          headers:                    # 每一次走桥的请求都会带上
            X-Client: my-app
            X-Request-ID: "{uuid}"    # 每个 {uuid} 每请求重新生成
          stream_only: true           # 强制 stream:true
          guard_system: true          # 把 system 提示词折进第一条 user 轮
```

三个键都是可选的：

- `headers`——发给该模型的每个请求都带上。`{uuid}` 每次调用会换成新的 UUID，网关就是拿它
  做链路追踪的。
- `stream_only`——有些网关只有 `stream` 为真时才回话。
- `guard_system`——有些网关会丢弃或错误处理 `system` 消息，一旦涉及工具调用，指令就丢了。
  这个开关把系统提示词改写进第一条 user 轮，并换上一段简短、中性的 system 消息。

**只要某个模型配了任意一个请求头，这两个开关就默认变成 `true`**——理由是：既然需要自报身份，
那这个网关就是非标准的。想关掉就显式写 `false`。

三种给法，先命中的生效：

1. 环境变量——适合 CI、Docker，以及你不想改配置文件的机器：

   ```bash
   CCP_PROVIDER_HEADERS='{"my-gateway": {"X-Client": "my-app"}}'
   CCP_STREAM_ONLY_PROVIDERS='my-gateway,other-gateway'
   ```

2. `config.yaml` 里的 `plugins.entries.claude-code-parity.providers.<slug>`，就是上面的写法。
   这个命名空间属于插件自己，不会覆盖内置 provider。

3. `config.yaml` 里的 `providers.<slug>.extra_headers`——Hermes 自己给自定义 provider 用的那个
   字段。作为兜底读取，这样你已经配好的 provider 继续能用。

**怎么确认它真的生效了**（不会泄露任何取值）：

```bash
curl -s -H 'x-ccp-token: <token>' http://127.0.0.1:47823/health
```

```json
"provider_shaping": {"my-gateway": {"headers": 14, "stream_only": true, "guard_system": true}}
```

只有计数：读到了几个请求头，两个开关最终是不是开的。如果你配的那个模型没出现在这个表里，
说明插件读的是另一份 `config.yaml`——看同一个响应里的 `home` 字段。

## 怎么用

**输入框就是全部交互**：打字、拖文件进去、在右下角挑模型、发送。面板还会把动作注册到 Hermes
自己的命令面板里——打开工作区、新建会话、清空当前会话、刷新模型目录、打开全量设置页、检查
更新、执行升级、查看 CLI 功能矩阵、把当前会话导出成 Markdown。

**CLI 功能矩阵**（设置 → 升级与诊断）是一份诚实的账本：一个非交互、每轮一个进程的工作区能
复刻什么、不能复刻什么。斜杠命令在那里列出来供查阅；需要活的 TUI 才能跑的命令——模态对话框、
`Esc Esc` 回滚、并排 diff——都标了「未复刻」并给了替代方案。回滚不可用，就 `--resume` 回到
历史会话。

**设置页**有 107 项，分六组，每一项都标了它对应的那个启动参数或 `settings.json` 路径：

| 分组 | 覆盖内容 |
| :- | :- |
| 模型与推理 | 默认模型、推理强度及其上限、备用模型、允许/禁用列表、思考、快速模式、缓存 TTL、自动压缩、预算上限、结构化输出 |
| 权限与安全 | 权限模式、审批方式与超时、允许/禁止/需要询问的工具、内置工具集、附加目录、各种 bypass 开关、受限与安全模式、sandbox、autoMode |
| 提示词与输出 | 系统提示词替换/追加、快照、输出风格、语言、主题、编辑模式、署名、verbose 与 debug、hook 事件 |
| 会话与扩展 | 继续、分叉、会话名与 ID、持久化、子代理、MCP 配置、插件目录与 URL、hooks、env 变量、IDE 与 Chrome 集成、保留天数、记忆 |
| 运行参数 | 默认工作目录、单轮超时、工具调用策略 |
| 外观与界面 | 配色（Claude 珊瑚橙、Claude 深色、或跟随 Hermes）、思考展示、时间线、工具卡片、消息视图、字号 |

设置保存在
`<hermes-home>/desktop-plugins/claude-code-parity/.runtime/plugin-settings.json`，
每轮通过 `--settings` 注入。**你自己的 `~/.claude/settings.json` 永远不会被改写**——设置页会
把它以只读方式列出来，方便你对照。

**历史**列出每个会话的项目、模型和轮数。可以改名、归档、从回收站恢复、彻底删除。连续删除
会被限流：四秒内删得太多会暂停并提示，免得一个卡住的按键把列表清空。

**升级**会替你重跑安装器（先 `claude update`，再 npm，最后直接从平台包复制），校验新二进制，
并保留上一个可用版本，所以一个坏版本可以一键回滚。

## 工具审批

CLI 会拿到 `--permission-prompt-tool`，指向本插件自带的一个 MCP 服务
（`dashboard/approval_mcp.py`）。当某个工具需要决策时 CLI 会阻塞，面板弹出卡片，写着工具名和
它的参数，你选：

| 动作 | 含义 |
| :- | :- |
| **允许** | 就这一次 |
| **始终允许** | 本次会话内，这个工具不再问 |
| **拒绝** | 拒绝；模型会看到拒绝理由并自己调整 |

把**审批方式**设成 `host` 才会有这些卡片。设成 `none` 就从不询问，任何需要审批的工具直接被
拒绝——那是无人值守场景的安全设置。还有一个超时（在设置 → 权限与安全里）：没人应答就自动
拒绝，这样无人值守的 CLI 永远不会永久挂住。

手机上也有同样三个动作，所以长任务可以在隔壁房间点通过，不用走回电脑前。

## 手机访问

面板会在你的局域网里，用另一个端口、另一个口令，再服务一个手机尺寸的客户端：

1. 在面板里打开**手机访问**，它列出所有局域网地址和一个二维码。
2. 手机和电脑必须在**同一个 Wi-Fi** 下。扫码，或者直接输入网址。

几个能省时间的点：

- **口令是固定的**，每个安装一份；只有**IP 会变**——路由器重启后重新分配的租约变了。重新扫
  一次码就行，不用重新配置。
- 手机端是一条严格的允许清单，不是整个 API：列表、发送、轮询、审批。
- 手机页是一个静态文件，没有构建步骤，而且同样是双语的。

## 语言

侧栏有一个 **EN / 中文** 开关。它不是只换一层皮：

- 面板自己的文案只在一处翻译——UI 渲染的每一个字符串字面量都经过 JSX 工厂里的同一个翻译器，
  所以新加的按钮不可能悄悄只出中文。
- **后端**的文案在服务端翻译。设置 schema、功能矩阵、升级日志、每一条诊断信息都是中文写作、
  在 UI 要求 `?lang=en` 时以英文下发；面板现在给每个请求都追加这个参数。
- 手机端有自己的表，按 `?lang=` → `localStorage` → `navigator.language` 的顺序取语言。
- **你的内容永远不会被翻译。** 模型输出、工具输出、你自己打的字都原样透传，只有插件自己的
  界面外壳会变。

## 装进 Claude Code 本身

这个仓库同时也是一个 Claude Code marketplace，所以 `claude` 可以把它加进来：

```bash
claude plugin marketplace add MnemosyneOS/claude-code-parity
claude plugin install claude-code-parity@mnemosyneos
```

在那里你拿到的是**协议桥技能**（`integrations/claude-code/skills/`）：正在运行的工作区的完整
HTTP 契约——怎么和本机回环中继握手、列模型、开一轮、轮询事件流、应答审批——这样 Claude Code
（或任何 agent）可以在面板之外驱动这个后端。

你**拿不到**的是桌面面板：那一半是 Hermes Desktop 插件，只能在 Hermes 里跑。两半是同一个
项目、同一个版本号；Hermes 那一半是产品，Claude Code 那一半是集成面。

Hermes 侧不需要 marketplace 这一步，`hermes plugins install` 直接吃 Git URL 或 `owner/repo`。
要进 Hermes 的精选目录则需要向上游目录仓库提 PR；`hermes plugins validate` 是它必须过的门禁，
而这棵树是过的。

## 安全模型

在把面板暴露给任何东西之前，请读这一节。

- **回环中继的 token 按安装随机生成**，落在 `.runtime/relay.json`，从不进版本库。写死在源码里的
  token 等于公开、等于没有；它的意义是让你随手打开的某个网页无法驱动本机 API。
- **中继只应答回环地址**（`127.0.0.1`、`::1`），并且**拒绝任何 `http://` 或 `https://` 的
  `Origin`**——放行 `file://`、`app://` 和 `null`，也就是 Desktop 窗口发出来的那种。浏览器标签页
  里的网页够不到握手端点。
- **CORS 是正则允许清单**，不是 `*`。
- **手机端有自己的口令和自己的端口**，与面板分开，只开放它需要的端点。
- **没有遥测、没有统计、不回传任何东西。** 唯一的出网流量是发给你配置的模型端点，加上 CLI 自己
  做更新检查时的那些。
- **审批对接的是 CLI 自己的权限系统。** 本插件不削弱 Claude Code 的权限，只是给你一个更好的
  地方去回答。`bypassPermissions` 之所以存在是因为 CLI 有，而它默认是关的。

## 故障排查

| 现象 | 原因 | 处理 |
| :- | :- | :- |
| 面板提示后端未连接 | Python 后端只在「插件已启用」**且**「网关重启过」时才挂载 | `hermes plugins enable claude-code-parity` 然后 `hermes gateway restart` |
| `claude_ok: false`，提示「文件只有 160 字节」 | 指向了 npm 占位脚本（`claude.cmd`）而不是二进制 | 设置 → 升级与诊断 → **修复安装**；插件会优先取 `node_modules/@anthropic-ai/claude-code/bin/claude.exe` |
| `… 403 {"detail":"relay token required"}` | 升级重新生成了 token，前端手里是旧的 | 重载面板；它遇到 403 会自动重新握手 |
| 握手就返回 403 | 中继没起来，或者请求来自 web origin | 启动 Hermes Desktop；不要在浏览器标签页里调它 |
| 上游 `HTTP 400 code:11128 Illegal API …` | 你的网关要求自报身份的请求头 | [配置 provider 请求头](#唯一可能需要你配置的东西) |
| 发送时报 `NotADirectoryError: [WinError 267]` | 工作目录不存在 | 设置 → 运行参数 → 默认工作目录，或清空它，回退到 Hermes 的 `terminal.cwd`、再回退到用户主目录 |
| stderr 里有 `[claude-code:unrecognized_model]` | CLI 不认识这个模型名；无害，桥会替换请求 | 忽略，或者在输入框里选模型，让桥做映射 |
| 手机连不上 | 不在同一 Wi-Fi、开着 VPN，或者 IP 变了 | 同一网络、关掉 VPN、重新扫码 |
| 能用但回答很慢 | 模型选择器里的 `probe=true`，或者模型首 token 慢 | 选择器有缓存；先量一下这个 provider 自己的延迟 |

日志在 `<hermes-home>/logs/`。面板自己的诊断在 设置 → 升级与诊断；带中继 token 请求
`GET /health` 拿到的是同一份数据的 JSON。

## 仓库结构

```
plugin.yaml                     Hermes 插件清单（agent 半边）
dashboard/
  manifest.json                 面板注册
  plugin_api.py                 后端：设置 schema、任务、协议桥、中继、手机端
  mobile_page.py                手机端（单文件静态页，双语）
  approval_mcp.py               应答 CLI 权限询问的 MCP 服务
desktop/
  plugin.js                     面板本体（React，无构建步骤）
integrations/claude-code/
  .claude-plugin/plugin.json    Claude Code 插件清单
  skills/hermes-claude-bridge/  协议桥契约，写成 Claude Code 技能
.claude-plugin/marketplace.json Claude Code marketplace 条目
docs/                           配置、架构、手机端、发布说明
```

## 开发

面板没有构建步骤：`desktop/plugin.js` 原样加载。后端是纯 Python，由 Hermes 自己的解释器跑。

```bash
# 准入校验——必须输出 "Validation passed."
hermes plugins validate .

# 改完之后覆盖安装
hermes plugins install MnemosyneOS/claude-code-parity --force --enable
hermes gateway restart
```

这个代码库遵守两条规矩，评审时也该照这两条要求它：

1. **源码里没有凭据、没有厂商名、没有个人路径。** 部署事实放在配置里，源码去读配置。
2. **每一半只有一个 i18n 收口点。** 面板在 JSX 工厂里翻译，后端在响应构造处翻译。不要在调用点
   到处撒翻译。

## 许可证与商标

MIT，见 [LICENSE](LICENSE)。

Claude 与 Claude Code 是 Anthropic, PBC 的商标。本项目是 Claude Code CLI 的独立接口，与
Anthropic 无隶属、无背书、无赞助关系。Hermes 与 Hermes Agent 是 Nous Research 的产品；
本插件是该宿主的第三方插件。
