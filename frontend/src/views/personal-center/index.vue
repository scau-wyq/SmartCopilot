<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue';
import type { DataTableColumns } from 'naive-ui';
import { NButton, NTag } from 'naive-ui';
import {
  fetchProfile,
  fetchSaveCustomLlm,
  fetchTestCustomLlm,
  fetchUpdateModelPreference
} from '@/service/api';

const authStore = useAuthStore();
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const profile = ref<Api.Profile.Detail | null>(null);
const tokenRecords = ref<Api.User.TokenRecord[]>([]);
const tokenRecordLoading = ref(false);
const selectedModelMode = ref<Api.Model.Mode>('FREE');

const customModel = reactive<Api.Profile.CustomModelPayload>({
  baseUrl: '',
  model: '',
  apiKey: ''
});

const pagination = reactive({
  page: 1,
  pageSize: 10,
  itemCount: 0,
  onUpdatePage: async (page: number) => {
    pagination.page = page;
    await loadTokenRecords();
  }
});

const modelModeOptions = [
  { label: '免费模型', value: 'FREE' },
  { label: '计费模型', value: 'PAID' },
  { label: '我的模型', value: 'CUSTOM' }
];

function formatToken(value: number) {
  return Number(value || 0).toLocaleString('zh-CN');
}

async function loadProfile() {
  loading.value = true;
  try {
    const { error, data } = await fetchProfile();
    if (!error && data) {
      profile.value = data;
      selectedModelMode.value = data.modelSettings.modelMode;
      customModel.baseUrl = data.modelSettings.customModel.baseUrl;
      customModel.model = data.modelSettings.customModel.model;
      customModel.apiKey = '';
    }
  } finally {
    loading.value = false;
  }
}

async function loadTokenRecords() {
  tokenRecordLoading.value = true;
  try {
    const { error, data } = await request<Api.Common.PaginatingQueryRecord<Api.User.TokenRecord>>({
      url: '/users/token-records',
      method: 'get',
      params: {
        page: pagination.page - 1,
        size: pagination.pageSize
      }
    });
    if (!error && data) {
      tokenRecords.value = data.content || [];
      pagination.itemCount = data.totalElements || 0;
    }
  } finally {
    tokenRecordLoading.value = false;
  }
}

async function saveModelPreference() {
  saving.value = true;
  try {
    const { error } = await fetchUpdateModelPreference(selectedModelMode.value);
    if (!error) {
      window.$message?.success('默认模型已保存');
      await loadProfile();
    }
  } finally {
    saving.value = false;
  }
}

async function saveCustomModel() {
  if (!customModel.baseUrl || !customModel.model) {
    window.$message?.warning('请填写 Base URL 和模型名称');
    return;
  }
  saving.value = true;
  try {
    const payload: Api.Profile.CustomModelPayload = {
      baseUrl: customModel.baseUrl,
      model: customModel.model
    };
    if (customModel.apiKey?.trim()) {
      payload.apiKey = customModel.apiKey.trim();
    }
    const { error } = await fetchSaveCustomLlm(payload);
    if (!error) {
      window.$message?.success('自定义模型已保存');
      customModel.apiKey = '';
      await loadProfile();
    }
  } finally {
    saving.value = false;
  }
}

async function testCustomModel() {
  if (!customModel.baseUrl || !customModel.model) {
    window.$message?.warning('请填写 Base URL 和模型名称');
    return;
  }
  testing.value = true;
  try {
    const { error } = await fetchTestCustomLlm({
      baseUrl: customModel.baseUrl,
      model: customModel.model,
      apiKey: customModel.apiKey || undefined
    });
    if (!error) {
      window.$message?.success('模型连通性测试成功');
    }
  } finally {
    testing.value = false;
  }
}

