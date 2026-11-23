<script setup lang="ts">
/**
 * 大模型提供商设置对话框。
 *
 * 【为什么需要这个功能】
 *   最初大模型只能通过 .env 配置（AI_PROVIDER / DEEPSEEK_API_KEY）。
 *   在开发机上这没问题，但项目打包成桌面版发给别人之后完全不成立：
 *
 *       · 使用者拿不到你的 .env
 *       · 也不会去改环境变量、更不知道改完要重启
 *       · 把 Key 交给别人 = 把自己的额度让出去
 *
 *   所以要给一个界面：自己选服务商、填自己的 Key、点一下测通、立即生效。
 *
 * 【设计要点】
 *   1. 支持 4 类：DeepSeek / 通义千问 / 本地 Ollama / OpenAI 兼容（自定义）
 *      —— "OpenAI 兼容"这一类覆盖面最广：硅基流动、月之暗面、
 *         One-API 中转、vLLM、LM Studio 都能填进来。
 *   2. Key 只显示打码值（sk-8****cdef）。保存时如果不填，后端保持原值不变
 *      —— 这样"只改模型名"不会把 Key 冲掉。
 *   3. 提供"测试连接"，发一次极小的真实请求。
 *      常见失败原因里「模型名填错」「余额不足」只有真实调用才能发现，
 *      单纯 ping 一个地址是查不出来的。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { aiApi } from '@/api'

import type {
  ModelProviderItem,
  ProviderPayload,
  ProviderPreset,
  ProviderTestResult,
} from '@/types'

// ---------------------------------------------------------------------------
// 对外接口
// ---------------------------------------------------------------------------
const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** 配置发生任何变更后触发，父组件据此刷新 RAG 状态 */
  (e: 'changed'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const providers = ref<ModelProviderItem[]>([])
const presets = ref<ProviderPreset[]>([])

/** 正在编辑的配置 id；null 表示"新增" */
const editingId = ref<number | null>(null)

/** 最近一次测试结果（展示在表单下方） */
const testResult = ref<ProviderTestResult | null>(null)

/** 表单数据 */
const form = ref({
  provider_type: 'deepseek',
  name: '',
  base_url: '',
  model: '',
  api_key: '',
})

const isEditing = computed(() => editingId.value !== null)

/** 当前服务商类型的预设 */
const currentPreset = computed<ProviderPreset | undefined>(() =>
  presets.value.find((item) => item.provider_type === form.value.provider_type),
)

/** 该类型是否必须填 Key */
const needsKey = computed(() => currentPreset.value?.needs_key ?? true)

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
async function loadAll() {
  loading.value = true
  try {
    const [presetData, listData] = await Promise.all([
      aiApi.providerPresets(),
      aiApi.providers(),
    ])
    presets.value = presetData.presets ?? []
    providers.value = listData.items ?? []

    // 没有配置时，用第二个预设（默认 deepseek）预填表单
    if (!providers.value.length && !isEditing.value) {
      applyPreset(presetData.default_type || 'deepseek')
    }
  } catch (err) {
    ElMessage.error((err as Error)?.message || '加载模型配置失败')
  } finally {
    loading.value = false
  }
}

/** 按类型回填默认地址与模型 */
function applyPreset(type: string) {
  const preset = presets.value.find((item) => item.provider_type === type)
  form.value.provider_type = type
  if (preset) {
    form.value.base_url = preset.base_url
    form.value.model = preset.model
    if (!form.value.name) {
      form.value.name = preset.label
    }
  }
}

/** 切换服务商类型（只有在新增时才自动回填，避免覆盖用户已填内容） */
function onTypeChange(type: string) {
  if (isEditing.value) {
    form.value.provider_type = type
    return
  }
  applyPreset(type)
}

// ---------------------------------------------------------------------------
// 表单操作
// ---------------------------------------------------------------------------
function resetForm() {
  editingId.value = null
  testResult.value = null
  form.value = {
    provider_type: 'deepseek',
    name: '',
    base_url: '',
    model: '',
    api_key: '',
  }
  applyPreset('deepseek')
}

function startCreate() {
  resetForm()
}

function startEdit(item: ModelProviderItem) {
  editingId.value = item.id
  testResult.value = null
  form.value = {
    provider_type: item.provider_type,
    name: item.name,
    base_url: item.base_url,
    model: item.model,
    // 回显打码值，作为"已保存过 Key"的提示；提交时后端会识别并忽略它
    api_key: item.api_key_masked,
  }
}

async function save() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请填写配置名称')
    return
  }

  const payload: ProviderPayload = {
    name: form.value.name.trim(),
    provider_type: form.value.provider_type,
    base_url: form.value.base_url.trim(),
    model: form.value.model.trim(),
  }

  // 只有用户真的改了 Key（不含打码标记）才提交
  const rawKey = form.value.api_key.trim()
  if (rawKey && !rawKey.includes('****')) {
    payload.api_key = rawKey
  } else if (!isEditing.value) {
    payload.api_key = ''
  }

  saving.value = true
  try {
    if (isEditing.value && editingId.value !== null) {
      await aiApi.updateProvider(editingId.value, payload)
      ElMessage.success('已更新')
    } else {
      await aiApi.createProvider(payload)
      ElMessage.success('已保存')
    }
    await loadAll()
    emit('changed')
    resetForm()
  } catch (err) {
    ElMessage.error((err as Error)?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function activate(item: ModelProviderItem) {
  try {
    await aiApi.activateProvider(item.id)
    ElMessage.success(`已切换到「${item.name}」`)
    await loadAll()
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error)?.message || '切换失败')
  }
}

