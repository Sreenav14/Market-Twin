import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAppMapSkills, fetchAppMapSkillUsage, type AppMapSkillLibraryLine } from "../../lib/api";
import { statusEntry } from "../../lib/status";
import { BADGE_TONES, StatusPill } from "../ui/StatusBadge";
import { Button } from "../ui/button";

type SkillGroupId = "source" | "draft" | "verified" | "attention" | "retired";

const SKILL_GROUP_HEADINGS: {
  id: Exclude<SkillGroupId, "retired">;
  heading: string;
}[] = [
  { id: "source", heading: "Source knowledge — not yet a skill" },
  { id: "draft", heading: "Draft task skills" },
  { id: "verified", heading: "Verified skills" },
  { id: "attention", heading: "Skills requiring attention" },
];

// A task candidate (doc 29 section 3.4): a document-sourced task skill
// that has not been compiled or executed. The skills endpoint does not
// expose the source kind yet (task_source_kind on the line type), so
// until it does, no line classifies as a candidate and the Source
// knowledge group stays hidden rather than guessing from draft state.
function isTaskCandidate(skill: AppMapSkillLibraryLine): boolean {
  return (
    skill.skill_kind === "task" &&
    skill.lifecycle_status === "draft" &&
    skill.task_source_kind === "document"
  );
}

function skillGroupId(skill: AppMapSkillLibraryLine): SkillGroupId {
  if (skill.lifecycle_status === "retired") return "retired";
  if (isTaskCandidate(skill)) return "source";
  if (
    skill.lifecycle_status === "replay_verified" ||
    skill.lifecycle_status === "active"
  ) {
    return "verified";
  }
  if (
    skill.lifecycle_status === "suspect" ||
    skill.lifecycle_status === "quarantined"
  ) {
    return "attention";
  }
  return "draft";
}

function SkillUsageDetail({
  base,
  skillId,
}: {
  base: string;
  skillId: string;
}) {
  const usage = useQuery({
    queryKey: ["app-map-skill-usage", base, skillId],
    queryFn: () => fetchAppMapSkillUsage(base, skillId),
    retry: false,
  });
  if (usage.isPending) {
    return (
      <p className="muted" style={{ fontSize: "12px" }}>
        Loading usage…
      </p>
    );
  }
  if (usage.isError || !usage.data) {
    return (
      <p role="alert" style={{ fontSize: "12px" }}>
        Could not load this skill's usage.{" "}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void usage.refetch()}
        >
          Retry usage
        </Button>
      </p>
    );
  }
  const data = usage.data;
  const kinds = Object.entries(data.events_by_kind).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  const latest = data.latest_version;
  return (
    <div className="app-map-skill-usage" style={{ fontSize: "12px" }}>
      {latest ? (
        <p className="muted" style={{ margin: "4px 0" }}>
          Latest version v{latest.version_number} ·{" "}
          {latest.lifecycle_status
            ? statusEntry("skill", latest.lifecycle_status).word
            : "no lifecycle state"}{" "}
          · {latest.replay_count} replays · {latest.heal_count} heals · last
          replay: {latest.last_replay_result ?? "never"}
          {latest.last_replay_at
            ? ` (${new Date(latest.last_replay_at).toLocaleString()})`
            : ""}
          {latest.retired_reason ? ` · retired: ${latest.retired_reason}` : ""}
        </p>
      ) : (
        <p className="muted" style={{ margin: "4px 0" }}>
          No versions yet.
        </p>
      )}
      {kinds.length ? (
        <p style={{ margin: "4px 0" }}>
          Usage history:{" "}
          {kinds.map(([kind, count]) => `${kind} × ${count}`).join(" · ")}
        </p>
      ) : (
        <p className="muted" style={{ margin: "4px 0" }}>
          No usage recorded yet.
        </p>
      )}
      <p className="muted" style={{ margin: "4px 0" }}>
        {data.total_model_calls} model calls · {data.total_model_tokens}{" "}
        tokens · {data.diagnosis_model_calls} diagnosis model calls
      </p>
    </div>
  );
}

