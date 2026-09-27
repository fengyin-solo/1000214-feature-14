<template>
  <section class="page" data-module="security">
    <header class="page-head">
      <div>
        <h2>安防巡视管理</h2>
        <p class="page-desc">维护安防记录，围绕巡视编号、巡视区域、巡视人员、巡视时间做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记安防记录</button>
        <button class="btn" type="button" @click="exportRows">导出安防巡视清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="panel">
      <h3>班次核对与交接</h3>
      <div class="shift-bar">
        <label class="filter-item">
          <span>巡视班次</span>
          <input v-model="shift" placeholder="如：2026-09-27 白班" @change="reloadShiftPanels" />
        </label>
        <button class="btn" type="button" @click="runShiftAction('collect')">取样入核对区</button>
        <button class="btn" type="button" @click="runShiftAction('review')">逐项核对</button>
        <button class="btn primary" type="button" @click="runShiftAction('confirm')">确认生成交接文件</button>
      </div>
      <p v-if="shiftMessage" class="shift-message">{{ shiftMessage }}</p>

      <h4>取样核对区（{{ reviewRows.length }}）</h4>
      <table class="data-table">
        <thead>
          <tr><th>巡视编号</th><th>巡视区域</th><th>巡视人员</th><th>核对状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in reviewRows" :key="String(row.id)">
            <td>{{ row['巡视编号'] ?? '—' }}</td>
            <td>{{ row['巡视区域'] ?? '—' }}</td>
            <td>{{ row['巡视人员'] ?? '—' }}</td>
            <td><span class="tag" :class="tagClass(row['核对状态'])">{{ row['核对状态'] ?? '—' }}</span></td>
          </tr>
          <tr v-if="!reviewRows.length">
            <td colspan="4" class="empty-state">核对区为空，填写班次后先取样入区</td>
          </tr>
        </tbody>
      </table>

      <h4>待修正清单（{{ correctionRows.length }}）</h4>
      <table class="data-table">
        <thead>
          <tr><th>巡视编号</th><th>巡视区域</th><th>巡视人员</th><th>修正原因</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in correctionRows" :key="String(row.id)">
            <template v-if="editingId === Number(row.id)">
              <td><input v-model="editForm['巡视编号']" /></td>
              <td><input v-model="editForm['巡视区域']" /></td>
              <td><input v-model="editForm['巡视人员']" /></td>
              <td>{{ row['修正原因'] ?? '—' }}</td>
              <td class="row-actions">
                <button class="link" type="button" @click="submitCorrection(row)">提交</button>
                <button class="link" type="button" @click="editingId = null">取消</button>
              </td>
            </template>
            <template v-else>
              <td>{{ row['巡视编号'] ?? '—' }}</td>
              <td>{{ row['巡视区域'] ?? '—' }}</td>
              <td>{{ row['巡视人员'] ?? '—' }}</td>
              <td>{{ row['修正原因'] ?? '—' }}</td>
              <td><button class="link" type="button" @click="startEdit(row)">修正</button></td>
            </template>
          </tr>
          <tr v-if="!correctionRows.length">
            <td colspan="5" class="empty-state">没有待修正记录</td>
          </tr>
        </tbody>
      </table>

      <h4>结果文件（{{ fileRows.length }}）</h4>
      <table class="data-table">
        <thead>
          <tr><th>文件编号</th><th>文件类型</th><th>巡视班次</th><th>生成时间</th><th>记录数</th><th>异常数</th></tr>
        </thead>
        <tbody>
          <tr v-for="file in fileRows" :key="String(file.id)">
            <td>{{ file['文件编号'] ?? '—' }}</td>
            <td><span class="tag" :class="file['文件类型'] === '说明文件' ? 'ok' : ''">{{ file['文件类型'] ?? '—' }}</span></td>
            <td>{{ file['巡视班次'] ?? '—' }}</td>
            <td>{{ file['生成时间'] ?? '—' }}</td>
            <td>{{ file['记录数'] ?? 0 }}</td>
            <td>{{ file['异常数'] ?? 0 }}</td>
          </tr>
          <tr v-if="!fileRows.length">
            <td colspan="6" class="empty-state">还没有生成结果文件，确认核对通过后自动打包</td>
          </tr>
        </tbody>
      </table>
    </section>

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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
      <span>共 {{ total }} 条安防巡视记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/security'
const columns = ["巡视编号", "巡视区域", "巡视人员", "巡视班次", "巡视时间", "异常描述", "处理情况", "交接事项", "核对状态"]
const actions = ["开始巡视", "记录异常", "完成巡视"]
const stats = [{"label": "今日巡视", "value": 0}, {"label": "异常巡视", "value": 0}, {"label": "待巡视区域", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const shift = ref('')
const shiftMessage = ref('')
const reviewRows = ref<Row[]>([])
const correctionRows = ref<Row[]>([])
const fileRows = ref<Row[]>([])
const editingId = ref<number | null>(null)
const editForm = ref<Record<string, string>>({})

function tagClass(status: unknown) {
  if (status === '已核对') return 'ok'
  if (status === '待修正') return 'warn'
  return ''
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '安防记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '安防巡视动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安防巡视操作失败'
  }
}

async function runShiftAction(action: 'collect' | 'review' | 'confirm') {
  errorMessage.value = ''
  shiftMessage.value = ''
  if (!shift.value.trim()) {
    shiftMessage.value = '请先填写巡视班次'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/shifts/${action}`, {
      method: 'POST',
      body: JSON.stringify({ values: { 巡视班次: shift.value.trim() } }),
    })
    const payload = await response.json()
    shiftMessage.value = payload.message ?? '班次操作完成'
    await Promise.all([reload(), reloadShiftPanels()])
  } catch (error) {
    shiftMessage.value = error instanceof Error ? error.message : '班次操作失败'
  }
}

function startEdit(row: Row) {
  editingId.value = Number(row.id)
  editForm.value = {
    巡视编号: String(row['巡视编号'] ?? ''),
    巡视区域: String(row['巡视区域'] ?? ''),
    巡视人员: String(row['巡视人员'] ?? ''),
  }
}

async function submitCorrection(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/correct`, {
      method: 'POST',
      body: JSON.stringify({ values: editForm.value }),
    })
    const payload = await response.json()
    shiftMessage.value = payload.message ?? '记录已修正'
    editingId.value = null
    await reloadShiftPanels()
  } catch (error) {
    shiftMessage.value = error instanceof Error ? error.message : '修正提交失败'
  }
}

async function reloadShiftPanels() {
  const query = shift.value.trim() ? `?shift=${encodeURIComponent(shift.value.trim())}` : ''
  try {
    const [review, corrections, files] = await Promise.all([
      fetchJson<{ items?: Row[] }>(`${ENDPOINT}/review${query}`),
      fetchJson<{ items?: Row[] }>(`${ENDPOINT}/corrections${query}`),
      fetchJson<{ items?: Row[] }>(`${ENDPOINT}/files${query}`),
    ])
    reviewRows.value = review.items ?? []
    correctionRows.value = corrections.items ?? []
    fileRows.value = files.items ?? []
  } catch (error) {
    shiftMessage.value = error instanceof Error ? error.message : '班次面板读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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
  void reloadShiftPanels()
})
</script>
