import { quizAddress, useHashRoute } from "../../app/router";
import { AttemptPlayer } from "./AttemptPlayer";
import { BanksScreen } from "./BanksScreen";
import { QuizList } from "./QuizList";
import { QuizManage } from "./QuizManage";
import { StudentQuiz } from "./StudentQuiz";
import { TeacherAttempt } from "./TeacherAttempt";
import "./quizzes.css";

/**
 * A course site's Quizzes tab (feature 10). It reads the rest of the address itself, so the site screen only
 * names the tab: #/sites/4/quizzes/12/attempts/30 opens that attempt inside the site.
 */
export function QuizzesTab({ siteId, teaching }: { siteId: number; teaching: boolean }) {
  return (
    <div className="quizzes">
      <QuizView siteId={siteId} teaching={teaching} />
    </div>
  );
}

function QuizView({ siteId, teaching }: { siteId: number; teaching: boolean }) {
  const [path, navigate] = useHashRoute();
  const view = quizAddress(path);
  const base = `/sites/${siteId}/quizzes`;
  const open = (rest: string) => navigate(`${base}/${rest}`);
  const toList = () => navigate(base);

  if (view.view === "banks" && teaching) return <BanksScreen siteId={siteId} onBack={toList} />;
  if (view.view === "quiz")
    return teaching ? (
      <QuizManage key={view.quizId} siteId={siteId} quizId={view.quizId} section={view.section} onOpen={open} onBack={toList} />
    ) : (
      <StudentQuiz key={view.quizId} quizId={view.quizId} onOpen={open} onBack={toList} />
    );
  if (view.view === "attempt")
    return teaching ? (
      <TeacherAttempt key={view.attemptId} attemptId={view.attemptId} onBack={() => open(`${view.quizId}/results`)} />
    ) : (
      <AttemptPlayer key={view.attemptId} attemptId={view.attemptId} onBack={() => open(String(view.quizId))} />
    );
  return <QuizList siteId={siteId} teaching={teaching} onOpen={open} />;
}
