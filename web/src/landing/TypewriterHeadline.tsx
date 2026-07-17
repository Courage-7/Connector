import { useEffect, useState } from "react";

const words = ["tools.", "data.", "mail.", "agents."] as const;

type TypingState = {
  wordIndex: number;
  characterCount: number;
  phase: "typing" | "holding" | "deleting";
};

function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return undefined;
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return reduced;
}

export function TypewriterHeadline() {
  const reducedMotion = useReducedMotion();
  const [typing, setTyping] = useState<TypingState>({
    wordIndex: 0,
    characterCount: words[0].length,
    phase: "holding",
  });

  useEffect(() => {
    if (reducedMotion) return undefined;

    const delay = typing.phase === "holding" ? 1450 : typing.phase === "deleting" ? 42 : 72;
    const timeout = window.setTimeout(() => {
      setTyping((current) => {
        const word = words[current.wordIndex];
        if (current.phase === "holding") {
          return { ...current, phase: "deleting" };
        }
        if (current.phase === "deleting") {
          if (current.characterCount > 0) {
            return { ...current, characterCount: current.characterCount - 1 };
          }
          const wordIndex = (current.wordIndex + 1) % words.length;
          return { wordIndex, characterCount: 0, phase: "typing" };
        }
        if (current.characterCount < word.length) {
          return { ...current, characterCount: current.characterCount + 1 };
        }
        return { ...current, phase: "holding" };
      });
    }, delay);

    return () => window.clearTimeout(timeout);
  }, [reducedMotion, typing]);

  const activeWord = reducedMotion ? words[0] : words[typing.wordIndex].slice(0, typing.characterCount);

  return (
    <h1 className="hero-title" aria-label="Connect your tools. Keep control.">
      <span className="hero-title-line">
        Connect your <span className="typing-slot" aria-hidden="true">
          <span className="typing-word">{activeWord}</span>
          <span className="typing-cursor" />
        </span>
      </span>
      <span className="hero-title-line hero-title-control">Keep control.</span>
    </h1>
  );
}
