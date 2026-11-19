import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, type SharedValue } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { AppImage } from '@/components/shared/AppImage';
import { GradientScrim } from '@/components/shared/GradientScrim';
import { Wordmark } from '@/components/shared/Wordmark';
import { StylistNote } from '@/components/outfits/StylistNote';
import { SKIN_TONES, STYLE_PREFERENCES } from '@/constants/categories';
import { fonts, landing } from '@/constants/theme';
import { hapticLight } from '@/utils/haptics';
import {
  DEMO_OUTFITS,
  DEMO_WARDROBE,
  FACTORS,
  FAQ,
  GARMENTS,
  PAINS,
  PIPELINE,
  PROBLEM_RAIL,
  STEPS,
  type SampleOutfit,
} from './content';
import {
  Container,
  DemoTag,
  Hairline,
  LButton,
  Reveal,
  SectionHead,
  Tile,
  useBreakpoints,
  useType,
} from './primitives';

const SECTION_SPACE = { wide: 136, mid: 104, small: 80 };

function useSectionPadding() {
  const { wide, mid } = useBreakpoints();
  return wide ? SECTION_SPACE.wide : mid ? SECTION_SPACE.mid : SECTION_SPACE.small;
}

/* ------------------------------------------------------------------ */
/* Hero                                                                */
/* ------------------------------------------------------------------ */

export function Hero({ onPrimary, onSecondary }: { onPrimary: () => void; onSecondary: () => void }) {
  const t = useType();
  const { wide, mid } = useBreakpoints();
  const outfit = DEMO_OUTFITS[0];

  const copy = (
    <View style={{ flex: wide ? 0.92 : undefined, paddingRight: wide ? 48 : 0, justifyContent: 'center' }}>
      <Animated.Text
        entering={FadeInDown.duration(600)}
        accessibilityRole="header"
        style={[t.display, { maxWidth: 560 }]}
      >
        Stop wondering what to wear.
      </Animated.Text>
      <Animated.Text entering={FadeInDown.duration(600).delay(70)} style={[t.lead, { marginTop: 24, maxWidth: 440 }]}>
        AURA styles the clothes you already own into outfits you’ll love.
      </Animated.Text>
      <Animated.View
        entering={FadeInDown.duration(600).delay(140)}
        style={{ flexDirection: mid ? 'row' : 'column', alignItems: mid ? 'center' : 'stretch', gap: mid ? 24 : 12, marginTop: 36 }}
      >
        <LButton label="Build my wardrobe" icon="arrow-forward" onPress={onPrimary} />
        <LButton label="See how it works" variant="text" onPress={onSecondary} />
      </Animated.View>
    </View>
  );

  return (
    <Container style={{ paddingTop: wide ? 48 : 28, paddingBottom: wide ? 160 : 72 }}>
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 0 : 48 }}>
        {copy}
        <Animated.View entering={FadeIn.duration(700).delay(160)} style={{ flex: wide ? 1.08 : undefined }}>
          <OutfitAssembly outfit={outfit} compact={!mid} />
        </Animated.View>
      </View>
    </Container>
  );
}

/** The signature: four garments from a wardrobe resolve into one styled outfit, with the stylist's reason. */
function OutfitAssembly({ outfit, compact }: { outfit: SampleOutfit; compact: boolean }) {
  const { width, gutter } = useBreakpoints();
  const pieces = outfit.pieces.map((id) => GARMENTS[id]);

  if (compact) {
    const available = width - gutter * 2;
    const tileW = (available - 8 * 3) / 4;
    return (
      <View>
        <Text style={{ fontFamily: fonts.body, fontSize: 13, color: landing.muted, marginBottom: 8 }}>
          From your wardrobe
        </Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {pieces.map((g) => (
            <Tile key={g.id} garment={g} width={tileW} />
          ))}
        </View>
        <View style={{ alignItems: 'center', paddingVertical: 10 }}>
          <Ionicons name="arrow-down" size={18} color={landing.gold} />
        </View>
        <OutfitResultCard outfit={outfit} imageAspect={4 / 3.4} />
      </View>
    );
  }

  const tileW = 116;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end' }}>
      <View style={{ width: tileW * 2 + 12 }}>
        <Text style={{ fontFamily: fonts.body, fontSize: 13, color: landing.muted, marginBottom: 10 }}>
          From your wardrobe
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {pieces.map((g) => (
            <Tile key={g.id} garment={g} width={tileW} showLabel />
          ))}
        </View>
      </View>
      <View style={{ width: 56, alignItems: 'center' }} accessibilityElementsHidden>
        <View style={{ height: 1, width: 40, backgroundColor: landing.gold }} />
        <Ionicons name="chevron-forward" size={14} color={landing.gold} style={{ position: 'absolute', right: 6 }} />
      </View>
      <View style={{ width: 312 }}>
        <OutfitResultCard outfit={outfit} imageAspect={4 / 4.6} floatingWhy />
      </View>
    </View>
  );
}

