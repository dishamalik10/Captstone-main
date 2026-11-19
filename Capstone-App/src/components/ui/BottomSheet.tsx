import { useCallback, useMemo, forwardRef } from 'react';
import { Text, useWindowDimensions } from 'react-native';
import GorhomBottomSheet, { BottomSheetBackdrop, BottomSheetScrollView } from '@gorhom/bottom-sheet';
import type { BottomSheetBackdropProps } from '@gorhom/bottom-sheet';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useThemeColors } from '@/hooks/useThemeColors';
import { fonts, layout } from '@/constants/theme';

interface BottomSheetProps {
  children: React.ReactNode;
  title?: string;
  snapPoints?: string[];
  onClose?: () => void;
}

export const BottomSheet = forwardRef<GorhomBottomSheet, BottomSheetProps>(
  ({ children, title, snapPoints: customSnapPoints, onClose }, ref) => {
    const palette = useThemeColors();
    const insets = useSafeAreaInsets();
    const { width } = useWindowDimensions();
    const snapPoints = useMemo(() => customSnapPoints ?? ['55%', '88%'], [customSnapPoints]);
    const sheetWidth = Math.min(width, layout.reading);

    const renderBackdrop = useCallback(
      (props: BottomSheetBackdropProps) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.55} />
      ),
      [],
    );

    return (
      <GorhomBottomSheet
        ref={ref}
        index={-1}
        snapPoints={snapPoints}
        enablePanDownToClose
        onClose={onClose}
        backdropComponent={renderBackdrop}
        style={width > sheetWidth ? { marginHorizontal: (width - sheetWidth) / 2 } : undefined}
        backgroundStyle={{
          backgroundColor: palette.surface,
          borderTopLeftRadius: 20,
          borderTopRightRadius: 20,
          borderWidth: 1,
          borderColor: palette.border,
        }}
        handleIndicatorStyle={{ backgroundColor: palette.borderStrong, width: 36, height: 4 }}
      >
        <BottomSheetScrollView
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 4, paddingBottom: 32 + insets.bottom }}
          keyboardShouldPersistTaps="handled"
        >
          {title ? (
            <Text
              accessibilityRole="header"
              style={{ color: palette.textPrimary, fontFamily: fonts.display, fontSize: 24, lineHeight: 30, marginBottom: 20 }}
            >
              {title}
            </Text>
          ) : null}
          {children}
        </BottomSheetScrollView>
      </GorhomBottomSheet>
    );
  },
);

BottomSheet.displayName = 'BottomSheet';
export const AppBottomSheet = BottomSheet;
