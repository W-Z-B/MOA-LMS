/** Types for help requests (item 7.17). They mirror helpdesk.api: keep in step with /api/docs. */

export interface HelpRequest {
  id: number;
  subject: string;
  message: string;
  /** The address in the web app the person asked from, e.g. /sites/4; empty when none was sent. */
  page: string;
  status: "open" | "answered";
  asked_by_name: string | null;
  created_at: string;
  client_sent_at: string | null;
  answer: string;
  answered_by_name: string | null;
  answered_at: string | null;
  /** True when the reader sent it. */
  mine: boolean;
}