function OutfitResultCard({
  outfit,
  imageAspect,
  floatingWhy,
}: {
  outfit: SampleOutfit;
  imageAspect: number;
  floatingWhy?: boolean;
}) {
  return (
    <View>
      <View
        style={{
          borderRadius: 6,
          overflow: 'hidden',
          backgroundColor: landing.card,
          borderWidth: 1,
          borderColor: landing.rule,
        }}
      >
        <View style={{ width: '100%', aspectRatio: imageAspect, backgroundColor: landing.paper2 }}>
          <AppImage
            source={{ uri: outfit.image }}
            style={{ width: '100%', height: '100%', backgroundColor: landing.paper2 }}
            contentFit="cover"
            accessibilityLabel={`Sample outfit: ${outfit.name}`}
          />
          <GradientScrim color={landing.night} opacity={0.7} from={0.55} />
          <View style={{ position: 'absolute', left: 16, right: 16, bottom: 14 }}>
            <Text style={{ fontFamily: fonts.body, fontSize: 13, color: landing.nightMuted }}>
              {outfit.occasion}, {outfit.weather}
            </Text>
            <Text style={{ fontFamily: fonts.display, fontSize: 26, lineHeight: 31, color: landing.inkPaper, marginTop: 2 }}>
              {outfit.name}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, padding: 12 }}>
          {outfit.pieces.map((id) => (
            <View key={id} style={{ width: 34, height: 34, borderRadius: 3, overflow: 'hidden', backgroundColor: landing.paper2 }}>
              <AppImage source={{ uri: GARMENTS[id].image }} style={{ width: '100%', height: '100%' }} contentFit="cover" />
            </View>
          ))}
          <Text style={{ fontFamily: fonts.body, fontSize: 13, color: landing.muted, marginLeft: 6 }}>Sample recommendation</Text>
        </View>
      </View>
      <WhyBubble
        text={outfit.why}
        style={
          floatingWhy
            ? { position: 'absolute', left: -96, top: '100%', marginTop: -30, width: 264, zIndex: 2 }
            : { marginTop: 12 }
        }
      />
    </View>
  );
}

function WhyBubble({ text, style }: { text: string; style?: object }) {
  return <StylistNote text={text} theme="light" style={style} />;
}

/* ------------------------------------------------------------------ */
/* Problem                                                             */
/* ------------------------------------------------------------------ */

