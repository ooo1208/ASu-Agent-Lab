<template>
  <main class="auth-shell">
    <section class="auth-brand" aria-labelledby="brand-title">
      <div class="brand-grid" aria-hidden="true"></div>
      <header class="brand-header">
        <a class="brand-mark" href="/" aria-label="ASu Agent Lab 首页">
          <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M7 8.5h18v11H14l-7 5v-16Z"/><path d="M12 13h8M12 17h5"/></svg>
          <span>ASu Agent Lab</span>
        </a>
        <span class="brand-meta">智能体协作与评估工作台</span>
      </header>

      <div class="brand-content">
        <div class="brand-copy">
          <p class="eyebrow">从业务执行到证据与评估</p>
          <h1 id="brand-title">让每次协作<br />都有依据。</h1>
          <p class="brand-note">连接业务数据、专业 Agent 与可回查证据，在你的工作空间里完成分析、协作和持续改进。</p>
        </div>

        <div class="workflow" aria-label="ASu 智能协作流程">
          <div class="workflow-heading"><span>ASu 智能协作流程</span><span>3 个阶段</span></div>
          <ol>
            <li><span class="workflow-index">01</span><div><strong>理解需求</strong><p>结合当前会话与长期偏好记忆</p></div></li>
            <li><span class="workflow-index">02</span><div><strong>证据分析</strong><p>查找原文、复核数字与专业 Agent 协同</p></div></li>
            <li><span class="workflow-index">03</span><div><strong>持续评估</strong><p>记录运行结果，将人工反馈转为黄金用例</p></div></li>
          </ol>
        </div>
      </div>

      <footer class="capability-strip" aria-label="平台能力">
        <span>个人资料空间</span><span>证据回查</span><span>异步评估</span><span>人工反馈</span>
      </footer>
    </section>

    <section class="auth-panel">
      <div class="panel-frame">
        <div class="panel-topline"><span>{{ mode === 'login' ? '账号登录' : '账号注册' }}</span><span>ASu Agent Lab</span></div>
        <form class="auth-form" @submit.prevent="submit">
          <div class="form-heading">
            <div class="form-symbol" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M16 3 27 8.5v7.7c0 6.5-4.5 10.7-11 12.8C9.5 26.9 5 22.7 5 16.2V8.5L16 3Z"/><path d="m11.5 16 3 3 6.5-7"/></svg></div>
            <h2>{{ mode === 'login' ? '欢迎回来' : '创建你的账号' }}</h2>
            <p>{{ mode === 'login' ? '登录后继续访问你的会话、资料和评估记录。' : '创建账号后，开始使用你的个人资料与协作空间。' }}</p>
          </div>

          <label v-if="mode === 'register'">
            <span>显示名称</span>
            <div class="input-line"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.5-4.2 2.7-6.3 6.5-6.3s6 2.1 6.5 6.3"/></svg><input v-model.trim="displayName" autocomplete="name" maxlength="50" placeholder="例如：ASu" required /></div>
          </label>
          <label>
            <span>用户名</span>
            <div class="input-line"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.5-4.2 2.7-6.3 6.5-6.3s6 2.1 6.5 6.3"/></svg><input v-model.trim="username" autocomplete="username" minlength="3" maxlength="32" placeholder="输入用户名" required /></div>
          </label>
          <label>
            <span>密码</span>
            <div class="input-line">
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10"/><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10"/></svg>
              <input v-model="password" :type="showPassword ? 'text' : 'password'" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" minlength="8" maxlength="128" placeholder="至少 8 位" required />
              <button class="password-toggle" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                <svg v-if="!showPassword" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12s3.2-5 9-5 9 5 9 5-3.2 5-9 5-9-5-9-5Z"/><circle cx="12" cy="12" r="2.5"/></svg>
                <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="m4 4 16 16M10.2 7.2A9.8 9.8 0 0 1 12 7c5.8 0 9 5 9 5a14.4 14.4 0 0 1-2.2 2.7M14.4 16.7A9.5 9.5 0 0 1 12 17c-5.8 0-9-5-9-5a15 15 0 0 1 3-3.4"/></svg>
              </button>
            </div>
          </label>

          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="submit-button" type="submit" :disabled="submitting">
            <span>{{ submitting ? '正在校验…' : (mode === 'login' ? '登录' : '创建账号') }}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M14 7l5 5-5 5"/></svg>
          </button>
          <button class="mode-button" type="button" @click="switchMode">{{ mode === 'login' ? '没有账号？创建账号' : '已有账号？返回登录' }}</button>

          <div class="privacy-note">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 20 7v5.6c0 4.7-3.3 7.8-8 9.4-4.7-1.6-8-4.7-8-9.4V7l8-4Z"/><path d="m8.5 12.5 2.2 2.2 4.8-5"/></svg>
            <p>你的会话、资料和评估记录按账号分别保存。</p>
          </div>
        </form>
        <footer class="panel-footer"><span>有据可查</span><span>可复核 · 可改进</span></footer>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref } from 'vue'
