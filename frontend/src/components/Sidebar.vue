<template>
  <aside class="sidebar">
    <!-- 侧边栏头部 -->
    <div class="sidebar-header">
      <div class="logo">
        <img class="logo-icon" :src="whaleGirlLogoUrl" alt="ERP_OPENCLAW 标志" />
        <div class="logo-copy">
          <strong>ERP_OPENCLAW</strong>
          <span>多智能体企业采购助手</span>
        </div>
      </div>
      <button class="new-chat-btn" @click="$emit('new-chat')">
        <span class="icon">+</span>
        新建对话
      </button>
    </div>

    <!-- 搜索框 -->
    <div class="search-box">
      <input
        type="text"
        v-model="searchKeyword"
        placeholder="搜索会话..."
        class="search-input"
      />
    </div>

    <!-- 会话列表 -->
    <div class="session-list">
      <div class="session-list-header">
        <span>历史记录</span>
      </div>

      <div class="session-items">
        <div
          v-for="session in filteredSessions"
          :key="session.thread_id"
          class="session-item"
          :class="{ active: session.thread_id === currentThreadId }"
          @click="$emit('select-session', session.thread_id)"
        >
          <div class="session-info">
            <span class="session-title">{{ session.title }}</span>
            <span class="session-time">{{ formatTime(session.updated_at) }}</span>
          </div>
          <button
            class="delete-btn"
            @click.stop="handleDelete(session.thread_id)"
            title="删除会话"
          >
            ×
          </button>
        </div>

        <!-- 空状态 -->
        <div v-if="sessions.length === 0" class="empty-state">
          <p>暂无会话记录</p>
          <p class="hint">开始一个新对话吧</p>
        </div>
      </div>
    </div>

    <!-- 侧边栏底部 -->
    <div class="sidebar-footer">
      <div class="user-info">
        <span class="user-avatar">{{ userInitial }}</span>
        <div class="user-copy">
          <strong>{{ currentUser?.display_name || currentUser?.username }}</strong>
          <span>@{{ currentUser?.username }}</span>
        </div>
        <button class="logout-btn" title="退出登录" @click="$emit('logout')">退出</button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import { whaleGirlLogoUrl } from '../config/assets.js'

// Props 定义
const props = defineProps({
  sessions: {
    type: Array,
    default: () => []
  },
  currentThreadId: {
    type: String,
    default: null
  },
  currentUser: { type: Object, default: null }
})

// Emits 定义
const emit = defineEmits(['select-session', 'new-chat', 'delete-session', 'logout'])

// 搜索关键词
const searchKeyword = ref('')
const userInitial = computed(() => (props.currentUser?.display_name || props.currentUser?.username || 'U').slice(0, 1).toUpperCase())

// 过滤后的会话列表
const filteredSessions = computed(() => {
  if (!searchKeyword.value) {
    return props.sessions
  }
  return props.sessions.filter(session =>
    session.title.toLowerCase().includes(searchKeyword.value.toLowerCase())
  )
})

/**
 * 格式化时间
 */
function formatTime(timestamp) {
  if (!timestamp) return ''

  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  // 一天内显示相对时间
  if (diff < 24 * 60 * 60 * 1000) {
    const hours = Math.floor(diff / (60 * 60 * 1000))
    if (hours < 1) {
      const minutes = Math.floor(diff / (60 * 1000))
      return minutes < 1 ? '刚刚' : `${minutes} 分钟前`
    }
    return `${hours} 小时前`
  }

  // 超过一天显示日期
  return `${date.getMonth() + 1}/${date.getDate()}`
}

/**
 * 处理删除会话
 */
function handleDelete(threadId) {
  if (confirm('确定要删除这个会话吗？')) {
    emit('delete-session', threadId)
  }
}
</script>

<style scoped>
.sidebar {
  width: 280px;
  height: 100vh;
  background: #ffffff;
  color: #1e293b;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-right: 1px solid #e2e8f0;
  position: relative;
}

/* 侧边栏头部 */
.sidebar-header {
  padding: 20px 16px;
  border-bottom: 1px solid #f1f5f9;
  background: #fafafa;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.logo-icon {
  width: 62px;
  height: 62px;
  flex: 0 0 62px;
  object-fit: contain;
  filter: drop-shadow(0 5px 10px rgba(0, 47, 167, 0.12));
}

.logo-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.logo-copy strong {
  color: #0f172a;
  font-size: 15px;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.logo-copy span {
  color: #64748b;
  font-size: 10px;
  line-height: 1.25;
}

.new-chat-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px 20px;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
  position: relative;
  overflow: hidden;
}

.new-chat-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(14, 165, 233, 0.4);
}

.new-chat-btn:active {
  transform: translateY(0);
}

.new-chat-btn .icon {
  font-size: 20px;
  font-weight: 300;
}

/* 搜索框 */
.search-box {
  padding: 16px;
}

.search-input {
  width: 100%;
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  color: #1e293b;
  font-size: 14px;
  outline: none;
  transition: all 0.3s ease;
}

.search-input:focus {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
}

.search-input::placeholder {
  color: #94a3b8;
}

