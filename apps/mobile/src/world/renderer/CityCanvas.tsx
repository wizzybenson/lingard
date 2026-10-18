/** 2.5D city map: layered parallax, location markers, NPC sprites with an idle bob. Rendering only. */
import { Canvas, Circle, Group, LinearGradient, Path, Rect, Text, matchFont, vec } from "@shopify/react-native-skia";
import { useFocusEffect } from "expo-router";
import { useCallback, useMemo } from "react";
import { Platform } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { cancelAnimation, useDerivedValue, useSharedValue, withRepeat, withTiming, runOnJS } from "react-native-reanimated";

import { LAYERS, MARKER_RADIUS, clampPan, hitTest, initials, npcsAt, placedLocations, project, skyline, worldWidth, type Size } from "../model";
import type { Location, WorldView } from "../types";

// Skia objects are created at render time, never at import: on the web CanvasKit loads asynchronously.
const FONT_SPEC = { fontFamily: Platform.select({ ios: "Helvetica", default: "sans-serif" }), fontSize: 12 };

interface Props {
  view: WorldView;
  size: Size;
  onSelect: (location: Location) => void;
}

export function CityCanvas({ view, size, onSelect }: Props) {
  const colours = view.palette;
  // CanvasKit on the web has no system fonts; labels there come from the accessible list under the map.
  const font = useMemo(() => (Platform.OS === "web" ? null : matchFont(FONT_SPEC)), []);
  const pan = useSharedValue(0);
  const start = useSharedValue(0);
  const bob = useSharedValue(0);
  // The idle bob redraws every frame, so it only runs while the map is on screen.
  useFocusEffect(
    useCallback(() => {
      bob.set(withRepeat(withTiming(1, { duration: 1400 }), -1, true));
      return () => cancelAnimation(bob);
    }, [bob]),
  );
  const placed = placedLocations(view);
  const width = worldWidth(view);
  const far = useMemo(() => skyline(size, 1, size.height * 0.45, width), [size, width]);
  const mid = useMemo(() => skyline(size, 4, size.height * 0.3, width), [size, width]);  const districts = view.districts.filter((d) => d.unlocked);

  const pick = (x: number, y: number) => {
    const location = hitTest(view, { x, y }, size, pan.value);
    if (location) onSelect(location);
  };

  const gesture = Gesture.Race(
    Gesture.Pan()
      // Horizontal drags pan the map; vertical ones belong to the page so it still scrolls on a phone.
      .activeOffsetX([-10, 10])
      .failOffsetY([-10, 10])
      .onStart(() => {
        start.value = pan.value;
      })
      .onUpdate((e) => {
        pan.value = clampPan(start.value + e.translationX, size, width);
      }),
    Gesture.Tap().onEnd((e) => {
      runOnJS(pick)(e.x, e.y);
    }),
  );

  const farTransform = useDerivedValue(() => [{ translateX: pan.value * LAYERS[1].depth }]);
  const midTransform = useDerivedValue(() => [{ translateX: pan.value * LAYERS[2].depth }]);
  const nearTransform = useDerivedValue(() => [{ translateX: pan.value }]);
  const bobTransform = useDerivedValue(() => [{ translateY: -3 * bob.value }]);

  return (
    <GestureDetector gesture={gesture}>
      <Canvas style={{ width: size.width, height: size.height }} accessibilityLabel={`Map of ${view.name}`}>
        <Rect x={0} y={0} width={size.width} height={size.height}>
          <LinearGradient start={vec(0, 0)} end={vec(0, size.height)} colors={colours.sky} />
        </Rect>
        <Group transform={farTransform}>
          <Path path={far} color={colours.far} opacity={0.7} />
        </Group>
        <Group transform={midTransform}>
          <Path path={mid} color={colours.mid} />
          <Rect x={-size.width} y={size.height * 0.82} width={size.width * (width + 2)} height={size.height * 0.18} color={colours.water} />
        </Group>
        <Group transform={nearTransform}>
          {font &&
            districts.map((district, i) => (
              <Text key={district.key} x={i * size.width + 12} y={22} text={district.name} font={font} color="#ffffff" />
            ))}
          {placed.map(({ location, point }) => {
            const centre = project(point, size, 0);
            const people = npcsAt(view, location.key);
            return (
              <Group key={location.key}>
                <Circle cx={centre.x} cy={centre.y} r={MARKER_RADIUS} color={colours.near} opacity={0.85} />
                {font && (
                  <Text
                    // Kept inside its district's screen: a label near the right edge shifts left instead of being cut.
                    x={Math.max(
                      Math.floor(centre.x / size.width) * size.width + 8,
                      Math.min(centre.x - MARKER_RADIUS, (Math.floor(centre.x / size.width) + 1) * size.width - font.getTextWidth(location.name) - 8),
                    )}
                    y={centre.y + MARKER_RADIUS + 16}
                    text={location.name}
                    font={font}
                    color="#ffffff"
                  />
                )}
                <Group transform={bobTransform}>
                  {people.map((npc, i) => (
                    <Group key={npc.key}>
                      <Circle cx={centre.x + 16 + i * 22} cy={centre.y - 22} r={12} color="#f4e3c1" />
                      {font && <Text x={centre.x + 9 + i * 22} y={centre.y - 18} text={initials(npc.name)} font={font} color="#2b2b2b" />}
                    </Group>
                  ))}
                </Group>
              </Group>
            );
          })}
        </Group>
      </Canvas>
    </GestureDetector>
  );
}