export function Problem() {
  const t = useType();
  const pad = useSectionPadding();
  const { wide, width, gutter } = useBreakpoints();
  const cols = wide ? 5 : 4;
  const gridWidth = wide ? 560 : width - gutter * 2;
  const tileW = (gridWidth - 10 * (cols - 1)) / cols;
  const rail = PROBLEM_RAIL.slice(0, wide ? 10 : 8);

  return (
    <View style={{ backgroundColor: landing.paper2 }}>
      <Container style={{ paddingVertical: pad }}>
        <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 72 : 40, alignItems: wide ? 'center' : 'stretch' }}>
          <View style={{ flex: wide ? 1 : undefined }}>
            <SectionHead title="Too many clothes. Still nothing to wear?" />
            <View style={{ marginTop: 32 }}>
              {PAINS.map((line, i) => (
                <View key={line}>
                  {i > 0 && <Hairline />}
                  <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 14, paddingVertical: 14 }}>
                    <Text style={[t.numeral, { width: 24, fontSize: 16 }]}>{i + 1}</Text>
                    <Text style={[t.lead, { flex: 1, color: landing.ink }]}>{line}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
          <View style={{ width: gridWidth }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              {rail.map((id, i) => (
                <Tile key={id} garment={GARMENTS[id]} width={tileW} dim={i % 3 !== 1} />
              ))}
            </View>
            <Text style={[t.small, { marginTop: 14 }]}>
              A full rail, and the same rushed decision every morning.
            </Text>
          </View>
        </View>
      </Container>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/* How it works                                                        */
/* ------------------------------------------------------------------ */

export function HowItWorks({ revealed }: { revealed: SharedValue<number> }) {
  const t = useType();
  const pad = useSectionPadding();
  const { wide, mid } = useBreakpoints();

  return (
    <Container style={{ paddingVertical: pad }}>
      <SectionHead title="Three steps to a better morning" lead="Upload once. AURA does the deciding from then on." />
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 32 : 48, marginTop: mid ? 64 : 48 }}>
        {STEPS.map((step, i) => (
          <Reveal key={step.n} revealed={revealed} index={i} style={{ flex: wide ? 1 : undefined }}>
            <View style={{ borderTopWidth: 1, borderTopColor: landing.ink, paddingTop: 20 }}>
              <Text style={t.numeral}>{step.n}</Text>
              <Text accessibilityRole="header" style={[t.h3, { marginTop: 12 }]}>
                {step.title}
              </Text>
              <Text style={[t.body, { marginTop: 10, maxWidth: 420 }]}>{step.body}</Text>
              <View style={{ marginTop: 28 }}>
                <StepVisual index={i} />
              </View>
            </View>
          </Reveal>
        ))}
      </View>
    </Container>
  );
}

