<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const refill = ref<any>(null)
async function load() {
  rows.value = await api('/lanes')
}
async function adjust(r: any, delta: number) {
  const stock = r.stock + delta
  if (stock < 0) return
  await api(`/lanes/${r.id}`, { method: 'PATCH', body: JSON.stringify({ stock }) })
  await load()
}
onMounted(async () => {
  await load()
  try { refill.value = await api('/refills/run?location_id=1', { method: 'POST' }) } catch { /* */ }
})
</script>
<template>
  <h1>货道格子</h1>
  <p class="sub">机面货道网格 · 格内库存条 · 右侧补货小票 · ± 调整库存实时生效</p>
  <div class="vf-machine-layout">
    <div class="vf-slot-grid">
      <div v-for="r in rows" :key="r.id" class="vf-slot">
        <div class="vf-slot-no">{{ r.slot_no }}</div>
        <div class="vf-slot-sku">{{ r.sku_name }}</div>
        <div class="vf-slot-bar">
          <div
            class="vf-slot-fill"
            :class="{ 'vf-need': r.gap > 0 }"
            :style="{ width: Math.min(r.fill_pct, 100) + '%' }"
          />
        </div>
        <div class="vf-slot-meta">{{ r.stock }}/{{ r.capacity }} · 缺 {{ r.gap }}</div>
        <div class="vf-slot-adj">
          <button class="vf-adj-btn" :disabled="r.stock <= 0" @click="adjust(r, -1)">−</button>
          <button class="vf-adj-btn" @click="adjust(r, 1)">＋</button>
        </div>
      </div>
    </div>
    <aside class="vf-receipt" v-if="refill">
      <h2>*** 补货建议单 ***</h2>
      <div class="vf-receipt-line" v-for="l in refill.lines" :key="l.lane_id">
        <span>{{ l.slot_no }} {{ l.sku_name }}</span>
        <span>x{{ l.fill_qty }}</span>
      </div>
      <p class="muted" style="margin:0.75rem 0 0;font-size:0.72rem;color:#6a5e48;text-align:center">
        — 机面打印预览 —
      </p>
    </aside>
  </div>
</template>
