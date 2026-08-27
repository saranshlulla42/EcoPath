import { Block } from '../../types/chat';
import { NarrativeBlockView } from './blocks/NarrativeBlock';
import { LineChartBlockView } from './blocks/LineChartBlock';
import { BarChartBlockView } from './blocks/BarChartBlock';
import { StatCardBlockView } from './blocks/StatCardBlock';
import { ComparisonTableBlockView } from './blocks/ComparisonTableBlock';
import { MapPlaceholder } from './blocks/MapPlaceholder';
import { MapHighlightBlockView } from './blocks/MapHighlightBlock';
import { MigrationMapBlockView } from './blocks/MigrationMapBlock';
import { FollowUpsBlockView } from './blocks/FollowUpsBlock';

export function BlockRenderer({ block, isLastBlock, onFollowUp }: { block: Block; isLastBlock: boolean, onFollowUp?: (text: string) => void }) {
  switch (block.type) {
    case 'narrative':
      return <NarrativeBlockView block={block} />;
    case 'line_chart':
      return <LineChartBlockView block={block} />;
    case 'bar_chart':
      return <BarChartBlockView block={block} />;
    case 'stat_card':
      return <StatCardBlockView block={block} />;
    case 'comparison_table':
      return <ComparisonTableBlockView block={block} />;
    case 'map_highlight':
      return <MapHighlightBlockView block={block} />;
    case 'migration_map':
      // A migration block with no usable route has nothing to draw; fall back
      // to the placeholder rather than an empty frame.
      return block.routes?.length
        ? <MigrationMapBlockView block={block} />
        : <MapPlaceholder block={block} />;
    case 'follow_ups':
      return <FollowUpsBlockView block={block} onSelect={onFollowUp} />;
    default:
      return null;
  }
}
