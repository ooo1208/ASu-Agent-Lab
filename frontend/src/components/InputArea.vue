<template>
  <div class="input-area">
    <div class="input-container">
      <!-- 工具调用开关 -->
      <div class="tool-toggle">
        <label class="toggle-label">
          <input
            type="checkbox"
            :checked="showToolCalls"
            @change="emit('toggle-tool-calls', $event.target.checked)"
            class="toggle-checkbox"
          />
          <span class="toggle-switch"></span>
          <span class="toggle-text">显示工具调用</span>
        </label>
      </div>

      <!-- 输入框 -->
      <div class="input-wrapper" :class="{ focused: isFocused, streaming: streaming }">
        <textarea
          ref="textareaRef"
          v-model="inputText"
          @focus="isFocused = true"
          @blur="isFocused = false"
          @keydown.enter.exact.prevent="handleSend"
          @input="autoResize"
          placeholder="输入消息，Enter 发送..."
          rows="1"
          :disabled="streaming"
          class="input-textarea"
        ></textarea>
        <!-- 发送按钮：流式时变为停止按钮 -->
        <button
          v-if="!streaming"
          class="send-btn"
          @click="handleSend"
          :disabled="!inputText.trim()"
        >
          <span>发送</span>
        </button>
        <button
          v-else
          class="stop-btn"
          @click="handleStop"
        >
          <span class="stop-icon">■</span>
          <span>停止</span>
        </button>
      </div>

      <!-- 提示信息 -->
      <div class="input-hint">
        <span v-if="!streaming">按 Enter 发送，Shift + Enter 换行</span>
        <span v-else class="streaming-hint">正在生成回复...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

/**
 * 输入区域组件
 *
 * 提供消息输入功能：
 * - 正常状态：显示"发送"按钮
 * - 流式输出时：输入框禁用，按钮变为"停止"
 */

const props = defineProps({
  streaming: {
    type: Boolean,
    default: false
  },
  showToolCalls: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['send', 'stop', 'toggle-tool-calls'])

// 输入文本
const inputText = ref('')
// 是否获取焦点
const isFocused = ref(false)
// textarea 引用
const textareaRef = ref(null)

/**
 * 发送消息
 */
function handleSend() {
  const text = inputText.value.trim()
  if (!text) return

  emit('send', text)
  inputText.value = ''

  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
    }
  })
}

/**
 * 停止对话
 */
function handleStop() {
  emit('stop')
}

/**
 * 自动调整 textarea 高度
 */
function autoResize() {
  const textarea = textareaRef.value
  if (!textarea) return

  textarea.style.height = 'auto'
  textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
}
</script>

<style scoped>
.input-area {
  padding: 16px 24px 24px;
  background: #ffffff;
  border-top: 1px solid #e2e8f0;
}

.input-container {
  max-width: 1100px;
  margin: 0 auto;
}

/* 工具调用开关 */
.tool-toggle {
  margin-bottom: 12px;
}

.toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.toggle-checkbox {
  display: none;
}

.toggle-switch {
  position: relative;
  width: 44px;
  height: 24px;
  background: #e2e8f0;
  border-radius: 12px;
  transition: all 0.2s ease;
}

.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.toggle-checkbox:checked + .toggle-switch {
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
}

.toggle-checkbox:checked + .toggle-switch::after {
  transform: translateX(20px);
  background: #fff;
}

.toggle-text {
  font-size: 13px;
  color: #64748b;
  font-weight: 500;
}

/* 输入框包装 */
.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  transition: all 0.2s ease;
}

.input-wrapper.focused {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
}

.input-wrapper.streaming {
  background: #fef2f2;
  border-color: #fecaca;
}

/* 输入框 */
.input-textarea {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  line-height: 1.6;
  resize: none;
  outline: none;
  min-height: 24px;
  max-height: 200px;
  color: #1e293b;
  font-weight: 500;
}

.input-textarea::placeholder {
  color: #94a3b8;
}

.input-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 发送按钮 */
.send-btn {
  flex-shrink: 0;
  padding: 10px 20px;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.3);
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
}

.send-btn:active:not(:disabled) {
  transform: translateY(0);
}

.send-btn:disabled {
  background: #e2e8f0;
  color: #94a3b8;
  cursor: not-allowed;
  box-shadow: none;
}

/* 停止按钮 */
.stop-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
  animation: stopPulse 2s ease-in-out infinite;
}

.stop-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.5);
}

.stop-btn:active {
  transform: translateY(0);
}

.stop-icon {
  font-size: 12px;
}

/* 提示信息 */
.input-hint {
  margin-top: 10px;
  text-align: center;
}

.input-hint span {
  font-size: 12px;
  color: #94a3b8;
}

.streaming-hint {
  color: #ef4444 !important;
  animation: blink 1.5s ease-in-out infinite;
}

@keyframes stopPulse {
  0%, 100% { box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3); }
  50% { box-shadow: 0 2px 16px rgba(239, 68, 68, 0.5); }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Swiss workspace visual system */
.input-area {
  padding: 14px 28px 18px;
  background: rgba(247,247,248,.96);
  border-top-color: #d9dce3;
}
.input-container { max-width: 980px; }
.tool-toggle { margin: 0 0 10px; }
.toggle-label { gap: 8px; }
.toggle-switch {
  width: 34px;
  height: 18px;
  background: #cfd3db;
  border-radius: 9px;
}
.toggle-switch::after { width: 14px; height: 14px; box-shadow: none; }
.toggle-checkbox:checked + .toggle-switch { background: #002fa7; }
.toggle-checkbox:checked + .toggle-switch::after { transform: translateX(16px); }
.toggle-text { color: #596170; font-size: 11px; font-weight: 600; }

.input-wrapper {
  min-height: 58px;
  padding: 10px 10px 10px 16px;
  background: #ffffff;
  border-color: #bfc4ce;
  border-radius: 7px;
}
.input-wrapper.focused { border-color: #002fa7; box-shadow: inset 3px 0 0 #002fa7; }
.input-wrapper.streaming { background: #ffffff; border-color: #bfc4ce; }
.input-textarea {
  color: #111318;
  font-family: Arial, 'Helvetica Neue', Helvetica, sans-serif;
  font-size: 14px;
  font-weight: 400;
}
.input-textarea::placeholder { color: #8a919e; }
.send-btn,
.stop-btn {
  min-width: 78px;
  min-height: 40px;
  justify-content: center;
  padding: 0 16px;
  border: 1px solid #002fa7;
  border-radius: 4px;
  background: #002fa7;
  box-shadow: none;
  font-size: 13px;
}
.send-btn:hover:not(:disabled) { color: #002fa7; background: #ffffff; transform: none; box-shadow: none; }
.send-btn:disabled { color: #9aa0aa; background: #eef0f4; border-color: #d9dce3; }
.stop-btn { border-color: #b42318; background: #b42318; animation: none; }
.stop-btn:hover { background: #8f1c13; transform: none; box-shadow: none; }
.input-hint { margin-top: 7px; }
.input-hint span { color: #8a919e; font-size: 10px; letter-spacing: .02em; }

@media (max-width: 720px) {
  .input-area { padding: 10px 12px 12px; }
  .input-wrapper { min-height: 52px; }
  .input-hint { display: none; }
}

.input-area {
  background: #e5e8ee;
  border-top: 3px solid #002fa7;
}
.input-wrapper { box-shadow: 4px 4px 0 rgba(0,47,167,.055); }
.input-wrapper.focused { box-shadow: inset 3px 0 0 #002fa7, 4px 4px 0 rgba(0,47,167,.055); }
</style>
