<template>
  <div v-if="authChecking" class="auth-loading">正在确认登录状态…</div>
  <AuthScreen v-else-if="!currentUser" @authenticated="handleAuthenticated" />
  <div v-else class="app-container">
    <!-- 侧边栏 -->
    <Sidebar
      v-show="activePage === 'chat'"
      :sessions="sessions"
      :current-thread-id="currentThreadId"
      :current-user="currentUser"
      @select-session="handleSelectSession"
      @new-chat="handleNewChat"
      @delete-session="handleDeleteSession"
      @logout="handleLogout"
    />

    <!-- 主内容区 -->
    <main class="main-content">
      <header class="lab-navigation">
        <a class="lab-brand" href="#" @click.prevent="activePage = 'chat'">ASu <span>Agent Lab</span></a>
        <nav aria-label="工作区导航">
          <button v-for="item in workspacePages" :key="item.id" :class="{ active: activePage === item.id }" :aria-current="activePage === item.id ? 'page' : undefined" @click="activePage = item.id">{{ item.label }}</button>
        </nav>
        <div class="lab-account"><span>{{ currentUser.display_name || currentUser.username }}</span><button @click="handleLogout">退出</button></div>
      </header>
      <div v-if="labStatus?.mode === 'demo'" class="demo-banner" role="status"><span class="mode-dot" aria-hidden="true"></span><strong>本地合成演示，不调用大模型</strong><span>证据、计算与评估操作会保存到你的个人空间。</span></div>
      <div v-show="activePage === 'chat'" class="chat-workspace">
      <AsyncTaskPanel :tasks="asyncTasks" :refreshing="tasksRefreshing" @refresh="loadTasks" />
      <!-- 对话区域 -->
      <ChatArea
        :demo-mode="labStatus?.mode === 'demo'"
        :messages="messages"
        :streaming="isStreaming"
        :show-tool-calls="showToolCalls"
      />

      <!-- ★ 人工介入中断横幅（数据补充 / HITL 审批） -->
      <InterruptBanner
        v-if="interruptData"
        :interrupt-data="interruptData"
        :submitting="isResuming"
        @resume="handleResume"
      />

      <!-- 输入区域：中断激活时隐藏，正常/流式时显示 -->
      <InputArea
        v-if="!interruptData"
        @send="handleSend"
        @stop="handleStop"
        @toggle-tool-calls="showToolCalls = $event"
        :disabled="false"
        :streaming="isStreaming"
        :show-tool-calls="showToolCalls"
      />
      </div>
      <LabWorkspace v-show="activePage !== 'chat'" :page="activePage" />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import AuthScreen from './components/AuthScreen.vue'
import Sidebar from './components/Sidebar.vue'
import ChatArea from './components/ChatArea.vue'
import InputArea from './components/InputArea.vue'
import InterruptBanner from './components/InterruptBanner.vue'
import AsyncTaskPanel from './components/AsyncTaskPanel.vue'
import LabWorkspace from './components/LabWorkspace.vue'
import { streamChat, resumeChat, getChatState } from './api/chat.js'
import { getSessions, getMessages, deleteSession } from './api/history.js'
import { getTasks } from './api/tasks.js'
import { logout, restoreSession } from './api/auth.js'
import { authFetch } from './api/client.js'

/**
 * DeepAgent 聊天应用主组件
 *
 * 消息流按时间顺序混合展示：
 *   [user] → [assistant 文本] → [tool 调用] → [assistant 文本] → ...
 * 支持 Human-in-the-Loop 中断：
 *   ... → [interrupt] → [用户决策/补充] → [继续]
 */

// ============================================================
// 状态定义
// ============================================================

const activePage = ref('chat')
const labStatus = ref(null)
const workspacePages = [{ id: 'chat', label: '聊天' }, { id: 'evidence', label: '证据工作台' }, { id: 'evaluation', label: '评估中心' }]

