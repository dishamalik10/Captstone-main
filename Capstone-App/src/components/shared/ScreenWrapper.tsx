import { View, Text, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '@/components/ui/Button';
import { EmptyState } from './EmptyState';
import { useThemeColors } from '@/hooks/useThemeColors';
import { layout } from '@/constants/theme';

interface ScreenWrapperProps {
  children?: React.ReactNode;
  className?: string;
  loading?: boolean;
  error?: string | null;
  empty?: boolean;
  emptyTitle?: string;
  emptyMessage?: string;
  emptyActionLabel?: string;
  onEmptyAction?: () => void;
  onRetry?: () => void;
}

export function ScreenWrapper({
  children,
  loading,
  error,
  empty,
  emptyTitle = 'Nothing here yet',
  emptyMessage = 'Start adding items to see them here.',
  emptyActionLabel,
  onEmptyAction,
  onRetry,
  className,
}: ScreenWrapperProps) {
  const palette = useThemeColors();
  const screenStyle = {
    flex: 1,
    width: '100%',
    maxWidth: layout.app,
    alignSelf: 'center',
    backgroundColor: palette.background,
  } as const;

  if (loading) {
    return (
      <SafeAreaView style={screenStyle} edges={['top']}>
        <View
          style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}
          accessibilityRole="progressbar"
          accessibilityLabel="Loading"
        >
          <ActivityIndicator size="small" color={palette.accent} />
          <Text className="text-text-secondary font-body text-sm mt-3">Loading…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error) {
    return (
      <SafeAreaView style={screenStyle} edges={['top']}>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 }}>
          <View className="w-16 h-16 rounded-full border border-border items-center justify-center mb-5">
            <Ionicons name="cloud-offline-outline" size={26} color={palette.destructive} />
          </View>
          <Text accessibilityRole="header" className="text-text-primary font-display text-2xl mb-2 text-center">
            This didn’t load
          </Text>
          <Text className="text-text-secondary font-body text-base text-center mb-8 max-w-sm">{error}</Text>
          {onRetry && <Button variant="secondary" label="Try again" icon="refresh" onPress={onRetry} />}
        </View>
      </SafeAreaView>
    );
  }

  if (empty) {
    return (
      <SafeAreaView style={screenStyle} edges={['top']}>
        <EmptyState
          title={emptyTitle}
          message={emptyMessage}
          actionLabel={emptyActionLabel}
          onAction={onEmptyAction}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={screenStyle} edges={['top']} className={className}>
      {children}
    </SafeAreaView>
  );
}
