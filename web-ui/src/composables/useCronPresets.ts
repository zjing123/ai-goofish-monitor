import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

/** Sentinel value meaning "no schedule" (manual runs only). */
export const EMPTY_CRON_VALUE = '__manual__'

/**
 * Shared cron preset list used by the task form and the sale-check
 * settings panel. Labels live under `tasks.form.cron.*`.
 */
export function useCronPresets() {
  const { t } = useI18n()
  return computed(() => [
    { value: EMPTY_CRON_VALUE, label: t('tasks.form.cron.manual') },
    { value: '*/5 * * * *', label: t('tasks.form.cron.every5Minutes') },
    { value: '*/10 * * * *', label: t('tasks.form.cron.every10Minutes') },
    { value: '*/15 * * * *', label: t('tasks.form.cron.every15Minutes') },
    { value: '*/20 * * * *', label: t('tasks.form.cron.every20Minutes') },
    { value: '*/30 * * * *', label: t('tasks.form.cron.every30Minutes') },
    { value: '0 * * * *', label: t('tasks.form.cron.hourly') },
    { value: '0 */2 * * *', label: t('tasks.form.cron.every2Hours') },
    { value: '0 */4 * * *', label: t('tasks.form.cron.every4Hours') },
    { value: '0 */6 * * *', label: t('tasks.form.cron.every6Hours') },
    { value: '0 */12 * * *', label: t('tasks.form.cron.every12Hours') },
    { value: '0 2 * * *', label: t('tasks.form.cron.daily2') },
    { value: '0 8 * * *', label: t('tasks.form.cron.daily8') },
    { value: '0 12 * * *', label: t('tasks.form.cron.daily12') },
    { value: '0 18 * * *', label: t('tasks.form.cron.daily18') },
    { value: '0 20 * * *', label: t('tasks.form.cron.daily20') },
    { value: '0 8,12,18 * * *', label: t('tasks.form.cron.daily81218') },
    { value: '0 9 * * 1-5', label: t('tasks.form.cron.weekday9') },
    { value: '0 10 * * 6,0', label: t('tasks.form.cron.weekend10') },
  ])
}
