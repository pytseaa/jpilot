import { useState } from "react";
import type { Review } from "./api";
import { ReviewScreen } from "./ReviewScreen";
import { UploadForm } from "./UploadForm";

export function App() {
  const [review, setReview] = useState<Review | null>(null);
  return (
    <main>
      {review ? (
        <ReviewScreen review={review} onRestart={() => setReview(null)} />
      ) : (
        <UploadForm onRead={setReview} />
      )}
    </main>
  );
}
