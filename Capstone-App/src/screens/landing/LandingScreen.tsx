import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, Text, View, type LayoutChangeEvent } from 'react-native';
import Animated, {
  FadeIn,
  FadeOut,
  interpolate,
  useAnimatedReaction,
  useAnimatedRef,
  useAnimatedScrollHandler,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  Extrapolation,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { Wordmark } from '@/components/shared/Wordmark';
import { fonts, landing, layout } from '@/constants/theme';
import { hapticLight } from '@/utils/haptics';
import { LButton, useBreakpoints } from './primitives';
import {
  Experience,
  Faq,
  FinalCTA,
  Footer,
  Hero,
  HowItWorks,
  Personalisation,
  Problem,
  Technology,
} from './sections';

interface LandingScreenProps {
  /** Hero and nav call to action: into the existing Welcome flow. */
  onGetStarted: () => void;
  /** Final call to action: straight to sign up. */
  onStartStyling: () => void;
  onLogin: () => void;
}

type SectionKey = 'problem' | 'how' | 'features' | 'tech' | 'faq';

const NAV_LINKS: { key: SectionKey; label: string }[] = [
  { key: 'how', label: 'How it works' },
  { key: 'features', label: 'Features' },
  { key: 'tech', label: 'Technology' },
  { key: 'faq', label: 'FAQ' },
];

export function LandingScreen({ onGetStarted, onStartStyling, onLogin }: LandingScreenProps) {
  const insets = useSafeAreaInsets();
  const { wide, mid, height, gutter } = useBreakpoints();
  const reduceMotion = useReducedMotion();
  const scrollRef = useAnimatedRef<Animated.ScrollView>();
  const scrollY = useSharedValue(0);
  const howY = useSharedValue(Number.MAX_SAFE_INTEGER);
  const viewport = useSharedValue(height);
  const howRevealed = useSharedValue(0);
  const offsets = useRef<Partial<Record<SectionKey, number>>>({});
  const [menuOpen, setMenuOpen] = useState(false);

  const navHeight = (mid ? 72 : 60) + insets.top;
  useEffect(() => {
    viewport.value = height;
  }, [height, viewport]);

  const onScroll = useAnimatedScrollHandler((e) => {
    scrollY.value = e.contentOffset.y;
  });

  useAnimatedReaction(
    () => scrollY.value + viewport.value * 0.85 > howY.value,
    (inView) => {
      if (inView && howRevealed.value === 0) howRevealed.value = 1;
    },
  );

  const navSurface = useAnimatedStyle(() => ({
    opacity: interpolate(scrollY.value, [0, 24], [0, 1], Extrapolation.CLAMP),
  }));

  const record = (key: SectionKey) => (e: LayoutChangeEvent) => {
    offsets.current[key] = e.nativeEvent.layout.y;
    if (key === 'how') howY.value = e.nativeEvent.layout.y;
  };

  const scrollToSection = useCallback(
    (key: string) => {
      setMenuOpen(false);
      const y = offsets.current[key as SectionKey];
      if (y === undefined) return;
      scrollRef.current?.scrollTo({ y: Math.max(0, y - navHeight + 1), animated: !reduceMotion });
    },
    [navHeight, reduceMotion, scrollRef],
  );

  return (
    <View style={{ flex: 1, backgroundColor: landing.paper }}>
      <StatusBar style="dark" />
      <Animated.ScrollView
        ref={scrollRef}
        onScroll={onScroll}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: navHeight }}
        style={{ flex: 1 }}
      >
        <Hero onPrimary={onGetStarted} onSecondary={() => scrollToSection('how')} />
        <View onLayout={record('problem')}>
          <Problem />
        </View>
        <View onLayout={record('how')}>
          <HowItWorks revealed={howRevealed} />
        </View>
        <View onLayout={record('features')}>
          <Experience />
        </View>
        <Personalisation />
        <View onLayout={record('tech')}>
          <Technology />
        </View>
        <FinalCTA onStart={onStartStyling} onLogin={onLogin} />
        <View onLayout={record('faq')}>
          <Faq />
        </View>
        <Footer links={NAV_LINKS} onLink={scrollToSection} />
      </Animated.ScrollView>

      {/* Sticky navigation */}
      <View
        accessibilityRole="header"
        style={{ position: 'absolute', top: 0, left: 0, right: 0, height: navHeight, paddingTop: insets.top, zIndex: 300 }}
      >
        <Animated.View
          pointerEvents="none"
          style={[
            {
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: landing.paper,
              borderBottomWidth: 1,
              borderBottomColor: landing.rule,
            },
            navSurface,
          ]}
        />
        <View
          style={{
            flex: 1,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
            maxWidth: layout.content + gutter * 2,
            alignSelf: 'center',
            paddingHorizontal: gutter,
          }}
        >
          <Pressable
            accessibilityRole="link"
            accessibilityLabel="AURA, back to top"
            onPress={() => scrollRef.current?.scrollTo({ y: 0, animated: !reduceMotion })}
            style={{ minHeight: 44, justifyContent: 'center' }}
          >
            <Wordmark size={mid ? 20 : 18} color={landing.ink} style={{ paddingLeft: 0 }} />
          </Pressable>

          {wide && (
            <View style={{ flexDirection: 'row', gap: 4 }} accessibilityRole="menubar">
              {NAV_LINKS.map((l) => (
                <NavLink key={l.key} label={l.label} onPress={() => scrollToSection(l.key)} />
              ))}
            </View>
          )}

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: mid ? 12 : 4 }}>
            {mid && <NavLink label="Log in" onPress={onLogin} />}
            <LButton label={mid ? 'Get started' : 'Start'} small onPress={onGetStarted} />
            {!wide && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={menuOpen ? 'Close menu' : 'Open menu'}
                accessibilityState={{ expanded: menuOpen }}
                onPress={() => {
                  hapticLight();
                  setMenuOpen((v) => !v);
                }}
                style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}
              >
                <Ionicons name={menuOpen ? 'close' : 'menu'} size={24} color={landing.ink} />
              </Pressable>
            )}
          </View>
        </View>
      </View>

      {menuOpen && !wide && (
        <Animated.View
          entering={FadeIn.duration(180)}
          exiting={FadeOut.duration(120)}
          style={{
            position: 'absolute',
            top: navHeight,
            left: 0,
            right: 0,
            backgroundColor: landing.paper,
            borderBottomWidth: 1,
            borderBottomColor: landing.rule,
            paddingHorizontal: gutter,
            paddingBottom: 16,
            zIndex: 300,
          }}
        >
          {NAV_LINKS.map((l) => (
            <Pressable
              key={l.key}
              accessibilityRole="link"
              accessibilityLabel={l.label}
              onPress={() => scrollToSection(l.key)}
              style={{ minHeight: 52, justifyContent: 'center', borderBottomWidth: 1, borderBottomColor: landing.rule }}
            >
              <Text style={{ fontFamily: fonts.display, fontSize: 22, color: landing.ink }}>{l.label}</Text>
            </Pressable>
          ))}
          <Pressable
            accessibilityRole="link"
            accessibilityLabel="Log in"
            onPress={() => {
              setMenuOpen(false);
              onLogin();
            }}
            style={{ minHeight: 52, justifyContent: 'center' }}
          >
            <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 16, color: landing.ink2 }}>Log in</Text>
          </Pressable>
        </Animated.View>
      )}
    </View>
  );
}

function NavLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={label}
      onPress={onPress}
      style={(state) => ({
        minHeight: 44,
        paddingHorizontal: 14,
        borderRadius: 4,
        justifyContent: 'center',
        backgroundColor: (state as { hovered?: boolean }).hovered ? landing.paper2 : 'transparent',
      })}
    >
      <Text style={{ fontFamily: fonts.body, fontSize: 15, color: landing.ink2 }}>{label}</Text>
    </Pressable>
  );
}
