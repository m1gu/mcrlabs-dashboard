import type { OverviewData, OverviewFilters } from '../overview/types'

export type GlimsOverviewFilters = OverviewFilters

export interface GlimsSummaryResponse {
  samples: number
  tests: number
  customers: number
  reports: number
  avg_tat_hours: number | null
  samples_by_type?: Record<string, number>
  tests_by_type?: Record<string, number>
  reports_by_type?: Record<string, number>
  tat_by_type?: Record<string, number>
  last_updated_at: string | null
}

export interface GlimsActivityResponse {
  points: Array<{
    date: string
    samples: number
    tests: number
    samples_reported: number
    samples_breakdown?: Record<string, number>
    tests_breakdown?: Record<string, number>
    reported_breakdown?: Record<string, number>
  }>
}

export interface GlimsNewCustomersResponse {
  customers: Array<{
    id: number
    name: string
    created_at: string
  }>
}

export interface GlimsNewCustomersFromSheetResponse {
  customers: Array<{
    client_id: number
    client_name: string
    date_created: string
  }>
  total: number
}

export interface GlimsTopCustomersResponse {
  customers: Array<{
    id: number
    name: string
    tests: number
    tests_reported: number
  }>
}

export interface GlimsTestsByLabelResponse {
  labels: Array<{
    key: string
    count: number
    breakdown?: Record<string, number>
  }>
}

export interface GlimsTatDailyResponse {
  points: Array<{
    date: string
    average_hours: number | null
    within_tat: number
    beyond_tat: number
    within_breakdown?: Record<string, number>
    beyond_breakdown?: Record<string, number>
    hours_breakdown?: Record<string, number>
    moving_average_hours?: number | null
  }>
}

export type GlimsOverviewData = OverviewData

export interface GlimsCustomerListResponse {
  customers: Array<{
    id: number
    name: string
  }>
}
