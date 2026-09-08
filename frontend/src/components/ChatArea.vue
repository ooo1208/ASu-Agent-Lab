<template>
  <div class="chat-area">
    <!-- 消息列表 -->
    <div class="message-list" ref="messageListRef">
      <!-- 空状态 -->
      <div v-if="displayMessages.length === 0" class="empty-state">
        <div class="empty-layout">
          <div class="empty-visual">
            <span class="visual-index">01</span>
            <div class="empty-icon"><img :src="whaleGirlHeroUrl" alt="ASu Agent Lab" /></div>
            <div class="visual-meta">
              <span>{{ demoMode ? '合成样例' : '业务数据' }}</span>
              <span>{{ demoMode ? '本地工作区' : '用户沙箱' }}</span>
            </div>
          </div>
          <div class="empty-copy">
            <span class="empty-eyebrow">ASu Agent Lab</span>
            <h2>今天想先处理什么？</h2>
            <p>{{ demoMode ? '在证据工作台导入资料后，可输入关键词检索。输入“演示下单 2 件”，体验本地 ERP 审批流程。' : '描述采购或财务分析任务，系统通过专业 Agent 和业务工具完成分析与执行。' }}</p>
            <div class="system-strip" aria-label="系统能力">
              <span>MCP 工具</span>
              <span>子 Agent</span>
              <span>长期记忆</span>
            </div>
            <div class="feature-list">
              <div class="feature-item">
                <span class="feature-index">01</span>
                <span>证据查找与引用回查</span>
              </div>
              <div class="feature-item">
                <span class="feature-index">02</span>
                <span>财务指标精确计算</span>
              </div>
              <div class="feature-item">
                <span class="feature-index">03</span>
                <span>采购审批与订单执行</span>
              </div>
              <div class="feature-item">
                <span class="feature-index">04</span>
                <span>异步评估与人工反馈</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 消息列表（user / assistant / tool 按时间顺序混合展示）-->
      <div v-else class="messages">
        <MessageItem
          v-for="(message, index) in displayMessages"
          :key="message.id || index"
          :message="message"
          :is-streaming="isStreamingForMessage(message)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import MessageItem from './MessageItem.vue'
import { whaleGirlHeroUrl } from '../config/assets.js'

/**
 * 对话区域组件
 *
 * 显示消息列表（user / assistant / tool 按时间顺序混合展示）
 * 当 showToolCalls 为 false 时，过滤掉 tool 消息只显示 AI 回复
 */

const props = defineProps({
  demoMode: { type: Boolean, default: false },
  messages: {
    type: Array,
    default: () => []
  },
  streaming: {
    type: Boolean,
    default: false
  },
  showToolCalls: {
    type: Boolean,
    default: true
  }
})

// 根据开关过滤展示的消息
const displayMessages = computed(() => {
  if (props.showToolCalls) {
    return props.messages
  }
  // 过滤掉 tool 消息，只保留 user 和 assistant
  return props.messages.filter(m => m.role !== 'tool')
})

// 消息列表引用
const messageListRef = ref(null)

/**
 * 判断当前消息是否处于流式输出状态
 * 只有最后一条 assistant 消息在 streaming 时才显示光标
 */
function isStreamingForMessage(msg) {
  if (!props.streaming || msg.role !== 'assistant') return false
  // 找到 messages 中最后一条 assistant 消息
  const lastAssistant = [...props.messages].reverse().find(m => m.role === 'assistant')
  return lastAssistant === msg
}

// 监听消息变化，自动滚动到底部
watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      scrollToBottom()
    })
  }
)

// 深度监听消息内容变化（流式更新时也会触发滚动）
watch(
  () => props.messages,
  () => {
    nextTick(() => {
      scrollToBottom()
    })
  },
  { deep: true }
)

/**
 * 滚动到底部
 */
function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
}

/* 消息列表 */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
}

.message-list::-webkit-scrollbar {
  width: 6px;
}

.message-list::-webkit-scrollbar-track {
  background: transparent;
}

.message-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.message-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* 空状态 */
.empty-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  text-align: center;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.empty-icon {
  margin-bottom: 24px;
  animation: float 3s ease-in-out infinite;
}

