import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { TimelineScrubber } from "../components/migration/TimelineScrubber";

describe("TimelineScrubber", () => {
  let onWeekChange: ReturnType<typeof vi.fn>;
  let onPlayToggle: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onWeekChange = vi.fn();
    onPlayToggle = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders with correct week indicator", () => {
    render(
      <TimelineScrubber
        currentWeek={15}
        isPlaying={false}
        onWeekChange={onWeekChange}
        onPlayToggle={onPlayToggle}
      />
    );

    expect(screen.getByText("W15")).toBeTruthy();
  });

  it("fires onPlayToggle when play button is clicked", () => {
    render(
      <TimelineScrubber
        currentWeek={1}
        isPlaying={false}
        onWeekChange={onWeekChange}
        onPlayToggle={onPlayToggle}
      />
    );

    const playBtn = screen.getByLabelText("Play animation");
    fireEvent.click(playBtn);
    expect(onPlayToggle).toHaveBeenCalledTimes(1);
  });

  it("shows pause label when isPlaying is true", () => {
    render(
      <TimelineScrubber
        currentWeek={1}
        isPlaying={true}
        onWeekChange={onWeekChange}
        onPlayToggle={onPlayToggle}
      />
    );

    expect(screen.getByLabelText("Pause animation")).toBeTruthy();
  });

  it("fires onWeekChange when slider changes", () => {
    render(
      <TimelineScrubber
        currentWeek={1}
        isPlaying={false}
        onWeekChange={onWeekChange}
        onPlayToggle={onPlayToggle}
      />
    );

    const slider = screen.getByLabelText("Migration week");
    fireEvent.change(slider, { target: { value: "26" } });
    expect(onWeekChange).toHaveBeenCalledWith(26);
  });

  it("fires onWeekChange when a month label is clicked", () => {
    render(
      <TimelineScrubber
        currentWeek={1}
        isPlaying={false}
        onWeekChange={onWeekChange}
        onPlayToggle={onPlayToggle}
      />
    );

    // Click "Jul" — should map to week 27
    const julBtn = screen.getByText("Jul");
    fireEvent.click(julBtn);
    expect(onWeekChange).toHaveBeenCalledWith(27);
  });

  it("displays week 1 through 52 range on the slider", () => {
    render(
      <TimelineScrubber
        currentWeek={52}
        isPlaying={false}
        onWeekChange={onWeekChange}
        onPlayToggle={onPlayToggle}
      />
    );

    const slider = screen.getByLabelText("Migration week") as HTMLInputElement;
    expect(slider.min).toBe("1");
    expect(slider.max).toBe("52");
    expect(slider.value).toBe("52");
  });
});