/* 会话列表 */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 2px;
}

.session-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.session-list-header {
  padding: 12px 16px 8px;
  font-size: 12px;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
}

.session-items {
  padding: 0 12px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  margin-bottom: 4px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.session-item:hover {
  background: #f1f5f9;
}

.session-item.active {
  background: #e0f2fe;
  border-color: #7dd3fc;
}

.session-info {
  flex: 1;
  overflow: hidden;
}

.session-title {
  display: block;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #1e293b;
  font-weight: 500;
}

.session-time {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 3px;
}

.session-item.active .session-time {
  color: #0ea5e9;
}

.delete-btn {
  opacity: 0;
  padding: 6px 10px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #dc2626;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s ease;
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: #fee2e2;
  border-color: #f87171;
}

/* 空状态 */
.empty-state {
  padding: 60px 24px;
  text-align: center;
  color: #94a3b8;
}

.empty-state p {
  margin-bottom: 10px;
}

.empty-state .hint {
  font-size: 13px;
  color: #cbd5e1;
}

/* 侧边栏底部 */
.sidebar-footer {
  padding: 16px;
  border-top: 1px solid #f1f5f9;
  background: #fafafa;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar { width: 32px; height: 32px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 50%; background: #002fa7; color: #fff; font-size: 13px; font-weight: 700; }
.user-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; line-height: 1.25; }
.user-copy strong, .user-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-copy strong { color: #1e293b; font-size: 13px; }
.user-copy span { color: #94a3b8; font-size: 11px; }
.logout-btn { padding: 5px 7px; border: 0; background: transparent; color: #64748b; font-size: 12px; cursor: pointer; }
.logout-btn:hover { color: #dc2626; }

/* Swiss workspace visual system */
.sidebar {
  width: 292px;
  color: #111318;
  background: #f7f7f8;
  border-right-color: #d9dce3;
  border-top: 4px solid #002fa7;
}

.sidebar-header {
  padding: 22px 20px 20px;
  background: #f7f7f8;
  border-bottom-color: #d9dce3;
}

.logo { margin-bottom: 22px; }
.logo-icon { width: 56px; height: 56px; flex-basis: 56px; filter: none; }
.logo-copy strong { color: #111318; font-size: 15px; }
.logo-copy span { color: #687080; letter-spacing: .02em; }

.new-chat-btn {
  min-height: 48px;
  justify-content: space-between;
  padding: 0 16px;
  background: #002fa7;
  border: 1px solid #002fa7;
  border-radius: 6px;
  box-shadow: none;
  transition: background .18s ease, color .18s ease;
}

.new-chat-btn:hover {
  color: #002fa7;
  background: #ffffff;
  transform: none;
  box-shadow: none;
}

.new-chat-btn .icon { font-size: 18px; }

.search-box { padding: 16px 20px 10px; }
.search-input {
  height: 44px;
  padding: 0 13px;
  color: #111318;
  background: #ffffff;
  border-color: #d9dce3;
  border-radius: 4px;
  transition: border-color .18s ease;
}
.search-input:focus { border-color: #002fa7; box-shadow: none; }
.search-input::placeholder { color: #8a919e; }

.session-list { padding-top: 8px; }
.session-list-header {
  padding: 12px 20px 9px;
  color: #687080;
  font-size: 10px;
  letter-spacing: .14em;
}
.session-items { padding: 0 12px 16px; }
.session-item {
  position: relative;
  margin: 0;
  padding: 13px 12px 13px 16px;
  border: 0;
  border-bottom: 1px solid #e2e4e9;
  border-radius: 0;
}
.session-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: transparent;
}
.session-item:hover { background: #ffffff; }
.session-item.active { background: #ffffff; border-color: #e2e4e9; }
.session-item.active::before { background: #002fa7; }
.session-title { color: #252932; font-size: 13px; }
.session-time { color: #8a919e; font-size: 10px; }
.session-item.active .session-title,
.session-item.active .session-time { color: #002fa7; }
.delete-btn {
  width: 28px;
  height: 28px;
  padding: 0;
  color: #687080;
  background: #ffffff;
  border: 1px solid #d9dce3;
  border-radius: 3px;
  font-size: 15px;
}

.sidebar-footer { padding: 14px 20px; background: #ffffff; border-top-color: #d9dce3; }
.user-avatar { border-radius: 4px; background: #002fa7; }
.logout-btn { color: #687080; text-decoration: underline; text-underline-offset: 3px; }

@media (max-width: 900px) and (min-width: 721px) {
  .sidebar { width: 250px; }
  .logo-copy span { display: none; }
}

@media (max-width: 720px) {
  .sidebar {
    width: 100%;
    height: auto;
    max-height: 270px;
    flex-shrink: 0;
    border-right: 0;
    border-bottom: 1px solid #d9dce3;
  }
  .sidebar-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 14px;
  }
  .logo { flex: 1; margin: 0; }
  .logo-icon { width: 44px; height: 44px; flex-basis: 44px; }
  .new-chat-btn { width: auto; min-height: 40px; gap: 20px; }
  .search-box { padding: 8px 14px 4px; }
  .search-input { height: 38px; }
  .session-list { max-height: 86px; padding: 4px 0; }
  .session-list-header { display: none; }
  .session-items { display: flex; gap: 6px; padding: 4px 14px 8px; overflow-x: auto; }
  .session-item { min-width: 190px; border: 1px solid #d9dce3; padding: 9px 10px 9px 14px; }
  .session-item::before { top: 7px; bottom: 7px; }
  .sidebar-footer { padding: 8px 14px; }
}

@media (max-width: 480px) {
  .logo-copy span { display: none; }
  .logo-copy strong { font-size: 13px; }
  .new-chat-btn { padding: 0 12px; gap: 8px; }
}

/* Higher-density blue navigation rail */
.sidebar {
  color: #ffffff;
  background: #002fa7;
  border-top-color: #002fa7;
  border-right-color: #00247f;
}
.sidebar-header { background: #002fa7; border-bottom-color: rgba(255,255,255,.22); }
.logo-copy strong { color: #ffffff; }
.logo-copy span { color: rgba(255,255,255,.66); }
.logo-icon { filter: drop-shadow(0 8px 14px rgba(0,0,0,.2)); }
.new-chat-btn {
  color: #002fa7;
  background: #ffffff;
  border-color: #ffffff;
}
.new-chat-btn:hover { color: #ffffff; background: #002fa7; border-color: rgba(255,255,255,.72); }
.search-input {
  color: #ffffff;
  background: rgba(255,255,255,.08);
  border-color: rgba(255,255,255,.34);
}
.search-input:focus { border-color: #ffffff; }
.search-input::placeholder { color: rgba(255,255,255,.58); }
.session-list-header { color: rgba(255,255,255,.6); }
.session-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,.28); }
.session-item { border-bottom-color: rgba(255,255,255,.18); }
.session-item:hover { background: rgba(255,255,255,.09); }
.session-title { color: rgba(255,255,255,.9); }
.session-time { color: rgba(255,255,255,.54); }
.session-item.active { background: #ffffff; border-color: #ffffff; }
.session-item.active::before { background: #ffffff; }
.session-item.active .session-title,
.session-item.active .session-time { color: #002fa7; }
.delete-btn { color: #002fa7; background: #ffffff; border-color: rgba(255,255,255,.72); }
.empty-state { color: rgba(255,255,255,.72); }
.empty-state .hint { color: rgba(255,255,255,.48); }
.sidebar-footer { background: #00247f; border-top-color: rgba(255,255,255,.22); }
.user-avatar { color: #002fa7; background: #ffffff; }
.user-copy strong { color: #ffffff; }
.user-copy span { color: rgba(255,255,255,.6); }
.logout-btn { color: rgba(255,255,255,.72); }
.logout-btn:hover { color: #ffffff; }

@media (max-width: 720px) {
  .sidebar { border-bottom-color: #00247f; }
  .session-item { border-color: rgba(255,255,255,.25); }
  .session-item.active { border-color: #ffffff; }
}

/* Softer mist-blue navigation palette */
.sidebar {
  color: #213653;
  background: #eaf1fb;
  border-top-color: #315fa8;
  border-right-color: #c8d6ea;
}
.sidebar-header { background: #eaf1fb; border-bottom-color: #c8d6ea; }
.logo-copy strong { color: #172a46; }
.logo-copy span { color: #637895; }
.logo-icon { filter: drop-shadow(0 6px 12px rgba(49,95,168,.16)); }
.new-chat-btn {
  color: #ffffff;
  background: #315fa8;
  border-color: #315fa8;
}
.new-chat-btn:hover { color: #315fa8; background: #ffffff; border-color: #315fa8; }
.search-input {
  color: #213653;
  background: rgba(255,255,255,.72);
  border-color: #b7c8df;
}
.search-input:focus { border-color: #315fa8; }
.search-input::placeholder { color: #71839b; }
.session-list-header { color: #637895; }
.session-list::-webkit-scrollbar-thumb { background: #a9bad2; }
.session-item { border-bottom-color: #cad7e8; }
.session-item:hover { background: rgba(255,255,255,.62); }
.session-title { color: #213653; }
.session-time { color: #71839b; }
.session-item.active { background: #ffffff; border-color: #c8d6ea; }
.session-item.active::before { background: #315fa8; }
.session-item.active .session-title,
.session-item.active .session-time { color: #315fa8; }
.delete-btn { color: #315fa8; background: #ffffff; border-color: #b7c8df; }
.empty-state { color: #637895; }
.empty-state .hint { color: #8293aa; }
.sidebar-footer { background: #dce7f6; border-top-color: #c0d0e4; }
.user-avatar { color: #ffffff; background: #315fa8; }
.user-copy strong { color: #172a46; }
.user-copy span { color: #637895; }
.logout-btn { color: #526a89; }
.logout-btn:hover { color: #315fa8; }

@media (max-width: 720px) {
  .sidebar { border-bottom-color: #c8d6ea; }
  .session-item { border-color: #bdcce0; }
  .session-item.active { border-color: #9fb5d2; }
}
</style>
