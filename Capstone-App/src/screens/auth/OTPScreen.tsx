import { useRef, useState } from 'react';
import { View, Text, TextInput, Pressable } from 'react-native';
import { Button } from '@/components/ui/Button';
import { AuthScaffold } from '@/components/shared/AuthScaffold';
import { hapticLight, hapticSuccess } from '@/utils/haptics';
import { cn } from '@/utils/helpers';
import { useThemeColors } from '@/hooks/useThemeColors';

interface OTPScreenProps {
  email: string;
  onVerify: (code: string) => void;
  onResend: () => void;
  loading?: boolean;
}

export function OTPScreen({ email, onVerify, onResend, loading }: OTPScreenProps) {
  const palette = useThemeColors();
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(0);
  const inputs = useRef<(TextInput | null)[]>([]);
  const complete = code.every((c) => c);

  const handleChange = (text: string, index: number) => {
    const newCode = [...code];
    newCode[index] = text;
    setCode(newCode);
    if (text && index < 5) inputs.current[index + 1]?.focus();
    if (newCode.every((c) => c) && newCode.join('').length === 6) {
      hapticSuccess();
      onVerify(newCode.join(''));
    }
  };

  return (
    <AuthScaffold title="Check your inbox" subtitle={`Enter the 6-digit code sent to ${email}.`}>
      <View className="flex-row justify-between gap-2 mb-8">
        {code.map((digit, i) => (
          <TextInput
            key={i}
            ref={(ref) => {
              inputs.current[i] = ref;
            }}
            accessibilityLabel={`Digit ${i + 1} of 6`}
            value={digit}
            autoFocus={i === 0}
            onFocus={() => setFocusedIndex(i)}
            onBlur={() => setFocusedIndex((cur) => (cur === i ? null : cur))}
            onChangeText={(t) => handleChange(t.slice(-1), i)}
            onKeyPress={({ nativeEvent }) => {
              if (nativeEvent.key === 'Backspace' && !code[i] && i > 0) inputs.current[i - 1]?.focus();
            }}
            keyboardType="number-pad"
            textContentType="oneTimeCode"
            autoComplete="one-time-code"
            maxLength={1}
            selectionColor={palette.accent}
            className={cn(
              'flex-1 h-16 max-w-14 bg-surface border rounded-sm text-text-primary text-center font-display text-2xl',
              focusedIndex === i ? 'border-accent' : digit ? 'border-border-strong' : 'border-border',
            )}
          />
        ))}
      </View>

      <Button label="Verify" size="lg" onPress={() => onVerify(code.join(''))} loading={loading} disabled={!complete} />

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Resend code"
        onPress={() => {
          hapticLight();
          onResend();
        }}
        className="items-center justify-center min-h-12 mt-3"
      >
        <Text className="text-text-secondary font-body text-base">
          Didn’t get it? <Text className="text-text-primary font-body-semibold underline">Resend code</Text>
        </Text>
      </Pressable>
    </AuthScaffold>
  );
}
