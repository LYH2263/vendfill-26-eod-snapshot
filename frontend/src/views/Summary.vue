<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const s = ref<any>({})
const pack = ref<any>(null)
const loading = ref(false)
const err = ref<{ code: string; message: string } | null>(null)

async function refreshSummary() {
  s.value = await api('/refills/summary?location_id=1')
}

async function exportEod() {
  loading.value = true
  err.value = null
  try {
    // 这份包在导出瞬间钉死：之后库存再变，返回内容也不会被回刷
    pack.value = await api('/refills/eod-exports?location_id=1', { method: 'POST' })
  } catch (e: any) {
    // 无点位(LOCATION_NOT_FOUND) 与 包被回刷(EXPORT_SNAPSHOT_REFRESHED) 是两套码
    let code = 'ERROR'
    let message = e.message
    try {
      const d = JSON.parse(e.message)
      if (d.detail?.code) { code = d.detail.code; message = d.detail.message }
    } catch { /* 非结构化错误，保留原文 */ }
    err.value = { code, message }
  } finally {
    loading.value = false
    refreshSummary()  // 货道页/汇总等实时视图仍跟新库存
  }
}

onMounted(refreshSummary)
</script>

<template>
  <h1>汇总</h1>
  <p class="sub">本点位补货建议合计（实时，跟当前库存）</p>
  <div class="card grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">建议补货总量</div><div class="stat">{{ s.total_fill }}</div></div>
    <div><div class="muted">待补货道</div><div class="stat">{{ s.need_fill_count }}</div></div>
    <div><div class="muted">满仓货道</div><div class="stat">{{ s.full_count }}</div></div>
    <div><div class="muted">超占货道</div><div class="stat">{{ s.overbooked_count }}</div></div>
  </div>

  <div style="margin-top:1.25rem">
    <button class="btn" :disabled="loading" @click="exportEod">
      {{ loading ? '导出中…' : '日终导出（钉死口径包）' }}
    </button>
    <p class="muted" style="margin:0.5rem 0 0;font-size:0.78rem">
      导出后再改库存，不会回写这份包；货道页与之后新生成的补货单仍按新库存走。
    </p>
  </div>

  <div v-if="err" class="card" style="margin-top:1rem;border-color:#c0392b">
    <strong>导出失败 · 码：{{ err.code }}</strong>
    <div class="muted" style="margin-top:0.25rem">{{ err.message }}</div>
  </div>

  <div v-if="pack" class="vf-receipt" style="margin-top:1rem">
    <h2>*** 日终口径包 #{{ pack.id }} ***</h2>
    <div class="vf-receipt-line"><span>导出时间</span><span>{{ pack.exported_at }}</span></div>
    <div class="vf-receipt-line" style="font-weight:700">
      <span>待补总件数</span><span>{{ pack.total_fill }}</span>
    </div>
    <div style="margin-top:0.5rem;font-weight:700">满仓货道（{{ pack.full_lanes.length }}）</div>
    <div class="vf-receipt-line" v-for="l in pack.full_lanes" :key="'f' + l.lane_id">
      <span>{{ l.slot_no }} {{ l.sku_name }}</span>
      <span>{{ l.stock }}+{{ l.in_transit }}/{{ l.capacity }}</span>
    </div>
    <div class="muted" v-if="!pack.full_lanes.length">（无）</div>
    <div style="margin-top:0.5rem;font-weight:700">超占货道（{{ pack.overbooked_lanes.length }}）</div>
    <div class="vf-receipt-line" v-for="l in pack.overbooked_lanes" :key="'o' + l.lane_id">
      <span>{{ l.slot_no }} {{ l.sku_name }}</span>
      <span>{{ l.stock }}+{{ l.in_transit }}/{{ l.capacity }} · 缺{{ l.gap }}</span>
    </div>
    <div class="muted" v-if="!pack.overbooked_lanes.length">（无）</div>
    <p style="text-align:center;margin:1rem 0 0;font-size:0.72rem;color:#6a5e48">
      本包已钉死 · 不随后续库存变化
    </p>
  </div>
</template>
