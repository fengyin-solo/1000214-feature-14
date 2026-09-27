<template>
  <section class="page" data-module="security">
    <header class="page-head">
      <div>
        <h2>安防巡视管理</h2>
        <p class="page-desc">维护安防记录，围绕巡视编号、巡视区域、巡视人员、巡视班次做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记安防记录</button>
        <button class="btn" type="button" @click="exportRows">导出安防巡视清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="shift-panel">
      <header class="shift-head">
        <div>
          <h3>班次核对与交接</h3>
          <p class="page-desc">
            先把本班记录放进取样核对区，再按巡视区域和人员逐项检查；重复巡视编号留在待修正清单，
            确认后打包交接文件，本班无异常时同时生成说明文件，未核对的内容不进入正式记录。
          </p>
        </div>
        <div class="page-actions">
          <button class="btn" type="button" :disabled="!currentShift" @click="runShiftAction('stage')">班次取样</button>
          <button class="btn" type="button" :disabled="!currentShift" @click="runShiftAction('review')">逐项核对</button>
          <button class="btn primary" type="button" :disabled="!currentShift" @click="runShiftAction('confirm')">确认交接</button>
        </div>
      </header>

      <table class="data-table">
        <thead>
          <tr>
            <th>巡视班次</th>
            <th>记录数</th>
            <th>待核对</th>
            <th>已核对</th>
            <th>待修正</th>
            <th>异常数</th>
            <th>班次状态</th>
            <th>文件数</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="shift in shifts"
            :key="shift.巡视班次"
            :class="{ 'shift-active': shift.巡视班次 === currentShift }"
          >
            <td>{{ shift.巡视班次 }}</td>
            <td>{{ shift.记录数 }}</td>
            <td>{{ shift.待核对 }}</td>
            <td>{{ shift.已核对 }}</td>
            <td>{{ shift.待修正 }}</td>
            <td>{{ shift.异常数 }}</td>
            <td>{{ shift.班次状态 }}</td>
            <td>{{ shift.文件数 }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="selectShift(shift.巡视班次)">查看本班</button>
            </td>
          </tr>
          <tr v-if="!shifts.length">
            <td colspan="9" class="empty-state">暂无班次数据，登记安防记录时填写巡视班次即可归班</td>
          </tr>
        </tbody>
      </table>

      <p v-if="shiftMessage" class="shift-message">{{ shiftMessage }}</p>

      <div v-if="currentShift" class="shift-detail">
        <h4>待修正清单（{{ currentShift }}）</h4>
        <table class="data-table">
          <thead>
            <tr>
              <th>巡视编号</th>
              <th>巡视区域</th>
              <th>巡视人员</th>
              <th>核对意见</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in corrections" :key="String(row.id)">
              <td>{{ row.巡视编号 ?? '—' }}</td>
              <td>{{ row.巡视区域 ?? '—' }}</td>
              <td>{{ row.巡视人员 ?? '—' }}</td>
              <td>{{ row.核对意见 ?? '—' }}</td>
              <td class="row-actions">
                <button class="link" type="button" @click="correctRow(row)">修正编号</button>
              </td>
            </tr>
            <tr v-if="!corrections.length">
              <td colspan="5" class="empty-state">待修正清单为空</td>
            </tr>
          </tbody>
        </table>

        <h4>交接文件（{{ currentShift }}）</h4>
        <ul class="file-list">
          <li v-for="file in files" :key="file.文件名" class="file-item">
            <strong class="file-type">{{ file.文件类型 }}</strong>
            <span>{{ file.文件名 }}</span>
            <span class="file-time">{{ file.生成时间 }}</span>
            <span v-if="file.文件类型 === '交接文件'">记录 {{ file.记录数 }} 条，异常 {{ file.异常数 }} 条</span>
            <span v-else>{{ file.说明 }}</span>
          </li>
          <li v-if="!files.length" class="empty-state">确认交接后在此查看交接文件；本班无异常时会同时生成说明文件</li>
        </ul>
      </div>
    </section>

    <form v-if="showCreate" class="filter-bar create-bar" @submit.prevent="submitCreate">
      <label v-for="field in createFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit">提交登记</button>
      <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(row, column) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无安防巡视数据，可先登记安防记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条安防巡视记录<span v-if="currentShift">（当前班次：{{ currentShift }}）</span></span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

type ShiftSummary = {
  巡视班次: string
  记录数: number
  待核对: number
  已核对: number
  待修正: number
  异常数: number
  班次状态: string
  文件数: number
}

type ShiftFile = {
  文件类型: string
  文件名: string
  生成时间: string
  记录数?: number
  异常数?: number
  说明?: string
}

const ENDPOINT = '/api/security'
const columns = ["巡视编号", "巡视区域", "巡视人员", "巡视班次", "巡视时间", "异常描述", "处理情况", "交接事项", "核对状态"]
const actions = ["开始巡视", "记录异常", "完成巡视"]
const stats = [{"label": "今日巡视", "value": 0}, {"label": "异常巡视", "value": 0}, {"label": "待巡视区域", "value": 0}]
const createFields = ["巡视编号", "巡视区域", "巡视人员", "巡视班次"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showCreate = ref(false)
const createForm = ref<Record<string, string>>({})

const shifts = ref<ShiftSummary[]>([])
const currentShift = ref('')
const shiftMessage = ref('')
const corrections = ref<Row[]>([])
const files = ref<ShiftFile[]>([])

function formatCell(row: Row, column: string) {
  const value = row[column]
  if (value === true) return '是'
  if (value === false) return '否'
  return value ?? '—'
}

function resetFilters() {
  filters.value = {}
  currentShift.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '安防巡视动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安防巡视操作失败'
  }
}

async function submitCreate() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '安防记录登记失败'
      return
    }
    showCreate.value = false
    createForm.value = {}
    await Promise.all([reload(), loadShifts()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安防记录登记失败'
  }
}

