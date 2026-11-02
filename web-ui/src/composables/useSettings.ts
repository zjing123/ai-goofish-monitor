import { ref, onMounted } from 'vue'
import * as settingsApi from '@/api/settings'
import type {
  NotificationSettings,
  NotificationSettingsUpdate,
  NotificationTestResponse,
  AiSettings,
  RotationSettings,
  SaleCheckSettings,
  SaleCheckSettingsUpdate,
  SystemStatus
} from '@/api/settings'

export function useSettings() {
  const notificationSettings = ref<NotificationSettings>({})
  const aiSettings = ref<AiSettings>({})
  const rotationSettings = ref<RotationSettings>({})
  const saleCheckSettings = ref<SaleCheckSettings>({
    SALE_CHECK_ENABLED: true,
    SALE_CHECK_CRON: '20 */2 * * *',
    SALE_CHECK_BATCH_SIZE: 40,
    SALE_CHECK_LOOKBACK_DAYS: 7,
    SALE_CHECK_RECHECK_HOURS: 12,
    next_run_time: null,
    is_running: false,
  })
  const systemStatus = ref<SystemStatus | null>(null)
  const isReady = ref(false)
  
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<Error | null>(null)

  async function fetchAll() {
    isLoading.value = true
    error.value = null
    try {
      const [notif, ai, rotation, saleCheck, status] = await Promise.all([
        settingsApi.getNotificationSettings(),
        settingsApi.getAiSettings(),
        settingsApi.getRotationSettings(),
        settingsApi.getSaleCheckSettings(),
        settingsApi.getSystemStatus()
      ])
      notificationSettings.value = notif
      aiSettings.value = ai
      rotationSettings.value = rotation
      saleCheckSettings.value = saleCheck
      systemStatus.value = status
    } catch (e) {
      if (e instanceof Error) error.value = e
    } finally {
      isLoading.value = false
      isReady.value = true
    }
  }

  async function refreshStatus() {
    isLoading.value = true
    error.value = null
    try {
      systemStatus.value = await settingsApi.getSystemStatus()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function saveNotificationSettings(payload: NotificationSettingsUpdate) {
    isSaving.value = true
    try {
      await settingsApi.updateNotificationSettings(payload)
      const [notif, status] = await Promise.all([
        settingsApi.getNotificationSettings(),
        settingsApi.getSystemStatus()
      ])
      notificationSettings.value = notif
      systemStatus.value = status
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function testNotification(payload: {
    channel?: string
    settings: NotificationSettingsUpdate
  }): Promise<NotificationTestResponse> {
    isSaving.value = true
    try {
      return await settingsApi.testNotificationSettings(payload)
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function saveAiSettings() {
    isSaving.value = true
    try {
      const payload = { ...aiSettings.value }
      const apiKey = (payload.OPENAI_API_KEY || '').trim()
      if (apiKey) {
        payload.OPENAI_API_KEY = apiKey
      } else {
        delete payload.OPENAI_API_KEY
      }
      await settingsApi.updateAiSettings(payload)
      if (aiSettings.value.OPENAI_API_KEY) {
        aiSettings.value.OPENAI_API_KEY = ''
      }
      // Refresh status
      systemStatus.value = await settingsApi.getSystemStatus()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function saveRotationSettings() {
    isSaving.value = true
    try {
      await settingsApi.updateRotationSettings(rotationSettings.value)
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function saveSaleCheckSettings() {
    isSaving.value = true
    try {
      const payload: SaleCheckSettingsUpdate = {
        SALE_CHECK_ENABLED: saleCheckSettings.value.SALE_CHECK_ENABLED,
        SALE_CHECK_CRON: saleCheckSettings.value.SALE_CHECK_CRON,
        SALE_CHECK_BATCH_SIZE: saleCheckSettings.value.SALE_CHECK_BATCH_SIZE,
        SALE_CHECK_LOOKBACK_DAYS: saleCheckSettings.value.SALE_CHECK_LOOKBACK_DAYS,
        SALE_CHECK_RECHECK_HOURS: saleCheckSettings.value.SALE_CHECK_RECHECK_HOURS,
      }
      const updated = await settingsApi.updateSaleCheckSettings(payload)
      saleCheckSettings.value = { ...saleCheckSettings.value, ...updated }
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  async function refreshSaleCheckSettings() {
    try {
      saleCheckSettings.value = await settingsApi.getSaleCheckSettings()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    }
  }

  async function testAiConnection() {
    isSaving.value = true
    try {
      const payload = { ...aiSettings.value }
      const apiKey = (payload.OPENAI_API_KEY || '').trim()
      if (apiKey) {
        payload.OPENAI_API_KEY = apiKey
      } else {
        delete payload.OPENAI_API_KEY
      }
      const res = await settingsApi.testAiSettings(payload)
      return res
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSaving.value = false
    }
  }

  onMounted(fetchAll)

  return {
    notificationSettings,
    aiSettings,
    rotationSettings,
    saleCheckSettings,
    systemStatus,
    isLoading,
    isSaving,
    isReady,
    error,
    fetchAll,
    saveNotificationSettings,
    testNotification,
    saveAiSettings,
    saveRotationSettings,
    saveSaleCheckSettings,
    refreshSaleCheckSettings,
    testAiConnection,
    refreshStatus,
  }
}
