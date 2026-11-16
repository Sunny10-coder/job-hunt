export interface CaseSummary {
  id: string;
  case_number: number;
  name: string;
  description: string;
  examiner: string;
  status: "active" | "archived";
  authorization_statement: string;
  dir_path: string;
  created_at: string;
  updated_at: string;
  counts?: Record<string, number>;
  settings?: Record<string, unknown>;
}

export interface Evidence {
  id: string;
  original_name: string;
  source_type: string;
  size_bytes: number;
  sha256: string;
  imported_at: string;
  message_count: number;
  language: string | null;
  date_order: string | null;
  date_order_confidence: number | null;
  parse_confidence: number | null;
  status: string;
  notes: string;
  extra?: Record<string, unknown>;
}

export interface ImportJob {
  id: string;
  case_id: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  stage: string;
  progress: number;
  started_at: string | null;
  finished_at: string | null;
  error?: string | null;
  log: { at: string; stage: string; message: string }[];
  errors: { severity: string; code: string; message: string; line_no: number | null }[];
  files_total?: number;
}

export interface Conversation {
  id: string;
  title: string;
  kind: "chat" | "group";
  message_count: number;
  media_count: number;
  first_at: string | null;
  last_at: string | null;
  attachments?: number;
  bookmarks?: number;
  participants?: number;
  incoming?: number;
  outgoing?: number;
  last_message?: string;
  last_sender?: string;
  last_message_type?: string;
  message_total?: number;
}

export interface Message {
  id: string;
  sender_id: string | null;
  sender_raw: string;
  sent_at_utc: string;
  sent_at_local: string;
  body: string;
  message_type: string;
  is_system: boolean;
  is_deleted: boolean;
  is_edited: boolean;
  is_forwarded: boolean;
  has_media: boolean;
  media_ref: string | null;
  source_ref: string;
  evidence_id: string;
  parse_confidence: number;
  original_timestamp: string;
  tz_offset_min: number;
  attachments: number;
  bookmarked?: boolean;
  tags?: string[];
}

export interface MessageDetail extends Omit<Message, "attachments" | "bookmarked" | "tags"> {
  conversation_id: string;
  conversation_title: string;
  kind: string;
  raw_text: string;
  char_count: number;
  word_count: number;
  session_id: string | null;
  attachments: Attachment[];
  references: { ref_type: string; ref_value: string }[];
  versions: { version: number; body: string; observed_at: string; evidence_id: string }[];
  observations: { evidence_id: string; source_ref: string; original_name: string; sha256: string }[];
  tags: string[];
  bookmark: { id: string; label: string; created_at: string } | null;
  notes: { id: string; body: string; created_at: string; author: string }[];
}

export interface Attachment {
  id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  sha256: string | null;
  missing: number;
  linked: number;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  meta?: Record<string, unknown>;
  conversation?: string | null;
  sent_at_utc?: string | null;
  sender_raw?: string | null;
}

export interface Contact {
  id: string;
  display_name: string;
  phone: string | null;
  is_self: boolean;
  first_seen: string | null;
  last_seen: string | null;
  messages: number;
  conversations: number;
  attachments: number;
  media_messages: number;
  incoming: number;
  outgoing: number;
  active_hours: number[];
}

export interface ContactProfile {
  contact: Contact;
  messages: number;
  first_at: string | null;
  last_at: string | null;
  media_messages: number;
  avg_length: number;
  conversations: number;
  hourly: { hour: string; count: number }[];
  weekday: { day: string; count: number }[];
  monthly: { bucket: string; count: number }[];
  topics: { word: string; count: number }[];
  groups: { id: string; title: string }[];
  notes: { id: string; body: string; created_at: string }[];
  tags: { tag: string; count: number }[];
  conversation_initiations: number;
  response: { median_minutes: number; samples: number } | null;
  words: { word: string; count: number }[];
  emojis: { emoji: string; count: number }[];
  interpretation_note: string;
}

export interface AnalyticsBundle {
  overview: {
    messages: number;
    real_messages: number;
    system_messages: number;
    conversations: number;
    contacts: number;
    groups: number;
    incoming: number;
    outgoing: number;
    media_messages: number;
    voice_notes: number;
    links: number;
    deleted_markers: number;
    edited_markers: number;
    active_days: number;
    avg_messages_per_active_day: number;
    avg_message_length: number;
    first_at: string | null;
    last_at: string | null;
    has_self_contact: boolean;
    formula: string;
  };
  hourly: ActivitySeries;
  daily: ActivitySeries;
  weekly: ActivitySeries;
  monthly: ActivitySeries;
  weekday: ActivitySeries;
  heatmap: { grid: number[][]; weekdays: string[]; hours: string[]; max: number; formula: string };
  response: ResponseTimes;
  words: { scanned_messages: number; words: { word: string; count: number }[]; formula: string };
  emojis: { emojis: { emoji: string; count: number }[]; total: number };
  languages: { languages: { language: string; count: number }[]; method: string };
  sessions: { sessions: { conversation_id: string; start: string; end: string; messages: number; minutes: number; participants: number }[]; total_sessions: number; gap_minutes: number };
  top_contacts: Contact[];
  conversations: Conversation[];
}