async function remove(item: ModelProviderItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除配置「${item.name}」吗？删除后无法恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    await aiApi.deleteProvider(item.id)
    ElMessage.success('已删除')
    await loadAll()
    emit('changed')
    if (editingId.value === item.id) resetForm()
  } catch (err) {
    ElMessage.error((err as Error)?.message || '删除失败')
  }
}

async function test(item: ModelProviderItem) {
  testingId.value = item.id
  testResult.value = null
  try {
    const result = await aiApi.testProvider(item.id)
    testResult.value = result
    if (result.ok) {
      ElMessage.success('连接成功')
    } else {
      ElMessage.warning('连接失败，请查看下方说明')
    }
    await loadAll()
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error)?.message || '测试失败')
  } finally {
    testingId.value = null
  }
}

// ---------------------------------------------------------------------------
// 打开时加载
// ---------------------------------------------------------------------------
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      loadAll().then(() => {
        if (!providers.value.length) resetForm()
      })
    }
  },
)

/** 类型标签的颜色 */
function typeTagType(type: string): 'success' | 'warning' | 'info' | 'primary' {
  if (type === 'deepseek') return 'primary'
  if (type === 'dashscope') return 'success'
  if (type === 'ollama') return 'info'
  return 'warning'
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="模型提供商"
    width="820px"
    :close-on-click-modal="false"
    append-to-body
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
      <template #title>在这里填入你自己的大模型 API。Key 会被加密保存在本机，不会上传。</template>
      没有配置也能使用 AI 助手，但回答只会罗列检索到的数据；接入大模型后才会
      生成自然语言分析与建议。
    </el-alert>

    <!-- ==================== 已有配置 ==================== -->
    <div v-loading="loading">
      <div class="section-title">已保存的配置</div>

      <el-empty
        v-if="!providers.length"
        description="还没有配置，请在下方添加一个"
        :image-size="60"
      />

      <el-table v-else :data="providers" size="small" stripe>
        <el-table-column label="名称" min-width="150">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.name }}</span>
              <el-tag v-if="row.is_active" size="small" type="success" effect="dark">
                使用中
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="typeTagType(row.provider_type)">
              {{ row.provider_label }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="模型" min-width="140">
          <template #default="{ row }">
            <code class="mono">{{ row.effective_model }}</code>
          </template>
        </el-table-column>

        <el-table-column label="Key" width="130">
          <template #default="{ row }">
            <code class="mono">{{ row.api_key_masked || '—' }}</code>
          </template>
        </el-table-column>

        <el-table-column label="上次测试" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.last_test_ok === true"
              size="small"
              type="success"
              effect="plain"
            >
              成功
            </el-tag>
            <el-tag
              v-else-if="row.last_test_ok === false"
              size="small"
              type="danger"
              effect="plain"
            >
              失败
            </el-tag>
            <span v-else class="text-muted">未测试</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="230">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_active"
              link
              type="primary"
              size="small"
              @click="activate(row)"
            >
              启用
            </el-button>
            <el-button link size="small" @click="startEdit(row)">编辑</el-button>
            <el-button
              link
              size="small"
              :loading="testingId === row.id"
              @click="test(row)"
            >
              测试连接
            </el-button>
            <el-button link type="danger" size="small" @click="remove(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 测试结果 -->
      <el-alert
        v-if="testResult"
        :type="testResult.ok ? 'success' : 'error'"
        :closable="false"
        show-icon
        style="margin-top: 10px"
      >
        <template #title>
          {{ testResult.ok ? '连接成功' : '连接失败' }}
          <span class="text-muted">（{{ testResult.latency_ms }} ms）</span>
        </template>
        <div class="test-msg">{{ testResult.message }}</div>
      </el-alert>
    </div>

    <el-divider />

    <!-- ==================== 新增 / 编辑 ==================== -->
    <div class="section-title">
      {{ isEditing ? '编辑配置' : '添加新配置' }}
      <el-button
        v-if="isEditing"
        link
        type="primary"
        size="small"
        style="margin-left: 8px"
        @click="startCreate"
      >
        改为新增
      </el-button>
    </div>

    <el-form label-width="96px" label-position="right" size="default">
      <el-form-item label="服务商">
        <el-select
          :model-value="form.provider_type"
          style="width: 100%"
          @change="onTypeChange"
        >
          <el-option
            v-for="p in presets"
            :key="p.provider_type"
            :label="p.label"
            :value="p.provider_type"
          />
        </el-select>
        <div v-if="currentPreset?.hint" class="hint">{{ currentPreset.hint }}</div>
      </el-form-item>

      <el-form-item label="配置名称">
        <el-input v-model="form.name" placeholder="给这套配置起个名字，例如「我的 DeepSeek」" />
      </el-form-item>

      <el-form-item label="接口地址">
        <el-input
          v-model="form.base_url"
          :placeholder="
            form.provider_type === 'dashscope'
              ? '通义千问走官方 SDK，无需填写'
              : '例如 https://api.deepseek.com'
          "
        />
      </el-form-item>

      <el-form-item label="模型名称">
        <el-input v-model="form.model" placeholder="例如 deepseek-flash / qwen-plus" />
      </el-form-item>

      <el-form-item label="API Key">
        <el-input
          v-model="form.api_key"
          type="password"
          show-password
          :placeholder="
            isEditing
              ? '留空表示不修改已保存的 Key'
              : needsKey
                ? '粘贴你的 API Key'
                : '本地 Ollama 通常不需要'
          "
        />
        <div class="hint">
          <template v-if="!needsKey">
            该服务商通常不需要 Key，留空即可。
          </template>
          <template v-else-if="isEditing">
            Key 已加密保存；如需更换请直接粘贴新 Key，留空则保持不变。
          </template>
          <template v-else>
            Key 会加密后保存在本机数据库，接口不会返回明文。
          </template>
          <a
            v-if="currentPreset?.key_url && !isEditing"
            :href="currentPreset.key_url"
            target="_blank"
            rel="noopener"
            class="key-link"
          >
            去申请 Key →
          </a>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="footer-bar">
        <span class="text-muted footer-tip">
          保存后点「测试连接」可验证是否可用
        </span>
        <div>
          <el-button @click="visible = false">关闭</el-button>
          <el-button type="primary" :loading="saving" @click="save">
            {{ isEditing ? '保存修改' : '保存配置' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mono {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #606266;
}

.hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.7;
  margin-top: 4px;
}

.key-link {
  margin-left: 6px;
  color: #409eff;
  text-decoration: none;
}

.key-link:hover {
  text-decoration: underline;
}

.test-msg {
  font-size: 12px;
  line-height: 1.7;
  word-break: break-all;
}

.footer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-tip {
  font-size: 12px;
}
</style>
