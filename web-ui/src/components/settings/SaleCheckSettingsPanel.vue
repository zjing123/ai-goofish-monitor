<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toast'
import { formatDateTime } from '@/i18n'
import type { SaleCheckSettings } from '@/api/settings'
import { getSaleCheckLog } from '@/api/settings'
import { triggerSaleCheck } from '@/api/results'
import { EMPTY_CRON_VALUE, useCronPresets } from '@/composables/useCronPresets'

const props = defineProps<{
  settings: SaleCheckSettings
  isReady: boolean
  isSaving: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'refresh'): void
}>()

const { t } = useI18n()

// Reuse the task form's preset/custom cron pattern and preset options.
const cronMode = ref<'preset' | 'custom'>('preset')

const allCronPresets = useCronPresets()
const SALE_CHECK_BASE_TWO_HOUR_CRON = '0 */2 * * *'
// Keep the check off the top of the hour so it does not race with task runs.
const SALE_CHECK_OFFSET_CRON = '20 */2 * * *'
// The sale check job has its own enable switch, so drop the manual option.
const cronPresets = computed(() =>
  allCronPresets.value
    .filter((preset) => preset.value !== EMPTY_CRON_VALUE)
    .map((preset) =>
      preset.value === SALE_CHECK_BASE_TWO_HOUR_CRON
        ? { value: SALE_CHECK_OFFSET_CRON, label: t('settings.saleCheck.cronEvery2hOffset') }
        : preset
    )
)

const isPresetCron = computed(() =>
  cronPresets.value.some((preset) => preset.value === props.settings.SALE_CHECK_CRON)
)

// Pick the matching tab once settings are loaded; do not flip tabs while the
// user is typing a custom expression.
watch(
  () => props.isReady,
  (ready) => {
    if (ready) {
      cronMode.value = isPresetCron.value ? 'preset' : 'custom'
    }
  },
  { immediate: true }
)

const DEFAULT_CRON = SALE_CHECK_OFFSET_CRON

const presetCronValue = computed({
  get: () => {
    if (isPresetCron.value) return props.settings.SALE_CHECK_CRON
    return cronPresets.value.find((preset) => preset.value === DEFAULT_CRON)?.value ?? DEFAULT_CRON
  },
  set: (value: string) => {
    props.settings.SALE_CHECK_CRON = value
  },
})

const logLines = ref<string[]>([])
const logUpdatedAt = ref<string | null>(null)
const isLogLoading = ref(false)
const isTriggering = ref(false)
let logTimer: number | undefined

async function loadLog(silent = false) {
  if (!silent) isLogLoading.value = true
  try {
    const data = await getSaleCheckLog(200)
    logLines.value = data.lines
    logUpdatedAt.value = data.updated_at
  } catch (e) {
    if (!silent) {
      toast({
        title: t('settings.saleCheck.logFailed'),
        description: (e as Error).message,
        variant: 'destructive',
      })
    }
  } finally {
    if (!silent) isLogLoading.value = false
  }
}

