import type { OverviewFilters } from '../overview/types'

export type GlimsTestsFilters = OverviewFilters

export interface GlimsTestsSummaryResponse {
    total_tests: number
    avg_prep_to_start_hours: number | null
    tests_by_type?: Record<string, number>
    avg_by_type?: Record<string, number>
}

export interface GlimsTestsActivityPoint {
    date: string
    prep_breakdown: Record<string, number>
    start_breakdown: Record<string, number>
    total_prep: number
    total_start: number
}

export interface GlimsTestsActivityResponse {
    points: GlimsTestsActivityPoint[]
}

export interface GlimsTestsTrendPoint {
    date: string
    avg_hours: number | null
    moving_avg_hours: number | null
}

export interface GlimsTestsTrendResponse {
    points: GlimsTestsTrendPoint[]
}

export interface GlimsTestsData {
    summary: {
        totalTests: number
        avgPrepToStartHours: number | null
        testsByType: Record<string, number>
        avgByType: Record<string, number>
    }
    activity: Array<{
        date: Date
        label: string
        prepBreakdown: Record<string, number>
        startBreakdown: Record<string, number>
        totalPrep: number
        totalStart: number
    }>
    trend: Array<{
        date: Date
        label: string
        avgHours: number | null
        movingAvgHours: number | null
    }>
}
