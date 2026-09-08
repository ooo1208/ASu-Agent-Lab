<template>
  <section class="lab-workspace" :aria-label="page === 'evidence' ? '证据工作台' : '评估中心'">
    <template v-if="page === 'evidence'">
      <header class="workspace-heading">
        <div><p class="eyebrow">EVIDENCE STUDIO</p><h1>让每一个数字，都有出处。</h1><p>导入财务资料，查找证据，完成可复核的计算。</p></div>
        <span class="workspace-tag">个人资料空间</span>
      </header>
      <div class="evidence-grid">
        <section class="panel import-panel">
          <div class="panel-heading"><span class="step">01</span><div><h2>导入资料</h2><p>TXT、Markdown、CSV 或文本 PDF · 最大 10 MB</p></div></div>
          <label class="field">资料分组<input v-model.trim="namespace" maxlength="200" placeholder="default" /></label>
          <label class="file-picker"><input ref="fileInput" type="file" accept=".txt,.md,.csv,.pdf" @change="selectFile" :disabled="busy.file || busy.ingest" /><strong>{{ busy.file ? '正在读取文件…' : (selectedFile?.name || '选择本地文件') }}</strong><span>{{ selectedFile ? formatSize(selectedFile.size) : '文件只会在点击导入后上传' }}</span></label>
          <div class="inline-actions"><button class="link-button" type="button" @click="fillDocumentDemo" :disabled="busy.ingest">填入合成财报样例</button><button v-if="selectedFile" class="link-button" type="button" @click="clearFile">清除文件</button></div>
          <label v-if="!selectedFile" class="field">文档名称<input v-model.trim="filename" maxlength="240" placeholder="report.md" /></label>
          <label v-if="!selectedFile || !isPdf" class="field">{{ selectedFile ? '内容预览' : '文档内容' }}<textarea v-model="documentText" :readonly="!!selectedFile" rows="9" placeholder="也可以粘贴财务文本，在导入前确认内容。" /></label>
          <p v-else class="quiet-note">PDF 将保留原始页码。扫描图片需要先转换为可提取文本的 PDF。</p>
          <p v-if="documentIsDemo" class="sample-note">合成教学数据，不对应真实公司。点击下方按钮后才会导入。</p>
          <button class="primary" type="button" @click="ingestDocument" :disabled="busy.ingest || busy.file || !canIngest">{{ busy.ingest ? '正在建立证据索引…' : '导入并建立证据' }}<span aria-hidden="true">↗</span></button>
          <p v-if="errors.ingest" class="error" role="alert">{{ errors.ingest }}</p>
          <div v-if="imported" class="success" role="status"><strong>已导入 {{ imported.filename }}</strong><span>{{ imported.fragment_count }} 个证据片段 · {{ imported.namespace }}</span></div>
        </section>

        <section class="panel search-panel">
          <div class="panel-heading"><span class="step">02</span><div><h2>查找与回查</h2><p>按指标、实体或年份搜索，并打开原始片段。</p></div></div>
          <form class="search-form" @submit.prevent="searchEvidence"><label class="sr-only" for="evidence-query">证据搜索关键词</label><input id="evidence-query" v-model.trim="query" placeholder="例如：营业收入、revenue、2025" maxlength="1000" /><button class="primary compact" :disabled="busy.search || !query">{{ busy.search ? '查找中…' : '搜索证据' }}</button></form>
          <p class="quiet-note">当前分组：{{ namespace || 'default' }} · 关键词检索</p>
          <p v-if="errors.search" class="error" role="alert">{{ errors.search }}</p>
          <div v-if="!searched && !busy.search" class="empty"><span class="empty-symbol" aria-hidden="true">⌕</span><h3>从一份资料开始</h3><p>导入文档后，输入关键词查找可引用的原文。</p></div>
          <div v-else-if="searched && !hits.length && !busy.search" class="empty"><h3>没有找到匹配证据</h3><p>请确认资料分组，或换用文档中的指标、公司名称和年份。</p></div>
          <div v-else class="evidence-results" aria-live="polite">
            <article v-for="hit in hits" :key="hit.citation_id" class="evidence-card">
              <div class="evidence-title"><strong>{{ hit.filename }}</strong><span>{{ location(hit) }}</span></div>
              <p class="evidence-text">{{ hit.text }}</p>
              <div class="evidence-footer"><code>{{ hit.citation_id }}</code><button class="link-button" @click="openCitation(hit.citation_id)" :disabled="busy.citation">回查原文 ↗</button></div>
            </article>
          </div>
          <p v-if="errors.citation" class="error" role="alert">{{ errors.citation }}</p>
          <aside v-if="citation" class="citation-detail" aria-label="原始证据详情"><div class="evidence-title"><h3>{{ citation.filename }}</h3><button class="icon-button" @click="citation = null" aria-label="关闭原文">×</button></div><p class="quiet-note">{{ location(citation) }} · 分组 {{ citation.namespace }}</p><pre>{{ citation.text }}</pre><code>{{ citation.citation_id }}</code></aside>
        </section>

        <section class="panel calculate-panel">
          <div class="panel-heading"><span class="step">03</span><div><h2>可复核计算</h2><p>十进制计算保留输入、公式与结果。输入金额应使用相同币种和单位。</p></div></div>
          <div class="calculation-grid"><div><label class="field">计算指标<select v-model="operation" @change="resetOperands"><option v-for="(item, key) in operations" :key="key" :value="key">{{ item.title }}</option></select></label><div class="operand-grid"><label v-for="field in currentOperation.fields" :key="field.key" class="field">{{ field.label }}<input v-model.trim="operands[field.key]" inputmode="decimal" placeholder="十进制数字" /></label></div><button class="primary compact" @click="calculateMetric" :disabled="busy.calculate">{{ busy.calculate ? '计算中…' : '计算结果' }}</button><p v-if="errors.calculate" class="error" role="alert">{{ errors.calculate }}</p></div>
            <div class="calculation-result" aria-live="polite"><template v-if="calculation"><span class="result-label">{{ operations[calculation.operation]?.title || calculation.operation }}</span><strong>{{ calculation.result }}<small>{{ calculation.unit === 'percent' ? '%' : (calculation.unit === 'ratio' ? ' 倍' : '') }}</small></strong><code>{{ calculation.formula }}</code><p>输入：{{ Object.entries(calculation.inputs).map(([key, value]) => `${key} = ${value}`).join(' · ') }}</p></template><template v-else><span class="result-label">计算结果</span><strong class="result-placeholder">—</strong><p>选择指标并填写原始数字</p></template></div></div>
        </section>
      </div>
    </template>

    <template v-else-if="page === 'evaluation'">
      <header class="workspace-heading"><div><p class="eyebrow">EVALUATION CENTER</p><h1>从一次运行，到持续改进。</h1><p>提交执行快照，查看异步评分，把人工修正沉淀为黄金用例。</p></div><button class="secondary" @click="refreshEvaluation" :disabled="busy.jobs">{{ busy.jobs ? '刷新中…' : '刷新任务' }}</button></header>
      <div class="metric-strip"><div><span>最近任务</span><strong>{{ jobs.length }}</strong></div><div><span>等待 / 执行中</span><strong>{{ jobs.filter(j => ['pending', 'running'].includes(j.status)).length }}</strong></div><div><span>已完成评分</span><strong>{{ jobs.filter(j => j.status === 'complete').length }}</strong></div><div><span>需要处理</span><strong>{{ jobs.filter(j => j.status === 'failed').length }}</strong></div></div>
      <p v-if="errors.jobs" class="error" role="alert">{{ errors.jobs }}</p>
      <div class="evaluation-grid">
        <section class="panel evaluation-create"><div class="panel-heading"><span class="step">01</span><div><h2>创建评估任务</h2><p>这里提交合成快照，用于验证评估流程。</p></div></div>
          <div class="inline-actions"><button class="secondary compact" @click="fillEvaluationDemo(false)">填入通过样例</button><button class="secondary compact" @click="fillEvaluationDemo(true)">填入差错样例</button></div>
          <label class="field">用例名称<input v-model.trim="evaluationName" maxlength="200" placeholder="合成收入增长率" /></label>
          <div class="snapshot-grid"><label class="field">实际执行快照 · actual<textarea v-model="actualJson" rows="12" spellcheck="false" class="code-input" /></label><label class="field">评估标准 · expected<textarea v-model="expectedJson" rows="12" spellcheck="false" class="code-input" /></label></div>
          <p class="sample-note">示例中的答案、调用与耗时均为合成记录，不代表模型实际运行或业务效果。</p>
          <button class="primary" @click="submitEvaluation" :disabled="busy.submit">{{ busy.submit ? '正在提交…' : '提交到评估队列' }}<span aria-hidden="true">↗</span></button><p v-if="errors.submit" class="error" role="alert">{{ errors.submit }}</p><p v-if="submittedJob" class="success" role="status">已进入评估队列。结果由后台评估进程处理，页面每 5 秒刷新。</p>
        </section>
        <section class="panel job-list"><div class="panel-heading"><span class="step">02</span><div><h2>运行记录</h2><p>展示当前账号最近 50 个任务。</p></div></div><div v-if="!jobs.length" class="empty"><h3>{{ busy.jobs ? '正在加载任务…' : '还没有评估任务' }}</h3><p>提交一个合成样例，观察队列、评分和反馈的完整流程。</p></div><button v-for="job in jobs" :key="job.id" class="job-row" :class="{ selected: selectedJob?.id === job.id }" @click="selectJob(job.id)"><div><strong>{{ job.trace_id }}</strong><span>{{ formatTime(job.created_at) }} · 尝试 {{ job.attempts }} 次</span></div><span class="status-badge" :class="job.status">{{ statusLabel(job.status) }}</span></button></section>
      </div>

      <section v-if="selectedJob" class="panel job-detail"><div class="panel-heading"><span class="step">03</span><div><h2>评估明细</h2><p>{{ selectedJob.trace_id }}</p></div><span class="status-badge" :class="selectedJob.status">{{ statusLabel(selectedJob.status) }}</span></div>
        <p v-if="['pending', 'running'].includes(selectedJob.status)" class="queue-note" role="status">{{ selectedJob.status === 'pending' ? '等待后台评估进程领取任务。当前尚未产生评分。' : '后台正在执行评估，完成后将展示评分。' }}</p>
        <div v-if="selectedJob.status === 'failed'" class="error"><p>{{ selectedJob.last_error || '评估未能完成，请检查后台服务后重试。' }}</p><button class="secondary compact" @click="retryJob" :disabled="busy.retry">{{ busy.retry ? '提交重试中…' : '重新排队' }}</button></div>
        <div v-if="selectedJob.scores?.length" class="score-grid"><article v-for="score in selectedJob.scores" :key="score.name" class="score-card"><div><span>{{ scoreLabels[score.name] || score.name }}</span><strong>{{ Math.round(score.value * 100) }}<small>%</small></strong></div><div class="score-track"><span :style="{ width: `${Math.max(0, Math.min(100, score.value * 100))}%` }" :class="{ imperfect: score.value < 1 }"></span></div><p>{{ score.reason }}</p></article></div>
        <div v-if="selectedJob.status === 'complete'" class="delivery-line"><strong>评分结果已保存</strong><span v-for="(count, state) in selectedJob.delivery" :key="state">观测同步{{ deliveryLabel(state) }} {{ count }}</span><button v-if="selectedJob.delivery?.failed" class="link-button" @click="retryJob" :disabled="busy.retry">重试同步</button></div>
        <p v-if="errors.detail" class="error" role="alert">{{ errors.detail }}</p>
        <details class="snapshot-details"><summary>查看实际快照与标准</summary><div class="snapshot-grid"><pre>{{ pretty(selectedJob.payload?.actual) }}</pre><pre>{{ pretty(selectedJob.payload?.expected) }}</pre></div></details>

        <div class="feedback-layout"><form @submit.prevent="submitFeedback"><h3>人工反馈</h3><label class="field">核验结论<select v-model.number="feedbackRating"><option :value="1">符合预期</option><option :value="0">需要修正</option></select></label><label class="field">反馈说明<textarea v-model="feedbackComment" maxlength="4000" rows="3" placeholder="说明错误原因、修正依据或确认结果。" /></label><label class="field">已核对的标准答案 · corrected_expected<textarea v-model="correctedExpected" rows="6" class="code-input" spellcheck="false" /></label><button class="primary compact" :disabled="busy.feedback">{{ busy.feedback ? '保存中…' : '保存反馈' }}</button><p v-if="errors.feedback" class="error" role="alert">{{ errors.feedback }}</p></form>
          <div class="feedback-history"><h3>反馈与黄金用例</h3><label class="field">黄金集版本<input v-model.trim="datasetVersion" maxlength="100" placeholder="reviewed-v1" /></label><p v-if="!feedbacks.length" class="quiet-note">保存反馈后，可将核对过的评估标准加入黄金集。</p><article v-for="feedback in feedbacks" :key="feedback.id" class="feedback-item"><div><strong>{{ feedback.rating === 1 ? '符合预期' : '需要修正' }}</strong><span>{{ formatTime(feedback.created_at) }}</span></div><p>{{ feedback.comment || '未填写说明' }}</p><button class="link-button" @click="promoteFeedback(feedback.id)" :disabled="busy.promote || !feedback.corrected_expected">加入黄金集 ↗</button></article><div class="inline-actions"><button class="secondary compact" @click="loadGolden" :disabled="busy.golden || !datasetVersion">{{ busy.golden ? '读取中…' : '查看黄金集' }}</button></div><p v-if="promotedCase" class="success" role="status">已加入 {{ datasetVersion }}，可供后续回归评估。</p><p v-if="errors.golden" class="error" role="alert">{{ errors.golden }}</p><details v-if="golden" class="snapshot-details" open><summary>{{ golden.version }} · {{ golden.cases?.length || 0 }} 个用例</summary><pre>{{ pretty(golden) }}</pre></details></div>
        </div>
      </section>
      <p v-else-if="errors.detail" class="error" role="alert">{{ errors.detail }}</p>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { authFetch } from '../api/client.js'

