/** A location's layered artwork (background, then foreground props), drawn with Skia so SVG works on every platform. */
import { Canvas, Group, ImageSVG, Skia, type SkSVG } from "@shopify/react-native-skia";
import { useEffect, useState } from "react";

import type { ApiClient } from "@/api/client";

const ART_WIDTH = 800;
const ART_HEIGHT = 500;

export function LocationArt({ api, layers, width }: { api: ApiClient; layers: string[]; width: number }) {
  const key = layers.join("|");
  const [loaded, setLoaded] = useState<{ key: string; svgs: SkSVG[] }>({ key: "", svgs: [] });
  useEffect(() => {
    let live = true;
    Promise.all(layers.map((layer) => api.text(`/v1/art/${layer}`)))
      .then((sources) => {
        const svgs = sources.map((source) => Skia.SVG.MakeFromString(source)).filter((s): s is SkSVG => s !== null);
        if (live) setLoaded({ key, svgs });
      })
      .catch(() => live && setLoaded({ key, svgs: [] })); // art is decoration: a missing file just leaves the card plain
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, key]);
  const svgs = loaded.key === key ? loaded.svgs : [];
  if (svgs.length === 0) return null;
  const scale = width / ART_WIDTH;
  const height = ART_HEIGHT * scale;
  return (
    <Canvas style={{ width, height, borderRadius: 8 }} accessibilityElementsHidden>
      {/* ImageSVG draws at the SVG's own size, so scale the group rather than passing width and height. */}
      <Group transform={[{ scale }]}>
        {svgs.map((svg, i) => (
          <ImageSVG key={i} svg={svg} x={0} y={0} width={ART_WIDTH} height={ART_HEIGHT} />
        ))}
      </Group>
    </Canvas>
  );
}
