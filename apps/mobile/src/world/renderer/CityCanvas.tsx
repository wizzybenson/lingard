/** 2.5D city map: layered parallax, location markers, NPC sprites with an idle bob. Rendering only. */
import { Canvas, Circle, Group, LinearGradient, Path, Rect, Skia, Text, matchFont, vec } from "@shopify/react-native-skia";
import { useEffect, useMemo } from "react";
import { Platform } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { useDerivedValue, useSharedValue, withRepeat, withTiming, runOnJS } from "react-native-reanimated";

import { LAYERS, MARKER_RADIUS, clampPan, hitTest, initials, npcsAt, placedLocations, project, worldWidth, type Size } from "../model";
import type { Location, WorldView } from "../types";

// Skia objects are created at render time, never at import: on the web CanvasKit loads asynchronously.
const FONT_SPEC = { fontFamily: Platform.select({ ios: "Helvetica", default: "sans-serif" }), fontSize: 12 };

function skyline(size: Size, seed: number, height: number, widthFactor: number): string {
  const path = Skia.Path.Make();
  path.moveTo(0, size.height);
  let x = 0;
  let step = 0;
  while (x < size.width * (widthFactor + 0.1)) {
    const h = height * (0.6 + 0.4 * Math.abs(Math.sin(seed + step * 1.7)));
    path.lineTo(x, size.height - h);
    x += 30 + 25 * Math.abs(Math.cos(seed * 3 + step));
    path.lineTo(x, size.height - h);
    step += 1;
  }
  path.lineTo(x, size.height);
  path.close();
  return path.toSVGString();
}

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
  useEffect(() => {
    bob.value = withRepeat(withTiming(1, { duration: 1400 }), -1, true);
  }, [bob]);
  const placed = placedLocations(view);
  const width = worldWidth(view);
  const far = useMemo(() => skyline(size, 1, size.height * 0.45, width), [size, width]);
  const mid = useMemo(() => skyline(size, 4, size.height * 0.3, width), [size, width]);
  const districts = view.districts.filter((d) => d.unlocked);

  const pick = (x: number, y: number) => {
    const location = hitTest(view, { x, y }, size, pan.value);
    if (location) onSelect(location);
  };

  const gesture = Gesture.Race(
    Gesture.Pan()
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
                  <Text x={centre.x - MARKER_RADIUS} y={centre.y + MARKER_RADIUS + 16} text={location.name.slice(0, 22)} font={font} color="#ffffff" />
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

