"use client";

import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Loader2, ShieldAlert, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { createExtinctionRiskReport } from "@/lib/api";
import type { ExtinctionRiskReportResult } from "@/lib/types";
import { EvidenceComparisonPanel } from "./EvidenceComparisonPanel";


type Props = {
    speciesName: string;
    scientificName: string;
    gbifKey: string;
    countryCode?: string;
};

function formatGenerationMode(mode: string) {
    switch (mode) {
        case "model_synthesis":
            return "Model synthesis";
        case "hybrid_recovery":
            return "Hybrid recovery";
        case "evidence_based_recovery":
            return "Evidence-based recovery";
        default:
            return "Reviewer draft";
    }
}

function formatModelStatus(status: string) {
    switch (status) {
        case "complete":
            return "Model complete";
        case "partial":
            return "Model partial";
        case "invalid_json":
            return "Model JSON invalid";
        case "empty":
            return "Model empty";
        case "timeout":
            return "Model timeout";
        case "unavailable":
            return "Model unavailable";
        case "http_error":
            return "Model HTTP issue";
        default:
            return "Model recovered";
    }
}


function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <p style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.62rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
            marginBottom: "0.5rem",
            fontWeight: 500,
        }}>
            {children}
        </p>
    );
}


function Pill({ children }: { children: React.ReactNode }) {
    return (
        <span style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontFamily: "var(--font-mono)",
            fontSize: "0.62rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--accent-primary)",
            background: "var(--accent-muted)",
            border: "1px solid var(--border)",
            padding: "4px 8px",
            borderRadius: "var(--r-sm)",
            fontWeight: 500,
        }}>
            {children}
        </span>
    );
}


