import React from "react";
import { DataRow } from "./DataRow";
import { labelOf, relationshipTypeLabels } from "../labels";
import type { Investigation } from "../types";

function ProfileBlock({ title, values }: { title: string; values: string[] }) {
  return (
    <div>
      <span>{title}</span>
      <code>{values.length ? values.slice(0, 3).join("、") : "未确认"}</code>
    </div>
  );
}

export function DecisionProfilePanel({ profile }: { profile?: Investigation }) {
  const entities = profile?.entities ?? [];
  const relationships = profile?.relationships ?? [];
  const riskSignals = profile?.risk_report?.top_risk_signals ?? [];
  const identity = entities.find((e) => e.type === "identity");
  const contacts = entities.filter((e) => ["email", "phone", "social_profile", "profile_url"].includes(e.type));
  const personalAttributes = entities.filter((e) =>
    ["age_claim", "age_range", "gender_claim", "public_personal_attribute", "dietary_preference", "hospitality_preference"].includes(e.type),
  );
  const roles = entities.filter((e) => ["bio_snippet", "interest_tag", "declared_location"].includes(e.type));

  return (
    <article className="review-panel decision-profile-panel">
      <div className="section-heading">
        <h3>决策人画像</h3>
        <span>{profile ? "已并入企业任务" : "等待画像"}</span>
      </div>
      {profile ? (
        <>
          <div className="decision-profile-head">
            <strong>{identity?.value ?? profile.seed_value}</strong>
            <span>{profile.summary}</span>
          </div>
          <div className="profile-summary">
            <ProfileBlock title="联系方式" values={contacts.map((e) => e.value)} />
            <ProfileBlock title="职位/地区/兴趣" values={roles.map((e) => e.value)} />
            <ProfileBlock title="公开个人属性" values={personalAttributes.map((e) => e.value)} />
            <ProfileBlock title="复核风险" values={riskSignals.map((s) => s.kind)} />
          </div>
          <div className="detail-stack compact-stack">
            {relationships.slice(0, 4).map((r) => (
              <DataRow
                key={r.id}
                title={`${r.from_value} → ${r.to_value}`}
                meta={`${labelOf(relationshipTypeLabels, r.relationship_type)} / ${r.confidence.toFixed(2)}`}
              />
            ))}
          </div>
        </>
      ) : (
        <div className="empty compact">企业任务中还没有匹配到独立决策人画像。后续情报官回写后会自动并入。</div>
      )}
    </article>
  );
}
