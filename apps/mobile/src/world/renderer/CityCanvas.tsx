/** 2.5D city map: layered parallax painted in Skia, with each place as a native marker that pans with the near
 * layer: a pill with the place's icon and name, and the faces of who is there. Native markers keep names sharp and
 * readable on any sky, and make every place a real, accessible button. */
import Ionicons from "@expo/vector-icons/Ionicons";
import { Canvas, Group, LinearGradient, Path, Rect, vec } from "@shopify/react-native-skia";
import * as Haptics from "expo-haptics";
import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, { useAnimatedStyle, useDerivedValue, useSharedValue } from "react-native-reanimated";

import { Avatar } from "@/ui/kit";
import { colors, fonts, radius, shadow } from "@/ui/theme";

import { placeIcon } from "../icons";
import { LAYERS, MARKER_HEIGHT, MARKER_WIDTH, clampPan, markerLeft, npcsAt, placedLocations, project, skyline, worldWidth, type Size } from "../model";
import type { Location, WorldView } from "../types";

interface Props {
  view: WorldView;
  size: Size;
  onSelect: (location: Location) => void;
}

export function CityCanvas({ view, size, onSelect }: Props) {
  const colours = view.palette;
  const pan = useSharedValue(0);
  const start = useSharedValue(0);
  const placed = placedLocations(view);
  const width = worldWidth(view);
  const far = useMemo(() => skyline(size, 1, size.height * 0.45, width), [size, width]);
  const mid = useMemo(() => skyline(size, 4, size.height * 0.3, width), [size, width]);
  const districts = view.districts.filter((d) => d.unlocked);

  // Horizontal drags pan the map; vertical ones belong to the page so it still scrolls on a phone.
  const gesture = Gesture.Pan()
    .activeOffsetX([-10, 10])
    .failOffsetY([-10, 10])
    .onStart(() => {
      start.value = pan.value;
    })
    .onUpdate((e) => {
      pan.value = clampPan(start.value + e.translationX, size, width);
    });

  const farTransform = useDerivedValue(() => [{ translateX: pan.value * LAYERS[1].depth }]);
  const midTransform = useDerivedValue(() => [{ translateX: pan.value * LAYERS[2].depth }]);
  const nearStyle = useAnimatedStyle(() => ({ transform: [{ translateX: pan.value }] }));

  return (
    <GestureDetector gesture={gesture}>
      <View style={{ width: size.width, height: size.height }} accessibilityLabel={view.name}>
        <Canvas style={StyleSheet.absoluteFill}>
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
        </Canvas>
        <Animated.View style={[StyleSheet.absoluteFill, nearStyle]} pointerEvents="box-none">
          {districts.map((district, i) => (
            <View key={district.key} style={[styles.district, { left: i * size.width + 12 }]} pointerEvents="none">
              <Text style={styles.districtText}>{district.name}</Text>
            </View>
          ))}
          {placed.map(({ location, point }) => {
            const centre = project(point, size, 0);
            const people = npcsAt(view, location.key);
            return (
              <View key={location.key} pointerEvents="box-none" style={{ position: "absolute", left: markerLeft(centre.x, size), top: centre.y - MARKER_HEIGHT - 10, width: MARKER_WIDTH, alignItems: "center" }}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={[location.name, ...people.map((p) => p.name)].join(", ")}
                  hitSlop={8}
                  onPress={() => {
                    void Haptics.selectionAsync();
                    onSelect(location);
                  }}
                  style={({ pressed }) => [styles.pill, shadow(2), pressed && { transform: [{ scale: 0.96 }] }]}
                >
                  <View style={styles.icon}>
                    <Ionicons name={placeIcon(location)} size={14} color={colors.accentInk} />
                  </View>
                  <Text style={styles.name} numberOfLines={1}>
                    {location.short_name ?? location.name}
                  </Text>
                  {people.length > 0 && (
                    <View style={styles.faces}>
                      {people.slice(0, 2).map((npc, n) => (
                        <View key={npc.key} style={[styles.face, n > 0 && { marginLeft: -8 }]}>
                          <Avatar name={npc.name} size={20} />
                        </View>
                      ))}
                    </View>
                  )}
                </Pressable>
                <View style={styles.pin} pointerEvents="none" />
              </View>
            );
          })}
        </Animated.View>
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  district: { position: "absolute", top: 10, backgroundColor: "rgba(20,32,56,0.35)", borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3 },
  districtText: { fontFamily: fonts.semibold, fontSize: 12, color: "#fff", letterSpacing: 0.3 },
  pill: {
    height: MARKER_HEIGHT,
    maxWidth: MARKER_WIDTH,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingLeft: 5,
    paddingRight: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
  },
  icon: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center" },
  name: { fontFamily: fonts.semibold, fontSize: 13, color: colors.ink, flexShrink: 1 },
  faces: { flexDirection: "row", marginLeft: 2 },
  face: { borderWidth: 1.5, borderColor: colors.card, borderRadius: 11 },
  pin: { width: 10, height: 10, borderRadius: 5, marginTop: 4, backgroundColor: colors.card, borderWidth: 2.5, borderColor: colors.accent },
});