async function runNow() {
  isTriggering.value = true
  try {
    await triggerSaleCheck()
    toast({
      title: t('settings.saleCheck.runStarted'),
      description: t('settings.saleCheck.runHint'),
    })
    emit('refresh')
    window.setTimeout(() => loadLog(true), 3000)
  } catch (e) {
    toast({
      title: t('settings.saleCheck.runFailed'),
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    isTriggering.value = false
  }
}

function formatNextRun(value?: string | null) {
  if (!value) return t('settings.saleCheck.neverRun')
  return formatDateTime(value, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  loadLog(true)
  logTimer = window.setInterval(() => {
    if (props.settings.is_running) loadLog(true)
  }, 5000)
})

onBeforeUnmount(() => {
  if (logTimer) window.clearInterval(logTimer)
})
</script>

<template>
  <div class="space-y-4">
    <Card class="app-surface border-none">
      <CardHeader>
        <div class="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{{ t('settings.saleCheck.title') }}</CardTitle>
            <CardDescription>{{ t('settings.saleCheck.description') }}</CardDescription>
          </div>
          <span
            class="shrink-0 rounded-full px-3 py-1 text-xs font-semibold"
            :class="settings.is_running ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ settings.is_running ? t('settings.saleCheck.running') : t('settings.saleCheck.idle') }}
          </span>
        </div>
      </CardHeader>

      <CardContent v-if="isReady" class="grid gap-6">
        <div class="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/60 p-4">
          <div>
            <p class="font-medium text-slate-900">{{ t('settings.saleCheck.enable') }}</p>
            <p class="text-xs text-slate-500">{{ t('settings.saleCheck.enableHint') }}</p>
          </div>
          <Switch v-model:checked="settings.SALE_CHECK_ENABLED" />
        </div>

        <div class="grid gap-4 lg:grid-cols-2">
          <div class="grid gap-2">
            <Label>{{ t('settings.saleCheck.cron') }}</Label>
            <Tabs v-model="cronMode" class="w-full">
              <TabsList class="grid w-full grid-cols-2">
                <TabsTrigger value="preset">{{ t('tasks.form.cronPresetTab') }}</TabsTrigger>
                <TabsTrigger value="custom">{{ t('tasks.form.cronCustomTab') }}</TabsTrigger>
              </TabsList>
              <TabsContent value="preset">
                <Select v-model="presetCronValue">
                  <SelectTrigger class="w-full">
                    <SelectValue :placeholder="t('settings.saleCheck.cronPlaceholder')" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="preset in cronPresets" :key="preset.value" :value="preset.value">
                      {{ preset.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p class="mt-1 text-xs text-slate-500">{{ t('settings.saleCheck.cronPresetHint') }}</p>
              </TabsContent>
              <TabsContent value="custom">
                <Input v-model="settings.SALE_CHECK_CRON" placeholder="20 */2 * * *" />
                <p class="mt-1 text-xs text-slate-500">{{ t('settings.saleCheck.cronHint') }}</p>
              </TabsContent>
            </Tabs>
          </div>
          <div class="grid gap-2">
            <Label>{{ t('settings.saleCheck.nextRun') }}</Label>
            <div class="h-10 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
              {{ formatNextRun(settings.next_run_time) }}
            </div>
          </div>
        </div>

        <div class="grid gap-4 sm:grid-cols-3">
          <div class="grid gap-2">
            <Label>{{ t('settings.saleCheck.batchSize') }}</Label>
            <Input v-model.number="settings.SALE_CHECK_BATCH_SIZE" type="number" min="1" max="500" />
            <p class="text-xs text-slate-500">{{ t('settings.saleCheck.batchSizeHint') }}</p>
          </div>
          <div class="grid gap-2">
            <Label>{{ t('settings.saleCheck.lookbackDays') }}</Label>
            <Input v-model.number="settings.SALE_CHECK_LOOKBACK_DAYS" type="number" min="1" max="90" />
            <p class="text-xs text-slate-500">{{ t('settings.saleCheck.lookbackDaysHint') }}</p>
          </div>
          <div class="grid gap-2">
            <Label>{{ t('settings.saleCheck.recheckHours') }}</Label>
            <Input v-model.number="settings.SALE_CHECK_RECHECK_HOURS" type="number" min="0" max="168" step="0.5" />
            <p class="text-xs text-slate-500">{{ t('settings.saleCheck.recheckHoursHint') }}</p>
          </div>
        </div>
      </CardContent>

      <CardContent v-else class="py-8 text-sm text-gray-500">
        {{ t('settings.saleCheck.loading') }}
      </CardContent>

      <CardFooter v-if="isReady" class="flex flex-wrap justify-end gap-2">
        <Button variant="outline" @click="runNow" :disabled="isTriggering || settings.is_running">
          {{ t('settings.saleCheck.runNow') }}
        </Button>
        <Button @click="emit('save')" :disabled="isSaving">{{ t('settings.saleCheck.save') }}</Button>
      </CardFooter>
    </Card>

    <Card class="app-surface border-none">
      <CardHeader>
        <div class="flex items-center justify-between gap-3">
          <div>
            <CardTitle class="text-base">{{ t('settings.saleCheck.logTitle') }}</CardTitle>
            <CardDescription>
              {{ t('settings.saleCheck.logHint') }}
              <span v-if="logUpdatedAt"> · {{ formatDateTime(logUpdatedAt, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }}</span>
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" @click="loadLog(false)" :disabled="isLogLoading">
            {{ t('settings.saleCheck.logRefresh') }}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <pre
          v-if="logLines.length"
          class="max-h-[320px] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-relaxed text-slate-200"
        >{{ logLines.join('\n') }}</pre>
        <p v-else class="py-6 text-center text-sm text-slate-500">{{ t('settings.saleCheck.logEmpty') }}</p>
      </CardContent>
    </Card>
  </div>
</template>
