<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue';
import type { DataTableColumns } from 'naive-ui';
import { NButton, NTag } from 'naive-ui';
import {
  fetchCreateRechargeOrder,
  fetchMockPayRechargeOrder,
  fetchRechargeOrders,
  fetchRechargePackages
} from '@/service/api';

const TOKEN_UNIT = 10000;
const authStore = useAuthStore();
const loading = ref(false);
const orderLoading = ref(false);
const paying = ref(false);
const packages = ref<Api.Recharge.Package[]>([]);
const orders = ref<Api.Recharge.Order[]>([]);
const selectedPackageId = ref<number | null>(null);
const activeTab = ref('all');
const currentTradeNo = ref('');

function formatMoney(value: number) {
  return `¥${(value / 100).toFixed(2)}`;
}

function formatTokenWan(value: number) {
  const wan = value / TOKEN_UNIT;
  return `${wan.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万`;
}

async function getPackages() {
  loading.value = true;
  try {
    const { error, data } = await fetchRechargePackages();
    if (!error && data) {
      packages.value = data;
      selectedPackageId.value ||= data[0]?.id ?? null;
    }
  } finally {
    loading.value = false;
  }
}

async function getOrders() {
  orderLoading.value = true;
  try {
    const status = activeTab.value === 'all' ? undefined : activeTab.value;
    const { error, data } = await fetchRechargeOrders(status);
    if (!error && data) {
      orders.value = data;
    }
  } finally {
    orderLoading.value = false;
  }
}

async function createOrder(packageId: number) {
  paying.value = true;
  try {
    const { error, data } = await fetchCreateRechargeOrder(packageId);
    if (!error && data) {
      currentTradeNo.value = data.outTradeNo;
      window.$message?.success('订单已创建，请确认模拟支付');
    }
  } finally {
    paying.value = false;
  }
}

async function mockPay(tradeNo?: string) {
  const targetTradeNo = tradeNo || currentTradeNo.value;
  if (!targetTradeNo) {
    window.$message?.warning('请先创建订单');
    return;
  }
  paying.value = true;
  try {
    const { error } = await fetchMockPayRechargeOrder(targetTradeNo);
    if (!error) {
      window.$message?.success('模拟支付成功，Token 已到账');
      currentTradeNo.value = '';
      await authStore.initUserInfo();
      await getOrders();
    }
  } finally {
    paying.value = false;
  }
}

const orderColumns = computed<DataTableColumns<Api.Recharge.Order>>(() => [
  {
    title: '订单号',
    key: 'tradeNo',
    minWidth: 180,
    ellipsis: { tooltip: true }
  },
  {
    title: '说明',
    key: 'description',
    minWidth: 160,
    ellipsis: { tooltip: true }
  },
  {
    title: '金额',
    key: 'amount',
    width: 110,
    render: row => formatMoney(row.amount)
  },
  {
    title: 'LLM Token',
    key: 'llmToken',
    width: 130,
    render: row => formatTokenWan(row.llmToken)
  },
  {
    title: 'Embedding Token',
    key: 'embeddingToken',
    width: 150,
    render: row => formatTokenWan(row.embeddingToken)
  },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: row => {
      const map: Record<string, { text: string; type: 'default' | 'success' | 'warning' | 'error' }> = {
        NOT_PAY: { text: '未支付', type: 'warning' },
        PAYING: { text: '支付中', type: 'warning' },
        SUCCEED: { text: '支付成功', type: 'success' },
        FAIL: { text: '支付失败', type: 'error' },
        CANCELLED: { text: '已取消', type: 'default' }
      };
      const item = map[row.status] || { text: row.status, type: 'default' };
      return h(NTag, { type: item.type }, () => item.text);
    }
  },
  {
    title: '创建时间',
    key: 'createdAt',
    width: 180,
    render: row => new Date(row.createdAt).toLocaleString('zh-CN')
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    render: row =>
      row.status === 'NOT_PAY' || row.status === 'PAYING'
        ? h(
            NButton,
            {
              size: 'small',
              type: 'primary',
              loading: paying.value,
              onClick: () => mockPay(row.tradeNo)
            },
            () => '模拟支付'
          )
        : '-'
  }
]);

onMounted(async () => {
  await Promise.all([getPackages(), getOrders()]);
});
</script>

<template>
  <div class="min-h-500px overflow-auto p-4">
    <div class="mx-auto max-w-1200px flex flex-col gap-4">
      <NCard title="余额充值" :bordered="false" size="small">
        <template #header-extra>
          <NTag type="info">模拟支付</NTag>
        </template>

        <NSpin :show="loading">
          <div v-if="packages.length" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <NCard
              v-for="pkg in packages"
              :key="pkg.id"
              hoverable
              size="small"
              class="cursor-pointer"
              :class="{ 'ring-2 ring-[rgb(var(--primary-color))]': selectedPackageId === pkg.id }"
              @click="selectedPackageId = pkg.id"
            >
              <div class="flex min-h-230px flex-col">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="text-18px font-700">{{ pkg.packageName }}</div>
                    <div class="mt-1 text-13px text-stone-500">{{ pkg.packageDesc || 'Token 充值套餐' }}</div>
                  </div>
                  <NTag v-if="pkg.enabled" type="success" size="small">可用</NTag>
                </div>

                <div class="mt-5 text-28px font-800 text-[rgb(var(--primary-color))]">
                  {{ formatMoney(pkg.packagePrice) }}
                </div>

                <div class="mt-4 flex flex-col gap-2 text-13px">
                  <div>LLM Token：{{ formatTokenWan(pkg.llmToken) }}</div>
                  <div>Embedding Token：{{ formatTokenWan(pkg.embeddingToken) }}</div>
                </div>

                <div class="mt-auto pt-5">
                  <NButton type="primary" block :loading="paying" @click.stop="createOrder(pkg.id)">
                    创建订单
                  </NButton>
                </div>
              </div>
            </NCard>
          </div>
          <NEmpty v-else description="暂无充值套餐" />
        </NSpin>

        <NAlert v-if="currentTradeNo" type="info" class="mt-4" :show-icon="false">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <span>当前待支付订单：{{ currentTradeNo }}</span>
            <NButton size="small" type="primary" :loading="paying" @click="mockPay()">确认模拟支付</NButton>
          </div>
        </NAlert>
      </NCard>

      <NCard title="充值记录" :bordered="false" size="small">
        <NTabs v-model:value="activeTab" type="segment" size="small" @update:value="getOrders">
          <NTabPane name="all" tab="全部" />
          <NTabPane name="NOT_PAY" tab="未支付" />
          <NTabPane name="SUCCEED" tab="支付成功" />
          <NTabPane name="FAIL" tab="支付失败" />
        </NTabs>
        <NDataTable
          class="mt-3"
          :columns="orderColumns"
          :data="orders"
          :loading="orderLoading"
          :scroll-x="1050"
          size="small"
        />
      </NCard>
    </div>
  </div>
</template>