export function ExtinctionRiskReportPanel({ speciesName, scientificName, gbifKey, countryCode }: Props) {
    const reportMutation = useMutation({
        mutationFn: () => {
            const payload = {
                species_name: scientificName || speciesName,
                gbif_key: gbifKey ? Number(gbifKey) : undefined,
                country_code: countryCode && countryCode !== "GLOBAL" ? countryCode : undefined,
            };
            console.log("[ExtinctionRisk] Generating report with payload:", payload);
            return createExtinctionRiskReport(payload);
        },
        onSuccess: (data) => {
            console.log("[ExtinctionRisk] Report generated successfully:", data);
        },
        onError: (error) => {
            console.error("[ExtinctionRisk] Report generation failed:", error);
        },
    });

    const report = reportMutation.data as ExtinctionRiskReportResult | undefined;

    return (
        <section id="extinction-risk-report" style={{ marginTop: "4rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "3rem" }}>
            <SectionLabel>Extinction Risk Draft</SectionLabel>
            <div style={{
                border: "1px solid var(--border)",
                borderRadius: "var(--r-md)",
                background: "var(--surface-raised)",
                boxShadow: "var(--shadow-card)",
                padding: "1.25rem",
            }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", marginBottom: "1rem" }}>
                    <div>
                        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "1.35rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                            Decision-support report
                        </h2>
                        <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", lineHeight: 1.7, color: "var(--text-secondary)", maxWidth: 760 }}>
                            Generate a local, reviewer-facing extinction-risk draft using the species profile, live evidence retrieval, and the Ollama-hosted report model. This is explicitly a human-review artifact, not an automated verdict.
                        </p>
                    </div>
                    <button
                        onClick={() => reportMutation.mutate()}
                        disabled={reportMutation.isPending}
                        style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 8,
                            border: "1px solid var(--border)",
                            background: reportMutation.isPending ? "var(--surface)" : "var(--accent-primary)",
                            color: reportMutation.isPending ? "var(--text-secondary)" : "var(--text-on-accent)",
                            borderRadius: "var(--r-md)",
                            padding: "0.8rem 1rem",
                            cursor: reportMutation.isPending ? "not-allowed" : "pointer",
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.62rem",
                            letterSpacing: "0.12em",
                            textTransform: "uppercase",
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                        }}
                    >
                        {reportMutation.isPending ? <Loader2 size={14} style={{ animation: "spin 0.8s linear infinite" }} /> : <Sparkles size={14} />}
                        {reportMutation.isPending ? "Generating…" : "Generate report"}
                    </button>
                </div>

                {reportMutation.isError && (
                    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "var(--danger-soft)", border: "1px solid rgba(192,57,43,0.18)", borderRadius: "var(--r-md)", padding: "0.85rem 1rem", marginBottom: "1rem" }}>
                        <AlertCircle size={16} style={{ color: "var(--danger)", marginTop: 2, flexShrink: 0 }} />
                        <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.88rem", lineHeight: 1.7, color: "var(--text-primary)" }}>
                            The local report service could not complete the draft. Check that Ollama is running and the backend can reach the configured model.
                        </p>
                    </div>
                )}

                {!report && !reportMutation.isError && (
                    <div style={{ display: "flex", alignItems: "center", gap: 10, border: "1px dashed var(--border)", borderRadius: "var(--r-md)", padding: "0.9rem 1rem", background: "var(--surface)" }}>
                        <ShieldAlert size={16} style={{ color: "var(--text-tertiary)" }} />
                        <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", lineHeight: 1.7, color: "var(--text-secondary)" }}>
                            The report is not fetched automatically. Generate it when you want a fresh decision-support draft.
                        </p>
                    </div>
                )}

                {report && (
                    <div style={{ display: "grid", gap: "1rem" }}>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <Pill>Draft for human review</Pill>
                            <Pill>Status: {report.current_conservation_status}</Pill>
                            <Pill>{formatGenerationMode(report.generation_mode)}</Pill>
                            <Pill>{formatModelStatus(report.model_output_status)}</Pill>
                            <Pill>Evidence: {report.evidence_items_reviewed}</Pill>
                            {report.limited_evidence_reasons.length > 0 && <Pill>Limited evidence</Pill>}
                        </div>

                        <p role="status">Evidence fidelity requires human review. {report.validation_errors?.join(" ")}</p>
                        {!!report.missing_evidence_fields?.length && <p>Missing evidence: {report.missing_evidence_fields.join(", ")}</p>}

                        {report.model_output_status !== "complete" && (
                            <div style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "rgba(214, 129, 14, 0.08)", border: "1px solid rgba(214, 129, 14, 0.22)", borderRadius: "var(--r-md)", padding: "0.85rem 1rem" }}>
                                <AlertCircle size={16} style={{ color: "rgb(214, 129, 14)", marginTop: 2, flexShrink: 0 }} />
                                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.88rem", lineHeight: 1.7, color: "var(--text-primary)" }}>
                                    The model response was incomplete or invalid. Recovery content is shown as an unverified draft and requires human review.
                                </p>
                            </div>
                        )}

                        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: "1rem" }} className="risk-grid">
                            <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "1rem", background: "var(--surface)" }}>
                                <SectionLabel>Assessment</SectionLabel>
                                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.92rem", lineHeight: 1.8, color: "var(--text-primary)" }}>
                                    {report.survivability_assessment}
                                </p>
                            </div>
                            <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "1rem", background: "var(--surface)" }}>
                                <SectionLabel>Reviewer notes</SectionLabel>
                                <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.92rem", lineHeight: 1.8, color: "var(--text-primary)" }}>
                                    {report.reviewer_notes}
                                </p>
                            </div>
                        </div>

                        <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "1rem", background: "var(--surface)" }}>
                            <SectionLabel>Decision-support draft</SectionLabel>
                            <div style={{ fontFamily: "var(--font-sans)", fontSize: "0.92rem", lineHeight: 1.85, color: "var(--text-primary)" }}>
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.decision_support_draft}</ReactMarkdown>
                            </div>
                        </div>

                        {report.limited_evidence_reasons.length > 0 && (
                            <div style={{ border: "1px solid rgba(214, 129, 14, 0.22)", borderRadius: "var(--r-md)", padding: "1rem", background: "rgba(214, 129, 14, 0.08)" }}>
                                <SectionLabel>Evidence limitations</SectionLabel>
                                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
                                    {report.limited_evidence_reasons.map((reason) => (
                                        <li key={reason} style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--text-primary)", paddingLeft: 12, borderLeft: "1px solid rgba(214, 129, 14, 0.35)" }}>
                                            {reason}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: "1rem" }} className="risk-grid">
                            <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "1rem", background: "var(--surface)" }}>
                                <SectionLabel>Key threats</SectionLabel>
                                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
                                    {report.key_threats.map((threat) => (
                                        <li key={threat} style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--text-secondary)", paddingLeft: 12, borderLeft: "1px solid var(--border-subtle)" }}>
                                            {threat}
                                        </li>
                                    ))}
                                </ul>
                            </div>

                            <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "1rem", background: "var(--surface)" }}>
                                <SectionLabel>Mitigation actions</SectionLabel>
                                <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
                                    {report.mitigation_actions.length > 0 ? report.mitigation_actions.map((action) => (
                                        <li key={action} style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--text-secondary)", paddingLeft: 12, borderLeft: "1px solid var(--border-subtle)" }}>
                                            {action}
                                        </li>
                                    )) : (
                                        <li style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                                            No mitigation actions were returned by the model.
                                        </li>
                                    )}
                                </ul>
                            </div>
                        </div>

                        <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "var(--r-md)", padding: "1rem", background: "var(--surface)" }}>
                            <SectionLabel>Sources</SectionLabel>
                            <div style={{ display: "grid", gap: 10 }}>
                                {report.sources.map((source) => (
                                    <a
                                        key={`${source.url}-${source.title}`}
                                        href={source.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ display: "grid", gap: 4, paddingBottom: 10, borderBottom: "1px solid var(--border-subtle)" }}
                                    >
                                        <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.9rem", color: "var(--accent-primary)", fontWeight: 600 }}>
                                            {source.title}
                                        </span>
                                        <span style={{ fontFamily: "var(--font-sans)", fontSize: "0.86rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
                                            {source.snippet || source.url}
                                        </span>
                                        <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                                            {source.seendate ?? source.source ?? "Evidence"}
                                        </span>
                                    </a>
                                ))}
                            </div>
                        </div>

                        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
                            {report.disclaimer} Model: {report.model_name}.
                        </p>
                    </div>
                )}
            </div>

            <EvidenceComparisonPanel key={scientificName} scientificName={scientificName} />

            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </section>
    );
}
