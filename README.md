# welcome_bye_group

 AstrBot 入群欢迎插件 —— 自动在群聊中发送入群、离群、退群提醒消息。

## 功能特性

| 消息类型 | 说明 |
|---|---|
| **入群欢迎** | 新成员加入群聊时，自动发送自定义欢迎消息 |
| **离群通知** | 成员主动退出群聊时，发送通知 |
| **退群通知** | 成员被管理员移出群聊时，发送通知 |
| **LLM 自动生成** | 使用 AI 模型自动生成欢迎/退群/被踢消息（可选） |
| **全局配置** | 一次配置，所有群通用；群级配置可单独覆盖 |

### 模板变量

消息模板支持以下变量，占位符会在实际发送时被替换：

| 变量 | 说明 |
|---|---|
| `{at}` | @提及新成员 |
| `{time}` | 事件发生时间 |
| `{user_id}` | 成员的 QQ 号 |

### 配置优先级

配置分两层，群级配置优先于全局配置：

1. **群级配置**（通过 `/welcome set`、`/welcome leave`、`/welcome kick` 设置）—— 该群开启后使用自己的模板
2. **全局配置**（通过插件配置界面或 `/global_welcome`、`/global_leave`、`/global_kick` 命令设置）—— 全局模式开启时，未单独配置的群使用全局模板
3. 两者都未开启时不发送任何通知

使用 `/welcome status` 可查看当前群实际生效的配置及其来源。

---

## 命令

所有命令以 `/welcome` 开头，在群聊中发送即可。

### 入群欢迎

| 命令 | 说明 |
|---|---|
| `/welcome on` | 开启当前群的入群欢迎 |
| `/welcome off` | 关闭当前群的入群欢迎 |
| `/welcome set <消息>` | 设置入群欢迎（不填内容则重置为默认） |
| `/welcome test` | 测试入群欢迎（不触发事件） |

### 测试命令

> 由于 AstrBot 命令注册器不支持嵌套的 `command_group`，所有命令都挂载在 `/welcome` 顶层下。原 issue #28 中提出的 `/leave test`、`/kick test` 命令格式无法实现，使用 `/welcome test_leave`、`/welcome test_kick` 替代。

### 离群通知

| 命令 | 说明 |
|---|---|
| `/welcome leave <消息>` | 设置退群通知（不填内容则禁用） |
| `/welcome test_leave` | 测试当前退群通知 |

### 退群通知（被踢）

| 命令 | 说明 |
|---|---|
| `/welcome kick <消息>` | 设置被踢通知（不填内容则禁用） |
| `/welcome test_kick` | 测试当前被踢通知 |

### 全局配置

| 命令 | 说明 |
|---|---|
| `/global_switch` | 开启/关闭全局模式 |
| `/global_welcome <消息>` | 设置全局入群欢迎语 |
| `/global_leave <消息>` | 设置全局退群提示 |
| `/global_kick <消息>` | 设置全局被踢提示 |
| `/welcome status` | 查看当前群生效的配置及来源 |

也可以在 AstrBot 控制台的插件配置界面中直接设置这四项。

### LLM 配置

| 命令 | 说明 |
|---|---|
| `/welcome llm` | 开启/关闭 LLM 自动生成消息功能 |
| `/welcome llm_provider <id>` | 设置 LLM 模型供应商 ID |
| `/welcome llm_list` | 列出所有可用的 LLM provider |

---

## 安装

本插件适用于 [AstrBot](https://github.com/Soulter/helloworld)。

将本仓库克隆到 AstrBot 的插件目录即可：

```bash
cd <你的AstrBot插件目录>
git clone https://github.com/mjy1113451/welcome_group.git
```

---

## 配置

插件首次运行后会在数据目录生成 `welcome_group/config.json`，默认配置如下：

```json
{
  "default_message": "欢迎 {at} 加入本群！当前时间：{time}",
  "default_leave_message": "{user_id} 离开了本群。",
  "default_kick_message": "{user_id} 被移出了本群。",
  "global_enabled": false,
  "global_welcome_message": "欢迎 {at} 加入本群！当前时间：{time}",
  "global_leave_message": "{user_id} 离开了本群。",
  "global_kick_message": "{user_id} 被移出了本群。",
  "groups": {},
  "llm_enabled": false,
  "llm_provider_id": ""
}
```

`global_enabled` 为 `true` 时，未在 `groups` 中单独开启的群会使用 `global_*` 模板。

`groups` 字段中每个群组可独立配置，例如：

```json
{
  "groups": {
    "123456789": {
      "enabled": true,
      "message": "欢迎 {at} 来到交流群！",
      "leave_enabled": false,
      "leave_message": "",
      "kick_enabled": true,
      "kick_message": "{user_id} 被管理员移出了本群。"
    }
  }
}
```

### LLM 功能配置

1. 首先在 AstrBot 中配置至少一个 LLM provider（如 OpenAI、DeepSeek 等）
2. 使用 `/welcome llm_list` 查看可用的 provider ID
3. 使用 `/welcome llm_provider <id>` 设置要使用的 provider（可选，留空则使用当前聊天的 provider）
4. 使用 `/welcome llm` 开启 LLM 自动生成功能

开启 LLM 功能后，插件将使用 AI 模型自动生成欢迎/退群/被踢消息，而非使用静态模板。

---

## 项目结构

```
welcome_group/
├── main.py              # 插件主逻辑
├── _conf_schema.json    # 插件配置 schema（AstrBot 控制台配置界面所需）
├── metadata.yaml        # 插件元信息（AstrBot 加载所需）
├── README.md            # 本文档
├── LICENSE              # AGPLv3 开源协议
└── .gitignore
```

---

## 依赖

- **Python 3.10+**
- **AstrBot** 平台（运行时由 AstrBot 提供）

---

## 开源协议

本项目基于 [License](https://github.com/mjy1113451/welcome_group/blob/master/LICENSE) 开源。
