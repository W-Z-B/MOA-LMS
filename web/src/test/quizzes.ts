/** Fictional quiz data for the quiz screens' component tests (feature 10). */

import type { Attempt, AttemptQuestion, Question, QuestionBank, Quiz } from "../api/types-quizzes";

export const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

export const quiz = (over: Partial<Quiz> = {}): Quiz => ({
  id: 12,
  site: 9,
  title: "Soils check",
  description: "Ten minutes on soils.",
  opens_at: null,
  closes_at: null,
  time_limit_minutes: 10,
  attempts_allowed: 2,
  grading_method: "highest",
  pass_mark: "50.00",
  weight: "1.00",
  is_practice: false,
  is_published: true,
  shuffle_questions: false,
  shuffle_answers: true,
  questions_per_page: 0,
  navigation: "free",
  review_marks: "immediately",
  review_correct: "after_close",
  review_feedback: "immediately",
  auto_release: true,
  feedback_bands: [],
  max_mark: "2.00",
  my_status: null,
  ...over,
});

export const mcQuestion = (over: Partial<AttemptQuestion> = {}): AttemptQuestion => ({
  position: 1,
  page: 1,
  qtype: "multichoice",
  text: "<p>Which is a plant nutrient?</p>",
  image_url: null,
  data: { single: true, choices: [{ id: "a", text: "Nitrogen" }, { id: "b", text: "<em>Sand</em>" }] },
  max_mark: "1.00",
  response: null,
  file_url: null,
  saved_at: null,
  ...over,
});

export const attempt = (over: Partial<Attempt> = {}): Attempt => ({
  id: 30,
  quiz: 12,
  quiz_title: "Soils check",
  student_no: "S2026901",
  number: 1,
  state: "in_progress",
  server_time: "2026-10-05T14:00:00Z",
  started_at: "2026-10-05T14:00:00Z",
  deadline: "2026-10-05T14:10:00Z",
  seconds_left: 600,
  submitted_at: null,
  auto_submitted: false,
  navigation: "free",
  current_page: 1,
  last_page: 1,
  is_released: false,
  needs_grading: null,
  score: null,
  max_score: "2.0000",
  percent: null,
  passed: null,
  overall_feedback: "",
  questions: [
    mcQuestion(),
    { ...mcQuestion(), position: 2, qtype: "shortanswer", text: "<p>The green pigment?</p>", data: {} },
  ],
  ...over,
});

export const bank = (over: Partial<QuestionBank> = {}): QuestionBank => ({
  id: 1,
  name: "Crop production questions",
  site: 9,
  department_code: "",
  description: "",
  owner_label: "AGR101",
  can_manage: true,
  ...over,
});

export const question = (over: Partial<Question> = {}): Question => ({
  id: 5,
  bank: 1,
  category: 3,
  qtype: "multichoice",
  name: "Plant nutrients",
  tags: ["soils"],
  is_archived: false,
  versions_count: 1,
  new_version: false,
  latest: {
    id: 7,
    number: 1,
    text: "Which is a plant nutrient?",
    text_html: "<p>Which is a plant nutrient?</p>",
    data: {
      single: true,
      shuffle: true,
      choices: [
        { id: "a", text: "Nitrogen", fraction: 1, feedback: "Yes." },
        { id: "b", text: "Sand", fraction: 0, feedback: "" },
      ],
    },
    default_mark: "1.00",
    general_feedback: "",
    image_url: null,
    created_at: "2026-10-01T10:00:00Z",
    in_use: false,
  },
  ...over,
});
