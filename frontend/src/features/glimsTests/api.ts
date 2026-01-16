import { apiFetchV2 } from '../../lib/api'
import { formatDateLabel, parseApiDate } from '../../utils/format'
import type { GlimsTestsData, GlimsTestsFilters, GlimsTestsSummaryResponse, GlimsTestsActivityResponse, GlimsTestsTrendResponse } from './types'

export async function fetchGlimsTestsData(filters: GlimsTestsFilters): Promise<GlimsTestsData> {
    const baseParams = {
        date_from: filters.dateFrom,
        date_to: filters.dateTo,
    }

    const [summary, activity, trend] = await Promise.all([
        apiFetchV2<GlimsTestsSummaryResponse>('/glims/tests/summary', baseParams),
        apiFetchV2<GlimsTestsActivityResponse>('/glims/tests/activity', baseParams),
        apiFetchV2<GlimsTestsTrendResponse>('/glims/tests/trend', {
            ...baseParams,
            moving_average_window: filters.timeframe === 'weekly' ? 14 : 7,
        }),
    ])

    return {
        summary: {
            totalTests: summary.total_tests,
            avgPrepToStartHours: summary.avg_prep_to_start_hours,
            testsByType: summary.tests_by_type || {},
            avgByType: summary.avg_by_type || {},
        },
        activity:
            activity.points?.map((point) => {
                const date = parseApiDate(point.date)!
                return {
                    date,
                    label: formatDateLabel(date),
                    prepBreakdown: point.prep_breakdown,
                    startBreakdown: point.start_breakdown,
                    totalPrep: point.total_prep,
                    totalStart: point.total_start,
                }
            }) ?? [],
        trend:
            trend.points?.map((point) => {
                const date = parseApiDate(point.date)!
                return {
                    date,
                    label: formatDateLabel(date),
                    avgHours: point.avg_hours,
                    movingAvgHours: point.moving_avg_hours,
                }
            }) ?? [],
    }
}
