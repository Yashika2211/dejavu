"use client";

// Ask DejaVu (spec 11.2): Cmd+K from anywhere, a free-form question, an answer with citations.

import * as Dialog from "@radix-ui/react-dialog";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { MemoryHit } from "@/lib/types";
import { MemoryList } from "./provenance";
import { Button } from "./ui";

type Answer = { answer: string; based_on: MemoryHit[] };

export function AskDejaVu() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const ask = async () => {
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api.post<Answer>("/ask", { question }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content className="fixed top-[12vh] left-1/2 z-50 flex max-h-[76vh] w-[min(720px,92vw)] -translate-x-1/2 flex-col rounded-lg border border-border bg-panel shadow-2xl">
          <Dialog.Title className="border-b border-border px-4 py-3 text-sm font-medium">Ask DejaVu</Dialog.Title>
          <Dialog.Description className="sr-only">
            Ask a question about past incidents. Answers cite the memories they rest on.
          </Dialog.Description>
          <form
            className="flex gap-2 border-b border-border p-3"
            onSubmit={(e) => {
              e.preventDefault();
              void ask();
            }}
          >
            <input
              autoFocus
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Have we seen x509: certificate has expired before?"
              className="h-9 flex-1 rounded border border-border bg-bg px-3 text-sm"
            />
            <Button type="submit" variant="memory" disabled={busy || !question.trim()}>
              {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : "Ask"}
            </Button>
          </form>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {error && <p className="text-sm text-critical">{error}</p>}
            {answer && (
              <div className="space-y-4">
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{answer.answer}</p>
                <div>
                  <p className="mb-2 text-[11px] tracking-wider text-muted uppercase">Citations</p>
                  <MemoryList hits={answer.based_on} limit={12} />
                </div>
              </div>
            )}
            {!answer && !error && (
              <p className="text-sm text-muted">Answers come from the live memory bank, with the memories they rest on.</p>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
