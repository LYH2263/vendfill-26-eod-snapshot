<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const data = ref<any>(null)
const errCode = ref('')
const errMsg = ref('')
const loading = ref(false)

async function readErr(e: any) {
  try {
    const body = JSON.parse(e.message)
    errCode.value = body?.detail?.code || ''
    errMsg.value = body?.detail?.message || e.message
  } catch {
    errCode.value = ''
    errMsg.value = e.message
  }
}

async function loadLatest() {
  errCode.value = ''; errMsg.value = ''
  try { data.value = await api('/exports/eod/latest') }
  catch (e: any) {
    data.value = null
    if (!e.message.includes('EOD_EXPORT_NOT_FOUND')) await readErr(e)
  }
}

async function doExport() {
  loading.value = true
  errCode.value = ''; errMsg.value = ''
  try { data.value = await api('/exports/eod', { method: 'POST' }) }
  catch (e: any) { await readErr(e) }
  finally { loading.value = false }
}

onMounted(loadLatest)
</script>

<template>
  <h1>日终口径包</h1>
  <p class="sub">导出瞬间钉死：待补总件数 · 满仓货道 · 超占货道 —— 之后改库存不回写本包</p>
  <button class="btn" :disabled="loading" @click="doExport">导出日终口径包</button>

  <div v-if="errCode" class="card" style="margin-top:1rem;border-color:var(--vf-red)">
    <span class="badge" :class="errCode === 'EOD_NO_LOCATIONS' ? 'badge-warn' : 'badge-bad'">{{ errCode }}</span>
    <span style="margin-left:0.5rem">{{ errMsg }}</span>
  </div>

  <div v-if="data" style="margin-top:1rem">
    <div class="card">
      <div class="muted">导出时间</div>
      <div>{{ data.exported_at }}</div>
      <div class="muted" style="margin-top:0.4rem">校验指纹</div>
      <div style="font-size:0.72rem;word-break:break-all">{{ data.sha256 }}</div>
      <div class="muted" style="margin-top:0.4rem">待补总件数</div>
      <div class="stat">{{ data.total_fill }}</div>
    </div>
    <div class="card">
      <div class="muted" style="margin-bottom:0.4rem">满仓货道（{{ data.full_lanes.length }}）</div>
      <table>
        <thead><tr><th>货道</th><th>商品</th><th>库存</th><th>在途</th><th>容量</th></tr></thead>
        <tbody>
          <tr v-for="l in data.full_lanes" :key="l.lane_id">
            <td>{{ l.slot_no }}</td><td>{{ l.sku_name }}</td><td>{{ l.stock }}</td><td>{{ l.in_transit }}</td><td>{{ l.capacity }}</td>
          </tr>
          <tr v-if="!data.full_lanes.length"><td colspan="5" class="muted">无</td></tr>
        </tbody>
      </table>
    </div>
    <div class="card">
      <div class="muted" style="margin-bottom:0.4rem">超占货道（{{ data.overbooked_lanes.length }}）</div>
      <table>
        <thead><tr><th>货道</th><th>商品</th><th>库存</th><th>在途</th><th>容量</th><th>缺口</th></tr></thead>
        <tbody>
          <tr v-for="l in data.overbooked_lanes" :key="l.lane_id">
            <td>{{ l.slot_no }}</td><td>{{ l.sku_name }}</td><td>{{ l.stock }}</td><td>{{ l.in_transit }}</td><td>{{ l.capacity }}</td>
            <td><span class="badge badge-bad">{{ l.gap }}</span></td>
          </tr>
          <tr v-if="!data.overbooked_lanes.length"><td colspan="6" class="muted">无</td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <p v-else-if="!errCode" class="muted" style="margin-top:1rem">尚未导出过口径包</p>
</template>