.empty-icon img {
  width: clamp(220px, 25vw, 300px);
  height: clamp(220px, 25vw, 300px);
  object-fit: contain;
  filter: drop-shadow(0 18px 28px rgba(0, 47, 167, 0.14));
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.empty-state h2 {
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 12px;
}

.empty-state p {
  font-size: 15px;
  color: #64748b;
  margin-bottom: 40px;
}

.feature-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  max-width: 540px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.feature-item:hover {
  transform: translateY(-2px);
  border-color: #0ea5e9;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.1);
}

.feature-icon {
  font-size: 24px;
}

.feature-item span:last-child {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

/* 消息列表 */
.messages {
  max-width: 1200px;
  margin: 0 auto;
}

/* Swiss workspace visual system */
.chat-area { background: #ffffff; }
.message-list {
  padding: 0;
  background-image:
    linear-gradient(rgba(17, 19, 24, .025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(17, 19, 24, .025) 1px, transparent 1px);
  background-size: 72px 72px;
}
.message-list::-webkit-scrollbar-thumb { background: #b9bec8; border-radius: 0; }

.empty-state {
  min-height: 100%;
  padding: clamp(36px, 6vh, 72px) clamp(28px, 6vw, 96px);
  align-items: stretch;
  text-align: left;
  background: linear-gradient(135deg, rgba(247,247,248,.92) 0%, rgba(255,255,255,.96) 58%);
}

.empty-layout {
  width: min(100%, 1060px);
  margin: auto;
  display: grid;
  grid-template-columns: minmax(260px, .82fr) minmax(360px, 1.18fr);
  align-items: center;
  border-top: 1px solid #bfc4ce;
  border-bottom: 1px solid #bfc4ce;
}

.empty-visual {
  position: relative;
  min-height: 430px;
  display: grid;
  place-items: center;
  border-right: 1px solid #bfc4ce;
  overflow: hidden;
}

.empty-visual::after {
  content: '';
  position: absolute;
  inset: 20px;
  border: 1px solid rgba(0,47,167,.13);
  pointer-events: none;
}

.visual-index {
  position: absolute;
  top: 16px;
  left: 18px;
  z-index: 1;
  color: #002fa7;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .12em;
}

.empty-icon { margin: 0; animation: float 4s ease-in-out infinite; }
.empty-icon img {
  width: clamp(250px, 25vw, 330px);
  height: clamp(250px, 25vw, 330px);
  filter: drop-shadow(0 20px 26px rgba(0,47,167,.12));
}

.empty-copy { padding: clamp(34px, 4vw, 54px); }
.empty-eyebrow {
  display: block;
  margin-bottom: 20px;
  color: #002fa7;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .16em;
  text-transform: uppercase;
}
.empty-state h2 {
  max-width: 520px;
  margin: 0 0 18px;
  color: #111318;
  background: none;
  -webkit-text-fill-color: currentColor;
  font-size: clamp(34px, 3.6vw, 48px);
  font-weight: 540;
  line-height: 1.08;
  letter-spacing: -.055em;
}
.empty-state p {
  max-width: 540px;
  margin: 0 0 38px;
  color: #596170;
  font-size: 14px;
  line-height: 1.8;
}
.feature-list {
  width: 100%;
  max-width: none;
  gap: 0;
  border-top: 1px solid #d9dce3;
}
.feature-item {
  min-height: 62px;
  gap: 14px;
  padding: 14px 12px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid #d9dce3;
  border-radius: 0;
  box-shadow: none;
}
.feature-item:nth-child(odd) { border-right: 1px solid #d9dce3; }
.feature-item:hover {
  color: #002fa7;
  background: #f7f7f8;
  border-color: #d9dce3;
  transform: none;
  box-shadow: none;
}
.feature-index {
  flex: 0 0 auto;
  color: #002fa7;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
}
.feature-item span:last-child { color: #252932; font-size: 12px; font-weight: 600; }
.messages { width: min(100%, 980px); padding: 34px 20px 48px; }

@media (max-width: 980px) {
  .empty-state { padding: 32px; }
  .empty-layout { grid-template-columns: minmax(220px,.72fr) minmax(330px,1.28fr); }
  .empty-visual { min-height: 380px; }
  .empty-copy { padding: 38px; }
}

@media (max-width: 720px) {
  .empty-state { justify-content: flex-start; padding: 24px 18px; overflow-y: auto; }
  .empty-layout { grid-template-columns: 1fr; margin: 0 auto; }
  .empty-visual { min-height: 230px; border-right: 0; border-bottom: 1px solid #bfc4ce; }
  .empty-icon img { width: 220px; height: 220px; }
  .empty-copy { padding: 28px 24px 32px; }
  .empty-state h2 { font-size: 34px; }
  .empty-state p { margin-bottom: 24px; }
  .messages { padding: 22px 10px 34px; }
}

@media (max-width: 480px) {
  .feature-list { grid-template-columns: 1fr; }
  .feature-item:nth-child(odd) { border-right: 0; }
}

/* Higher-density blue workspace */
.chat-area { background: #eef0f4; }
.message-list {
  background-color: #eef0f4;
  background-image:
    linear-gradient(rgba(0,47,167,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,47,167,.045) 1px, transparent 1px);
}
.empty-state { background: #eef0f4; }
.empty-layout {
  background: #ffffff;
  border-color: #aeb5c2;
  box-shadow: 12px 12px 0 rgba(0,47,167,.06);
}
.empty-visual {
  color: #ffffff;
  background-color: #002fa7;
  background-image:
    linear-gradient(rgba(255,255,255,.09) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.09) 1px, transparent 1px);
  background-size: 54px 54px;
  border-right-color: #00247f;
}
.empty-visual::after { border-color: rgba(255,255,255,.28); }
.visual-index { color: #ffffff; }
.empty-icon img { filter: drop-shadow(0 22px 30px rgba(0,0,0,.24)); }
.visual-meta {
  position: absolute;
  right: 18px;
  bottom: 16px;
  left: 18px;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid rgba(255,255,255,.42);
  color: rgba(255,255,255,.78);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .12em;
}
.empty-copy { background: #ffffff; }
.system-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin: 0 0 24px;
  color: #ffffff;
  background: #002fa7;
  border: 1px solid #002fa7;
}
.system-strip span {
  padding: 9px 10px;
  border-right: 1px solid rgba(255,255,255,.3);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .08em;
  text-align: center;
}
.system-strip span:last-child { border-right: 0; }
.feature-item { background: #f7f7f8; }
.feature-item:nth-child(2),
.feature-item:nth-child(3) { background: #ffffff; }
.feature-item:hover { background: #eef3ff; }

@media (max-width: 720px) {
  .empty-layout { box-shadow: 7px 7px 0 rgba(0,47,167,.06); }
  .empty-visual { border-right: 0; border-bottom-color: #00247f; }
  .visual-meta { bottom: 10px; }
}
</style>