export interface ActivitySeries {
  granularity: string;
  series: { bucket: string; count: number; media: number }[];
  inactivity?: { longest_gaps: { from: string; to: string; days: number }[]; method: string };
  bursts?: { date: string; count: number; z: number }[];
  formula: string;
}

export interface ResponseTimes {
  samples: number;
  excluded_session_breaks: number;
  median_minutes: number | null;
  average_minutes: number | null;
  p90_minutes: number | null;
  histogram: { label: string; count: number }[];
  by_direction: Record<string, { samples: number; median: number }>;
  per_contact: { contact_id: string; contact: string; median_minutes: number; samples: number }[];
  methodology: Record<string, string | number>;
}

export interface Dashboard {
  overview: AnalyticsBundle["overview"];
  daily: { bucket: string; count: number; media: number }[];
  hourly: { bucket: string; count: number; media: number }[];
  heatmap: { grid: number[][]; weekdays: string[]; max: number };
  top_contacts: Contact[];
  conversations: Conversation[];
  evidence: { id: string; original_name: string; source_type: string; message_count: number; imported_at: string; sha256: string }[];
  findings: number;
  notes: { id: string; body: string; created_at: string; message_body?: string }[];
  bookmarks: { id: string; label: string; body: string; sent_at_utc: string; conversation_title: string }[];
  sentiment_enabled: boolean;
  quick_actions: { label: string; route: string }[];
}

export interface SearchResult {
  id: string;
  conversation_id: string;
  conversation: string;
  sender_raw: string;
  sent_at_utc: string;
  body: string;
  message_type: string;
  has_media: boolean;
  is_deleted: boolean;
  is_edited: boolean;
  source_ref: string;
  evidence_id: string;
  parse_confidence: number;
  snippet: string;
}

export interface TimelineEvent {
  id: string;
  at: string;
  kind: string;
  title: string;
  detail: string;
  message_id: string | null;
  type?: string;
  media?: boolean;
}

export interface RecoveryFinding {
  id: string;
  kind: string;
  status: string;
  summary: string;
  detail: Record<string, unknown>;
  message_id: string | null;
  evidence_id: string | null;
  created_at: string;
}

export interface NetworkGraphData {
  nodes: { id: string; label: string; kind: string; weight: number; contact_id?: string; conversation_id?: string }[];
  edges: { id: string; source: string; target: string; kind: string; inferred: boolean; weight: number; label: string }[];
  metrics: Record<string, string | number>;
}

export interface AiCitation {
  id?: string;
  message_id: string;
  score: number;
  snippet: string;
  marker?: string;
  validated?: boolean;
  sender?: string;
  conversation?: string;
  sent_at_utc?: string;
  reason?: string;
}

export interface AiAnswer {
  id: string;
  question: string;
  answer: string;
  status: string;
  error: string | null;
  provider: string;
  model: string;
  citations: AiCitation[];
  invalid_citations: string[];
  observed: {
    stats: Record<string, unknown>;
    retrieved: number;
    truncated: boolean;
    notes: string[];
    records?: { message_id: string; snippet: string; sender?: string; conversation?: string; sent_at_utc?: string; score?: number; reason?: string }[];
  };
  duration_ms: number;
  disclosure: string;
  sections: {
    observed_evidence: AiCitation[];
    computed_statistics: Record<string, unknown>;
    ai_interpretation: string;
  };
}

export interface Settings {
  theme: "dark" | "light";
  density: "comfortable" | "compact";
  language: string;
  source_timezone: string;
  default_evidence_dir: string;
  default_report_dir: string;
  hash_verification: boolean;
  validate_imports: boolean;
  duplicate_handling: string;
  auto_backup: boolean;
  application_lock: boolean;
  ai_provider: string;
  ai_model: string;
  ai_embedding_model: string;
  ai_context_length: number;
  ai_temperature: number;
  ai_enabled: boolean;
  ai_external_enabled: boolean;
  ai_external_base_url: string;
  transcription_model: string;
  interpretive_analysis: boolean;
  anomaly_sensitivity: number;
  report_theme: string;
  report_include_charts: boolean;
  keyboard_shortcuts: boolean;
  date_format: string;
  audit_retention_days: number;
  auto_backup_interval_hours: number;
  [key: string]: unknown;
}