const props = defineProps({ page: { type: String, required: true } })
const busy = reactive({})
const errors = reactive({})
const namespace = ref('default')
const filename = ref('synthetic_report.md')
const documentText = ref('')
const documentIsDemo = ref(false)
const selectedFile = ref(null)
const fileBase64 = ref('')
const fileInput = ref(null)
const imported = ref(null)
const query = ref('营业收入')
const hits = ref([])
const searched = ref(false)
const citation = ref(null)
const isPdf = computed(() => selectedFile.value?.name.toLowerCase().endsWith('.pdf'))
const canIngest = computed(() => namespace.value && (selectedFile.value ? fileBase64.value : filename.value && documentText.value.trim()))
const operations = {
  change_rate: { title: '收入 / 指标增长率', fields: [{ key: 'old', label: '上期数值' }, { key: 'new', label: '本期数值' }], defaults: ['100', '120'] },
  debt_ratio: { title: '资产负债率', fields: [{ key: 'liabilities', label: '负债总额' }, { key: 'assets', label: '资产总额' }], defaults: ['80', '200'] },
  gross_margin: { title: '毛利率', fields: [{ key: 'revenue', label: '营业收入' }, { key: 'cost', label: '营业成本' }], defaults: ['120', '72'] },
  current_ratio: { title: '流动比率', fields: [{ key: 'current_assets', label: '流动资产' }, { key: 'current_liabilities', label: '流动负债' }], defaults: ['90', '45'] },
  net_margin: { title: '净利率', fields: [{ key: 'net_profit', label: '净利润' }, { key: 'revenue', label: '营业收入' }], defaults: ['18', '120'] },
  add: { title: '加法', fields: [{ key: 'a', label: '数值 A' }, { key: 'b', label: '数值 B' }], defaults: ['0.1', '0.2'] },
  subtract: { title: '减法', fields: [{ key: 'a', label: '数值 A' }, { key: 'b', label: '数值 B' }], defaults: ['120', '100'] },
  multiply: { title: '乘法', fields: [{ key: 'a', label: '数值 A' }, { key: 'b', label: '数值 B' }], defaults: ['12', '10'] },
  divide: { title: '除法', fields: [{ key: 'a', label: '被除数' }, { key: 'b', label: '除数' }], defaults: ['120', '100'] },
}
const operation = ref('change_rate')
const currentOperation = computed(() => operations[operation.value])
const operands = ref({ old: '100', new: '120' })
const calculation = ref(null)
const jobs = ref([])
const selectedJob = ref(null)
const submittedJob = ref('')
const evaluationName = ref('合成收入增长率')
const actualJson = ref('')
const expectedJson = ref('')
const feedbacks = ref([])
const feedbackRating = ref(1)
const feedbackComment = ref('')
const correctedExpected = ref('')
const datasetVersion = ref('reviewed-v1')
const promotedCase = ref('')
const golden = ref(null)
let pollTimer = null
let selectionRequest = 0
let mounted = true
const scoreLabels = { numeric_accuracy: '数值准确性', evidence_recall: '证据召回', citation_precision: '引用准确性', task_completion: '任务完成', tool_selection: '工具选择', parameter_completeness: '参数完整性', approval_safety: '审批保护', forbidden_tool_safety: '工具权限', latency_budget: '耗时预算', token_budget: 'Token 预算' }

