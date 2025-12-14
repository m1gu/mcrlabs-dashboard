/**
 * GLIMS Spreadsheet monitor: sends status changes and dispensary suggestions to the backend.
 *
 * Configure Script Properties:
 * - API_BASE_URL: e.g., https://api.tu-dominio.com
 * - API_TOKEN: bearer/API key
 * - SPREADSHEET_ID: target Sheet ID
 * - OVERVIEW_TAB: e.g., Overview
 * - DISPENSARIES_TAB: e.g., Dispensaries
 * - STATUS_HEADER: e.g., Status
 * - SAMPLE_ID_HEADER: e.g., SampleID
 * - DISPENSARY_HEADER: e.g., Dispensary
 */

function getConfig() {
  const props = PropertiesService.getScriptProperties();
  const required = [
    'API_BASE_URL',
    'API_TOKEN',
    'SPREADSHEET_ID',
    'OVERVIEW_TAB',
    'DISPENSARIES_TAB',
    'STATUS_HEADER',
    'SAMPLE_ID_HEADER',
    'DISPENSARY_HEADER',
  ];
  const cfg = {};
  required.forEach((key) => {
    const val = props.getProperty(key);
    if (!val) {
      throw new Error('Missing script property: ' + key);
    }
    cfg[key] = val;
  });
  return {
    apiBaseUrl: cfg.API_BASE_URL.replace(/\/+$/, ''),
    apiToken: cfg.API_TOKEN,
    spreadsheetId: cfg.SPREADSHEET_ID,
    overviewTab: cfg.OVERVIEW_TAB,
    dispensariesTab: cfg.DISPENSARIES_TAB,
    statusHeader: cfg.STATUS_HEADER,
    sampleIdHeader: cfg.SAMPLE_ID_HEADER,
    dispensaryHeader: cfg.DISPENSARY_HEADER,
  };
}

function onEdit(e) {
  try {
    const cfg = getConfig();
    const range = e.range;
    const sheet = range.getSheet();
    const ss = sheet.getParent();
    if (ss.getId() !== cfg.spreadsheetId) {
      return; // different sheet
    }
    const sheetName = sheet.getName();
    if (sheetName === cfg.overviewTab) {
      handleOverviewEdit(e, cfg);
    } else if (sheetName === cfg.dispensariesTab) {
      handleDispensaryEdit(e, cfg);
    }
  } catch (err) {
    console.error('onEdit error', err);
  }
}

function handleOverviewEdit(e, cfg) {
  const sheet = e.range.getSheet();
  const row = e.range.getRow();
  if (row <= 1) return; // header or invalid

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const statusCol = headers.indexOf(cfg.statusHeader) + 1;
  const sampleCol = headers.indexOf(cfg.sampleIdHeader) + 1;
  if (statusCol <= 0 || sampleCol <= 0) return;
  if (e.range.getColumn() !== statusCol) return; // ignore other columns

  const status = (e.value || '').toString().trim();
  const sampleId = sheet.getRange(row, sampleCol).getValue();
  if (!status || !sampleId) return;

  const payload = {
    sample_id: sampleId.toString().trim(),
    status: status,
    changed_at: new Date().toISOString(),
    metadata: {
      row: row,
      user: Session.getActiveUser().getEmail() || null,
    },
  };
  try {
    postJson(cfg.apiBaseUrl + '/api/v2/glims/status-events', payload, cfg.apiToken);
  } catch (err) {
    console.error('Failed to post status event', err);
  }
}

function handleDispensaryEdit(e, cfg) {
  const sheet = e.range.getSheet();
  const row = e.range.getRow();
  if (row <= 1) return;

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const dispCol = headers.indexOf(cfg.dispensaryHeader) + 1;
  if (dispCol <= 0) return;
  if (e.range.getColumn() !== dispCol) return;

  const name = (e.value || '').toString().trim();
  if (!name) return;

  const payload = {
    name: name,
    sheet_line_number: row,
  };
  try {
    postJson(cfg.apiBaseUrl + '/api/v2/glims/dispensaries/suggest', payload, cfg.apiToken);
  } catch (err) {
    console.error('Failed to suggest dispensary', err);
  }
}

function postJson(url, body, token) {
  const headers = {
    Authorization: 'Bearer ' + token,
    'Content-Type': 'application/json',
  };
  const resp = UrlFetchApp.fetch(url, {
    method: 'post',
    muteHttpExceptions: true,
    headers: headers,
    payload: JSON.stringify(body),
  });
  const code = resp.getResponseCode();
  if (code >= 400) {
    throw new Error('Request failed: ' + code + ' body=' + resp.getContentText());
  }
  return JSON.parse(resp.getContentText() || '{}');
}
