import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext, useParams } from "react-router-dom";

import { InlineAlert } from "../../components/ui/Feedback";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState, ErrorPanel, LoadingPanel } from "../../components/ui/StateViews";
import { api } from "../../lib/api";
import { AppShellContext } from "../../layouts/AppShell";

/**
 * Persona definitions for one application (U-P5-03). Personas are
 * profiles of real conditions — the conditions block is fixed by the
 * persona type and the server rejects any edit that changes it, adds
 * unknown keys, or introduces a score. What the owner edits here is
 * the voice: who is speaking and what they notice.
 */
export function ApplicationPersonasPage() {
  const { applicationId = "" } = useParams();
  const { workspace, user } = useOutletContext<AppShellContext>();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const personas = useQuery({
    queryKey: ["application-personas", user.id, workspace.id, applicationId],
    queryFn: ({ signal }) => api.listPersonas(applicationId, signal),
  });

  const save = useMutation({
    mutationFn: (args: { personaId: string; yaml: string }) =>
      api.updatePersona(applicationId, args.personaId, args.yaml),
    onSuccess: (saved) => {
      setSaveError(null);
      setDraft(saved.yaml);
      void queryClient.invalidateQueries({
        queryKey: ["application-personas", user.id, workspace.id, applicationId],
      });
    },
    onError: (error) => {
      setSaveError(error instanceof Error ? error.message : "Could not save the persona.");
    },
  });

  if (personas.isPending) return <LoadingPanel label="Loading personas" />;
  if (personas.isError) {
    return <ErrorPanel message="Persona definitions are unavailable." action={(
      <button className="secondary-button" type="button" onClick={() => void personas.refetch()}>Retry</button>
    )} />;
  }
  const list = personas.data;
  const selected = list.find((persona) => persona.persona_id === selectedId) ?? list[0] ?? null;
  const editorValue = draft ?? selected?.yaml ?? "";

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Personas"
        title="Who tests as a person"
        description="Each persona is a set of real conditions — a small phone on a slow network, a keyboard only, a reader working in a second language. Their impressions appear as quotes tied to the exact page. They never produce scores and never change a verdict."
      />
      {list.length === 0 ? (
        <EmptyState
          title="No personas yet"
          copy="Run a Persona Test and MarketTwin generates this application's personas from what the checker found. They will appear here, ready to review and adjust."
        />
      ) : (
        <div className="persona-editor-layout">
          <ul className="persona-list" aria-label="Personas">
            {list.map((persona) => (
              <li key={persona.persona_id}>
                <button
                  type="button"
                  className={selected?.persona_id === persona.persona_id ? "persona-list-item is-selected" : "persona-list-item"}
                  onClick={() => { setSelectedId(persona.persona_id); setDraft(null); setSaveError(null); }}
                >
                  <strong>{persona.name}</strong>
                  <span className="muted">{persona.persona_type}{persona.enabled ? "" : " · turned off"}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected ? (
            <section className="persona-editor" aria-label={`Edit ${selected.name}`}>
              <label className="field">
                <span>Definition (YAML)</span>
                <textarea
                  rows={24}
                  value={editorValue}
                  onChange={(event) => setDraft(event.target.value)}
                  spellCheck={false}
                />
              </label>
              <p className="muted">
                You can edit the name, the voice, the journeys, and whether this persona runs.
                The conditions block is fixed by the persona type — the server rejects a definition
                whose conditions differ, and any definition containing a score.
              </p>
              {saveError ? <InlineAlert severity="error" role="alert" title={saveError} /> : null}
              <div className="button-row">
                <button
                  type="button"
                  className="primary-button"
                  disabled={save.isPending || draft === null}
                  onClick={() => save.mutate({ personaId: selected.persona_id, yaml: editorValue })}
                >
                  Save persona
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={draft === null}
                  onClick={() => { setDraft(null); setSaveError(null); }}
                >
                  Discard changes
                </button>
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
