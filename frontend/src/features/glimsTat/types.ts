export interface GlimsTatFilters {
  dateFrom: string
  dateTo: string
  dispensaryQuery: string
  minOpenHours: number
  thresholdHours: number
}

export interface GlimsTatStats {
  totalSamples: number
  averageOpenHours: number | null
  percentile95OpenHours: number | null
  thresholdHours: number | null
}

export interface GlimsTatSample {
  sampleId: string
  dispensaryName: string | null
  dateReceived: Date | null
  reportDate: Date | null
  testsCount: number
  openTimeHours: number
  openTimeLabel: string
  isOutlier: boolean
}

export interface GlimsTatData {
  stats: GlimsTatStats
  samples: GlimsTatSample[]
}