async function loadLabStatus() {
  try {
    const response = await authFetch('/api/lab/status')
    if (response.ok) labStatus.value = await response.json()
  } catch { labStatus.value = null }
}

// 会话列表
const sessions = ref([])
// 当前会话 ID
const currentThreadId = ref(null)
// 消息列表（混合 user/assistant/tool，按时间顺序）
const messages = ref([])
// 是否正在流式输出
const isStreaming = ref(false)
// 是否正在处理中断恢复
const isResuming = ref(false)
// 是否显示工具调用
const showToolCalls = ref(true)
// 中断数据（null = 无中断，object = 有中断等待处理）
const interruptData = ref(null)
// AbortController 用于停止流式请求
let abortController = null
const currentUser = ref(null)
const authChecking = ref(true)
const asyncTasks = ref([])
const tasksRefreshing = ref(false)
let taskRefreshTimer = null

// ============================================================
// 生命周期
// ============================================================

/**
 * 组件挂载时加载会话列表
 */
onMounted(async () => {
  window.addEventListener('auth-expired', handleAuthExpired)
  currentUser.value = await restoreSession()
  authChecking.value = false
  if (currentUser.value) {
    loadLabStatus()
    await loadSessions()
    await loadTasks()
    taskRefreshTimer = window.setInterval(loadTasks, 5000)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('auth-expired', handleAuthExpired)
  if (taskRefreshTimer) window.clearInterval(taskRefreshTimer)
})

async function handleAuthenticated(user) {
  currentUser.value = user
  loadLabStatus()
  handleNewChat()
  await loadSessions()
  await loadTasks()
  if (!taskRefreshTimer) taskRefreshTimer = window.setInterval(loadTasks, 5000)
}

function handleAuthExpired() {
  currentUser.value = null
  labStatus.value = null
  sessions.value = []
  asyncTasks.value = []
  if (taskRefreshTimer) {
    window.clearInterval(taskRefreshTimer)
    taskRefreshTimer = null
  }
  handleNewChat()
}

function handleLogout() {
  logout()
  handleAuthExpired()
}

async function loadTasks() {
  if (!currentUser.value || tasksRefreshing.value) return
  tasksRefreshing.value = true
  try {
    const response = await getTasks(50)
    asyncTasks.value = response.tasks || []
  } catch (error) {
    console.error('[App] 加载异步任务失败:', error)
  } finally {
    tasksRefreshing.value = false
  }
}

// ============================================================
// 会话管理
// ============================================================

/**
 * 加载会话列表
 */
async function loadSessions() {
  try {
    const response = await getSessions(1, 100)
    sessions.value = response.sessions || []
  } catch (error) {
    console.error('[App] 加载会话列表失败:', error)
    sessions.value = []
  }
}

/**
 * 选择会话
 */
async function handleSelectSession(threadId) {
  activePage.value = 'chat'
  if (threadId === currentThreadId.value) return

  currentThreadId.value = threadId
  interruptData.value = null  // 切换会话时清除中断状态
  await loadMessages(threadId)
  if (labStatus.value?.mode === 'demo') {
    try {
      const snapshot = await getChatState(threadId)
      if (snapshot.pending?.status === 'awaiting_approval' && currentThreadId.value === threadId) {
        interruptData.value = { thread_id: threadId, interrupt_type: 'hitl_approval', action_requests: [{ name: 'order_create', args: snapshot.pending.payload }], review_configs: [{ action_name: 'order_create', allowed_decisions: ['approve', 'reject'] }] }
      }
    } catch (error) { console.warn('无法恢复待审批操作', error) }
  }
}

/**
 * 新建对话
 */
function handleNewChat() {
  activePage.value = 'chat'
  // 如果有正在进行的请求，取消它
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  isStreaming.value = false
  isResuming.value = false
  interruptData.value = null
  currentThreadId.value = null
  messages.value = []
}

/**
 * 删除会话
 */
async function handleDeleteSession(threadId) {
  try {
    await deleteSession(threadId)
    await loadSessions()

    if (currentThreadId.value === threadId) {
      handleNewChat()
    }
  } catch (error) {
    console.error('[App] 删除会话失败:', error)
    alert('删除会话失败，请重试')
  }
}

/**
 * 加载会话消息
 */
async function loadMessages(threadId) {
  try {
    const response = await getMessages(threadId)
    messages.value = response.messages || []
  } catch (error) {
    console.error('[App] 加载会话消息失败:', error)
    messages.value = []
  }
}

// ============================================================
// 停止对话
// ============================================================

/**
 * 停止当前对话
 */
function handleStop() {
  if (abortController) {
    abortController.abort()
    abortController = null
    isStreaming.value = false
    isResuming.value = false
    console.log('[App] 用户停止了对话')
  }
}

// ============================================================
// 消息发送
// ============================================================

/**
 * 发送消息
 */
async function handleSend(message) {
  if (isStreaming.value) return

  // 添加用户消息
  messages.value.push({
    id: `user-${Date.now()}`,
    role: 'user',
    content: message
  })

  // 清除中断状态（如果有）
  interruptData.value = null

  // 设置流式状态
  isStreaming.value = true

  // 创建新的 AbortController
  abortController = new AbortController()

  try {
    const result = await streamChat(
      message,
      currentThreadId.value,
      {
        // 接收到 token 时的回调
        onToken: (content, source) => {
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            // 追加到已有的 assistant 消息
            lastMsg.content += content
            lastMsg.source = source
          } else {
            // 前一条是 tool 或没有消息，创建新的 assistant 消息
            messages.value.push({
              id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              role: 'assistant',
              content: content,
              source: source || 'main'
            })
          }
        },

        // 工具开始调用时的回调
        onToolStart: (tool) => {
          messages.value.push({
            id: tool.id,
            role: 'tool',
            tool_name: tool.name,
            args: '',
            text: '',
            images: [],
            source: tool.source || 'main',
            tool_status: 'calling'
          })
        },

        // 工具参数片段的回调
        onToolArgs: (args, source) => {
          // 从后向前查找最后一个 calling 状态的 tool，支持嵌套工具调用
          for (let i = messages.value.length - 1; i >= 0; i--) {
            if (messages.value[i].role === 'tool' && messages.value[i].tool_status === 'calling') {
              messages.value[i].args += args
              break
            }
          }
        },

        // 工具结果返回时的回调
        onToolResult: (tool) => {
          let toolMsg = null
          for (let i = messages.value.length - 1; i >= 0; i--) {
            if (messages.value[i].role === 'tool' && messages.value[i].id === tool.id) {
              toolMsg = messages.value[i]
              break
            }
          }
          if (toolMsg) {
            toolMsg.text = tool.text || ''
            toolMsg.images = tool.images || []
            toolMsg.tool_status = 'done'
          }
        },

        // 工具调用结束时的回调
        onToolEnd: (tool) => {
          if (tool) {
            let toolMsg = null
            for (let i = messages.value.length - 1; i >= 0; i--) {
              if (messages.value[i].role === 'tool' && messages.value[i].id === tool.id) {
                toolMsg = messages.value[i]
                break
              }
            }
            if (toolMsg && toolMsg.tool_status === 'calling') {
              toolMsg.tool_status = 'done'
            }
          }
          // 兜底：将所有仍在 calling 的工具标记为 done
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'done'
            }
          }
        },

        // ★ 中断检测回调
        onInterrupt: (data) => {
          console.log('[App] 检测到中断:', data.interrupt_type)
          if (data.thread_id) {
            currentThreadId.value = data.thread_id
            loadSessions()
          }
          // 兜底：将所有 calling 状态的工具标记为 done
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'done'
            }
          }
          // 清理空的 assistant 消息
          messages.value = messages.value.filter(m => {
            if (m.role === 'assistant' && !m.content) return false
            return true
          })
          // 设置中断数据，触发 InterruptBanner 显示
          interruptData.value = data
        },

        // 流结束时的回调
        onDone: (data) => {
          // 确保所有工具调用都标记为完成
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'done'
            }
          }
          // 清理空内容的 assistant 消息（流式过程中产生的残留）
          messages.value = messages.value.filter(m => {
            if (m.role === 'assistant' && !m.content && !data.aborted) {
              return false
            }
            return true
          })
          if (data.aborted) {
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content) {
              lastMsg.content = '（对话已停止）'
            }
          }
          // 仅在非中断完成时更新 thread_id
          if (data.thread_id && !currentThreadId.value && !data.interrupted) {
            currentThreadId.value = data.thread_id
            loadSessions()
          }
          loadTasks()
        },

        // 发生错误时的回调
        onError: (error) => {
          console.error('[App] 对话错误:', error)
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content) {
            lastMsg.content = `抱歉，发生了错误：${error.message}`
          } else {
            messages.value.push({
              id: `assistant-${Date.now()}`,
              role: 'assistant',
              content: `抱歉，发生了错误：${error.message}`,
              source: 'main'
            })
          }
        }
      },
      abortController.signal
    )
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('[App] 请求已被取消')
    } else {
      console.error('[App] 发送消息失败:', error)
    }
  } finally {
    isStreaming.value = false
    abortController = null
  }
}