async function selectShift(shift: string) {
  currentShift.value = shift
  shiftMessage.value = ''
  await Promise.all([reload(), loadCorrections(), loadFiles()])
}

async function runShiftAction(path: 'stage' | 'review' | 'confirm') {
  if (!currentShift.value) return
  shiftMessage.value = ''
  try {
    const response = await request(
      `${ENDPOINT}/shifts/${encodeURIComponent(currentShift.value)}/${path}`,
      { method: 'POST', body: JSON.stringify({ values: {} }) },
    )
    const payload = await response.json()
    shiftMessage.value = payload.message || '班次操作未生效，请稍后重试'
    await Promise.all([reload(), loadShifts(), loadCorrections(), loadFiles()])
  } catch (error) {
    shiftMessage.value = error instanceof Error ? error.message : '班次操作失败'
  }
}

async function correctRow(row: Row) {
  const code = window.prompt(`为记录 ${row.id} 输入新的巡视编号`, String(row.巡视编号 ?? ''))
  if (!code || !code.trim()) return
  shiftMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/correct`, {
      method: 'POST',
      body: JSON.stringify({ values: { 巡视编号: code.trim() } }),
    })
    const payload = await response.json()
    shiftMessage.value = payload.message || '修正未生效，请稍后重试'
    await Promise.all([reload(), loadShifts(), loadCorrections()])
  } catch (error) {
    shiftMessage.value = error instanceof Error ? error.message : '修正失败'
  }
}

async function loadShifts() {
  try {
    const payload = await fetchJson<{ items: ShiftSummary[] }>(`${ENDPOINT}/shifts`)
    shifts.value = payload.items ?? []
  } catch {
    shifts.value = []
  }
}

async function loadCorrections() {
  if (!currentShift.value) {
    corrections.value = []
    return
  }
  try {
    const payload = await fetchJson<{ items: Row[] }>(
      `${ENDPOINT}/shifts/${encodeURIComponent(currentShift.value)}/corrections`,
    )
    corrections.value = payload.items ?? []
  } catch {
    corrections.value = []
  }
}

async function loadFiles() {
  if (!currentShift.value) {
    files.value = []
    return
  }
  try {
    const payload = await fetchJson<{ items: ShiftFile[] }>(
      `${ENDPOINT}/shifts/${encodeURIComponent(currentShift.value)}/files`,
    )
    files.value = payload.items ?? []
  } catch {
    files.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value['巡视编号']) {
    query.set('keyword', filters.value['巡视编号'])
  }
  if (currentShift.value) {
    query.set('shift', currentShift.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('安防记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安防巡视列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadShifts()
})
</script>

<style scoped>
.shift-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}
.shift-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.shift-head h3 {
  margin: 0;
  font-size: 15px;
}
.shift-detail h4 {
  margin: 14px 0 6px;
  font-size: 13px;
}
.shift-active td {
  background: #eef4ff;
}
.shift-message {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--brand);
}
.file-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.file-item {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
}
.file-type {
  color: var(--brand);
}
.file-time {
  color: var(--muted);
}
.create-bar {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
