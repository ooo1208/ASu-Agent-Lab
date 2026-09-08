<template>
  <section v-if="tasks.length" class="async-task-panel" :class="{ collapsed: !expanded }" aria-live="polite">
    <button v-if="!expanded" class="collapsed-tab" type="button" @click="toggleExpanded">
      <span>后台任务</span><b>{{ tasks.length }}</b>
    </button>
    <div v-else class="drawer-panel">
      <div class="panel-header">
        <div><span class="panel-kicker">后台任务</span><h2>异步采购分析</h2></div>
        <div class="panel-actions">
          <button class="refresh-btn" type="button" :disabled="refreshing" @click="$emit('refresh')">{{ refreshing ? '刷新中' : '刷新' }}</button>
          <button class="collapse-btn" type="button" @click="toggleExpanded">收起</button>
        </div>
      </div>
      <div class="task-list">
        <article v-for="task in tasks" :key="task.task_id" class="task-card">
          <div class="task-main">
            <span class="status-dot" :class="`status-${task.status}`" aria-hidden="true"></span>
            <div class="task-copy">
              <div class="task-title-row"><strong>{{ statusLabel(task.status) }}</strong><time>{{ formatTime(task.created_at) }}</time></div>
              <p class="task-id">任务 ID：{{ task.task_id }}</p>
            </div>
          </div>
          <div v-if="isRunning(task.status)" class="task-progress" role="status"><span class="progress-line"><span></span></span><span>任务正在后台执行，页面会自动更新结果</span></div>
          <div v-else-if="task.status === 'success' && task.result" class="task-result"><span class="result-label">执行结果</span><p>{{ task.result }}</p></div>
          <div v-else-if="task.status === 'error'" class="task-error"><span class="result-label">失败原因</span><p>{{ task.error || '异步任务执行失败，请刷新后重试。' }}</p></div>
          <div v-else-if="task.status === 'cancelled'" class="task-muted">任务已取消</div>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({ tasks: { type: Array, default: () => [] }, refreshing: { type: Boolean, default: false } })
defineEmits(['refresh'])

const storageKey = 'erp_async_tasks_collapsed'
const expanded = ref(typeof window === 'undefined' || window.localStorage.getItem(storageKey) !== '1')

function toggleExpanded() {
  expanded.value = !expanded.value
  window.localStorage.setItem(storageKey, expanded.value ? '0' : '1')
}
function isRunning(status) { return ['pending', 'running', 'queued'].includes(status) }
function statusLabel(status) {
  return { pending: '等待执行', queued: '排队中', running: '执行中', success: '已完成', error: '执行失败', cancelled: '已取消', timeout: '执行超时', interrupted: '已中断' }[status] || '状态未知'
}
function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.async-task-panel { position: fixed; z-index: 30; top: 20px; right: 18px; bottom: 88px; width: min(380px, calc(100vw - 36px)); color: #111318; pointer-events: none; }
.drawer-panel { display: flex; height: 100%; flex-direction: column; overflow: hidden; border: 1px solid #d9dce3; border-top: 3px solid #002fa7; background: #f7f7f8; box-shadow: 0 14px 34px rgba(15, 30, 65, .16); pointer-events: auto; }
.panel-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px 12px; border-bottom: 1px solid #d9dce3; background: #f7f7f8; }
.panel-kicker, .result-label { display: block; color: #687080; font-size: 10px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.panel-header h2 { margin: 5px 0 0; font-size: 16px; letter-spacing: -.02em; }
.panel-actions { display: flex; gap: 6px; }
.refresh-btn, .collapse-btn { padding: 6px 9px; border: 1px solid #002fa7; background: #fff; color: #002fa7; font-size: 12px; cursor: pointer; }
.refresh-btn:hover:not(:disabled), .collapse-btn:hover { background: #002fa7; color: #fff; }
.refresh-btn:disabled { opacity: .55; cursor: wait; }
.task-list { flex: 1; overflow-y: auto; background: #d9dce3; }
.task-card { padding: 13px 16px; border-bottom: 1px solid #d9dce3; background: #fff; }
.task-main { display: flex; align-items: flex-start; gap: 10px; }
.status-dot { width: 9px; height: 9px; margin-top: 4px; flex: 0 0 auto; border-radius: 50%; background: #94a3b8; }
.status-running, .status-pending, .status-queued { background: #f59e0b; animation: pulse 1.6s ease-in-out infinite; }
.status-success { background: #059669; }
.status-error, .status-timeout { background: #dc2626; }
.status-cancelled, .status-interrupted { background: #64748b; }
.task-copy { min-width: 0; flex: 1; }
.task-title-row { display: flex; justify-content: space-between; gap: 12px; }
.task-title-row strong { font-size: 13px; }
.task-title-row time { color: #687080; font-size: 11px; white-space: nowrap; }
.task-id { margin: 4px 0 0; overflow: hidden; color: #687080; font: 11px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }
.task-progress, .task-result, .task-error, .task-muted { margin: 11px 0 0 19px; font-size: 12px; line-height: 1.55; }
.task-progress { display: flex; align-items: center; gap: 8px; color: #687080; }
.progress-line { width: 74px; height: 3px; overflow: hidden; background: #d9dce3; }
.progress-line span { display: block; width: 35%; height: 100%; background: #002fa7; animation: slide 1.4s ease-in-out infinite; }
.task-result p, .task-error p { max-height: 160px; margin: 5px 0 0; overflow: auto; white-space: pre-wrap; }
.task-result .result-label { color: #059669; }
.task-error .result-label { color: #dc2626; }
.task-muted { color: #687080; }
.collapsed-tab { position: absolute; top: 76px; right: 0; display: flex; width: 38px; min-height: 122px; align-items: center; justify-content: center; gap: 7px; padding: 12px 8px; border: 1px solid #d9dce3; border-right: 0; background: #f7f7f8; color: #002fa7; box-shadow: 0 8px 20px rgba(15, 30, 65, .12); cursor: pointer; pointer-events: auto; writing-mode: vertical-rl; }
.collapsed-tab span { font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.collapsed-tab b { min-width: 18px; padding: 2px 4px; border-radius: 10px; background: #002fa7; color: #fff; font-size: 10px; line-height: 1.4; writing-mode: horizontal-tb; }
@keyframes pulse { 50% { opacity: .45; } }
@keyframes slide { from { transform: translateX(-120%); } to { transform: translateX(320%); } }
@media (max-width: 720px) { .async-task-panel { top: 12px; right: 12px; bottom: 84px; width: calc(100vw - 24px); } .collapsed-tab { right: -4px; } .panel-header { padding: 12px; } .task-card { padding: 12px; } .task-title-row { display: block; } .task-title-row time { display: block; margin-top: 3px; } }
</style>