function StepVisual({ index }: { index: number }) {
  const panel = {
    backgroundColor: landing.paper2,
    borderRadius: 6,
    padding: 18,
    minHeight: 216,
    justifyContent: 'center' as const,
  };

  if (index === 0) {
    const g = GARMENTS.sweater;
    return (
      <View style={[panel, { flexDirection: 'row', alignItems: 'center', gap: 16 }]}>
        <Tile garment={g} width={108} />
        <View style={{ flex: 1, gap: 8 }}>
          {[
            ['Category', g.category],
            ['Colour', g.colour],
            ['Pattern', g.pattern],
          ].map(([k, v]) => (
            <View key={k} style={{ borderBottomWidth: 1, borderBottomColor: landing.rule, paddingBottom: 6 }}>
              <Text style={{ fontFamily: fonts.body, fontSize: 12, color: landing.muted }}>{k}</Text>
              <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 15, color: landing.ink }}>{v}</Text>
            </View>
          ))}
          <Text style={{ fontFamily: fonts.body, fontSize: 12, color: landing.muted }}>Sample tags</Text>
        </View>
      </View>
    );
  }

  if (index === 1) {
    return (
      <View style={[panel, { alignItems: 'center' }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Tile garment={GARMENTS.blazer} width={96} showLabel />
          <View style={{ alignItems: 'center', width: 64 }}>
            <View style={{ height: 1, width: 48, backgroundColor: landing.gold }} />
            <Text style={{ fontFamily: fonts.body, fontSize: 12, color: landing.ink2, marginTop: 6 }}>pairs well</Text>
          </View>
          <Tile garment={GARMENTS.chinos} width={96} showLabel />
        </View>
      </View>
    );
  }

  const outfit = DEMO_OUTFITS[1];
  return (
    <View style={[panel, { gap: 12 }]}>
      <View style={{ alignSelf: 'flex-start', borderRadius: 999, backgroundColor: landing.ink, paddingHorizontal: 12, paddingVertical: 5 }}>
        <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 13, color: landing.inkPaper }}>{outfit.occasion}</Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {outfit.pieces.map((id) => (
          <Tile key={id} garment={GARMENTS[id]} width={58} />
        ))}
      </View>
      <Text style={{ fontFamily: fonts.display, fontSize: 20, color: landing.ink }}>{outfit.name}</Text>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/* Product experience (interactive demo)                               */
/* ------------------------------------------------------------------ */

export function Experience() {
  const pad = useSectionPadding();
  const { wide, mid, width, gutter } = useBreakpoints();
  const [active, setActive] = useState(0);
  const outfit = DEMO_OUTFITS[active];
  const cols = 4;
  const gridWidth = wide ? 440 : width - gutter * 2 - (mid ? 64 : 32);
  const tileW = (gridWidth - 8 * (cols - 1)) / cols;

  return (
    <Container style={{ paddingVertical: pad }}>
      <SectionHead title="See a morning with AURA" lead="Choose an occasion and watch the wardrobe become an outfit." />
      <View
        style={{
          marginTop: mid ? 56 : 40,
          backgroundColor: landing.card,
          borderWidth: 1,
          borderColor: landing.rule,
          borderRadius: 8,
          padding: mid ? 32 : 16,
        }}
      >
        <View style={{ flexDirection: mid ? 'row' : 'column', justifyContent: 'space-between', alignItems: mid ? 'center' : 'flex-start', gap: 16 }}>
          <View accessibilityRole="radiogroup" accessibilityLabel="Occasion" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {DEMO_OUTFITS.map((o, i) => {
              const selected = i === active;
              return (
                <Pressable
                  key={o.occasion}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  accessibilityLabel={o.occasion}
                  onPress={() => {
                    hapticLight();
                    setActive(i);
                  }}
                  style={(state) => ({
                    minHeight: 44,
                    paddingHorizontal: 18,
                    borderRadius: 999,
                    borderWidth: 1,
                    justifyContent: 'center',
                    borderColor: selected ? landing.ink : landing.rule,
                    backgroundColor: selected
                      ? landing.ink
                      : (state as { hovered?: boolean }).hovered
                        ? landing.paper2
                        : 'transparent',
                  })}
                >
                  <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 15, color: selected ? landing.inkPaper : landing.ink2 }}>
                    {o.occasion}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          <DemoTag label="Demo with a sample wardrobe" />
        </View>

        <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 48 : 32, marginTop: mid ? 32 : 24 }}>
          <View style={{ width: gridWidth }}>
            <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 14, color: landing.ink, marginBottom: 12 }}>
              Sample wardrobe
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {DEMO_WARDROBE.map((id) => {
                const inOutfit = outfit.pieces.includes(id);
                return <Tile key={id} garment={GARMENTS[id]} width={tileW} dim={!inOutfit} highlight={inOutfit} />;
              })}
            </View>
            <Text style={{ fontFamily: fonts.body, fontSize: 13, color: landing.muted, marginTop: 12 }}>
              {outfit.pieces.length} of {DEMO_WARDROBE.length} pieces chosen
            </Text>
          </View>

          <Animated.View key={outfit.name} entering={FadeIn.duration(320)} style={{ flex: wide ? 1 : undefined, flexDirection: mid ? 'row' : 'column', gap: 20 }}>
            <View style={{ flex: mid ? 1 : undefined, borderRadius: 6, overflow: 'hidden', backgroundColor: landing.paper2, aspectRatio: mid ? undefined : 4 / 3.6, minHeight: mid ? 380 : undefined }}>
              <AppImage
                source={{ uri: outfit.image }}
                style={{ width: '100%', height: '100%', backgroundColor: landing.paper2 }}
                contentFit="cover"
                accessibilityLabel={`Sample outfit: ${outfit.name}`}
              />
            </View>
            <View style={{ flex: mid ? 1 : undefined, justifyContent: 'space-between', gap: 20 }}>
              <View>
                <Text style={{ fontFamily: fonts.body, fontSize: 14, color: landing.muted }}>
                  {outfit.occasion}, {outfit.weather}
                </Text>
                <Text style={{ fontFamily: fonts.display, fontSize: 32, lineHeight: 38, color: landing.ink, marginTop: 4 }}>
                  {outfit.name}
                </Text>
                <View style={{ marginTop: 20 }}>
                  {outfit.pieces.map((id, i) => (
                    <View key={id}>
                      {i > 0 && <Hairline />}
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10 }}>
                        <Text style={{ fontFamily: fonts.body, fontSize: 15, color: landing.ink }}>{GARMENTS[id].name}</Text>
                        <Text style={{ fontFamily: fonts.body, fontSize: 14, color: landing.muted }}>{GARMENTS[id].category}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              </View>
              <WhyBubble text={outfit.why} />
            </View>
          </Animated.View>
        </View>
      </View>
    </Container>
  );
}

