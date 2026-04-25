"use client";

import { TimelineScrubber, type SeasonWindow } from "./TimelineScrubber";

interface MigrationControlDate {
  week: number;
  label: string;
}

interface MigrationControlsProps {
  currentWeek: number;
  isPlaying: boolean;
  onWeekChange: (week: number) => void;
  onPlayToggle: () => void;
  onPrev: () => void;
  onNext: () => void;
  onReset: () => void;
  seasonWindows?: SeasonWindow | null;
  speciesColor?: string;
  dates?: MigrationControlDate[];
}

export function MigrationControls(props: MigrationControlsProps) {
  return (
    <TimelineScrubber
      currentWeek={props.currentWeek}
      isPlaying={props.isPlaying}
      onWeekChange={props.onWeekChange}
      onPlayToggle={props.onPlayToggle}
      onPrev={props.onPrev}
      onNext={props.onNext}
      onReset={props.onReset}
      seasonWindows={props.seasonWindows}
      speciesColor={props.speciesColor}
      dates={props.dates}
    />
  );
}