// ============================================================
// 中断恢复
// ============================================================

/**
 * 处理中断恢复（由 InterruptBanner 触发）
 *
 * @param {Object} resumeData - 恢复数据：
 *   - 数据补充: { supplement: "..." }
 *   - HITL 审批: { decisions: [{ type: "approve" }] }
 */
async function handleResume(resumeData) {
  if (isResuming.value || !currentThreadId.value) return

  isResuming.value = true

  // 创建新的 AbortController
  abortController = new AbortController()

  try {
    const result = await resumeChat(
      currentThreadId.value,
      resumeData,
      {
        onToken: (content, source) => {
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content += content
            lastMsg.source = source
          } else {
            messages.value.push({
              id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              role: 'assistant',
              content: content,
              source: source || 'main'
            })
          }
        },

        onToolStart: (tool) => {
          messages.value.push({
            id: tool.id,
            role: 'tool',
            tool_name: tool.name,
            args: '',
            text: '',
            images: [],
            source: tool.source || 'main',
            tool_status: 'calling'
          })
        },

        onToolArgs: (args, source) => {
          for (let i = messages.value.length - 1; i >= 0; i--) {
            if (messages.value[i].role === 'tool' && messages.value[i].tool_status === 'calling') {
              messages.value[i].args += args
              break
            }
          }
        },

        onToolResult: (tool) => {
          for (let i = messages.value.length - 1; i >= 0; i--) {
            if (messages.value[i].role === 'tool' && messages.value[i].id === tool.id) {
              messages.value[i].text = tool.text || ''
              messages.value[i].images = tool.images || []
              messages.value[i].tool_status = 'done'
              break
            }
          }
        },

        onToolEnd: (tool) => {
          if (tool) {
            for (let i = messages.value.length - 1; i >= 0; i--) {
              if (messages.value[i].role === 'tool' && messages.value[i].id === tool.id && messages.value[i].tool_status === 'calling') {
                messages.value[i].tool_status = 'done'
                break
              }
            }
          }
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'done'
            }
          }
        },

        // ★ 恢复后仍可能再次中断（如：先数据补充 → 再 HITL 审批）
        onInterrupt: (data) => {
          console.log('[App] 恢复后再次中断:', data.interrupt_type)
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'done'
            }
          }
          messages.value = messages.value.filter(m => {
            if (m.role === 'assistant' && !m.content) return false
            return true
          })
          interruptData.value = data
        },

        onDone: (data) => {
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'done'
            }
          }
          messages.value = messages.value.filter(m => {
            if (m.role === 'assistant' && !m.content) return false
            return true
          })
          // 非中断完成 → 清除中断状态
          if (!data.interrupted) {
            interruptData.value = null
            // 更新 thread_id
            if (data.thread_id && !currentThreadId.value) {
              currentThreadId.value = data.thread_id
              loadSessions()
            }
          }
          loadTasks()
        },

        onError: (error) => {
          console.error('[App] 恢复对话错误:', error)
          interruptData.value = null  // 出错时清除中断状态，恢复普通输入
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content) {
            lastMsg.content = `抱歉，发生了错误：${error.message}`
          } else {
            messages.value.push({
              id: `assistant-${Date.now()}`,
              role: 'assistant',
              content: `抱歉，发生了错误：${error.message}`,
              source: 'main'
            })
          }
        }
      },
      abortController.signal
    )
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('[App] 恢复请求已被取消')
    } else {
      console.error('[App] 恢复请求失败:', error)
    }
  } finally {
    isResuming.value = false
    abortController = null
  }
}
</script>