function SkillLibraryRow({
  base,
  skill,
}: {
  base: string;
  skill: AppMapSkillLibraryLine;
}) {
  const [expanded, setExpanded] = useState(false);
  const entry = isTaskCandidate(skill)
    ? statusEntry("skill", "source_knowledge")
    : skill.lifecycle_status
      ? statusEntry("skill", skill.lifecycle_status)
      : null;
  return (
    <li>
      <strong>{skill.name}</strong>{" "}
      <StatusPill tone="neutral" size="sm">
        {skill.skill_kind === "platform"
          ? "built-in"
          : skill.skill_kind === "task"
            ? "task"
            : "journey"}
      </StatusPill>{" "}
      {entry ? (
        <StatusPill tone={BADGE_TONES[entry.tone]} size="sm">
          {entry.word}
        </StatusPill>
      ) : (
        <StatusPill tone="neutral" size="sm">
          no versions yet
        </StatusPill>
      )}{" "}
      <span className="muted" style={{ fontSize: "12px" }}>
        {skill.version_number != null ? `v${skill.version_number} · ` : ""}
        last replay: {skill.last_replay_result ?? "never"}
        {skill.last_replay_at
          ? ` (${new Date(skill.last_replay_at).toLocaleString()})`
          : ""}{" "}
        · {skill.replay_count} replays · {skill.heal_count} heals ·{" "}
        {skill.diagnosis_model_calls} diagnosis model calls
        {skill.status_reason ? ` · reason: ${skill.status_reason}` : ""}
      </span>{" "}
      <Button
        variant="secondary"
        size="sm"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Hide history" : "History"}
      </Button>
      {expanded ? (
        <SkillUsageDetail base={base} skillId={skill.skill_id} />
      ) : null}
    </li>
  );
}

export function AppMapSkills({ base }: { base: string }) {
  const [showRetired, setShowRetired] = useState(false);
  const skills = useQuery({
    queryKey: ["app-map-skills", base],
    queryFn: () => fetchAppMapSkills(base),
    refetchInterval: 10000,
    retry: false,
  });
  const items: AppMapSkillLibraryLine[] = skills.data?.items ?? [];
  const groups = new Map<SkillGroupId, AppMapSkillLibraryLine[]>();
  for (const skill of items) {
    const id = skillGroupId(skill);
    groups.set(id, [...(groups.get(id) ?? []), skill]);
  }
  const retired = groups.get("retired") ?? [];
  return (
    <div className="app-map-phase3">
      <h4 style={{ marginBottom: "4px" }}>Skill library</h4>
      {skills.isError && <p role="alert">Could not load the skill library. <Button onClick={() => void skills.refetch()}>Retry skills</Button></p>}
      {skills.isPending ? (
        <p className="muted">Loading the skill library…</p>
      ) : skills.isError && !skills.data ? null : items.length ? (
        <>
          {SKILL_GROUP_HEADINGS.map(({ id, heading }) => {
            const members = groups.get(id) ?? [];
            if (!members.length) return null;
            return (
              <div className="app-map-skill-group" key={id}>
                <h5 style={{ margin: "8px 0 4px" }}>{heading}</h5>
                <ul className="app-map-skill-library">
                  {members.map((skill) => (
                    <SkillLibraryRow
                      key={skill.skill_id}
                      base={base}
                      skill={skill}
                    />
                  ))}
                </ul>
              </div>
            );
          })}
          {retired.length ? (
            <div className="app-map-skill-group">
              <Button
                variant="secondary"
                size="sm"
                aria-expanded={showRetired}
                onClick={() => setShowRetired((current) => !current)}
              >
                {showRetired ? "Hide retired" : `Retired (${retired.length})`}
              </Button>
              {showRetired ? (
                <ul className="app-map-skill-library">
                  {retired.map((skill) => (
                    <SkillLibraryRow
                      key={skill.skill_id}
                      base={base}
                      skill={skill}
                    />
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </>
      ) : (
        <p className="muted">
          No skills yet. Task skills are learned from recorded test runs and verified by replay.
        </p>
      )}
    </div>
  );
}