const pretty = value => JSON.stringify(value ?? {}, null, 2)
function jsonObject(source, label) {
  let parsed
  try { parsed = JSON.parse(source) } catch { throw new Error(`${label} 不是有效 JSON，请检查引号、逗号和括号。`) }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(`${label} 必须是 JSON 对象。`)
  return parsed
}
async function request(url, options = {}) {
  const response = await authFetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } })
  let data
  try { data = await response.json() } catch { throw new Error(response.ok ? '服务返回了无法读取的数据。' : `请求失败（${response.status}），请稍后重试。`) }
  if (!response.ok) {
    const detail = data.detail
    throw new Error(Array.isArray(detail) ? detail.map(item => `${item.loc?.slice(1).join('.') || '参数'}：${item.msg}`).join('；') : (typeof detail === 'string' ? detail : `请求失败（${response.status}）`))
  }
  return data
}
async function run(key, action) {
  if (busy[key]) return
  busy[key] = true
  errors[key] = ''
  try { return await action() } catch (error) { errors[key] = error.message || '操作失败，请稍后重试。' } finally { busy[key] = false }
}
function clearFile() {
  selectedFile.value = null
  fileBase64.value = ''
  documentText.value = ''
  documentIsDemo.value = false
  if (fileInput.value) fileInput.value.value = ''
}
async function selectFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  clearFile()
  await run('file', async () => {
    if (!/\.(txt|md|csv|pdf)$/i.test(file.name)) throw new Error('请选择 TXT、Markdown、CSV 或 PDF 文件。')
    if (!file.size) throw new Error('文件为空，请选择包含内容的资料。')
    if (file.size > 10 * 1024 * 1024) throw new Error('文件超过 10 MB，请拆分后再导入。')
    const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('无法读取本地文件。')); reader.readAsDataURL(file) })
    selectedFile.value = file
    fileBase64.value = encoded
    filename.value = file.name
    if (!/\.pdf$/i.test(file.name)) documentText.value = await file.text()
    imported.value = null
  })
  if (errors.file) errors.ingest = errors.file
}
function fillDocumentDemo() {
  clearFile()
  filename.value = 'synthetic_report.md'
  documentIsDemo.value = true
  documentText.value = '# 合成财务报告：ASu Demo Manufacturing\n\n本文件为合成教学数据，不对应真实公司。\n币种：人民币；金额单位：万元；同一公司合并报表。\n2024 年营业收入为 100，2025 年营业收入为 120。\n2025 年营业成本为 72，净利润为 18。\n2025 年资产为 200，负债为 80，所有者权益为 120。\n2025 年流动资产为 90，流动负债为 45。\n\n核验目标：营业收入增长率、资产负债率、毛利率和流动比率。'
  imported.value = null
  errors.ingest = ''
}
async function ingestDocument() {
  await run('ingest', async () => {
    imported.value = await request('/api/finance/documents', { method: 'POST', body: JSON.stringify({ filename: filename.value, content: selectedFile.value ? fileBase64.value : documentText.value, encoding: selectedFile.value ? 'base64' : 'utf-8', namespace: namespace.value }) })
  })
}
async function searchEvidence() {
  await run('search', async () => {
    const data = await request(`/api/finance/search?${new URLSearchParams({ q: query.value, namespace: namespace.value || 'default', limit: '8' })}`)
    hits.value = data.results || []
    searched.value = true
    citation.value = null
  })
}
async function openCitation(id) {
  await run('citation', async () => { citation.value = await request(`/api/finance/citations/${encodeURIComponent(id)}?${new URLSearchParams({ namespace: namespace.value || 'default' })}`) })
}
function resetOperands() {
  operands.value = Object.fromEntries(currentOperation.value.fields.map((field, index) => [field.key, currentOperation.value.defaults[index]]))
  calculation.value = null
  errors.calculate = ''
}
async function calculateMetric() {
  await run('calculate', async () => { calculation.value = await request('/api/finance/calculate', { method: 'POST', body: JSON.stringify({ operation: operation.value, values: operands.value }) }) })
}
function location(item) {
  const parts = []
  if (item.page) parts.push(`第 ${item.page} 页`)
  if (item.metadata?.table_row) parts.push(`表格第 ${item.metadata.table_row} 行`)
  if (item.line_start) parts.push(`第 ${item.line_start}${item.line_end > item.line_start ? `–${item.line_end}` : ''} 行`)
  return parts.join(' · ') || item.metadata?.evidence_key || '原始片段'
}
function formatSize(size) { return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(size / 1024)} KB` }
function formatTime(value) { return new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
function statusLabel(status) { return ({ pending: '等待评估', running: '评估中', complete: '已完成', failed: '失败' })[status] || status }
function deliveryLabel(status) { return ({ pending: '待发送', running: '发送中', sent: '已完成', failed: '失败' })[status] || status }
function fillEvaluationDemo(failed) {
  const citationId = 'synthetic-report:revenue-2025'
  evaluationName.value = failed ? '合成收入增长率 · 差错样例' : '合成收入增长率 · 通过样例'
  actualJson.value = pretty({ answer_numeric: failed ? '25' : '20', citations: failed ? ['unsupported-citation'] : [citationId], task_completed: true, tool_calls: [{ name: 'calculate_financial_metric', arguments: { operation: 'change_rate', values: { old: '100', new: '120' } }, status: 'success' }], safety: { side_effect_performed: false, approved: false }, latency_ms: 180, token_count: 0 })
  expectedJson.value = pretty({ answer_numeric: '20', absolute_tolerance: '0.01', evidence_ids: [citationId], allowed_evidence_ids: [citationId], task_completed: true, required_tools: { calculate_financial_metric: ['operation', 'values'] }, requires_approval: true, forbidden_tools: ['approve_loan'], max_latency_ms: 1000, max_tokens: 0 })
  errors.submit = ''
}
async function submitEvaluation() {
  await run('submit', async () => {
    const actual = jsonObject(actualJson.value, '实际执行快照')
    const expected = jsonObject(expectedJson.value, '评估标准')
    const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    const data = await request('/api/evaluation/jobs', { method: 'POST', body: JSON.stringify({ trace_id: `${evaluationName.value || 'synthetic-case'}-${id.slice(0, 8)}`, session_id: 'synthetic-workbench', version: 'synthetic-ui-v1', run_id: id, input_data: { question: '合成数据：收入从 100 增至 120，增长率是多少？', synthetic: true }, actual, expected }) })
    submittedJob.value = data.job_id
    await refreshEvaluation()
    await selectJob(data.job_id)
  })
}
async function refreshEvaluation() {
  await run('jobs', async () => {
    const data = await request('/api/evaluation/jobs?limit=50')
    if (!mounted) return
    jobs.value = Array.isArray(data) ? data : []
    if (selectedJob.value) await updateSelectedJob()
  })
}
async function updateSelectedJob() {
  const id = selectedJob.value?.id
  if (!id) return
  const data = await request(`/api/evaluation/jobs/${encodeURIComponent(id)}`)
  if (mounted && selectedJob.value?.id === id) selectedJob.value = data
}
async function selectJob(id) {
  const ticket = ++selectionRequest
  errors.detail = ''
  try {
    const [detail, feedback] = await Promise.all([request(`/api/evaluation/jobs/${encodeURIComponent(id)}`), request(`/api/evaluation/jobs/${encodeURIComponent(id)}/feedback`)])
    if (!mounted || ticket !== selectionRequest) return
    selectedJob.value = detail
    feedbacks.value = feedback
    correctedExpected.value = pretty(detail.payload?.expected)
    feedbackComment.value = ''
    promotedCase.value = ''
    errors.feedback = ''
  } catch (error) { if (ticket === selectionRequest) errors.detail = error.message }
}
async function retryJob() {
  await run('retry', async () => { await request(`/api/evaluation/jobs/${encodeURIComponent(selectedJob.value.id)}/retry`, { method: 'POST' }); await refreshEvaluation() })
  if (errors.retry) errors.detail = errors.retry
}
async function submitFeedback() {
  await run('feedback', async () => {
    const id = selectedJob.value.id
    const corrected = jsonObject(correctedExpected.value, '核对后的评估标准')
    await request(`/api/evaluation/jobs/${encodeURIComponent(id)}/feedback`, { method: 'POST', body: JSON.stringify({ rating: feedbackRating.value, comment: feedbackComment.value, corrected_expected: corrected }) })
    const data = await request(`/api/evaluation/jobs/${encodeURIComponent(id)}/feedback`)
    if (selectedJob.value?.id === id) feedbacks.value = data
  })
}
async function promoteFeedback(id) {
  await run('promote', async () => {
    if (!datasetVersion.value) throw new Error('请填写黄金集版本。')
    const result = await request(`/api/evaluation/feedback/${encodeURIComponent(id)}/promote`, { method: 'POST', body: JSON.stringify({ dataset_version: datasetVersion.value }) })
    promotedCase.value = result.case_id
    await loadGolden()
  })
  if (errors.promote) errors.golden = errors.promote
}
async function loadGolden() {
  await run('golden', async () => { golden.value = await request(`/api/evaluation/golden/${encodeURIComponent(datasetVersion.value)}`) })
}
watch(namespace, () => { hits.value = []; citation.value = null; searched.value = false; imported.value = null })
watch(datasetVersion, () => { golden.value = null; promotedCase.value = ''; errors.golden = '' })
watch(() => props.page, page => { if (page === 'evaluation') refreshEvaluation() })
onMounted(() => { fillEvaluationDemo(false); if (props.page === 'evaluation') refreshEvaluation(); pollTimer = window.setInterval(() => { if (props.page === 'evaluation' && !document.hidden) refreshEvaluation() }, 5000) })
onBeforeUnmount(() => { mounted = false; window.clearInterval(pollTimer) })
</script>

<style scoped>
.lab-workspace,.lab-workspace *{box-sizing:border-box}.lab-workspace{flex:1;min-height:0;overflow:auto;padding:36px clamp(18px,3.5vw,56px) 60px;background:#f6f8fc;color:#182d49;font-family:Arial,"Microsoft YaHei",sans-serif}.workspace-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin:0 auto 30px;max-width:1420px}.eyebrow{font-size:10px;font-weight:800;letter-spacing:.16em;color:#5077a4;margin:0 0 10px}.workspace-heading h1{font-size:clamp(25px,2.5vw,36px);line-height:1.35;letter-spacing:-.04em;margin:0 0 10px}.workspace-heading p:not(.eyebrow){color:#718098;font-size:13px;line-height:1.7;margin:0}.workspace-tag{border:1px solid #ced9e7;color:#58708b;background:#fff;padding:9px 13px;font-size:11px;white-space:nowrap;border-radius:5px}.evidence-grid,.evaluation-grid{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(350px,1.2fr);gap:22px;max-width:1420px;margin:auto}.panel{background:#fff;border:1px solid #dce4ef;border-radius:12px;padding:26px;min-width:0;box-shadow:0 4px 18px #16365703}.panel-heading{display:flex;gap:12px;align-items:center;margin-bottom:22px}.panel-heading>div{flex:1;min-width:0}.step{font-size:11px;font-weight:700;background:#edf2fb;color:#4772ac;width:32px;height:32px;border-radius:7px;display:grid;place-items:center;flex-shrink:0}.panel-heading h2{font-size:17px;line-height:1.4;margin:0}.panel-heading p{font-size:11px;color:#8290a4;line-height:1.65;margin:4px 0 0;overflow-wrap:anywhere}.field{display:flex;flex-direction:column;gap:8px;font-size:12px;font-weight:600;color:#50627a;margin-bottom:17px}.field input,.field textarea,.field select,.search-form input{width:100%;min-width:0;background:#fbfcfe;border:1px solid #d6e0ed;border-radius:6px;padding:11px 12px;color:#253c5a;font:400 13px/1.6 inherit;outline:none;transition:border-color .15s,box-shadow .15s}.field textarea{font-family:inherit;line-height:1.7;font-size:12px;resize:vertical;min-height:70px}.field input:focus,.field textarea:focus,.field select:focus,.search-form input:focus{border-color:#6c90c7;box-shadow:0 0 0 3px #315fa80b}.field textarea[readonly]{background:#f5f7fb;color:#718198}.field .code-input{font-family:Consolas,"SFMono-Regular",monospace;font-size:11px;line-height:1.55}.file-picker{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;min-height:115px;border:1px dashed #a9beda;background:#f7faff;border-radius:8px;padding:20px;cursor:pointer;text-align:center}.file-picker input{position:absolute;inset:0;opacity:0;width:100%;height:100%;cursor:pointer}.file-picker:focus-within{outline:2px solid #315fa8;outline-offset:2px}.file-picker strong{font-size:13px;overflow-wrap:anywhere}.file-picker span{font-size:11px;color:#8393aa}.primary,.secondary{display:inline-flex;align-items:center;justify-content:space-between;gap:16px;min-height:42px;padding:11px 16px;border:1px solid #315fa8;border-radius:6px;font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .15s}.primary{background:#315fa8;color:#fff}.primary:hover:not(:disabled){background:#254d8f}.secondary{background:#fff;color:#48678f;border-color:#cbd8ea}.secondary:hover:not(:disabled){background:#f0f5fc}.import-panel>.primary,.evaluation-create>.primary{width:100%}.compact{padding:8px 13px;min-height:37px;font-size:11px;white-space:nowrap}button:disabled{opacity:.5;cursor:wait}button:focus-visible{outline:2px solid #315fa8;outline-offset:3px}.link-button{border:0;background:none;padding:3px 0;color:#426da8;font:600 11px/1.5 inherit;cursor:pointer;text-align:left}.link-button:hover{text-decoration:underline;text-underline-offset:3px}.inline-actions{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:13px 0 18px}.quiet-note,.sample-note{font-size:11px;line-height:1.7;color:#8190a6;margin:12px 0}.sample-note{color:#8b753c;background:#fbf8ee;padding:10px 12px;border-left:2px solid #d8c181}.error{margin:14px 0 0;padding:11px 13px;border:1px solid #efd2d2;border-radius:6px;background:#fff8f8;color:#a94e51;font-size:12px;line-height:1.7;overflow-wrap:anywhere}.error p{margin:0 0 9px}.success{display:flex;flex-direction:column;gap:4px;padding:12px;border:1px solid #cce5dd;background:#f3fbf8;color:#3c7d69;border-radius:6px;margin:14px 0 0;font-size:11px;line-height:1.7}.success strong{font-size:12px}.search-form{display:flex;gap:10px}.search-form input{flex:1;font-size:12px}.evidence-results{display:flex;flex-direction:column;gap:14px;max-height:510px;overflow:auto;margin-top:20px;padding-right:3px}.evidence-card{border:1px solid #e0e7f0;border-radius:8px;padding:17px;background:#fff}.evidence-title{display:flex;justify-content:space-between;align-items:center;gap:12px}.evidence-title strong,.evidence-title h3{font-size:12px;margin:0;overflow-wrap:anywhere}.evidence-title>span{font-size:10px;color:#8794a7;white-space:nowrap}.evidence-text{font-size:12px;line-height:1.85;white-space:pre-wrap;overflow-wrap:anywhere;margin:13px 0 15px;color:#65768e;max-height:180px;overflow:auto}.evidence-footer{display:flex;gap:15px;justify-content:space-between;align-items:center;border-top:1px solid #edf1f6;padding-top:11px}.evidence-footer code,.citation-detail code{font-size:9px;color:#94a0b1;overflow-wrap:anywhere}.evidence-footer .link-button{flex-shrink:0}.empty{min-height:210px;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;padding:35px;color:#8493a8}.empty-symbol{font-size:42px;color:#adc0d8;line-height:1.2}.empty h3{font-size:14px;color:#6b809e;margin:13px 0 8px}.empty p{font-size:12px;line-height:1.8;max-width:310px;margin:0}.citation-detail{border-left:3px solid #7c9dc8;background:#f4f8fe;padding:17px;margin-top:18px}.citation-detail pre,.snapshot-details pre{font:11px/1.8 Consolas,"Microsoft YaHei",monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto}.icon-button{background:none;border:0;color:#8192a8;font-size:20px;cursor:pointer}.calculate-panel{grid-column:1/-1}.calculation-grid{display:grid;grid-template-columns:1fr 1fr;gap:36px}.operand-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.calculation-result{border-left:1px solid #e5ebf3;padding:10px 0 10px 36px;display:flex;flex-direction:column;justify-content:center;min-width:0}.result-label{color:#8395ae;font-size:11px}.calculation-result>strong{font-size:38px;color:#315fa8;letter-spacing:-.04em;font-weight:500;line-height:1.7;overflow-wrap:anywhere}.calculation-result strong small{font-size:18px;margin-left:4px}.calculation-result code{font-size:11px;color:#768eac;overflow-wrap:anywhere}.calculation-result p{font-size:10px;color:#98a5b6;line-height:1.8;overflow-wrap:anywhere}.calculation-result .result-placeholder{color:#ccd6e3}.metric-strip{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #dce4ef;border-radius:10px;background:#fff;margin:0 auto 22px;max-width:1420px}.metric-strip>div{display:flex;flex-direction:column;gap:12px;padding:22px 25px;border-right:1px solid #e7ecf4}.metric-strip>div:last-child{border:0}.metric-strip span{font-size:11px;color:#8193ab}.metric-strip strong{font-size:28px;font-weight:500;color:#315fa8}.evaluation-grid{grid-template-columns:minmax(400px,1.3fr) minmax(260px,.7fr)}.snapshot-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.job-list{max-height:760px;overflow:auto}.job-row{width:100%;display:flex;justify-content:space-between;gap:16px;align-items:center;padding:16px 8px;border:0;border-bottom:1px solid #edf1f7;background:none;text-align:left;cursor:pointer;font-family:inherit}.job-row:hover,.job-row.selected{background:#f3f7fd}.job-row>div{min-width:0;display:flex;flex-direction:column;gap:8px}.job-row strong{font-size:11px;color:#526b8c;overflow-wrap:anywhere}.job-row div span{font-size:10px;color:#97a3b5}.status-badge{font-size:10px;padding:5px 8px;border-radius:5px;white-space:nowrap;background:#f0f3f8;color:#8290a7;flex-shrink:0}.status-badge.complete{background:#ecf7f1;color:#47866d}.status-badge.failed{background:#fff0ef;color:#bc6360}.status-badge.running{background:#edf3fd;color:#587fb7}.status-badge.pending{background:#fbf6e9;color:#ac9556}.job-detail{max-width:1420px;margin:22px auto 0}.queue-note{background:#f4f7fc;border:1px solid #e0e8f4;padding:13px 15px;border-radius:6px;font-size:12px;color:#6983a5}.score-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:13px}.score-card{border:1px solid #e4eaf2;border-radius:7px;padding:14px;min-width:0}.score-card>div:first-child{display:flex;justify-content:space-between;gap:10px;align-items:center}.score-card span{font-size:10px;color:#7f8da1}.score-card strong{font-size:20px;font-weight:500;color:#467aa9}.score-card small{font-size:10px}.score-track{height:3px;background:#eef2f7;margin:12px 0}.score-track span{height:100%;display:block;background:#75a3ba}.score-track span.imperfect{background:#cb9a77}.score-card p{font-size:9px;line-height:1.6;color:#99a4b3;margin:0;overflow-wrap:anywhere}.delivery-line{display:flex;align-items:center;gap:15px;flex-wrap:wrap;padding:17px 0;font-size:10px;color:#899aae}.delivery-line strong{color:#6c8b7e;font-weight:500}.snapshot-details{font-size:11px;color:#7990ac;border-top:1px solid #e7edf5;padding-top:16px;margin-top:12px}.snapshot-details summary{cursor:pointer}.snapshot-details pre{background:#f8fafd;padding:14px;color:#6e819c;border-radius:6px}.feedback-layout{display:grid;grid-template-columns:1fr 1fr;gap:35px;border-top:1px solid #e4ebf4;padding-top:25px;margin-top:25px}.feedback-layout h3{font-size:15px;margin:0 0 19px}.feedback-history{border-left:1px solid #e7edf5;padding-left:35px}.feedback-item{border-bottom:1px solid #e7edf5;padding:13px 0}.feedback-item>div{display:flex;justify-content:space-between;gap:12px}.feedback-item strong{font-size:11px;color:#6984a7}.feedback-item span{font-size:10px;color:#9ba8b8}.feedback-item p{font-size:12px;color:#7b8da4;line-height:1.7;overflow-wrap:anywhere}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1100px){.score-grid{grid-template-columns:repeat(3,1fr)}.evaluation-grid{grid-template-columns:minmax(350px,1fr) minmax(240px,.7fr)}.snapshot-grid{grid-template-columns:1fr}.panel{padding:21px}.lab-workspace{padding:28px 24px 45px}}
@media(max-width:850px){.evidence-grid,.evaluation-grid{grid-template-columns:1fr}.calculation-grid{gap:20px}.calculation-result{padding-left:20px}.job-list{max-height:380px}.snapshot-grid{grid-template-columns:1fr 1fr}.workspace-tag{display:none}.workspace-heading h1{font-size:26px}.feedback-layout{gap:22px}.feedback-history{padding-left:22px}}
@media(max-width:600px){.lab-workspace{padding:23px 14px 35px}.workspace-heading{align-items:flex-start;gap:12px;margin-bottom:22px}.workspace-heading h1{font-size:23px}.workspace-heading p:not(.eyebrow){font-size:11px}.workspace-heading>.secondary{font-size:10px;padding:9px;flex-shrink:0}.panel{padding:18px}.evidence-grid,.evaluation-grid{gap:16px}.calculation-grid,.feedback-layout,.snapshot-grid{grid-template-columns:1fr}.calculation-result{border-left:0;border-top:1px solid #e5ebf3;padding:23px 0 0}.metric-strip>div{padding:17px 12px}.metric-strip span{font-size:9px}.metric-strip strong{font-size:25px}.score-grid{grid-template-columns:repeat(2,1fr)}.feedback-history{border-left:0;border-top:1px solid #e7edf5;padding:22px 0 0}.search-form{gap:7px}.search-form input{padding:9px;font-size:11px}.evidence-title{align-items:flex-start}.evidence-title>span{white-space:normal;text-align:right;flex-shrink:0;max-width:45%}.evidence-footer{align-items:flex-start}.evidence-footer code{font-size:8px}.calculation-result>strong{font-size:32px}.operand-grid{gap:10px}}
</style>