<style scoped>
.auth-loading {
  height: 100vh;
  display: grid;
  place-items: center;
  color: #64748b;
  background: #f8fafc;
  font-size: 14px;
  letter-spacing: .06em;
}

.app-container {
  display: flex;
  height: 100vh;
  background: #f7f7f8;
  position: relative;
  overflow: hidden;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  width: 100%;
  min-width: 0;
  background: #ffffff;
  position: relative;
  border-left: 0;
  box-shadow: none;
}

.lab-navigation{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:0 28px;min-height:65px;border-bottom:1px solid #e1e8f2;background:#fff;flex-shrink:0;z-index:1}.lab-brand{font-size:16px;font-weight:800;letter-spacing:-.04em;color:#315fa8;text-decoration:none;white-space:nowrap}.lab-brand span{font-size:12px;font-weight:500;color:#7d8fa9;letter-spacing:-.02em;margin-left:4px}.lab-navigation nav{display:flex;gap:8px;align-self:stretch;align-items:stretch}.lab-navigation nav button{position:relative;padding:0 17px;border:0;background:transparent;color:#7b8ca3;font-size:12px;font-family:inherit;cursor:pointer;white-space:nowrap}.lab-navigation nav button.active{color:#315fa8;font-weight:700}.lab-navigation nav button.active::after{position:absolute;content:'';height:3px;background:#315fa8;bottom:0;left:17px;right:17px;border-radius:2px 2px 0 0}.lab-navigation button:focus-visible{outline:2px solid #315fa8;outline-offset:-4px}.lab-account{display:flex;gap:15px;align-items:center;font-size:11px;color:#8393aa;min-width:0}.lab-account span{max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.lab-account button{border:0;background:none;color:#8496b0;font-size:10px;cursor:pointer;white-space:nowrap}.demo-banner{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;padding:10px 20px;background:#f4f7fd;border-bottom:1px solid #e3eaf5;color:#7a8fad;font-size:10px;line-height:1.5;flex-shrink:0}.demo-banner strong{font-weight:500;color:#5c7ca7}.mode-dot{width:5px;height:5px;border-radius:50%;background:#84a3ca;flex-shrink:0}.chat-workspace{display:flex;flex-direction:column;flex:1;min-height:0;overflow:hidden}
@media(max-width:1050px){.lab-navigation{padding:0 18px;gap:12px}.lab-brand span{display:none}.lab-account span{display:none}.lab-navigation nav button{padding:0 12px}.lab-navigation nav button.active::after{left:12px;right:12px}}
@media(max-width:600px){.lab-navigation{min-height:57px;padding:0 14px;gap:8px}.lab-brand{font-size:14px}.lab-navigation nav{gap:0}.lab-navigation nav button{font-size:11px;padding:0 11px}.lab-account{gap:0}.demo-banner{padding:9px 14px;justify-content:flex-start;gap:7px}.demo-banner>span:last-child{display:none}}

@media (max-width: 720px) {
  .app-container { flex-direction: column; }
  .main-content { min-height: 0; }
}
</style>
