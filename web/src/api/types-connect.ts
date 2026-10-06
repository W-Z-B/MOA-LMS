/** Outside tools over LTI 1.3 (item 6.07) and AI help within decision D5 (items 6.11, 6.12). */

export interface Tool {
  id: number;
  name: string;
  description: string;
  /** Registration details: course administrators only. */
  client_id?: string;
  deployment_id?: string;
  oidc_login_url: string;
  launch_url: string;
  deep_linking_url: string;
  redirect_urls?: string[];
  jwks_url?: string;
  public_key?: string;
  share_name: boolean;
  share_email: boolean;
  grades: boolean;
  class_list: boolean;
  is_active: boolean;
  /** What the tool receives about people, in words. */
  receives: string[];
  can_choose_content: boolean;
}

export interface Platform {
  issuer: string;
  jwks_url: string;
  auth_url: string;
  token_url: string;
  deep_link_return_url: string;
  launch_start: string;
}

export interface Placement {
  id: number;
  item: number;
  module_id: number;
  tool: number;
  tool_name: string;
  title: string;
  is_published: boolean;
  /** The LMS's own launch address, /api/lti/launch/<item>/: opens the tool in a new window. */
  launch_url: string;
}

export interface ToolLineItem {
  id: number;
  label: string;
  tool_name: string;
  placement: number | null;
  score_maximum: string;
  weight: string;
  grade_category: number | null;
}

export interface SiteTools {
  teaching: boolean;
  placements: Placement[];
  line_items: ToolLineItem[];
  tools: Tool[];
}

/** A tool item's address in a module: content lists show it as "Open the tool", not as a web address. */
export const isToolLaunch = (url: string) => /^\/api\/lti\/launch\/\d+\/$/.test(url);

export interface AiStatus {
  enabled: boolean;
  teaching: boolean;
  drafts: boolean;
  study_helper: boolean;
  helper_available: boolean;
  helper_reason: string | null;
  pictures: boolean;
}

export interface DraftChoice {
  id?: string;
  text: string;
  fraction: number;
  feedback: string;
}

export interface DraftQuestion {
  name: string;
  qtype: "multichoice";
  text: string;
  data: { single: boolean; shuffle: boolean; choices: DraftChoice[] };
  general_feedback: string;
}

export interface DraftRubric {
  title: string;
  kind: "scored";
  criteria: { title: string; description: string; levels: { points: string; description: string }[] }[];
}

export interface Draft<T> {
  draft: number;
  output: T;
}

export interface HelperAnswer {
  answered: boolean;
  answer: string;
  sources: { item: number; title: string; module: string; link: string }[];
}