import { login, register } from '../api/auth.js'

const emit = defineEmits(['authenticated'])
const mode = ref('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const submitting = ref(false)
const showPassword = ref(false)

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
  showPassword.value = false
}

async function submit() {
  if (submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const user = mode.value === 'login'
      ? await login(username.value, password.value)
      : await register(username.value, password.value, displayName.value)
    emit('authenticated', user)
  } catch (err) {
    error.value = err.message || '认证失败，请重试'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.auth-shell,.auth-shell *{box-sizing:border-box}
.auth-shell{min-height:100vh;display:grid;grid-template-columns:minmax(560px,1.2fr) minmax(430px,.8fr);background:#f7f7f8;color:#111318;font-family:Arial,"Helvetica Neue",sans-serif}.auth-brand{position:relative;min-height:100vh;padding:34px 48px 30px;display:flex;flex-direction:column;overflow:hidden;background:#002fa7;color:#fff}.brand-grid{position:absolute;inset:0;opacity:.13;background-image:linear-gradient(rgba(255,255,255,.55) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.55) 1px,transparent 1px);background-size:72px 72px;mask-image:linear-gradient(to bottom right,#000 15%,transparent 82%);pointer-events:none}.brand-header,.brand-content,.capability-strip{position:relative;z-index:1}.brand-header{display:flex;align-items:center;justify-content:space-between;padding-bottom:20px;border-bottom:1px solid rgba(255,255,255,.4)}.brand-mark{display:inline-flex;align-items:center;gap:11px;color:#fff;text-decoration:none;font-size:14px;font-weight:700;letter-spacing:-.01em}.brand-mark svg{width:27px;height:27px;fill:none;stroke:currentColor;stroke-width:1.6}.brand-meta,.eyebrow,.workflow-heading,.capability-strip,.panel-topline{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}.brand-meta{color:rgba(255,255,255,.7)}.brand-content{flex:1;display:grid;grid-template-columns:minmax(0,1.1fr) minmax(280px,.75fr);gap:clamp(40px,6vw,96px);align-items:center;padding:72px 0 60px}.brand-copy{max-width:650px}.eyebrow{margin:0;color:rgba(255,255,255,.72)}.brand-copy h1{margin:22px 0 28px;font-size:clamp(56px,6.1vw,96px);line-height:.96;letter-spacing:-.062em}.brand-note{max-width:510px;margin:0;color:rgba(255,255,255,.78);font-size:15px;line-height:1.8}.workflow{align-self:end;border-top:1px solid rgba(255,255,255,.55);border-bottom:1px solid rgba(255,255,255,.55)}.workflow-heading{display:flex;justify-content:space-between;padding:14px 0;color:rgba(255,255,255,.72)}.workflow ol{margin:0;padding:0;list-style:none}.workflow li{display:grid;grid-template-columns:42px 1fr;gap:10px;padding:18px 0;border-top:1px solid rgba(255,255,255,.24)}.workflow-index{padding-top:2px;color:rgba(255,255,255,.56);font-size:11px;font-weight:700}.workflow strong{display:block;margin-bottom:5px;font-size:14px}.workflow p{margin:0;color:rgba(255,255,255,.65);font-size:12px;line-height:1.55}.capability-strip{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid rgba(255,255,255,.4);color:rgba(255,255,255,.7)}.capability-strip span{padding-top:17px;text-align:center;border-right:1px solid rgba(255,255,255,.24)}.capability-strip span:first-child{text-align:left}.capability-strip span:last-child{border-right:0;text-align:right}
.brand-copy{min-width:0}.brand-copy h1{font-size:clamp(52px,4.6vw,76px);white-space:nowrap}
.auth-panel{min-height:100vh;padding:30px;border-left:1px solid #d9dce3;background:#fff}.panel-frame{width:100%;min-height:calc(100vh - 60px);display:grid;grid-template-rows:auto 1fr auto;border:1px solid #d9dce3}.panel-topline,.panel-footer{display:flex;justify-content:space-between;color:#687080}.panel-topline{padding:17px 20px;border-bottom:1px solid #d9dce3}.auth-form{width:min(100% - 48px,420px);margin:auto;padding:56px 0}.form-heading{margin-bottom:42px}.form-symbol{width:42px;height:42px;display:grid;place-items:center;margin-bottom:24px;border:1px solid #002fa7;color:#002fa7}.form-symbol svg,.input-line>svg,.password-toggle svg,.privacy-note svg,.submit-button svg{fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:square;stroke-linejoin:miter}.form-symbol svg{width:24px;height:24px}.form-heading h2{margin:0 0 10px;font-size:38px;line-height:1.08;letter-spacing:-.045em}.form-heading p{max-width:390px;margin:0;color:#687080;font-size:14px;line-height:1.65}label{display:block;margin-bottom:23px}label>span{display:block;margin-bottom:9px;color:#4d5563;font-size:12px;font-weight:700}.input-line{height:51px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #aeb4bf;transition:border-color .18s}.input-line:focus-within{border-bottom:2px solid #002fa7}.input-line>svg{width:18px;height:18px;flex:0 0 auto;color:#737b89}input{min-width:0;flex:1;height:100%;padding:0;border:0;outline:none;color:#111318;background:transparent;font:400 15px/1 Arial,"Helvetica Neue",sans-serif}input::placeholder{color:#9aa0aa}.password-toggle{width:34px;height:34px;display:grid;place-items:center;padding:0;border:0;background:transparent;color:#687080;cursor:pointer}.password-toggle:hover{color:#002fa7}.password-toggle svg{width:19px;height:19px}.form-error{margin:-3px 0 20px;padding:11px 13px;border-left:3px solid #002fa7;background:rgba(0,47,167,.05);color:#002fa7;font-size:13px}.submit-button{width:100%;height:52px;display:flex;align-items:center;justify-content:space-between;margin-top:32px;padding:0 18px;border:1px solid #002fa7;background:#002fa7;color:#fff;font-size:14px;font-weight:700;cursor:pointer;transition:background .18s,color .18s}.submit-button:hover:not(:disabled){background:#fff;color:#002fa7}.submit-button:disabled{opacity:.55;cursor:wait}.submit-button svg{width:20px;height:20px}.mode-button{width:100%;margin-top:16px;padding:4px;border:0;background:none;color:#596170;font-size:13px;cursor:pointer}.mode-button:hover{color:#002fa7;text-decoration:underline;text-underline-offset:4px}.privacy-note{display:grid;grid-template-columns:22px 1fr;gap:11px;margin-top:34px;padding-top:18px;border-top:1px solid #d9dce3;color:#687080}.privacy-note svg{width:20px;height:20px;color:#002fa7}.privacy-note p{margin:0;font-size:11px;line-height:1.65}.panel-footer{padding:16px 20px;border-top:1px solid #d9dce3;font-size:10px;font-weight:700;letter-spacing:.08em}
@media(max-width:1180px){.auth-shell{grid-template-columns:minmax(480px,1fr) minmax(400px,.8fr)}.brand-content{grid-template-columns:1fr;gap:44px}.workflow{max-width:520px;align-self:auto}.brand-copy h1{font-size:clamp(54px,7vw,78px)}}@media(max-width:860px){.auth-shell{grid-template-columns:1fr}.auth-brand{min-height:auto;padding:26px}.brand-meta{display:none}.brand-content{padding:58px 0 44px}.brand-copy,.brand-note{width:100%;max-width:100%}.brand-note{overflow-wrap:anywhere}.brand-copy h1{font-size:clamp(46px,12vw,68px)}.workflow{display:none}.capability-strip{grid-template-columns:repeat(2,1fr);row-gap:14px}.capability-strip span{text-align:left!important;border-right:0}.auth-panel{min-width:0;min-height:auto;padding:18px;border-left:0}.panel-frame{min-width:0;min-height:auto}.auth-form{padding:48px 0}}@media(max-width:480px){.auth-brand{padding:22px 20px}.brand-content{padding-top:46px}.brand-copy h1{font-size:46px}.brand-note{font-size:14px}.capability-strip{font-size:9px}.auth-panel{padding:0}.panel-frame{border-right:0;border-left:0}.auth-form{width:min(100% - 40px,420px)}.form-heading h2{font-size:34px}.panel-footer{flex-direction:column;gap:5px}}
</style>
