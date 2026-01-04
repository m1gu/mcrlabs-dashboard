import type { OverviewData, OverviewFilters } from '../overview/types'

export type GlimsOverviewFilters = OverviewFilters

export interface GlimsSummaryResponse {
  samples: number
  tests: number
  customers: number
  reports: number
  avg_tat_hours: number | null
  last_updated_at: string | null
}

export interface GlimsActivityResponse {
  points: Array<{
    date: string
    samples: number
    tests: number
    samples_reported: number
    samples_breakdown?: Record<string, number>
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
  }>
}

export interface GlimsTatDailyResponse {
  points: Array<{
    date: string
    average_hours: number | null
    within_tat: number
    beyond_tat: number
    moving_average_hours?: number | null
  }>
}

export type GlimsOverviewData = OverviewData
