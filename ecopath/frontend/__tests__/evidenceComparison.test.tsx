import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EvidenceComparisonPanel, safeEvidenceUrl } from "@/components/extinction-risk/EvidenceComparisonPanel";

const post=vi.hoisted(()=>vi.fn());
vi.mock("@/lib/api",()=>({api:{post}}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
function mount() {
    return render(<QueryClientProvider client={new QueryClient({defaultOptions:{mutations:{retry:false}}})}>
        <EvidenceComparisonPanel scientificName="Synthetic fixture" />
    </QueryClientProvider>);
}
async function upload() {
    const packet={payload:{scientific_name:"Synthetic fixture",example_id:"fixture",fields:{},sources:[]}};
    const file=new File([JSON.stringify(packet)],"evidence.json",{type:"application/json"});
    Object.defineProperty(file,"text",{value:async()=>JSON.stringify(packet)});
    fireEvent.change(screen.getByLabelText("Evidence packet"),{target:{files:[file]}});
    await waitFor(()=>expect((screen.getByText("Preview method") as HTMLButtonElement).disabled).toBe(false));
}
describe("fixed evidence draft rendering",()=>{
    it("rejects unsafe source links",()=>{
        expect(safeEvidenceUrl("javascript:alert(1)")).toBeUndefined();
        expect(safeEvidenceUrl("https://example.invalid/source")).toContain("https://");
    });
    it("shows validated fields, missingness, sources and review label",async()=>{
        post.mockResolvedValue({data:{draft_for_review:true,validation_status:"structured_valid",validation_errors:[],
            missing_fields:["iucn_status"],false_abstention_fields:[],
            report:{fields:{diet:{value:"FIXTURE_TOKEN_A",kind:"source_reported",source_ids:["s1"]}},claims:[],suggested_actions:[]},
            sources:[{source_id:"s1",excerpt:"FIXTURE_TOKEN_A"}],source_catalog:[],raw_response:"{}",disclaimer:"Draft for human review"}});
        mount();await upload();fireEvent.click(screen.getByText("Preview method"));
        await waitFor(()=>expect(screen.getAllByText("Draft for human review").length).toBeGreaterThan(0));
        expect(screen.getByText("Missing evidence: iucn_status")).toBeTruthy();
        expect(screen.getByText("Supplied evidence sources")).toBeTruthy();
    });
    it("shows invalid output without rendering a report",async()=>{
        post.mockResolvedValue({data:{draft_for_review:true,validation_status:"invalid",validation_errors:["invalid JSON"],
            missing_fields:[],false_abstention_fields:[],report:null,sources:[],source_catalog:[],raw_response:"BROKEN_FIXTURE",disclaimer:"Review required"}});
        mount();await upload();fireEvent.click(screen.getByText("Preview method"));
        await waitFor(()=>expect(screen.getByRole("alert").textContent).toContain("invalid JSON"));
        expect(screen.getByText("BROKEN_FIXTURE")).toBeTruthy();
    });
});
