import { ScrollView } from 'react-native';
import { Chip } from '@/components/ui/Chip';

const SUGGESTIONS = [
  'What should I wear today?',
  'Outfit for a date',
  'What matches this shirt?',
  'Trending colors?',
];

interface SuggestedRepliesProps {
  onSelect: (text: string) => void;
}

export function SuggestedReplies({ onSelect }: SuggestedRepliesProps) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={{ flexGrow: 0, flexShrink: 0, maxHeight: 60 }}
      contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 8, alignItems: 'center' }}
    >
      {SUGGESTIONS.map((text) => (
        <Chip key={text} label={text} onPress={() => onSelect(text)} className="mb-0" />
      ))}
    </ScrollView>
  );
}
