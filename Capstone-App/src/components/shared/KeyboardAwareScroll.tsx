import { KeyboardAvoidingView, Platform, ScrollView, type ScrollViewProps } from 'react-native';
import { cn } from '@/utils/helpers';

interface KeyboardAwareScrollProps extends ScrollViewProps {
  className?: string;
}

export function KeyboardAwareScroll({ children, className, contentContainerStyle, ...props }: KeyboardAwareScrollProps) {
  return (
    <KeyboardAvoidingView
      className="flex-1"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 0}
    >
      <ScrollView
        className={cn('flex-1', className)}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="interactive"
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[{ paddingBottom: 32 }, contentContainerStyle]}
        {...props}
      >
        {children}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