const tokenRecordColumns = computed<DataTableColumns<Api.User.TokenRecord>>(() => [
  {
    title: '时间',
    key: 'createdAt',
    width: 180,
    render: row => new Date(row.createdAt).toLocaleString('zh-CN')
  },
  {
    title: '类型',
    key: 'tokenType',
    width: 120,
    render: row => h(NTag, { type: row.tokenType === 'LLM' ? 'info' : 'success' }, () => row.tokenType)
  },
  {
    title: '方向',
    key: 'changeType',
    width: 110,
    render: row =>
      h(
        NTag,
        { type: row.changeType === 'INCREASE' ? 'success' : 'warning' },
        () => (row.changeType === 'INCREASE' ? '充值' : '消耗')
      )
  },
  {
    title: '数量',
    key: 'amount',
    width: 140,
    render: row => `${row.changeType === 'INCREASE' ? '+' : '-'}${formatToken(row.amount)}`
  },
  {
    title: '变动后余额',
    key: 'balanceAfter',
    width: 150,
    render: row => (row.balanceAfter === null ? '-' : formatToken(row.balanceAfter))
  },
  {
    title: '原因',
    key: 'reason',
    minWidth: 180,
    ellipsis: { tooltip: true }
  }
]);

onMounted(async () => {
  await Promise.all([loadProfile(), loadTokenRecords()]);
});
</script>

<template>
  <NSpin :show="loading">
    <div class="min-h-500px overflow-auto p-4">
      <div class="mx-auto max-w-1100px flex flex-col gap-4">
        <NCard :bordered="false" size="small">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center gap-3">
              <NAvatar round size="large">
                <icon-solar:user-circle-linear class="text-28px" />
              </NAvatar>
              <div>
                <div class="text-16px font-600">{{ profile?.username || authStore.userInfo.username }}</div>
                <div class="mt-1 flex flex-wrap gap-2">
                  <NTag type="primary" size="small">{{ profile?.role || authStore.userInfo.role }}</NTag>
                  <NTag v-for="tag in profile?.orgTags.orgTagDetails || []" :key="tag.tagId" size="small">
                    {{ tag.name }}
                  </NTag>
                </div>
              </div>
            </div>
            <NButton quaternary :loading="loading" @click="loadProfile">刷新</NButton>
          </div>
        </NCard>

        <div class="grid gap-4 md:grid-cols-2">
          <NCard title="LLM Token 余额" :bordered="false" size="small">
            <div class="text-26px font-700">{{ formatToken(profile?.balances.llmToken || 0) }}</div>
            <div class="mt-2 text-12px text-stone-500">计费模型聊天会消耗该余额</div>
          </NCard>
          <NCard title="Embedding Token 余额" :bordered="false" size="small">
            <div class="text-26px font-700">{{ formatToken(profile?.balances.embeddingToken || 0) }}</div>
            <div class="mt-2 text-12px text-stone-500">文件向量化和检索向量生成会消耗该余额</div>
          </NCard>
        </div>

        <NCard title="模型设置" :bordered="false" size="small">
          <div class="grid gap-5 lg:grid-cols-[320px_1fr]">
            <NForm label-placement="top">
              <NFormItem label="默认聊天模型">
                <NSelect v-model:value="selectedModelMode" :options="modelModeOptions" />
              </NFormItem>
              <NButton type="primary" :loading="saving" @click="saveModelPreference">保存默认模型</NButton>
            </NForm>

            <NForm label-placement="top">
              <div class="grid gap-3 md:grid-cols-2">
                <NFormItem label="Base URL">
                  <NInput v-model:value="customModel.baseUrl" placeholder="https://api.example.com/v1" />
                </NFormItem>
                <NFormItem label="Model">
                  <NInput v-model:value="customModel.model" placeholder="model-name" />
                </NFormItem>
              </div>
              <NFormItem :label="profile?.modelSettings.customModel.hasApiKey ? `API Key（已保存 ${profile.modelSettings.customModel.maskedApiKey}）` : 'API Key'">
                <NInput
                  v-model:value="customModel.apiKey"
                  type="password"
                  show-password-on="click"
                  placeholder="不修改可留空"
                />
              </NFormItem>
              <NSpace>
                <NButton :loading="testing" @click="testCustomModel">测试连接</NButton>
                <NButton type="primary" :loading="saving" @click="saveCustomModel">保存自定义模型</NButton>
              </NSpace>
            </NForm>
          </div>
        </NCard>

        <NCard title="Token 流水" :bordered="false" size="small">
          <NDataTable
            :columns="tokenRecordColumns"
            :data="tokenRecords"
            :loading="tokenRecordLoading"
            :pagination="pagination"
            :scroll-x="900"
            size="small"
          />
        </NCard>
      </div>
    </div>
  </NSpin>
</template>
