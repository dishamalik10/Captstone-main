import React, { Component, type ReactNode } from 'react';
import { View, Text } from 'react-native';
import { Button } from '@/components/ui/Button';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <View className="flex-1 bg-background items-center justify-center px-6">
          <Text className="text-text-primary font-display text-3xl mb-3 text-center">Something went wrong</Text>
          <Text className="text-text-secondary font-body text-base text-center mb-8 max-w-sm">
            AURA hit an unexpected error. Try again, and if it keeps happening, restart the app.
          </Text>
          <Button label="Try again" onPress={() => this.setState({ hasError: false })} />
        </View>
      );
    }
    return this.props.children;
  }
}