/* ------------------------------------------------------------------ */
/* Personalisation                                                     */
/* ------------------------------------------------------------------ */

export function Personalisation() {
  const t = useType();
  const pad = useSectionPadding();
  const { wide } = useBreakpoints();
  const styleSample = STYLE_PREFERENCES.slice(0, 6);

  return (
    <View style={{ backgroundColor: landing.paper2 }}>
      <Container style={{ paddingVertical: pad }}>
        <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 80 : 48 }}>
          <View style={{ flex: wide ? 0.9 : undefined }}>
            <SectionHead
              title="Your style. Your rules."
              lead="AURA adapts to the context you give it. Everything you share can be changed anytime in your profile."
            />
            <View style={{ marginTop: 40 }}>
              <Text style={t.label}>Every skin tone, considered</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                {SKIN_TONES.map((tone) => (
                  <View key={tone.key} style={{ alignItems: 'center', gap: 6 }}>
                    <View
                      accessibilityLabel={tone.label}
                      style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: tone.color, borderWidth: 1, borderColor: landing.rule }}
                    />
                    <Text style={{ fontFamily: fonts.body, fontSize: 12, color: landing.muted }}>{tone.label}</Text>
                  </View>
                ))}
              </View>
              <Text style={[t.label, { marginTop: 28 }]}>Any style, or several</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                {styleSample.map((s) => (
                  <View key={s.key} style={{ borderWidth: 1, borderColor: landing.rule, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 7, backgroundColor: landing.card }}>
                    <Text style={{ fontFamily: fonts.body, fontSize: 14, color: landing.ink2 }}>{s.label}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>

          <View style={{ flex: wide ? 1 : undefined, borderTopWidth: 1, borderTopColor: landing.ink }}>
            {FACTORS.map((f, i) => (
              <View key={f.name}>
                {i > 0 && <Hairline />}
                <View style={{ flexDirection: 'row', gap: 18, paddingVertical: 22, alignItems: 'flex-start' }}>
                  <View style={{ width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: landing.rule, alignItems: 'center', justifyContent: 'center', backgroundColor: landing.card }}>
                    <Ionicons name={f.icon} size={18} color={landing.ink} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[t.h3, { fontSize: 22 }]}>{f.name}</Text>
                    <Text style={[t.body, { marginTop: 4 }]}>{f.line}</Text>
                  </View>
                </View>
              </View>
            ))}
          </View>
        </View>
      </Container>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/* Technology                                                          */
/* ------------------------------------------------------------------ */

export function Technology() {
  const pad = useSectionPadding();
  const { wide, mid } = useBreakpoints();

  return (
    <View style={{ backgroundColor: landing.night }}>
      <Container style={{ paddingVertical: pad }}>
        <SectionHead
          onDark
          title="The technology behind the style"
          lead="Three models work in sequence, from a photo of one garment to an outfit you can wear."
        />

        <View style={{ flexDirection: wide ? 'row' : 'column', marginTop: mid ? 64 : 48, gap: wide ? 0 : 0 }}>
          {PIPELINE.map((p, i) => {
            const last = i === PIPELINE.length - 1;
            return (
              <View key={p.stage} style={{ flex: wide ? 1 : undefined, flexDirection: wide ? 'column' : 'row', gap: wide ? 0 : 18 }}>
                <View style={{ flexDirection: wide ? 'row' : 'column', alignItems: 'center' }}>
                  <View
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: 7,
                      borderWidth: 1,
                      borderColor: landing.goldOnInk,
                      backgroundColor: last ? landing.goldOnInk : landing.night,
                    }}
                  />
                  {!last && (
                    <View
                      style={
                        wide
                          ? { flex: 1, height: 1, backgroundColor: landing.nightRule }
                          : { width: 1, flex: 1, minHeight: 24, backgroundColor: landing.nightRule }
                      }
                    />
                  )}
                </View>
                <View style={{ paddingTop: wide ? 20 : 0, paddingRight: wide ? 28 : 0, paddingBottom: wide ? 0 : last ? 0 : 32, flex: wide ? undefined : 1, marginTop: wide ? 0 : -3 }}>
                  <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 14, color: landing.goldOnInk }}>{p.stage}</Text>
                  <Text style={{ fontFamily: fonts.display, fontSize: 22, lineHeight: 28, color: landing.inkPaper, marginTop: 6 }}>
                    {p.model}
                  </Text>
                  <Text style={{ fontFamily: fonts.body, fontSize: 15, lineHeight: 23, color: landing.nightMuted, marginTop: 8 }}>
                    {p.line}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>

        <View style={{ marginTop: mid ? 80 : 56, borderTopWidth: 1, borderTopColor: landing.nightRule, paddingTop: 40 }}>
          <View style={{ flexDirection: mid ? 'row' : 'column', gap: mid ? 64 : 32, alignItems: mid ? 'flex-end' : 'flex-start' }}>
            <Metric figure="0.87" label="AUC, compatibility prediction" />
            <Metric figure="52%" label="FITB, fill-in-the-blank accuracy" />
            <Text style={{ flex: mid ? 1 : undefined, fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: landing.nightMuted, maxWidth: 380 }}>
              Evaluation metrics for the outfit compatibility model. They describe model performance on a benchmark, not a guarantee for any single outfit.
            </Text>
          </View>
        </View>
      </Container>
    </View>
  );
}

function Metric({ figure, label }: { figure: string; label: string }) {
  const { wide } = useBreakpoints();
  return (
    <View>
      <Text
        style={{
          fontFamily: fonts.display,
          fontSize: wide ? 88 : 64,
          lineHeight: wide ? 92 : 68,
          letterSpacing: -2,
          color: landing.inkPaper,
          fontVariant: ['tabular-nums'],
        }}
      >
        {figure}
      </Text>
      <Text style={{ fontFamily: fonts.body, fontSize: 14, color: landing.nightMuted, marginTop: 6 }}>{label}</Text>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/* Final call to action                                                */
/* ------------------------------------------------------------------ */

export function FinalCTA({ onStart, onLogin }: { onStart: () => void; onLogin: () => void }) {
  const t = useType();
  const pad = useSectionPadding();
  const { mid } = useBreakpoints();
  return (
    <View style={{ backgroundColor: landing.terracotta }}>
      <Container style={{ paddingVertical: pad + 16 }}>
        <View style={{ alignItems: mid ? 'center' : 'flex-start' }}>
          <Text
            accessibilityRole="header"
            style={[t.display, { color: landing.terracottaInk, textAlign: mid ? 'center' : 'left', maxWidth: 820 }]}
          >
            Tomorrow’s outfit starts with AURA.
          </Text>
          <Text style={[t.lead, { color: landing.terracottaMuted, marginTop: 20, textAlign: mid ? 'center' : 'left', maxWidth: 520 }]}>
            Bring the clothes you own. Your stylist is ready.
          </Text>
          <View style={{ flexDirection: mid ? 'row' : 'column', alignItems: mid ? 'center' : 'stretch', alignSelf: mid ? 'center' : 'stretch', gap: mid ? 24 : 12, marginTop: 40 }}>
            <LButton label="Start styling" icon="arrow-forward" variant="paper" onPress={onStart} />
            <LButton label="I already have an account" variant="textLight" onPress={onLogin} />
          </View>
        </View>
      </Container>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/* FAQ                                                                 */
/* ------------------------------------------------------------------ */

export function Faq() {
  const pad = useSectionPadding();
  const { wide } = useBreakpoints();
  const [open, setOpen] = useState<number | null>(0);

  return (
    <View>
      <Container style={{ paddingVertical: pad }}>
        <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 80 : 32 }}>
          <View style={{ flex: wide ? 0.7 : undefined }}>
            <SectionHead title="Questions, answered" />
          </View>
          <View style={{ flex: wide ? 1.3 : undefined, borderTopWidth: 1, borderTopColor: landing.ink }}>
            {FAQ.map((item, i) => {
              const expanded = open === i;
              return (
                <View key={item.q} style={{ borderBottomWidth: 1, borderBottomColor: landing.rule }}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ expanded }}
                    accessibilityLabel={item.q}
                    onPress={() => {
                      hapticLight();
                      setOpen(expanded ? null : i);
                    }}
                    style={(state) => ({
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 16,
                      paddingVertical: 20,
                      opacity: (state as { hovered?: boolean }).hovered ? 0.75 : 1,
                    })}
                  >
                    <Text style={{ flex: 1, fontFamily: fonts.display, fontSize: 21, lineHeight: 28, color: landing.ink }}>{item.q}</Text>
                    <Ionicons name={expanded ? 'remove' : 'add'} size={22} color={landing.ink} />
                  </Pressable>
                  {expanded && (
                    <Animated.View entering={FadeIn.duration(220)} style={{ paddingBottom: 22, paddingRight: 40 }}>
                      <Text style={{ fontFamily: fonts.body, fontSize: 16, lineHeight: 25, color: landing.ink2, maxWidth: 620 }}>{item.a}</Text>
                    </Animated.View>
                  )}
                </View>
              );
            })}
          </View>
        </View>
      </Container>
    </View>
  );
}

/* ------------------------------------------------------------------ */
/* Footer                                                              */
/* ------------------------------------------------------------------ */

export function Footer({
  links,
  onLink,
}: {
  links: { key: string; label: string }[];
  onLink: (key: string) => void;
}) {
  const { mid } = useBreakpoints();
  return (
    <View style={{ backgroundColor: landing.paper2, borderTopWidth: 1, borderTopColor: landing.rule }}>
      <Container style={{ paddingTop: 56, paddingBottom: 40 }}>
        <View style={{ flexDirection: mid ? 'row' : 'column', justifyContent: 'space-between', gap: 32 }}>
          <View style={{ maxWidth: 320 }}>
            <Wordmark size={22} color={landing.ink} style={{ paddingLeft: 0 }} />
            <Text style={{ fontFamily: fonts.body, fontSize: 15, lineHeight: 23, color: landing.ink2, marginTop: 12 }}>
              Your personal AI stylist, working with the clothes you already own.
            </Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 56 }}>
            <View style={{ gap: 4 }}>
              <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 14, color: landing.ink, marginBottom: 6 }}>Explore</Text>
              {links.map((l) => (
                <FooterLink key={l.key} label={l.label} onPress={() => onLink(l.key)} />
              ))}
            </View>
            <View style={{ gap: 4 }}>
              <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 14, color: landing.ink, marginBottom: 6 }}>Company</Text>
              <FooterLink label="About" onPress={() => onLink('problem')} />
              <Text style={{ fontFamily: fonts.body, fontSize: 15, lineHeight: 36, color: landing.muted }}>Privacy</Text>
              <Text style={{ fontFamily: fonts.body, fontSize: 15, lineHeight: 36, color: landing.muted }}>Terms</Text>
            </View>
          </View>
        </View>
        <Hairline style={{ marginTop: 48, marginBottom: 20 }} />
        <Text style={{ fontFamily: fonts.body, fontSize: 13, color: landing.muted }}>
          © {new Date().getFullYear()} AURA. Sample garment photographs from Unsplash.
        </Text>
      </Container>
    </View>
  );
}

function FooterLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={label}
      onPress={onPress}
      style={(state) => ({ minHeight: 36, justifyContent: 'center', opacity: (state as { hovered?: boolean }).hovered ? 0.65 : 1 })}
    >
      <Text style={{ fontFamily: fonts.body, fontSize: 15, color: landing.ink2 }}>{label}</Text>
    </Pressable>
  );
}
