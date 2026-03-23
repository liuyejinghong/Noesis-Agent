# noesis chat 体验整改清单

## 测试日期: 2026-03-24

### 🔴 P0 — 必须修

#### 1. REPL 无 loading/thinking 状态指示
等模型回复时终端完全静默，用户不知道在干活还是卡死了。
opencode 有 spinner / streaming 输出。我们至少需要一个 spinner。

#### 2. 无 streaming 输出
当前是 `agent.run()` 一次性返回全部文本。长回复时用户要干等 5-10 秒。
应该用 `agent.run_stream()` 逐 token 输出。

#### 3. 欢迎界面过于简陋
当前只有 `Noesis Agent — 输入消息开始对话，输入 exit 退出`。
应该展示：版本号、当前模型、当前会话名、恢复了多少条历史、快捷命令提示。

#### 4. 无 `/` 快捷命令
opencode 有 `/status`、`/clear`、`/model` 等。我们需要：
- `/status` — 快速查看系统状态（不走 LLM）
- `/clear` — 清空当前会话历史
- `/session` — 切换/列出会话
- `/help` — 显示可用命令
- `/exit` — 退出

### 🟡 P1 — 应该修

#### 5. 无多行输入支持
用户想粘贴一大段配置或描述时，按回车就发出去了。
应支持 Shift+Enter 或 `"""` 多行模式。

#### 6. 错误处理太粗糙
当前 `except Exception as exc: print(f"错误: {exc}")` — 没有区分网络错误、认证过期、模型不可用等。
应区分处理并给出可行动的提示（如 "OpenAI 登录过期，运行 noesis login openai 重新登录"）。

#### 7. 历史消息无限增长
当前 `history = result.all_messages()` 会无限累积。
长对话后 token 会超限。需要截断策略或摘要压缩。

#### 8. 工具调用过程对用户不可见
用户说 "帮我看下状态"，模型调了 `show_system_status` 工具，用户只看到最终结果。
应该显示 "🔧 正在调用 show_system_status..." 让用户知道发生了什么。

### 🔵 P2 — 锦上添花

#### 9. 无 tab 补全
输入 `/s` 时应该能补全为 `/status` 或 `/session`。

#### 10. 无会话管理命令
`noesis chat sessions` — 列出所有会话
`noesis chat sessions delete <id>` — 删除会话

#### 11. Markdown 渲染可以更好
当前用 rich.Markdown，但代码块、表格的渲染在窄终端下效果一般。

#### 12. 无配置切换
REPL 里想临时换模型或换策略品种，目前做不到。
