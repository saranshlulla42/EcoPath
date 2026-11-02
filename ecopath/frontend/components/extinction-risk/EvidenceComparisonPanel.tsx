"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Method = "template" | "original" | "engineered" | "constrained" | "qlora";
type Payload = { scientific_name: string; example_id: string; [key: string]: unknown };
type Preview = {
    method: string;
    model_name: string;
    example_id: string;
    draft_for_review: boolean;
    validation_status: string;
    validation_errors: string[];
    missing_fields: string[];
    false_abstention_fields: string[];
    report: { fields: Record<string, { value: unknown; kind: string; source_ids: string[] }>; claims: { text: string; source_ids: string[] }[]; suggested_actions: string[] } | null;
    sources: { source_id: string; excerpt: string }[];
    source_catalog: { source_id: string; url?: string; retrieved_at?: string; record_id?: string }[];
    raw_response: string;
    disclaimer: string;
};

export function safeEvidenceUrl(value?: string) {
    if (!value) return undefined;
    try {
        const url = new URL(value);
        return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
    } catch { return undefined; }
}

export function EvidenceComparisonPanel({ scientificName }: { scientificName: string }) {
    const [method, setMethod] = useState<Method>("template");
    const [packet, setPacket] = useState<{ payload: Payload; source_catalog: object[] } | null>(null);
    const [fileError, setFileError] = useState("");
    const mutation = useMutation({
        mutationFn: async () => {
            if (!packet) throw new Error("Upload an evidence packet first");
            const response = await api.post<Preview>("/api/extinction-risk/evidence-preview", { ...packet, method }, { timeout: 360000 });
            return response.data;
        },
    });
    const result = mutation.data;
    return <details style={{ marginTop: "1.5rem", border: "1px solid var(--border)", padding: "1rem" }}>
        <summary>Compare methods on fixed evidence</summary>
        <p>Upload a reviewed evidence packet for this species. Every method receives the same supplied evidence. Drafts require human review; previews are separate from frozen research results.</p>
        <label>Evidence packet <input type="file" disabled={mutation.isPending} accept=".json,application/json" onChange={async event => {
            setPacket(null); mutation.reset(); setFileError("");
            const file = event.target.files?.[0];
            if (!file) return;
            try {
                const data = JSON.parse(await file.text());
                const payload = data.payload ?? data;
                if (payload.scientific_name !== scientificName) throw new Error("Evidence species must exactly match the displayed scientific name");
                if (!payload.example_id || !payload.fields || !Array.isArray(payload.sources)) throw new Error("Invalid evidence packet");
                setPacket({ payload, source_catalog: Array.isArray(data.source_catalog) ? data.source_catalog : [] });
            } catch (error) { setFileError(error instanceof Error ? error.message : "Could not read evidence packet"); }
        }} /></label>
        {fileError && <p role="alert">{fileError}</p>}
        <label>Report method <select disabled={mutation.isPending} value={method} onChange={event => { setMethod(event.target.value as Method); mutation.reset(); }}>
            <option value="template">Deterministic evidence template</option>
            <option value="original">Original instruction baseline</option>
            <option value="engineered">Engineered prompt</option>
            <option value="constrained">Engineered prompt with schema constraints</option>
            <option value="qlora">Configured adapted model with schema constraints</option>
        </select></label>
        <button disabled={!packet || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? "Generating draft…" : "Preview method"}</button>
        {mutation.isError && <p role="alert">The preview failed. Check the evidence packet and configured local model.</p>}
        {result && <div>
            <h3>Draft for human review</h3>
            <p>Method: {result.method}. Model: {result.model_name}. Example: {result.example_id}.</p>
            <p role="status">Validation: {result.validation_status}</p>
            {result.validation_errors.length > 0 && <p role="alert">Invalid or unsupported response: {result.validation_errors.join("; ")}</p>}
            <p>Missing evidence: {result.missing_fields.join(", ") || "None in collected fields"}</p>
            {result.false_abstention_fields.length > 0 && <p role="alert">Available evidence omitted: {result.false_abstention_fields.join(", ")}</p>}
            {result.report && <>
                <dl>{Object.entries(result.report.fields).map(([field, answer]) => <div key={field}>
                    <dt>{field}</dt><dd>{answer.kind === "unavailable" ? "Unavailable in supplied evidence" : JSON.stringify(answer.value)} {answer.source_ids.map(id => <a key={id} href={`#evidence-${id}`}>[{id}] </a>)}</dd>
                </div>)}</dl>
                {result.report.claims.length > 0 && <><h4>Claims awaiting human support review</h4><ul>{result.report.claims.map((claim, i) => <li key={i}>{claim.text} [{claim.source_ids.join(", ")}]</li>)}</ul></>}
                {result.report.suggested_actions.length > 0 && <><h4>Suggested actions for human consideration</h4><ul>{result.report.suggested_actions.map((action, i) => <li key={i}>{action}</li>)}</ul></>}
            </>}
            <h4>Supplied evidence sources</h4>
            {result.sources.map(source => {
                const metadata = result.source_catalog.find(item => item.source_id === source.source_id);
                const url = safeEvidenceUrl(metadata?.url);
                return <div id={`evidence-${source.source_id}`} key={source.source_id}>
                    <p>{source.source_id}: {source.excerpt}</p>
                    {url && <a href={url} target="_blank" rel="noopener noreferrer">Source record {metadata?.record_id}</a>}
                    <p>Retrieved: {metadata?.retrieved_at || "Unavailable"}</p>
                </div>;
            })}
            <details><summary>Raw response for review</summary><pre style={{ whiteSpace: "pre-wrap" }}>{result.raw_response}</pre></details>
            <p>{result.disclaimer}</p>
        </div>}
    </details>;
}
